"""Helper panel: where Library / FromHoudini objects are used in Map (filled in by the LM task)."""
from dataclasses import dataclass
import bpy
from .chunked import ChunkedOperator
from .placement import walk_collections

USAGE = None  # the last scan (Usage); operators read helper.USAGE each time

@dataclass
class Usage:
    library_objects: list  # mesh objects below Library, unique, sorted by name
    instances: dict  # mesh data -> [(object, its collection), ...] for mesh objects below Map

def scan_usage(p, chunk=4096):
    """ジェネレーター。Library配下のMesh Object collects、Map配下の各Collectionのobjectsを1度ずつ読んで、
    ob.dataがLibraryのMeshに含まれるものをinstancesへ入れる(Objectごとのusers_collectionは遅いので使わない)。
    chunk個ごとにyield。Usageを返す(return)。library_collかmap_collがNoneならValueError。"""
    if not p.library_coll or not p.map_coll:
        raise ValueError("Library and Map collections must be set.")

    # Library mesh objects
    library_objects = []
    for coll in walk_collections(p.library_coll):
        for ob in coll.objects:
            if ob.type == 'MESH':
                library_objects.append(ob)
    library_objects.sort(key=lambda o: o.name)

    # Map配下の各Collectionを走査して、使われているObjectを記録
    instances = {}

    total_count = 0
    for coll in walk_collections(p.map_coll):
        for ob in coll.objects:
            if ob.type == 'MESH':
                total_count += 1

    done_count = 0
    for coll in walk_collections(p.map_coll):
        for ob in coll.objects:
            if ob.type == 'MESH':
                data = ob.data
                # LibraryのMeshデータかどうかを確認
                is_library_mesh = any(ob2.data == data for ob2 in library_objects)
                if is_library_mesh:
                    if data in instances:
                        instances[data].append((ob, coll))
                    else:
                        instances[data] = [(ob, coll)]

                done_count += 1
                if done_count % chunk == 0:
                    yield

    usage = Usage(library_objects=library_objects, instances=instances)
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
        zone_value = ob.get('ub_zone')
        if zone_value and isinstance(zone_value, str) and zone_value.strip():
            zones[zone_value] = zones.get(zone_value, 0) + 1

    return {'count': count, 'collections': collections, 'zones': zones}

def unused(usage):
    """Mapで1つも使われていないLibrary Objectのlist(名前順)。"""
    used_data = set(usage.instances.keys())
    unused_objects = []

    for obj in usage.library_objects:
        if obj.data not in used_data:
            unused_objects.append(obj)

    return sorted(unused_objects, key=lambda o: o.name)

def library_of(usage, ob):
    """obのMeshデータを持つLibrary Objectのlist(名前順)。Mapにあるかどうかは問わない。"""
    data = ob.data
    result = []

    for lib_obj in usage.library_objects:
        if lib_obj.data == data:
            result.append(lib_obj)

    return sorted(result, key=lambda o: o.name)

class MRT_OT_HelperScan(ChunkedOperator, bpy.types.Operator):
    bl_idname = 'mrt.helper_scan'
    bl_label = 'Scan Usage'
    bl_description = 'Scan how Library objects are used in Map'

    def work(self, context):
        global USAGE
        p = context.scene.mrt_props
        usage = yield from scan_usage(p)
        USAGE = usage

        # カウントを取得して結果に設定
        library_count = len(usage.library_objects)
        instance_count = sum(len(instances) for instances in usage.instances.values())
        unused_count = len(unused(usage))

        self.result = f'Scanned {library_count} library objects, {instance_count} map instances, {unused_count} unused'

class MRT_OT_HelperSelectUsage(bpy.types.Operator):
    bl_idname = 'mrt.helper_select_usage'
    bl_label = 'Select Usage in Map'
    bl_description = 'Select Map objects that use the selected Library object(s)'

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        global USAGE
        if not USAGE:
            self.report({'ERROR'}, 'Run Scan Usage first.')
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
            if not any(lib_ob == ob for lib_ob in USAGE.library_objects):
                continue

            data = ob.data
            if data in USAGE.instances:
                instances = USAGE.instances[data]
                count = 0
                for instance_ob, _ in instances:
                    try:
                        instance_ob.select_set(True)
                        count += 1
                    except Exception:
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

    def execute(self, context):
        global USAGE
        if not USAGE:
            self.report({'ERROR'}, 'Run Scan Usage first.')
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
                    except Exception:
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

    def execute(self, context):
        global USAGE
        if not USAGE:
            self.report({'ERROR'}, 'Run Scan Usage first.')
            return {'CANCELLED'}

        unused_objects = unused(USAGE)

        # 選択を解除
        bpy.ops.object.select_all(action='DESELECT')

        count = 0
        for ob in unused_objects:
            try:
                ob.select_set(True)
                count += 1
            except Exception:
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

    def execute(self, context):
        global USAGE
        if not USAGE:
            self.report({'ERROR'}, 'Run Scan Usage first.')
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

        if not p.library_coll or not p.map_coll:
            layout.label(text='Set Library and Map in Import first.')
            return

        # Scan button
        layout.operator('mrt.helper_scan')

        # Scan summary
        if USAGE is None:
            layout.label(text='Not scanned yet.')
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
            is_library_obj = any(lib_ob == ob for lib_ob in USAGE.library_objects) if USAGE else False

            if is_library_obj:
                usage_info = usage_of(USAGE, ob)
                layout.label(text=f'{ob.name}: {usage_info["count"]} uses')

                # Up to 3 collections, most used first
                collections = sorted(usage_info['collections'].items(), key=lambda x: x[1], reverse=True)[:3]
                for coll_name, count in collections:
                    layout.label(text=f'  {coll_name}: {count}')
            else:
                # A Map object: show its Library object
                library_objects = library_of(USAGE, ob) if USAGE else []
                if library_objects:
                    lib_ob = library_objects[0]  # only the first one
                    layout.label(text=f'{ob.name} <- {lib_ob.name}')

        # Buttons
        layout.operator('mrt.helper_select_usage')
        layout.operator('mrt.helper_select_library')
        layout.operator('mrt.helper_select_unused')
        layout.operator('mrt.helper_report')


HELPER_CLASSES = (
    MRT_OT_HelperScan,
    MRT_OT_HelperSelectUsage,
    MRT_OT_HelperSelectLibrary,
    MRT_OT_HelperSelectUnused,
    MRT_OT_HelperReport,
    MRT_PT_Helper
)
