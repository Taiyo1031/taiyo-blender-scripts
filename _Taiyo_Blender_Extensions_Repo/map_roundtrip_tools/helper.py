"""Helper panel: where Library / FromHoudini objects are used in Map (filled in by the LM task)."""
import csv
from dataclasses import dataclass, field
from functools import wraps
import bpy
from .chunked import ChunkedOperator
from .constants import ARCHIVED_KEY, CSV_ID_KEY, ZONE_KEY
from .placement import effective_zone, made_by_import, normalize, walk_collections, walk_library, zone_path
from .placement_report import write_text
from .ui_common import draw_zone_banner

USAGE = None  # the last scan (Usage); operators read helper.USAGE each time
_DEBUG_TEXT = 'MRT Debug Report'

@dataclass
class Usage:
    library_objects: list  # mesh objects below Library, unique, sorted by name
    instances: dict  # mesh data -> [(object, its collection), ...] for mesh objects below Map
    library_set: set = None
    zone_counts: dict = field(default_factory=dict)
    _library_by_data: dict = field(default=None, init=False, repr=False)
    _unused: list = field(default=None, init=False, repr=False)

    def __post_init__(self):
        if self.library_set is None:
            self.library_set = set(self.library_objects)


def usage_is_valid(usage):
    """A scan can hold deleted RNA objects after Undo or a mesh import."""
    if usage is None:
        return False
    try:
        if usage.library_objects:
            usage.library_objects[0].name
    except ReferenceError:
        return False
    return True


def _require_usage(operator):
    if USAGE is None:
        operator.report({'ERROR'}, 'Run Scan Usage first.')
        return False
    if not usage_is_valid(USAGE):
        operator.report({'ERROR'}, 'Scan Usage again.')
        return False
    return True


def _guard_usage(execute):
    """A later object in a scan can also have been deleted since it was made."""
    @wraps(execute)
    def guarded(self, context):
        try:
            return execute(self, context)
        except ReferenceError:
            self.report({'ERROR'}, 'Scan Usage again.')
            return {'CANCELLED'}
    return guarded


def _library_by_data(usage):
    if usage._library_by_data is None:
        by_data = {}
        for ob in usage.library_objects:
            by_data.setdefault(ob.data, []).append(ob)
        for objects in by_data.values():
            objects.sort(key=lambda ob: ob.name)
        usage._library_by_data = by_data
    return usage._library_by_data

def scan_usage(p, chunk=4096):
    """ジェネレーター。Library配下のMesh Object collects、Map配下の各Collectionのobjectsを1度ずつ読んで、
    ob.dataがLibraryのMeshに含まれるものをinstancesへ入れる(Objectごとのusers_collectionは遅いので使わない)。
    chunk個ごとにyield。Usageを返す(return)。library_collかmap_collがNoneならValueError。"""
    if not p.library_coll or not p.map_coll:
        raise ValueError("Library and Map collections must be set.")

    # Library mesh objects
    library_objects = []
    seen_objects = set()
    for coll in walk_library(p):  # Library plus the New Meshes To collection
        for ob in coll.objects:
            if ob.type == 'MESH' and ob not in seen_objects:
                seen_objects.add(ob)
                library_objects.append(ob)
    library_objects.sort(key=lambda o: o.name)

    # Map配下の各Collectionを走査して、使われているObjectを記録
    instances = {}

    library_set = set(library_objects)
    library_data = {ob.data for ob in library_objects}
    zone_counts = {}
    counted_objects = set()
    done_count = 0
    for coll in walk_collections(p.map_coll):
        for ob in coll.objects:
            if ob.type == 'MESH':
                data = ob.data
                # LibraryのMeshデータかどうかを確認
                is_library_mesh = data in library_data
                if is_library_mesh:
                    if data in instances:
                        instances[data].append((ob, coll))
                    else:
                        instances[data] = [(ob, coll)]
                    if ob not in counted_objects:
                        counted_objects.add(ob)
                        zone = ob.get(ZONE_KEY)
                        if isinstance(zone, str) and zone.strip():
                            zone_counts[zone] = zone_counts.get(zone, 0) + 1

                done_count += 1
                if done_count % chunk == 0:
                    yield

    usage = Usage(library_objects=library_objects, instances=instances,
                  library_set=library_set, zone_counts=zone_counts)
    return usage

def usage_of(usage, library_object):
    """{'count': int, 'collections': {Collection名: 個数}, 'zones': {ub_zoneの値: 個数}}
    library_object.dataのMeshを使うMap内Objectを数える。ub_zoneが無い/空のObjectはzonesに入れない。"""
    data = library_object.data
    if data not in usage.instances:
        return {'count': 0, 'collections': {}, 'zones': {}}

    instances = usage.instances[data]
    count = len(instances)
    collections = {}
    zones = {}

    for ob, coll in instances:
        # Collectionごとの数をカウント
        coll_name = coll.name
        collections[coll_name] = collections.get(coll_name, 0) + 1

        # ub_zoneの値を取得してカウント
        zone_value = ob.get(ZONE_KEY)
        if zone_value and isinstance(zone_value, str) and zone_value.strip():
            zones[zone_value] = zones.get(zone_value, 0) + 1

    return {'count': count, 'collections': collections, 'zones': zones}

def unused(usage):
    """Mapで1つも使われていないLibrary Objectのlist(名前順)。"""
    if usage._unused is None:
        usage._unused = sorted((ob for ob in usage.library_objects if ob.data not in usage.instances),
                               key=lambda ob: ob.name)
    return usage._unused

def library_of(usage, ob):
    """obのMeshデータを持つLibrary Objectのlist(名前順)。Mapにあるかどうかは問わない。"""
    return _library_by_data(usage).get(ob.data, [])


def zone_library_objects(usage, zone):
    """Library mesh objects used by objects currently in the Map with this zone tag."""
    by_data = _library_by_data(usage)
    objects = set()
    for data, instances in usage.instances.items():
        if any(ob.get(ZONE_KEY) == zone for ob, _ in instances):
            objects.update(by_data.get(data, []))
    return sorted(objects, key=lambda ob: ob.name)


def _library_objects(p):
    return {ob for coll in walk_library(p) for ob in coll.objects if ob.type == 'MESH'}


def _csv_names(p, zone):
    path = zone_path(p, zone, 'csv_path')
    try:
        with open(bpy.path.abspath(path), newline='', encoding='utf-8-sig') as stream:
            reader = csv.reader(stream)
            header = next(reader, [])
            if 'objname' not in header:
                return set(), 'Placement CSV has no objname column; CSV names were not checked.'
            index = header.index('objname')
            names = {row[index] for row in reader if len(row) > index}
    except (OSError, UnicodeError, csv.Error, ValueError):
        return set(), 'Placement CSV could not be read; CSV names were not checked.'
    return names, ''


def _names_not_in_library(p, usage, zone):
    library_objects = usage.library_objects if usage_is_valid(usage) else _library_objects(p)
    library_data = {ob.data for ob in library_objects}
    exact = {ob.name for ob in library_objects}
    normalized = {normalize(name, p.name_mode) for name in exact}
    objects = set()
    if p.map_coll is not None:
        for coll in walk_collections(p.map_coll):
            for ob in coll.objects:
                if ob.type == 'MESH' and ob.get(ZONE_KEY) == zone and ob.data not in library_data:
                    objects.add(ob.name)
    names, note = _csv_names(p, zone)
    missing = [name for name in names if name not in exact
               and normalize(name, 'numeric_suffix') not in exact
               and normalize(name, p.name_mode) not in normalized]
    return {'objects': sorted(objects), 'csv': sorted(missing)}, note


def names_not_in_library(p, usage, zone):
    """Names missing by mesh data in the Map, and by placement name rules in the zone CSV."""
    result, _ = _names_not_in_library(p, usage, zone)
    return result


def _empty_zone_counts():
    return dict(original=0, imported=0, archived=0, outside=0, duplicate_ids=0)


def zone_state_counts(p):
    """Count zone tags and repeated CSV ids in one pass over all objects."""
    map_objects = ({ob for coll in walk_collections(p.map_coll) for ob in coll.objects}
                   if p.map_coll is not None else set())
    counts, ids = {}, {}
    for ob in bpy.data.objects:
        zone = ob.get(ZONE_KEY)
        archived = ob.get(ARCHIVED_KEY)
        csv_id = ob.get(CSV_ID_KEY)
        if zone:
            state = counts.setdefault(zone, _empty_zone_counts())
            state['imported' if made_by_import(ob, zone) else 'original'] += 1
            if ob not in map_objects and not archived:
                state['outside'] += 1
            if isinstance(csv_id, int) and csv_id >= 0:
                zone_ids = ids.setdefault(zone, {})
                zone_ids[csv_id] = zone_ids.get(csv_id, 0) + 1
        if archived:
            counts.setdefault(archived, _empty_zone_counts())['archived'] += 1
    for zone, zone_ids in ids.items():
        counts[zone]['duplicate_ids'] = sum(n > 1 for n in zone_ids.values())
    return counts


def _zone_state_line(zone, counts):
    return (f'{zone}: original {counts["original"]}, imported {counts["imported"]}, '
            f'archived {counts["archived"]}, outside {counts["outside"]}, '
            f'duplicate ids {counts["duplicate_ids"]}')


def _zone_state_lines(counts):
    return ['# Zone state', *(_zone_state_line(zone, counts[zone]) for zone in sorted(counts))]


def _debug_header(p, zone):
    library = p.library_coll.name if p.library_coll is not None else '(none)'
    map_name = p.map_coll.name if p.map_coll is not None else '(none)'
    return [f'# Library: {library} / Map: {map_name}', f'# Zone: {zone or "All Zones"}', '']


def _missing_name_lines(missing, note):
    lines = ['# Names not in Library', f'Objects ({len(missing["objects"])}):',
             *missing['objects'], f'CSV ({len(missing["csv"])}):', *missing['csv']]
    if note:
        lines.append('Note: ' + note)
    return lines


def _debug_usage(p):
    if usage_is_valid(USAGE):
        return USAGE
    if p.library_coll is None or p.map_coll is None:
        return Usage(sorted(_library_objects(p), key=lambda ob: ob.name), {})
    scan = scan_usage(p)
    while True:
        try:
            next(scan)
        except StopIteration as done:
            return done.value


class MRT_OT_HelperScan(ChunkedOperator, bpy.types.Operator):
    bl_idname = 'mrt.helper_scan'
    bl_label = 'Scan Usage'
    bl_description = 'Scan how Library objects are used in Map'

    def work(self, context):
        global USAGE
        USAGE = None
        p = context.scene.mrt_props
        usage = yield from scan_usage(p)
        USAGE = usage

        # カウントを取得して結果に設定
        library_count = len(usage.library_objects)
        instance_count = sum(len(instances) for instances in usage.instances.values())
        unused_count = len(unused(usage))

        self.result = f'Scanned {library_count} library objects, {instance_count} map instances, {unused_count} unused'
        zones = sorted(usage.zone_counts.items(), key=lambda item: (-item[1], item[0]))[:3]
        if zones:
            self.result += '; zones: ' + ', '.join(f'{zone} {count}' for zone, count in zones)

class MRT_OT_HelperSelectUsage(bpy.types.Operator):
    bl_idname = 'mrt.helper_select_usage'
    bl_label = 'Select Usage in Map'
    bl_description = 'Select Map objects that use the selected Library object(s)'

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    @_guard_usage
    def execute(self, context):
        global USAGE
        if not _require_usage(self):
            return {'CANCELLED'}

        # 選択中のLibrary Objectを取得（なければアクティブ）
        selected_objects = [ob for ob in context.selected_objects if ob.type == 'MESH']
        active_object = context.active_object
        if not selected_objects and active_object and active_object.type == 'MESH':
            selected_objects = [active_object]

        # Library Objectが選択されていない場合
        if not selected_objects:
            self.report({'WARNING'}, 'No library object selected.')
            return {'CANCELLED'}

        # 選択を解除
        bpy.ops.object.select_all(action='DESELECT')

        found = False

        for ob in selected_objects:
            # Is it a Library object?
            if ob not in USAGE.library_set:
                continue

            data = ob.data
            if data in USAGE.instances:
                instances = USAGE.instances[data]
                count = 0
                for instance_ob, _ in instances:
                    try:
                        instance_ob.select_set(True)
                        count += 1
                    except (ReferenceError, RuntimeError):
                        # 選択できないObjectは無視
                        pass
                if count > 0:
                    found = True

        if not found:
            self.report({'WARNING'}, 'No map objects found using the selected library object(s).')
            return {'CANCELLED'}

        # 最初の選択されたオブジェクトをアクティブに
        if context.selected_objects:
            context.view_layer.objects.active = context.selected_objects[0]

        return {'FINISHED'}

class MRT_OT_HelperSelectLibrary(bpy.types.Operator):
    bl_idname = 'mrt.helper_select_library'
    bl_label = 'Select Library Object'
    bl_description = 'Select the original library object(s) for selected Map objects'

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    @_guard_usage
    def execute(self, context):
        global USAGE
        if not _require_usage(self):
            return {'CANCELLED'}

        # 選択中のMap Objectを取得（なければアクティブ）
        selected_objects = [ob for ob in context.selected_objects if ob.type == 'MESH']
        active_object = context.active_object
        if not selected_objects and active_object and active_object.type == 'MESH':
            selected_objects = [active_object]

        # Map Objectが選択されていない場合
        if not selected_objects:
            self.report({'WARNING'}, 'No map object selected.')
            return {'CANCELLED'}

        # 選択を解除
        bpy.ops.object.select_all(action='DESELECT')

        found = False

        for ob in selected_objects:
            library_objects = library_of(USAGE, ob)
            if library_objects:
                count = 0
                for lib_ob in library_objects:
                    try:
                        lib_ob.select_set(True)
                        count += 1
                    except (ReferenceError, RuntimeError):
                        # 選択できないObjectは無視
                        pass
                if count > 0:
                    found = True

        if not found:
            self.report({'WARNING'}, 'No library object(s) found for the selected map object(s).')
            return {'CANCELLED'}

        # 最初の選択されたオブジェクトをアクティブに
        if context.selected_objects:
            context.view_layer.objects.active = context.selected_objects[0]

        return {'FINISHED'}

class MRT_OT_HelperSelectUnused(bpy.types.Operator):
    bl_idname = 'mrt.helper_select_unused'
    bl_label = 'Select Unused Library Objects'
    bl_description = 'Select library objects that are not used in Map'

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    @_guard_usage
    def execute(self, context):
        global USAGE
        if not _require_usage(self):
            return {'CANCELLED'}

        unused_objects = unused(USAGE)

        # 選択を解除
        bpy.ops.object.select_all(action='DESELECT')

        count = 0
        for ob in unused_objects:
            try:
                ob.select_set(True)
                count += 1
            except (ReferenceError, RuntimeError):
                pass

        if count > 0 and context.selected_objects:
            context.view_layer.objects.active = context.selected_objects[0]

        self.report({'INFO'}, f'Selected {count} unused library objects.')

        return {'FINISHED'}

class MRT_OT_HelperReport(bpy.types.Operator):
    bl_idname = 'mrt.helper_report'
    bl_label = 'Write Usage Report'
    bl_description = 'Write usage report to a text block'

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    @_guard_usage
    def execute(self, context):
        global USAGE
        if not _require_usage(self):
            return {'CANCELLED'}

        # テキストブロックを取得または作成
        report_name = 'MRT Usage Report'
        text_block = bpy.data.texts.get(report_name)
        if not text_block:
            text_block = bpy.data.texts.new(name=report_name)
        else:
            text_block.clear()

        # ヘッダーを追加
        p = context.scene.mrt_props
        header = f'# Library: {p.library_coll.name} / Map: {p.map_coll.name}\n'
        text_block.write(header)

        count_selected = 0

        for lib_ob in USAGE.library_objects:
            usage_info = usage_of(USAGE, lib_ob)

            # 行を構築
            line_parts = [lib_ob.name]
            line_parts.append(f'{usage_info["count"]} uses')

            collections = sorted(usage_info['collections'].items(), key=lambda x: x[1], reverse=True)
            if collections:
                collection_strs = [f'{coll}: {n}' for coll, n in collections[:3]]  # 最大3つ
                line_parts.append(', '.join(collection_strs))

            zones = sorted(usage_info['zones'].items(), key=lambda x: x[1], reverse=True)
            if zones:
                zone_strs = [f'{zone}: {n}' for zone, n in zones[:3]]  # 最大3つ
                line_parts.append(', '.join(zone_strs))

            text_block.write(' | '.join(line_parts) + '\n')

        self.report({'INFO'}, f'Usage report written to "{report_name}".')

        return {'FINISHED'}

class MRT_OT_HelperSelectZoneLibrary(bpy.types.Operator):
    bl_idname = 'mrt.helper_select_zone_library'
    bl_label = 'Select Library Meshes of Zone'
    bl_description = 'Select Library mesh objects used by the selected zone in the Map.'

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    @_guard_usage
    def execute(self, context):
        p = context.scene.mrt_props
        zone = effective_zone(p)
        if not zone:
            self.report({'ERROR'}, 'Choose one zone (not All Zones).')
            return {'CANCELLED'}
        if not _require_usage(self):
            return {'CANCELLED'}
        objects = zone_library_objects(USAGE, zone)
        if not objects:
            self.report({'WARNING'}, f'No Library objects used by {zone}.')
            return {'CANCELLED'}
        bpy.ops.object.select_all(action='DESELECT')
        selected = []
        for ob in objects:
            try:
                ob.select_set(True)
                selected.append(ob)
            except (ReferenceError, RuntimeError):
                pass
        if not selected:
            self.report({'WARNING'}, f'No selectable Library objects used by {zone}.')
            return {'CANCELLED'}
        context.view_layer.objects.active = selected[0]
        self.report({'INFO'}, f'Selected {len(selected)} Library objects used by {zone}.')
        return {'FINISHED'}


class MRT_OT_HelperMissingNames(bpy.types.Operator):
    bl_idname = 'mrt.helper_missing_names'
    bl_label = 'Names not in Library'
    bl_description = 'Write Map and Placement CSV names missing from the Library to a Text datablock.'

    @_guard_usage
    def execute(self, context):
        p = context.scene.mrt_props
        zone = effective_zone(p)
        if not zone:
            self.report({'ERROR'}, 'Choose one zone (not All Zones).')
            return {'CANCELLED'}
        missing, note = _names_not_in_library(p, USAGE, zone)
        write_text(_DEBUG_TEXT, _debug_header(p, zone) + _missing_name_lines(missing, note))
        self.report({'INFO'}, f'{zone}: {len(missing["objects"])} Map objects, '
                    f'{len(missing["csv"])} CSV names not in Library. See "{_DEBUG_TEXT}".')
        if note:
            self.report({'WARNING'}, note)
        return {'FINISHED'}


class MRT_OT_HelperZoneState(bpy.types.Operator):
    bl_idname = 'mrt.helper_zone_state'
    bl_label = 'Zone State Counts'
    bl_description = 'Write counts of original, imported, archived and outside objects for every zone.'

    def execute(self, context):
        p = context.scene.mrt_props
        zone = effective_zone(p)
        counts = zone_state_counts(p)
        if zone:
            counts.setdefault(zone, _empty_zone_counts())
        write_text(_DEBUG_TEXT, _debug_header(p, zone) + _zone_state_lines(counts))
        if zone:
            self.report({'INFO'}, _zone_state_line(zone, counts[zone]))
        else:
            self.report({'INFO'}, f'{len(counts)} zones written to "{_DEBUG_TEXT}".')
        return {'FINISHED'}


class MRT_OT_HelperDebugReport(bpy.types.Operator):
    bl_idname = 'mrt.helper_debug_report'
    bl_label = 'Write Debug Report to Text'
    bl_description = 'Write zone state, Library usage and missing names to one Text datablock.'

    @_guard_usage
    def execute(self, context):
        p = context.scene.mrt_props
        zone = effective_zone(p)
        counts = zone_state_counts(p)
        if zone:
            counts.setdefault(zone, _empty_zone_counts())
        lines = _debug_header(p, zone) + _zone_state_lines(counts)
        usage = _debug_usage(p)
        lines += ['', f'# Library meshes used by {zone or "All Zones"}']
        if zone:
            objects = zone_library_objects(usage, zone)
            lines += [ob.name for ob in objects] or ['(none)']
        else:
            zones = sorted(set(counts) | set(usage.zone_counts))
            lines += [f'{name}: {len(zone_library_objects(usage, name))} Library objects' for name in zones]
            if not zones:
                lines.append('(none)')
        note = ''
        if zone:
            missing, note = _names_not_in_library(p, usage, zone)
            lines += [''] + _missing_name_lines(missing, note)
        lines += ['', '# Unused Library objects']
        if usage_is_valid(USAGE):
            lines += [ob.name for ob in unused(USAGE)] or ['(none)']
        else:
            lines.append('Run Scan Usage first.' if USAGE is None else 'Scan Usage again.')
        write_text(_DEBUG_TEXT, lines)
        self.report({'INFO'}, f'Debug report written to "{_DEBUG_TEXT}".')
        if note:
            self.report({'WARNING'}, note)
        return {'FINISHED'}


class MRT_PT_Helper(bpy.types.Panel):
    bl_label = 'Helper'
    bl_idname = 'MRT_PT_helper'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Map Roundtrip'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        p = context.scene.mrt_props
        layout = self.layout
        layout.enabled = not p.running
        zone = draw_zone_banner(layout, context, 'Helper: how the Library meshes are used in the Map (all zones).')

        if not p.library_coll or not p.map_coll:
            layout.label(text='Set Library and Map in Import first.')
            return

        # Scan button
        layout.operator('mrt.helper_scan')

        # Scan summary
        valid_usage = usage_is_valid(USAGE)
        if USAGE is None:
            layout.label(text='Not scanned yet.')
        elif not valid_usage:
            layout.label(text='Scan Usage again.')
        else:
            lib_count = len(USAGE.library_objects)
            instance_count = sum(len(instances) for instances in USAGE.instances.values())
            unused_count = len(unused(USAGE))
            layout.label(text=f'Scanned: {lib_count} library objects, {instance_count} map instances, {unused_count} unused')

        # Information about the selected objects
        selected_objects = [ob for ob in context.selected_objects if ob.type == 'MESH']
        if not selected_objects:
            active_object = context.active_object
            if active_object and active_object.type == 'MESH':
                selected_objects = [active_object]

        # At most 5 objects
        display_count = min(len(selected_objects), 5)
        for i in range(display_count):
            ob = selected_objects[i]

            # Is it a Library object?
            is_library_obj = ob in USAGE.library_set if valid_usage else False

            if is_library_obj:
                usage_info = usage_of(USAGE, ob)
                layout.label(text=f'{ob.name}: {usage_info["count"]} uses')

                # Up to 3 collections, most used first
                collections = sorted(usage_info['collections'].items(), key=lambda x: x[1], reverse=True)[:3]
                for coll_name, count in collections:
                    layout.label(text=f'  {coll_name}: {count}')
            else:
                # A Map object: show its Library object
                library_objects = library_of(USAGE, ob) if valid_usage else []
                if library_objects:
                    lib_ob = library_objects[0]  # only the first one
                    layout.label(text=f'{ob.name} <- {lib_ob.name}')

        # Buttons
        layout.operator('mrt.helper_select_usage')
        layout.operator('mrt.helper_select_library')
        layout.operator('mrt.helper_select_unused')
        layout.operator('mrt.helper_report')

        box = layout.box()
        box.label(text='Debug (selected zone)')
        row = box.row()
        row.enabled = zone not in ('', 'ALL')
        row.operator('mrt.helper_select_zone_library')
        row = box.row()
        row.enabled = zone not in ('', 'ALL')
        row.operator('mrt.helper_missing_names')
        box.operator('mrt.helper_zone_state')
        box.operator('mrt.helper_debug_report')


HELPER_CLASSES = (
    MRT_OT_HelperScan,
    MRT_OT_HelperSelectUsage,
    MRT_OT_HelperSelectLibrary,
    MRT_OT_HelperSelectUnused,
    MRT_OT_HelperReport,
    MRT_OT_HelperSelectZoneLibrary,
    MRT_OT_HelperMissingNames,
    MRT_OT_HelperZoneState,
    MRT_OT_HelperDebugReport,
    MRT_PT_Helper
)
