import numpy as np
from collections import defaultdict
from typing import List, Tuple

MIN_HALF = 1e-3     # ボックス半径の下限(0半径は特異行列になるため)
FLOOR_HALF = 1e-5   # 単独点を縮めるときの最小半径
EPS_PAD = 1e-5      # AABBに足す余白(浮動小数点誤差対策)
REL_MARGIN = 1e-6   # 座標の大きさに比例する余白。Blenderは行列をfloat32で持ち、逆行列の平行移動項に約6e-8*|座標|の誤差が出る

class PointIndex:
    def __init__(self, points, cell=1.0):
        self.points = np.asarray(points, dtype=np.float64)
        self.cell = float(cell)
        if len(self.points) == 0:
            self.grid = {}
            return

        # グリッドセルのキーを計算
        indices = np.floor(self.points / self.cell).astype(np.int64)

        # セルごとに点番号をまとめる
        grid_dict = defaultdict(list)
        for i, idx in enumerate(indices):
            key = tuple(idx)
            grid_dict[key].append(i)

        # 辞書をリストに変換（キーの順序は保証されないが、処理には問題なし）
        self.grid = dict(grid_dict)

    def count_inside(self, center, half):
        center = np.asarray(center, dtype=np.float64)
        half = np.asarray(half, dtype=np.float64)

        # セルの範囲を計算
        min_cell = np.floor((center - half) / self.cell).astype(np.int64)
        max_cell = np.floor((center + half) / self.cell).astype(np.int64)

        # セル数が多すぎる場合は全点判定にフォールバック
        total_cells = (max_cell - min_cell + 1).prod()
        if total_cells > 100000:
            # フォールバック: 全点を直接ベクトルでチェック
            diff = np.abs(self.points - center)
            inside_mask = np.all(diff <= half, axis=1)
            return int(np.sum(inside_mask))

        count = 0
        for ci in np.ndindex(tuple(max_cell - min_cell + 1)):
            key = tuple(min_cell + np.array(ci))
            if key in self.grid:
                point_indices = self.grid[key]
                # ポイントの座標を取得して範囲内かチェック
                points_in_cell = self.points[point_indices]
                diff = np.abs(points_in_cell - center)
                inside_mask = np.all(diff <= half, axis=1)
                count += int(np.sum(inside_mask))

        return count

    def nearest_chebyshev(self, point, limit):
        if len(self.points) == 0:
            return float('inf')

        point = np.asarray(point, dtype=np.float64)
        # Chebyshev距離の計算
        diff = np.abs(self.points - point)
        distances = np.max(diff, axis=1)
        valid_mask = distances <= limit

        if not np.any(valid_mask):
            return float('inf')

        return float(np.min(distances[valid_mask]))

def cluster_by_grid(points, cell) -> List[np.ndarray]:
    points = np.asarray(points, dtype=np.float64)

    if len(points) == 0:
        return []

    # セルサイズが負またはゼロの場合は各点を1つのクラスタにする
    if cell <= 0.0:
        return [np.array([i], dtype=np.int64) for i in range(len(points))]

    indices = np.floor(points / cell).astype(np.int64)

    # キーごとに点番号を集める
    _, inverse = np.unique(indices, axis=0, return_inverse=True)
    inverse = np.asarray(inverse).reshape(-1)  # NumPy 2.0.0 may return a 2-D inverse

    # 安定ソートで同じセルの点番号を連続させ(各クラスタ内は昇順)、境界で分割する: O(n log n)
    order = np.argsort(inverse, kind='stable')
    boundaries = np.flatnonzero(np.diff(inverse[order])) + 1
    clusters = np.split(order, boundaries)

    # クラスタの最小点番号の昇順で返す
    clusters.sort(key=lambda cluster: int(cluster[0]))
    return clusters

def float32_margin(points):
    """Extra room so a box still contains its points after Blender's float32 matrix inverse."""
    points = np.asarray(points, dtype=np.float64)
    if len(points) == 0:
        return 0.0
    return REL_MARGIN * float(np.max(np.abs(points)))


def box_of(points, min_half=MIN_HALF, pad=EPS_PAD) -> Tuple[np.ndarray, np.ndarray]:
    points = np.asarray(points, dtype=np.float64)

    if len(points) == 0:
        center = np.zeros(3, dtype=np.float64)
        half = np.full(3, min_half, dtype=np.float64)
        return (center, half)

    # AABBを計算
    mins = np.min(points, axis=0)
    maxs = np.max(points, axis=0)
    margin = float32_margin(points)

    center = (mins + maxs) / 2.0
    half = np.maximum((maxs - mins) / 2.0 + max(pad, margin), max(min_half, 2.0 * margin))

    return (center, half)

def build_boxes_iter(points, others, cell, min_half=MIN_HALF, floor_half=FLOOR_HALF, pad=EPS_PAD, chunk=500):
    """Generator form of build_boxes: yields after every `chunk` grid clusters so a modal
    operator can stay responsive. The final (boxes, unseparable) is the generator's return value."""
    points = np.asarray(points, dtype=np.float64)
    others = np.asarray(others, dtype=np.float64).reshape(-1, 3)
    if len(points) == 0:
        return ([], [])
    clusters = cluster_by_grid(points, cell)
    yield
    point_index = PointIndex(others, cell=max(cell, 1.0))
    yield
    boxes = []
    unseparable = []
    for start in range(0, len(clusters), chunk):
        # A cluster that has to be split pushes its halves onto this local stack.
        stack = list(clusters[start:start + chunk])
        while stack:
            indices = stack.pop()
            center, half = box_of(points[indices], min_half=min_half, pad=pad)
            # Judge contamination on a slightly larger box: Blender's float32 matrices blur the edges.
            if point_index.count_inside(center, half + float32_margin(points[indices])) == 0:
                boxes.append((indices.copy(), center, half))
            elif len(indices) > 1:
                # Contaminated: split at the median of the longest axis (always makes progress).
                axis = int(np.argmax(half))
                ordered = indices[np.argsort(points[indices, axis], kind='stable')]
                mid = len(ordered) // 2
                stack.append(np.sort(ordered[:mid]))
                stack.append(np.sort(ordered[mid:]))
            else:
                # One point and an unselected origin inside its box: shrink the box if possible.
                point = points[indices[0]]
                nearest = point_index.nearest_chebyshev(point, limit=float(np.max(half)))
                new_half = nearest * 0.5
                if new_half < max(floor_half, 2.0 * float32_margin(point)):
                    unseparable.append(int(indices[0]))
                else:
                    boxes.append((indices.copy(), point.copy(), np.full(3, new_half, dtype=np.float64)))
        yield
    boxes.sort(key=lambda box: int(box[0][0]))
    unseparable.sort()
    return (boxes, unseparable)


def build_boxes(points, others, cell, min_half=MIN_HALF, floor_half=FLOOR_HALF, pad=EPS_PAD):
    """Cube boxes (indices, center, half) that hold the selected origins and no unselected origin."""
    generator = build_boxes_iter(points, others, cell, min_half, floor_half, pad, chunk=1 << 30)
    try:
        while True:
            next(generator)
    except StopIteration as done:
        return done.value
