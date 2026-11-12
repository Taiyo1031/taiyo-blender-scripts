"""Pure-numpy tests for zone_from_objects (box clustering without contamination)."""
import importlib.util
from pathlib import Path
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / '_Taiyo_Blender_Extensions_Repo' / 'map_roundtrip_tools' / 'zone_from_objects.py'
spec = importlib.util.spec_from_file_location('zone_from_objects', path)
zfo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(zfo)


def inside(point, center, half):
    return bool((np.abs(np.asarray(point) - center) <= half).all())


def check_invariants(points, others, boxes, unseparable):
    points = np.asarray(points, dtype=np.float64)
    others = np.asarray(others, dtype=np.float64).reshape(-1, 3)
    seen = []
    for indices, center, half in boxes:
        assert center.shape == (3,) and half.shape == (3,)
        assert (half >= zfo.FLOOR_HALF - 1e-12).all()
        for i in indices:
            assert inside(points[i], center, half), 'box must contain its own points'
        if len(others):
            assert not (np.abs(others - center) <= half).all(axis=1).any(), 'box contains an unselected origin'
        seen.extend(int(i) for i in indices)
    assert sorted(seen + list(unseparable)) == list(range(len(points))), 'every point exactly once'
    assert list(unseparable) == sorted(unseparable)


# --- cluster_by_grid
pts = np.array([[.1, .1, .1], [.9, .9, .9], [1.1, 0, 0]])
cl = zfo.cluster_by_grid(pts, 1.0)
assert [c.tolist() for c in cl] == [[0, 1], [2]]
assert [c.tolist() for c in zfo.cluster_by_grid(pts, 0)] == [[0], [1], [2]]
assert zfo.cluster_by_grid(np.empty((0, 3)), 1.0) == []
neg = np.array([[-.1, 0, 0], [.1, 0, 0]])
assert len(zfo.cluster_by_grid(neg, 1.0)) == 2

# --- box_of
c, h = zfo.box_of(np.array([[1., 2., 3.]]))
assert np.allclose(c, [1, 2, 3]) and np.allclose(h, zfo.MIN_HALF)
c, h = zfo.box_of(np.array([[0., 0., 0.], [4., 2., 0.]]))
assert np.allclose(c, [2, 1, 0])
assert np.allclose(h, [2 + zfo.EPS_PAD, 1 + zfo.EPS_PAD, zfo.MIN_HALF])

# --- PointIndex
idx = zfo.PointIndex(np.array([[0., 0., 0.], [1., 0., 0.], [5., 5., 5.]]), cell=1.0)
assert idx.count_inside(np.array([0.5, 0, 0]), np.array([.5, .1, .1])) == 2  # inclusive boundary
assert idx.count_inside(np.array([9., 9., 9.]), np.array([1., 1., 1.])) == 0
assert abs(idx.nearest_chebyshev(np.array([0., 0., 0.2]), 2.0) - 0.2) < 1e-12
assert idx.nearest_chebyshev(np.array([20., 20., 20.]), 1.0) == float('inf')
assert zfo.PointIndex(np.empty((0, 3)), cell=1.0).count_inside(np.zeros(3), np.ones(3)) == 0

# --- build_boxes basics
assert zfo.build_boxes(np.empty((0, 3)), np.empty((0, 3)), 1.0) == ([], [])
sel = np.array([[0., 0, 0], [1, 0, 0], [2, 0, 0]])
boxes, bad = zfo.build_boxes(sel, np.empty((0, 3)), 10.0)
assert len(boxes) == 1 and bad == []
check_invariants(sel, np.empty((0, 3)), boxes, bad)
# an unselected origin between them forces a split
other = np.array([[1., 0., .0005]])
boxes, bad = zfo.build_boxes(sel, other, 10.0)
assert len(boxes) >= 2 and bad == []
check_invariants(sel, other, boxes, bad)
# distance 0 means one box per point
boxes, bad = zfo.build_boxes(sel, np.empty((0, 3)), 0)
assert len(boxes) == 3 and bad == []
# identical origin cannot be separated
boxes, bad = zfo.build_boxes(np.array([[0., 0, 0]]), np.array([[0., 0, 0]]), 1.0)
assert boxes == [] and bad == [0]
# very close (not identical) origin is separated by shrinking
near = np.array([[.0004, 0, 0]])
boxes, bad = zfo.build_boxes(np.array([[0., 0, 0]]), near, 1.0)
assert bad == [] and len(boxes) == 1
check_invariants(np.array([[0., 0, 0]]), near, boxes, bad)
assert boxes[0][2][0] <= .0002 + 1e-12
# duplicated selected points are allowed
dup = np.array([[3., 3, 3], [3, 3, 3]])
boxes, bad = zfo.build_boxes(dup, np.empty((0, 3)), 1.0)
check_invariants(dup, np.empty((0, 3)), boxes, bad)
# inputs are not modified
before = sel.copy()
zfo.build_boxes(sel, other, 10.0)
assert (sel == before).all()

# --- randomized invariants
rng = np.random.default_rng(7)
sel = rng.uniform(0, 50, (2000, 3))
oth = rng.uniform(0, 50, (3000, 3))
oth[:50] = sel[:50] + rng.uniform(-.0004, .0004, (50, 3))  # nearby contaminants
oth[50:60] = sel[50:60]  # identical contaminants
for cell in (0, 1, 5, 25):
    boxes, bad = zfo.build_boxes(sel, oth, cell)
    check_invariants(sel, oth, boxes, bad)
    assert set(range(50, 60)) <= set(bad)

# --- performance (60k selected + 60k unselected)
sel = rng.uniform(0, 500, (60000, 3))
oth = rng.uniform(0, 500, (60000, 3))
t = time.perf_counter()
boxes, bad = zfo.build_boxes(sel, oth, 2.0)
seconds = time.perf_counter() - t
sample = rng.choice(len(boxes), 300, replace=False)
sub = [boxes[i] for i in sample]
for indices, center, half in sub:
    assert not (np.abs(oth - center) <= half).all(axis=1).any()
assert len(boxes) + len(bad) <= len(sel)
assert seconds < 30, f'too slow: {seconds:.1f}s'
print('ZONE_FROM_OBJECTS_TESTS_PASSED', {'boxes': len(boxes), 'unseparable': len(bad), 'seconds_60k': round(seconds, 2)}, flush=True)
