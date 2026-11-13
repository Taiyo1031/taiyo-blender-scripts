"""Add selected meshes to the current zone by creating Cube empties at their origins."""
import bpy
import numpy as np
from .chunked import ChunkedOperator
from .constants import ZONE_NAME_KEY
from .zone_from_objects import build_boxes_iter
from .zones import (ZoneBoxes, collect_candidate_meshes, collect_zone_boxes, ensure_zone,
                    inside_mask, points_of)


def _new_empty(name):
    return bpy.data.objects.new(name, None)


def _origins(objects, chunk=4096):
    """Generator: world-space origins (n, 4) read in slices so the UI stays responsive."""
    points = np.empty((len(objects), 4), dtype=np.float64)
    for start in range(0, len(objects), chunk):
        points[start:start + chunk] = points_of(objects[start:start + chunk])
        yield
    return points


def _owners(scene, targets, chunk=4096):
    """Generator: the collection each target object lives in, and the scene order of the collections.

    Only collections reachable from the scene count, in scene order (children before the scene root), and the first
    one wins for an object in several collections. Reads membership per collection, never per object.
    """
    wanted = set(targets)
    owners, order = {}, {}
    for rank, collection in enumerate((*scene.collection.children_recursive, scene.collection)):
        order[collection] = rank
        for i, ob in enumerate(collection.objects):
            if ob in wanted:
                owners.setdefault(ob, collection)
            if i % chunk == chunk - 1:
                yield
        yield
    return owners, order


def _box_collection(indices, targets, owners, order, fallback):
    """(collection, mixed): the collection most of the box's objects are in (ties: first in the scene)."""
    counts = {}
    for i in indices:
        collection = owners.get(targets[i], fallback)
        counts[collection] = counts.get(collection, 0) + 1
    best = min(counts, key=lambda c: (-counts[c], order.get(c, len(order))))
    if not best.is_editable:
        best = fallback
    return best, len(counts) > 1


def _intruders(other_points, centers, halves, budget=1_500_000):
    """Generator: how many unselected origins fall inside any new box.

    Box-vs-point comparison in slices (float32-rounded like Blender's stored matrices), yielding
    between slices. A correct build_boxes_iter() leaves this at 0; it is a safety net, not the grouping.
    """
    if not len(other_points) or not len(centers):
        return 0
    found = np.zeros(len(other_points), dtype=bool)
    step = max(1, budget // len(other_points))
    for start in range(0, len(centers), step):
        center = centers[start:start + step, None, :]
        half = halves[start:start + step, None, :]
        found |= (np.abs(other_points[None, :, :] - center) <= half).all(axis=2).any(axis=0)
        yield
    return int(np.count_nonzero(found))


class MRT_OT_AddObjectsToZone(ChunkedOperator, bpy.types.Operator):
    bl_idname = 'mrt.add_objects_to_zone'
    bl_label = 'Add Selected Objects'
    bl_description = '選択したMeshの原点にCube Emptyを作り、現在のZoneへまとめて追加します。Emptyは元のMeshがいるCollectionへ入ります。近い原点はMerge Distance以内で1つにまとめます。未選択のMeshが範囲に入る場合は自動で分割します'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return super().poll(context) and context.scene.mrt_props.zone_choice not in ('', 'ALL')

    def work(self, context):
        p = context.scene.mrt_props
        zone = p.zone_choice

        selected = [ob for ob in context.selected_objects if ob.type == 'MESH']
        ignored = len(context.selected_objects) - len(selected)
        if not selected:
            raise ValueError('Select at least one Mesh object.')

        self.progress('Reading objects', 0, 1)
        candidates = yield from collect_candidate_meshes(context)

        ensure_zone(p, zone)
        existing = collect_zone_boxes(context.scene, p.zone_prefix).get(zone)

        self.progress('Reading origins', 0, 1)
        selected_points = yield from _origins(selected)
        # Exclude objects that are already inside the zone.
        if existing is not None and (existing or existing.subtract):
            skipped = inside_mask(selected_points, existing)
        else:
            skipped = np.zeros(len(selected), dtype=bool)
        skipped_count = int(np.count_nonzero(skipped))
        targets = [ob for ob, skip in zip(selected, skipped) if not skip]
        if not targets:
            self.result = f'Nothing to add: {skipped_count} objects are already inside {zone}'
            return
        sel_pts = selected_points[~skipped][:, :3]
        selected_set = set(selected)
        others = [ob for ob in candidates if ob not in selected_set]
        other_pts = (yield from _origins(others))[:, :3]

        self.progress('Grouping origins', 0, 1)
        boxes, bad = yield from build_boxes_iter(sel_pts, other_pts, p.merge_distance)

        self.progress('Finding collections', 0, 1)
        owners, order = yield from _owners(context.scene, targets)
        root = context.scene.collection

        created = []
        mixed = 0
        try:
            # Create empties
            object_name = zone if zone.startswith(p.zone_prefix) else p.zone_prefix + zone
            for i, (indices, center, half) in enumerate(boxes):
                e = _new_empty(object_name)
                e.empty_display_type = 'CUBE'
                e.empty_display_size = 1.0
                e.show_in_front = True
                e.location = center
                e.scale = half
                e[ZONE_NAME_KEY] = zone
                e.mrt_zone_operation = 'ADD'
                e.mrt_zone_enabled = True
                collection, is_mixed = _box_collection(indices, targets, owners, order, root)
                collection.objects.link(e)
                mixed += is_mixed
                created.append(e)

                if i % 128 == 0:
                    done = i + 1
                    total = len(boxes)
                    self.progress('Creating zone empties', done, total)
                    yield

            # Safety net: no unselected origin may sit inside a new box.
            self.progress('Checking the new range', 0, 1)
            centers = np.array([center for _, center, _ in boxes], dtype=np.float32).astype(np.float64).reshape(-1, 3)
            halves = np.array([half for _, _, half in boxes], dtype=np.float32).astype(np.float64).reshape(-1, 3)
            if (yield from _intruders(other_pts, centers, halves)):
                raise RuntimeError('Internal check failed: an unselected object entered the new zone range.')

            # Selected objects removed again by an existing Subtract box (still reported, never silent).
            removed = 0
            if existing is not None and existing.subtract:
                merged = ZoneBoxes()
                merged.extend(existing)
                for center, half in zip(centers, halves):
                    inv = np.eye(4, dtype=np.float64)
                    inv[range(3), range(3)] = 1.0 / half
                    inv[:3, 3] = -center / half
                    merged.append((inv, 1.0))
                merged.subtract = list(existing.subtract)
                keep = np.ones(len(targets), dtype=bool)
                keep[list(bad)] = False
                sel_pts_h = np.pad(sel_pts[keep], ((0, 0), (0, 1)), constant_values=1.0)
                removed = int(np.count_nonzero(~inside_mask(sel_pts_h, merged)))

            p.zone_result = ''
            added = len(targets) - len(bad)
            self.result = f'Added {added} objects to {zone} with {len(boxes)} empties; skipped {skipped_count} already inside; unseparable {len(bad)}; removed by Subtract {removed}; ignored non-mesh {ignored}; mixed-collection empties {mixed}'

            if bad:
                names = [targets[i].name for i in bad[:5]]
                self.report({'WARNING'}, f'Unseparable (same origin as an unselected object): {", ".join(names)}')

        except BaseException:
            # Rollback
            for i, e in enumerate(created):
                bpy.data.objects.remove(e, do_unlink=True)
                if i % 128 == 127:
                    yield
            p.zone_result = ''
            raise
