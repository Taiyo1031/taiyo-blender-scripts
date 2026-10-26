"""Pure NumPy predicates. Coordinates are float64; touching counts as overlap."""
from itertools import product
import numpy as np

EPS = 1e-7
SIGNS = np.array(list(product((-1., 1.), repeat=3)))

def transform(points, matrix):
    return np.asarray(points) @ matrix[:3, :3].T + matrix[:3, 3]

def inside(points, shape, size):
    if shape == 'CUBE':
        return np.all(np.abs(points) <= size + EPS, axis=-1)
    return np.sum(points * points, axis=-1) <= (size + EPS) ** 2

def box_overlap(corners, size):
    # A transformed local BBox is a parallelepiped, including parent shear.
    center = corners.mean(axis=0)
    edges = np.array([(corners[4]-corners[0])/2,
                      (corners[2]-corners[0])/2,
                      (corners[1]-corners[0])/2])
    axes = [*np.eye(3), np.cross(edges[0], edges[1]),
            np.cross(edges[1], edges[2]), np.cross(edges[2], edges[0])]
    axes.extend(np.cross(edge, axis) for edge in edges for axis in np.eye(3))
    for axis in axes:
        norm = np.linalg.norm(axis)
        if norm <= 1e-14:
            continue
        axis = axis / norm
        if abs(center @ axis) > np.abs(edges @ axis).sum() + size*np.abs(axis).sum() + EPS:
            return False
    return True

def sphere_overlap(corners, size):
    # Exact closest point on an affine box to the sphere origin. Enumerate
    # the 27 active sets of the box-constrained convex quadratic. Handles
    # enclosing boxes, shear, flat bounds and tangency without GJK cycling.
    center = corners.mean(axis=0)
    edges = np.column_stack(((corners[4]-corners[0])/2,
                             (corners[2]-corners[0])/2,
                             (corners[1]-corners[0])/2))
    for status in product((-1, 0, 1), repeat=3):
        free = [i for i, s in enumerate(status) if s == 0]
        fixed = [i for i, s in enumerate(status) if s != 0]
        point = center.copy()
        if fixed:
            point += edges[:, fixed] @ np.array([status[i] for i in fixed])
        if free:
            weights = np.linalg.lstsq(edges[:, free], -point, rcond=None)[0]
            if np.any(np.abs(weights) > 1 + EPS):
                continue
            point += edges[:, free] @ np.clip(weights, -1, 1)
        if point @ point <= (size + EPS)**2:
            return True
    return False

def predicate(origins, bounds, inverse, shape, size, mode):
    """Vectorized point/containment tests; accurate narrow phase for overlap."""
    if mode == 'ORIGIN':
        return inside(transform(origins, inverse), shape, size)
    if mode == 'BOUNDS_CENTER':
        return inside(transform(bounds.mean(axis=1), inverse), shape, size)
    local = transform(bounds, inverse)
    if mode == 'FULLY_INSIDE':
        return inside(local, shape, size).all(axis=1)
    # Broad phase in volume-local space also works for ellipsoids/shear.
    candidates = np.all(local.max(axis=1) >= -size-EPS, axis=1) & np.all(local.min(axis=1) <= size+EPS, axis=1)
    out = np.zeros(len(origins), dtype=bool)
    overlap = box_overlap if shape == 'CUBE' else sphere_overlap
    for i in np.flatnonzero(candidates):
        out[i] = overlap(local[i], size)
    return out
