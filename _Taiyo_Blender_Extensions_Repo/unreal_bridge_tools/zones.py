"""Vectorized origin-only zone selection, with bounded modal batches."""
import re
import time
import bpy
import numpy as np
from bpy.props import BoolProperty, EnumProperty, StringProperty
from .constants import ZONE_NAME_KEY

_ENUM_CACHE = []
_ENUM_RETIRED = []
_RUNNING = False


class ZoneBoxes(list):
    """Union of additive boxes, minus union of subtractive boxes.

    Remains list-compatible for callers of inside_mask and the benchmark.
    """
    def __init__(self):
        super().__init__()
        self.subtract = []


def zone_name(empty):
    return str(empty[ZONE_NAME_KEY]) if ZONE_NAME_KEY in empty else re.sub(r'\.\d+$', '', empty.name)


def zone_empties(scene, prefix):
    return (e for e in scene.objects if e.type == 'EMPTY'
            and e.empty_display_type == 'CUBE' and e.ubt_zone_enabled
            and (ZONE_NAME_KEY in e or e.name.startswith(prefix)))


class UBT_ZoneEntry(bpy.types.PropertyGroup):
    name: StringProperty(name='Zone Name', description='ゾーンの識別名。CSVファイル名もこの名前に揃えてください')


def ensure_zone(props, name):
    if name not in props.zones:
        props.zones.add().name = name


def zone_editable(context):
    return context.mode == 'OBJECT' and not _RUNNING and not context.scene.ubt_props.export_running


class UBT_OT_NewZone(bpy.types.Operator):
    bl_idname = 'ubt.new_zone'
    bl_label = 'New Zone'
    bl_description = '空のゾーンを登録します。登録後にAdd Emptyで範囲を作るか、既存Emptyを登録してください'
    bl_options = {'REGISTER', 'UNDO'}
    name: StringProperty(name='Zone Name', default='ZONE_A', description='例：ZONE_A。配置CSVのファイル名と同じ名前を推奨します')

    @classmethod
    def poll(cls, context):
        return zone_editable(context)

    def invoke(self, context, event):
        self.name = context.scene.ubt_props.zone_prefix + 'A'
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        name = self.name.strip()
        if not name or name == 'ALL':
            self.report({'ERROR'}, 'Choose a nonempty zone name other than ALL.')
            return {'CANCELLED'}
        p = context.scene.ubt_props
        ensure_zone(p, name)
        p.zone_choice = name
        p.zone_result = ''
        return {'FINISHED'}


class UBT_OT_RegisterZoneEmpties(bpy.types.Operator):
    bl_idname = 'ubt.register_zone_empties'
    bl_label = 'Register Selected Empties'
    bl_description = '選択した既存Emptyを現在のゾーンに登録します。名前は変えずCube表示にします。別ゾーンのEmptyは所属を変更します'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return zone_editable(context) and context.scene.ubt_props.zone_choice not in ('', 'ALL')

    def execute(self, context):
        p = context.scene.ubt_props
        selected = [e for e in context.selected_objects if e.type == 'EMPTY']
        if not selected:
            self.report({'ERROR'}, 'Select at least one Empty to register.')
            return {'CANCELLED'}
        if any(not e.is_editable for e in selected):
            self.report({'ERROR'}, 'Selected empties include read-only library objects.')
            return {'CANCELLED'}
        name = p.zone_choice
        ensure_zone(p, name)
        for e in selected:
            e[ZONE_NAME_KEY] = name
            e.empty_display_type = 'CUBE'
            e.ubt_zone_enabled = True
        p.zone_choice = name
        self.report({'INFO'}, f'Registered {len(selected)} empties to {name}.')
        return {'FINISHED'}


class UBT_OT_ZoneEmptyAction(bpy.types.Operator):
    bl_idname = 'ubt.zone_empty_action'
    bl_label = 'Zone Empty'
    bl_options = {'REGISTER', 'UNDO'}
    object_name: StringProperty(options={'HIDDEN'})
    action: EnumProperty(items=[('SELECT','Select','一覧のEmptyを選択して移動・拡大を編集します'), ('UNREGISTER','Unregister','登録を解除します。Empty本体は削除しません')])

    @classmethod
    def description(cls, context, properties):
        return 'このEmptyのゾーン登録を解除します。Objectは削除しません' if properties.action == 'UNREGISTER' else 'このEmptyを選択・アクティブにして、ビューポートで編集します'

    @classmethod
    def poll(cls, context):
        return zone_editable(context)

    def execute(self, context):
        e = context.scene.objects.get(self.object_name)
        if e is None or e.type != 'EMPTY':
            self.report({'ERROR'}, 'Empty no longer exists in this scene.')
            return {'CANCELLED'}
        if self.action == 'UNREGISTER':
            if not e.is_editable:
                return {'CANCELLED'}
            choice = context.scene.ubt_props.zone_choice
            e.ubt_zone_enabled = False
            if ZONE_NAME_KEY in e:
                del e[ZONE_NAME_KEY]
            props = context.scene.ubt_props
            available = {item[0] for item in zone_items(props, context)}
            props.zone_choice = choice if choice in available else 'ALL'
        else:
            if e.name not in context.view_layer.objects or not e.visible_get() or e.hide_select:
                self.report({'ERROR'}, 'Empty is hidden or not selectable in this view layer.')
                return {'CANCELLED'}
            bpy.ops.object.select_all(action='DESELECT')
            e.select_set(True)
            context.view_layer.objects.active = e
        return {'FINISHED'}


def register_zone_properties():
    bpy.types.Object.ubt_zone_enabled = BoolProperty(name='Zone Enabled', default=True, description='このEmptyをゾーン判定に使用します。Unregisterで解除し、Register Selected Emptiesで再登録できます')
    bpy.types.Object.ubt_zone_operation = EnumProperty(
        name='Operation', description='Addは範囲へ追加、Subtractは同じゾーンのAdd合成範囲からくり抜きます',
        items=[('ADD', 'Add', 'この箱の範囲をゾーンへ含めます'),
               ('SUBTRACT', 'Subtract', '同じゾーンのAdd範囲からこの箱の範囲を除外します')],
        default='ADD')


def unregister_zone_properties():
    del bpy.types.Object.ubt_zone_operation
    del bpy.types.Object.ubt_zone_enabled


def draw_zone_controls(layout, context):
    p = context.scene.ubt_props
    controls = layout.column()
    controls.enabled = not _RUNNING and not p.export_running
    controls.operator_context = 'INVOKE_DEFAULT'
    controls.operator('ubt.new_zone', text='New Zone', icon='ADD')
    controls.operator('ubt.register_zone_empties', icon='IMPORT')
    controls.operator('ubt.add_zone_empty', text='Add Empty', icon='ADD')
    choice = p.zone_choice
    empties = sorted(zone_empties(context.scene, p.zone_prefix), key=lambda e: (zone_name(e), e.name))
    previous = None
    visible = 0
    for empty in empties:
        name = zone_name(empty)
        if choice != 'ALL' and name != choice:
            continue
        visible += 1
        if choice == 'ALL' and previous != name:
            controls.label(text=name)
            previous = name
        row = controls.row(align=True)
        row.enabled = empty.is_editable
        select = row.operator('ubt.zone_empty_action', text=empty.name, icon='EMPTY_AXIS')
        select.object_name, select.action = empty.name, 'SELECT'
        row.prop(empty, 'ubt_zone_operation', text='')
        remove = row.operator('ubt.zone_empty_action', text='', icon='X')
        remove.object_name, remove.action = empty.name, 'UNREGISTER'
    if not visible:
        controls.label(text='No Empty in this zone. Add or register one.', icon='INFO')


class UBT_OT_AddZoneEmpty(bpy.types.Operator):
    bl_idname = 'ubt.add_zone_empty'
    bl_label = 'Add Zone Empty'
    bl_description = '現在のゾーンにCube Emptyを新規追加します。初期位置は3Dカーソル、OperationはAddです'
    bl_options = {'REGISTER', 'UNDO'}
    zone_name: StringProperty(name='Zone Name', description='このEmptyの所属ゾーン。CSVのファイル名と揃えてください')

    @classmethod
    def poll(cls, context):
        return not _RUNNING and context.mode == 'OBJECT' and not context.scene.ubt_props.export_running

    def invoke(self, context, event):
        p = context.scene.ubt_props
        if p.zone_choice != 'ALL':
            self.zone_name = p.zone_choice
            return self.execute(context)
        self.zone_name = p.zone_prefix + 'A'
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        p = context.scene.ubt_props
        name = self.zone_name.strip() or (p.zone_choice if p.zone_choice != 'ALL' else '')
        if not name or name == 'ALL':
            self.report({'ERROR'}, 'Choose a nonempty zone name other than ALL.')
            return {'CANCELLED'}
        object_name = name if name.startswith(p.zone_prefix) else p.zone_prefix + name
        empty = bpy.data.objects.new(object_name, None)
        try:
            empty.empty_display_type = 'CUBE'
            empty.empty_display_size = 1.0
            empty.show_in_front = True
            empty.location = context.scene.cursor.location
            empty[ZONE_NAME_KEY] = name
            empty.ubt_zone_operation = 'ADD'
            empty.ubt_zone_enabled = True
            context.scene.collection.objects.link(empty)
            bpy.ops.object.select_all(action='DESELECT')
            empty.select_set(True)
            context.view_layer.objects.active = empty
            ensure_zone(p, name)
            p.zone_choice = name
            p.zone_result = ''
        except Exception:
            bpy.data.objects.remove(empty, do_unlink=True)
            raise
        return {'FINISHED'}


def collect_zone_boxes(scene, prefix):
    zones = {}
    for e in zone_empties(scene, prefix):
        name = zone_name(e)
        try:
            inv = np.array(e.matrix_world.inverted(), dtype=np.float64)
        except ValueError:
            raise ValueError(f"Zone has a singular transform: {e.name}")
        boxes = zones.setdefault(name, ZoneBoxes())
        target = boxes.subtract if e.ubt_zone_operation == 'SUBTRACT' else boxes
        target.append((inv, float(e.empty_display_size)))
    return zones


def zone_items(self, context):
    global _ENUM_CACHE
    names = sorted({z.name for z in self.zones} | {zone_name(e) for e in zone_empties(context.scene, self.zone_prefix)}) if context else []
    items = [('ALL', 'All Zones', '全ゾーンの合成結果を選択します。ゾーン別CSVを出すときは個別のゾーンを選んでください', 0)] + [(n, n, 'このゾーンに登録されたAdd/Subtract Emptyで範囲を判定します', i + 1) for i, n in enumerate(names) if n != 'ALL']
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
    if getattr(boxes, 'subtract', None) and mask.any():
        mask &= ~inside_mask(pts, boxes.subtract)
    return mask


class UBT_OT_SelectInZone(bpy.types.Operator):
    bl_idname = 'ubt.select_in_zone'
    bl_label = 'Select In Zone'
    bl_description = '現在のZone範囲内に原点があるMeshを選択します。先にRecursive等で候補Collectionを指定し、選択後にSelectedでCSVを書き出してください'
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
            if choice not in zones:
                raise ValueError('Selected zone has no Cube empties. Use Add Empty or Register Selected Empties.')
            zones = {choice: zones[choice]}
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
