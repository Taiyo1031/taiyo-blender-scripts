"""Vectorized origin-only zone selection, with bounded modal batches."""
import re
import time
import bpy
import numpy as np

_ENUM_CACHE = []
_ENUM_RETIRED = []
_RUNNING = False


def collect_zone_boxes(scene, prefix):
    zones = {}
    for e in scene.objects:
        if e.type == 'EMPTY' and e.empty_display_type == 'CUBE' and e.name.startswith(prefix):
            name = str(e['zone']) if 'zone' in e else re.sub(r'\.\d+$', '', e.name)
            try:
                inv = np.array(e.matrix_world.inverted(), dtype=np.float64)
            except ValueError:
                raise ValueError(f"Zone has a singular transform: {e.name}")
            zones.setdefault(name, []).append((inv, float(e.empty_display_size)))
    return zones


def zone_items(self, context):
    global _ENUM_CACHE
    names = sorted({str(e['zone']) if 'zone' in e else re.sub(r'\.\d+$', '', e.name)
                    for e in context.scene.objects
                    if e.type == 'EMPTY' and e.empty_display_type == 'CUBE'
                    and e.name.startswith(self.zone_prefix)}) if context else []
    items = [('ALL', 'All Zones', '', 0)] + [(n, n, '', i + 1) for i, n in enumerate(names) if n != 'ALL']
    # Retain strings used by Blender's dynamic EnumProperty.
    if items != _ENUM_CACHE:
        _ENUM_RETIRED.append(_ENUM_CACHE)
        _ENUM_CACHE = items
    return _ENUM_CACHE


def points_of(objs):
    pts = np.empty((len(objs), 4), dtype=np.float64)
    pts[:, 3] = 1.0
    for i, ob in enumerate(objs):
        pts[i, :3] = ob.matrix_world.translation
    return pts


def inside_mask(pts, boxes):
    mask = np.zeros(len(pts), dtype=bool)
    for inv, size in boxes:
        local = pts @ inv.T
        mask |= (np.abs(local[:, :3]) <= size).all(axis=1)
    return mask


class UBT_OT_SelectInZone(bpy.types.Operator):
    bl_idname = 'ubt.select_in_zone'
    bl_label = 'Select In Zone'
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return not _RUNNING and context.mode == 'OBJECT' and not context.scene.ubt_props.export_running

    def work(self, context):
        from . import _iter_collection_objects, _iter_all_scene_objects
        p = context.scene.ubt_props
        if p.scope == 'selected':
            raise ValueError('Select In Zone does not support Selected scope.')
        if p.scope != 'all' and p.collection is None:
            raise ValueError('Select a collection.')
        zones = collect_zone_boxes(context.scene, p.zone_prefix)
        if not zones:
            raise ValueError(f'No zone empties found (Cube empties named "{p.zone_prefix}*").')
        choice = p.zone_choice
        if choice != 'ALL':
            zones = {choice: zones[choice]} if choice in zones else {}
        source = _iter_all_scene_objects(context) if p.scope == 'all' else _iter_collection_objects(p.collection, p.scope == 'recursive')
        objects = []
        for i, ob in enumerate(source):
            if ob.type == 'MESH':
                objects.append(ob)
            if i % 1024 == 0:
                yield
        # All validation precedes selection changes.
        bpy.ops.object.select_all(action='DESELECT')
        counts = dict.fromkeys(sorted(zones), 0)
        hidden = overlap = 0
        layer_objects = set(context.view_layer.objects)
        for start in range(0, len(objects), 2048):
            batch = objects[start:start + 2048]
            pts = points_of(batch)
            assigned = np.zeros(len(batch), dtype=bool)
            hits = np.zeros(len(batch), dtype=np.int32)
            for name in counts:
                mask = inside_mask(pts, zones[name])
                hits += mask
                selected = np.flatnonzero(mask & ~assigned)
                for hit_index, index in enumerate(selected):
                    ob = batch[index]
                    if ob not in layer_objects or ob.hide_select or not ob.visible_get():
                        hidden += 1
                    else:
                        ob.select_set(True)
                        counts[name] += 1
                    if hit_index % 64 == 0:
                        yield
                assigned |= mask
                yield
            overlap += int(np.count_nonzero(hits > 1))
            p.zone_result = f'Selecting {min(start + 2048, len(objects))}/{len(objects)} | ESC cancels'
            yield
        p.zone_result = 'Result: ' + ' / '.join(f'{n} {v}' for n, v in counts.items())
        self.report({'INFO'}, f'{p.zone_result}; hidden/unselectable {hidden}; overlapping {overlap}')

    def start(self, context, modal):
        global _RUNNING
        _RUNNING = True
        self._timer = None
        self._work = self.work(context)
        self._last_draw = 0
        if not modal:
            try:
                for _ in self._work:
                    pass
                return self.finish(context)
            except Exception as exc:
                return self.finish(context, str(exc))
        self._timer = context.window_manager.event_timer_add(.01, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        return self.start(context, bool(context.window))

    def execute(self, context):
        return self.start(context, False)

    def modal(self, context, event):
        if event.type == 'ESC':
            return self.finish(context, 'Cancelled. Partial selection kept.')
        if event.type == 'TIMER':
            try:
                deadline = time.perf_counter() + .3
                while time.perf_counter() < deadline:
                    next(self._work)
            except StopIteration:
                return self.finish(context)
            except Exception as exc:
                return self.finish(context, str(exc))
            if time.perf_counter() - self._last_draw > .18:
                self._last_draw = time.perf_counter()
                if context.area:
                    context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def finish(self, context, error=''):
        global _RUNNING
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
        self._work.close()
        _RUNNING = False
        if error:
            context.scene.ubt_props.zone_result = error
            self.report({'WARNING'} if error.startswith('Cancelled.') else {'ERROR'}, error)
        return {'CANCELLED'} if error else {'FINISHED'}
