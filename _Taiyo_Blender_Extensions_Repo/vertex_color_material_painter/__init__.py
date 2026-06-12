bl_info = {
    "name": "Vertex Color Material Painter",
    "author": "Taiyo",
    "version": (1, 0, 5),
    "blender": (4, 5, 9),
    "location": "View3D > Sidebar > VC Painter",
    "description": "Paint selected edit-mode faces with scene-saved material ID colors",
    "category": "Mesh",
}

import json

import bmesh
import bpy
from bpy.props import (
    CollectionProperty,
    EnumProperty,
    FloatVectorProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import Operator, Panel, PropertyGroup, UIList
from bpy_extras.io_utils import ExportHelper
from mathutils import Color


DEFAULT_ATTRIBUTE_NAME = "mat_color"
DEFAULT_COPY_TARGET_NAME = "mat_color_copy"
DEFAULT_ATTRIBUTE_TYPE = "BYTE_COLOR"
DEFAULT_NEW_COLOR_NAME = "Wood"
DEFAULT_NEW_COLOR = (0.45, 0.24, 0.09, 1.0)
FLOAT_COLOR_MATCH_TOLERANCE = 0.0001
BYTE_COLOR_MATCH_TOLERANCE = (1.0 / 255.0) + 0.0001
AUTO_REPAIR_MATCH_TOLERANCE = 0.01
SUPPORTED_COLOR_TYPES = {'BYTE_COLOR', 'FLOAT_COLOR'}
COLOR_TYPE_ITEMS = (
    ('BYTE_COLOR', "Byte Color", "軽量な8bit Color Attributeを作成します"),
    ('FLOAT_COLOR', "Float Color", "高精度なFloat Color Attributeを作成します"),
)
REMOVE_MATCH_MODE_ITEMS = (
    ('SAME_NAME', "Same Name", "同じ名前のAttributeを削除します"),
    ('DATA_TYPE', "Data Type", "同じデータ型のAttributeを削除します"),
    ('DOMAIN', "Domain", "同じドメインのAttributeを削除します"),
    ('TYPE_DOMAIN', "Type + Domain", "データ型とドメインが両方一致するAttributeを削除します"),
    ('ALL_REMOVABLE', "All Removable", "内部・必須属性を除くすべてのAttributeを削除します"),
)
REMOVE_FILTER_SOURCE_ITEMS = (
    ('DIRECT', "Direct", "名前、データ型、ドメインを直接指定します"),
    ('REFERENCE', "Reference Attribute", "アクティブMeshのAttributeから削除条件を取得します"),
)
REMOVE_DATA_TYPE_ITEMS = (
    ('FLOAT', "Float", "Float Attribute"),
    ('INT', "Integer", "Integer Attribute"),
    ('FLOAT_VECTOR', "Vector", "Vector Attribute"),
    ('FLOAT_COLOR', "Color", "Float Color Attribute"),
    ('BYTE_COLOR', "Byte Color", "Byte Color Attribute"),
    ('STRING', "String", "String Attribute"),
    ('BOOLEAN', "Boolean", "Boolean Attribute"),
    ('FLOAT2', "2D Vector", "2D Vector Attribute"),
    ('INT8', "8-Bit Integer", "8-Bit Integer Attribute"),
    ('INT16_2D', "2D 16-Bit Integer Vector", "2D 16-Bit Integer Vector Attribute"),
    ('INT32_2D', "2D Integer Vector", "2D Integer Vector Attribute"),
    ('QUATERNION', "Quaternion", "Quaternion Attribute"),
    ('FLOAT4X4', "4x4 Matrix", "4x4 Matrix Attribute"),
)
REMOVE_DOMAIN_ITEMS = (
    ('POINT', "Point", "Mesh point domain"),
    ('EDGE', "Edge", "Mesh edge domain"),
    ('FACE', "Face", "Mesh face domain"),
    ('CORNER', "Face Corner", "Mesh face corner domain"),
)


def _active_mesh_edit_object(context):
    obj = context.object

    if obj is None or obj.type != 'MESH':
        return None, "メッシュオブジェクトをアクティブにしてください。"

    if context.mode != 'EDIT_MESH':
        return None, "Edit Mode で実行してください。"

    return obj, None


def _clean_attribute_name(name):
    return name.strip() or DEFAULT_ATTRIBUTE_NAME


def _clean_copy_target_name(name):
    return name.strip() or DEFAULT_COPY_TARGET_NAME


def _clean_attribute_type(attribute_type):
    if attribute_type in SUPPORTED_COLOR_TYPES:
        return attribute_type

    return DEFAULT_ATTRIBUTE_TYPE


def _validate_color_attribute(attribute, attribute_name):
    if attribute is None:
        raise ValueError(f"Color Attribute がありません: {attribute_name}")

    if attribute.domain != 'CORNER' or attribute.data_type not in SUPPORTED_COLOR_TYPES:
        raise ValueError(
            f"'{attribute_name}' は BYTE_COLOR または FLOAT_COLOR の CORNER Attribute ではありません。"
        )


def _get_color_item(context, index):
    items = context.scene.vcmp_color_items

    if not items:
        return None, "カラーリストが空です。"

    if index < 0:
        index = context.scene.vcmp_active_index

    if index < 0 or index >= len(items):
        return None, "カラーを選択してください。"

    return items[index], None


def _object_mode_mesh_targets(context):
    selected_objects = getattr(context, "selected_editable_objects", None)

    if selected_objects is None:
        selected_objects = context.selected_objects

    return [
        obj for obj in selected_objects
        if obj is not None and obj.type == 'MESH' and obj.data is not None
    ]


def _bmesh_layer_collection(bm, attribute_type):
    if attribute_type == 'FLOAT_COLOR':
        return bm.loops.layers.float_color

    return bm.loops.layers.color


def _scene_linear_to_bmesh_color(color, attribute_type):
    if attribute_type != 'BYTE_COLOR':
        return tuple(color)

    rgb = Color(color[:3]).from_scene_linear_to_srgb()
    return (*rgb, color[3])


def _bmesh_color_to_scene_linear(color, attribute_type):
    if attribute_type != 'BYTE_COLOR':
        return tuple(color)

    rgb = Color(color[:3]).from_srgb_to_scene_linear()
    return (*rgb, color[3])


def _ensure_bmesh_color_attribute(mesh, bm, attribute_name, requested_type):
    attribute = mesh.color_attributes.get(attribute_name)

    if attribute is not None:
        _validate_color_attribute(attribute, attribute_name)
        attribute_type = attribute.data_type
        layer_collection = _bmesh_layer_collection(bm, attribute_type)
        layer = layer_collection.get(attribute_name)

        if layer is None:
            layer = layer_collection.new(attribute_name)

        return layer, attribute_type, False

    attribute_type = _clean_attribute_type(requested_type)

    try:
        mesh.color_attributes.new(
            name=attribute_name,
            type=attribute_type,
            domain='CORNER',
        )
    except RuntimeError:
        # Edit Mode can reject mesh data API edits in some contexts.
        # Creating the BMesh layer below produces the same Color Attribute.
        pass

    layer_collection = _bmesh_layer_collection(bm, attribute_type)
    layer = layer_collection.get(attribute_name)

    if layer is None:
        layer = layer_collection.new(attribute_name)

    return layer, attribute_type, True


def _get_bmesh_color_layer(mesh, bm, attribute_name):
    attribute = mesh.color_attributes.get(attribute_name)
    _validate_color_attribute(attribute, attribute_name)

    layer = _bmesh_layer_collection(bm, attribute.data_type).get(attribute_name)

    if layer is None:
        raise ValueError(f"Color Attribute がありません: {attribute_name}")

    return layer, attribute.data_type


def _ensure_object_color_attribute(mesh, attribute_name, requested_type):
    attribute = mesh.color_attributes.get(attribute_name)

    if attribute is None:
        attribute = mesh.color_attributes.new(
            name=attribute_name,
            type=_clean_attribute_type(requested_type),
            domain='CORNER',
        )
        return attribute, True

    _validate_color_attribute(attribute, attribute_name)

    return attribute, False


def _paint_selected_faces(obj, attribute_name, attribute_type, color):
    mesh = obj.data
    bm = bmesh.from_edit_mesh(mesh)
    bm.faces.ensure_lookup_table()
    selected_faces = [face for face in bm.faces if face.select]

    if not selected_faces:
        return 0, False, None

    color_layer, actual_type, created = _ensure_bmesh_color_attribute(
        mesh,
        bm,
        attribute_name,
        attribute_type,
    )
    bmesh_color = _scene_linear_to_bmesh_color(color, actual_type)

    for face in selected_faces:
        for loop in face.loops:
            loop[color_layer] = bmesh_color

    bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)

    return len(selected_faces), created, actual_type


def _paint_object_mode_meshes(objects, attribute_name, attribute_type, color):
    targets = [obj for obj in objects if len(obj.data.polygons) > 0]

    if not targets:
        return 0, 0, 0

    object_count = 0
    face_count = 0
    created_count = 0

    for obj in targets:
        try:
            attribute, created = _ensure_object_color_attribute(
                obj.data,
                attribute_name,
                attribute_type,
            )
        except ValueError as error:
            raise ValueError(f"{obj.name}: {error}") from error

        for polygon in obj.data.polygons:
            for loop_index in polygon.loop_indices:
                attribute.data[loop_index].color = color

        obj.data.update()
        object_count += 1
        face_count += len(obj.data.polygons)

        if created:
            created_count += 1

    return object_count, face_count, created_count


def _colors_match(color_a, color_b, attribute_type):
    tolerance = (
        BYTE_COLOR_MATCH_TOLERANCE
        if attribute_type == 'BYTE_COLOR'
        else FLOAT_COLOR_MATCH_TOLERANCE
    )

    return all(
        abs(float(color_a[index]) - float(color_b[index])) <= tolerance
        for index in range(4)
    )


def _select_faces_by_color(obj, attribute_name, color):
    mesh = obj.data
    bm = bmesh.from_edit_mesh(mesh)
    bm.faces.ensure_lookup_table()
    color_layer, attribute_type = _get_bmesh_color_layer(mesh, bm, attribute_name)

    selected_count = 0

    for face in bm.faces:
        face_matches = bool(face.loops) and all(
            _colors_match(
                _bmesh_color_to_scene_linear(loop[color_layer], attribute_type),
                color,
                attribute_type,
            )
            for loop in face.loops
        )
        face.select_set(face_matches)

        if face_matches:
            selected_count += 1

    bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)

    return selected_count


def _copy_bmesh_color_attribute(obj, source_name, target_name, target_type):
    mesh = obj.data
    bm = bmesh.from_edit_mesh(mesh)
    bm.faces.ensure_lookup_table()

    source_layer, source_type = _get_bmesh_color_layer(mesh, bm, source_name)
    target_layer, actual_target_type, created = _ensure_bmesh_color_attribute(
        mesh,
        bm,
        target_name,
        target_type,
    )

    for face in bm.faces:
        for loop in face.loops:
            scene_linear_color = _bmesh_color_to_scene_linear(
                loop[source_layer],
                source_type,
            )
            loop[target_layer] = _scene_linear_to_bmesh_color(
                scene_linear_color,
                actual_target_type,
            )

    bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)

    return len(bm.faces), source_type, actual_target_type, created


def _copy_object_color_attribute(obj, source_name, target_name, target_type):
    mesh = obj.data
    source = mesh.color_attributes.get(source_name)
    _validate_color_attribute(source, source_name)
    source_colors = [tuple(data.color) for data in source.data]
    target, created = _ensure_object_color_attribute(mesh, target_name, target_type)

    if len(source_colors) != len(target.data):
        raise ValueError("コピー元とコピー先のデータ数が一致しません。")

    for index, source_color in enumerate(source_colors):
        target.data[index].color = source_color

    mesh.update()

    return len(mesh.polygons), source.data_type, target.data_type, created


def _copy_object_mode_meshes(objects, source_name, target_name, target_type):
    targets = [obj for obj in objects if len(obj.data.polygons) > 0]

    if not targets:
        return 0, 0, 0

    for obj in targets:
        source = obj.data.color_attributes.get(source_name)
        _validate_color_attribute(source, source_name)

        target = obj.data.color_attributes.get(target_name)

        if target is not None:
            _validate_color_attribute(target, target_name)

            if len(source.data) != len(target.data):
                raise ValueError(f"{obj.name}: コピー元とコピー先のデータ数が一致しません。")

    object_count = 0
    face_count = 0
    created_count = 0

    for obj in targets:
        try:
            copied_faces, _source_type, _target_type, created = _copy_object_color_attribute(
                obj,
                source_name,
                target_name,
                target_type,
            )
        except ValueError as error:
            raise ValueError(f"{obj.name}: {error}") from error

        object_count += 1
        face_count += copied_faces

        if created:
            created_count += 1

    return object_count, face_count, created_count


def _repair_target_objects(context):
    if context.mode != 'OBJECT':
        return []

    return [
        obj for obj in context.selected_objects
        if obj is not None and obj.type == 'MESH' and obj.data is not None
    ]


def _color_distance(color_a, color_b):
    return max(
        abs(float(color_a[index]) - float(color_b[index]))
        for index in range(4)
    )


def _classify_color_for_auto_repair(color, reference_colors):
    repaired_rgb = Color(color[:3]).from_scene_linear_to_srgb()
    repaired_color = (*repaired_rgb, color[3])
    direct_distance = min(
        _color_distance(color, reference_color)
        for reference_color in reference_colors
    )
    repaired_distance = min(
        _color_distance(repaired_color, reference_color)
        for reference_color in reference_colors
    )
    direct_matches = direct_distance <= AUTO_REPAIR_MATCH_TOLERANCE
    repaired_matches = repaired_distance <= AUTO_REPAIR_MATCH_TOLERANCE

    if repaired_matches and not direct_matches:
        return 'REPAIR', repaired_color
    if direct_matches and not repaired_matches:
        return 'CORRECT', color
    if direct_matches and repaired_matches:
        return 'AMBIGUOUS', color

    return 'UNKNOWN', color


def _mesh_attribute_scene_linear_colors(mesh, attribute_name):
    attribute = mesh.color_attributes[attribute_name]
    return [tuple(data.color) for data in attribute.data]


def _auto_color_repair_preview(context, attribute_name, analyze_colors=False):
    objects = _repair_target_objects(context)
    meshes = _unique_meshes(objects)
    matching_meshes = [
        mesh for mesh in meshes
        if (
            getattr(mesh, "is_editable", True)
            and (attribute := mesh.color_attributes.get(attribute_name)) is not None
            and attribute.data_type == 'BYTE_COLOR'
            and attribute.domain == 'CORNER'
        )
    ]
    reference_colors = [
        tuple(item.color)
        for item in context.scene.vcmp_color_items
    ]
    result = {
        "object_count": len(objects),
        "unique_mesh_count": len(meshes),
        "matching_mesh_count": len(matching_meshes),
        "matching_meshes": matching_meshes,
        "reference_color_count": len(reference_colors),
        "repair_color_count": 0,
        "correct_color_count": 0,
        "ambiguous_color_count": 0,
        "unknown_color_count": 0,
    }

    if not analyze_colors or not reference_colors:
        return result

    status_keys = {
        'REPAIR': "repair_color_count",
        'CORRECT': "correct_color_count",
        'AMBIGUOUS': "ambiguous_color_count",
        'UNKNOWN': "unknown_color_count",
    }
    for mesh in matching_meshes:
        for color in _mesh_attribute_scene_linear_colors(mesh, attribute_name):
            status, _color = _classify_color_for_auto_repair(
                color,
                reference_colors,
            )
            result[status_keys[status]] += 1

    return result


def _auto_repair_legacy_edit_mode_colors(context, attribute_name):
    preview = _auto_color_repair_preview(
        context,
        attribute_name,
        analyze_colors=False,
    )

    if not preview["object_count"]:
        raise ValueError("選択中またはEdit Mode中のMeshオブジェクトがありません。")

    if not preview["matching_mesh_count"]:
        raise ValueError(f"修復対象のBYTE_COLOR / CORNER Attributeがありません: {attribute_name}")

    if not preview["reference_color_count"]:
        raise ValueError("Color Listが空です。自動判定に使う色を登録してください。")

    color_count = 0
    reference_colors = [
        tuple(item.color)
        for item in context.scene.vcmp_color_items
    ]

    for mesh in preview["matching_meshes"]:
        attribute = mesh.color_attributes[attribute_name]
        mesh_color_count = 0

        for data in attribute.data:
            color = tuple(data.color)
            status, repaired_color = _classify_color_for_auto_repair(
                color,
                reference_colors,
            )
            if status != 'REPAIR':
                continue

            data.color = repaired_color
            color_count += 1
            mesh_color_count += 1

        if mesh_color_count:
            mesh.update()

    return preview, color_count


def _remove_target_objects(context):
    if context.mode == 'EDIT_MESH':
        candidates = getattr(context, "objects_in_mode", ())
    else:
        candidates = context.selected_objects

    return [
        obj for obj in candidates
        if obj is not None and obj.type == 'MESH' and obj.data is not None
    ]


def _unique_meshes(objects):
    meshes = []
    seen = set()

    for obj in objects:
        mesh = obj.data
        key = mesh.as_pointer()

        if key in seen:
            continue

        seen.add(key)
        meshes.append(mesh)

    return meshes


def _active_remove_reference_object(context, target_objects):
    obj = context.view_layer.objects.active

    if obj is None or obj.type != 'MESH' or obj.data is None:
        return None

    if not any(candidate == obj for candidate in target_objects):
        return None

    return obj


def _resolve_remove_filter(context, target_objects):
    scene = context.scene
    match_mode = scene.vcmp_remove_match_mode

    if match_mode == 'ALL_REMOVABLE':
        return {"match_mode": match_mode}, None

    source = scene.vcmp_remove_filter_source
    if source == 'REFERENCE':
        reference_obj = _active_remove_reference_object(context, target_objects)

        if reference_obj is None:
            return None, "選択中のアクティブMeshがありません。"

        attribute_name = scene.vcmp_remove_reference_attribute_name.strip()
        if not attribute_name:
            return None, "参照するAttributeを選択してください。"

        attribute = reference_obj.data.attributes.get(attribute_name)
        if attribute is None:
            return None, f"{reference_obj.name} に参照Attributeがありません: {attribute_name}"

        return {
            "match_mode": match_mode,
            "name": attribute.name,
            "data_type": attribute.data_type,
            "domain": attribute.domain,
            "source": source,
        }, None

    return {
        "match_mode": match_mode,
        "name": scene.vcmp_remove_attribute_name.strip(),
        "data_type": scene.vcmp_remove_data_type,
        "domain": scene.vcmp_remove_domain,
        "source": source,
    }, None


def _attribute_matches_remove_filter(attribute, filter_spec):
    match_mode = filter_spec["match_mode"]

    if match_mode == 'ALL_REMOVABLE':
        return True
    if match_mode == 'SAME_NAME':
        return attribute.name == filter_spec["name"]
    if match_mode == 'DATA_TYPE':
        return attribute.data_type == filter_spec["data_type"]
    if match_mode == 'DOMAIN':
        return attribute.domain == filter_spec["domain"]
    if match_mode == 'TYPE_DOMAIN':
        return (
            attribute.data_type == filter_spec["data_type"]
            and attribute.domain == filter_spec["domain"]
        )

    return False


def _attribute_is_removable(attribute):
    return not attribute.is_internal and not attribute.is_required


def _remove_filter_description(filter_spec):
    match_mode = filter_spec["match_mode"]

    if match_mode == 'ALL_REMOVABLE':
        return "All Removable"
    if match_mode == 'SAME_NAME':
        return f"Name = {filter_spec['name']}"
    if match_mode == 'DATA_TYPE':
        return f"Data Type = {filter_spec['data_type']}"
    if match_mode == 'DOMAIN':
        return f"Domain = {filter_spec['domain']}"

    return f"Data Type = {filter_spec['data_type']}, Domain = {filter_spec['domain']}"


def _build_remove_preview(context):
    target_objects = _remove_target_objects(context)
    target_meshes = _unique_meshes(target_objects)
    filter_spec, error = _resolve_remove_filter(context, target_objects)

    selected_object_pointers = {obj.as_pointer() for obj in target_objects}
    unselected_shared_object_count = sum(
        1
        for mesh in target_meshes
        for obj in bpy.data.objects
        if obj.data == mesh and obj.as_pointer() not in selected_object_pointers
    )

    preview = {
        "objects": target_objects,
        "meshes": target_meshes,
        "filter_spec": filter_spec,
        "error": error,
        "selected_object_count": len(target_objects),
        "unique_mesh_count": len(target_meshes),
        "attribute_count": 0,
        "protected_attribute_count": 0,
        "non_editable_mesh_count": 0,
        "unselected_shared_object_count": unselected_shared_object_count,
    }

    if not target_objects:
        preview["error"] = "選択中またはEdit Mode中のMeshオブジェクトがありません。"
        return preview

    if error:
        return preview

    if filter_spec["match_mode"] == 'SAME_NAME' and not filter_spec["name"]:
        preview["error"] = "削除するAttribute名を入力してください。"
        return preview

    for mesh in target_meshes:
        if not getattr(mesh, "is_editable", True):
            preview["non_editable_mesh_count"] += 1
            continue

        for attribute in mesh.attributes:
            if not _attribute_matches_remove_filter(attribute, filter_spec):
                continue

            if _attribute_is_removable(attribute):
                preview["attribute_count"] += 1
            else:
                preview["protected_attribute_count"] += 1

    return preview


def _remove_matching_attributes(context):
    preview = _build_remove_preview(context)

    if preview["error"]:
        raise ValueError(preview["error"])

    if preview["attribute_count"] == 0:
        raise ValueError("削除条件に一致する削除可能なAttributeがありません。")

    deleted_attribute_count = 0
    processed_mesh_count = 0
    failed_attribute_count = 0

    for mesh in preview["meshes"]:
        if not getattr(mesh, "is_editable", True):
            continue

        attribute_names = [
            attribute.name
            for attribute in mesh.attributes
            if (
                _attribute_matches_remove_filter(attribute, preview["filter_spec"])
                and _attribute_is_removable(attribute)
            )
        ]
        mesh_deleted_count = 0

        for attribute_name in attribute_names:
            attribute = mesh.attributes.get(attribute_name)

            if attribute is None:
                continue

            try:
                mesh.attributes.remove(attribute)
            except RuntimeError:
                failed_attribute_count += 1
                continue

            deleted_attribute_count += 1
            mesh_deleted_count += 1

        if mesh_deleted_count:
            mesh.update()
            processed_mesh_count += 1

    return {
        "deleted_attribute_count": deleted_attribute_count,
        "processed_mesh_count": processed_mesh_count,
        "skipped_mesh_count": len(preview["meshes"]) - processed_mesh_count,
        "failed_attribute_count": failed_attribute_count,
    }


def _color_list_json_data(color_items):
    return [
        {
            "Name": item.name,
            "Color": [float(channel) for channel in item.color[:3]],
        }
        for item in color_items
    ]


def _write_color_list_json(filepath, color_items):
    with open(filepath, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(
            _color_list_json_data(color_items),
            handle,
            ensure_ascii=False,
            indent=2,
        )
        handle.write("\n")


class VCMP_ColorItem(PropertyGroup):
    name: StringProperty(
        name="Name",
        description="Houdiniなど外部DCCで識別する用途名",
        default="Material",
    )

    color: FloatVectorProperty(
        name="Color",
        description="選択面へ塗るRGBAカラー",
        subtype='COLOR',
        size=4,
        min=0.0,
        max=1.0,
        default=(1.0, 1.0, 1.0, 1.0),
    )


class VCMP_UL_color_items(UIList):
    bl_idname = "VCMP_UL_color_items"

    def draw_item(
        self,
        context,
        layout,
        data,
        item,
        icon,
        active_data,
        active_propname,
        index,
    ):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.prop(item, "name", text="", emboss=False)
            row.prop(item, "color", text="")
            op = row.operator(
                VCMP_OT_apply_color.bl_idname,
                text="",
                icon='BRUSH_DATA',
                emboss=True,
            )
            op.index = index
            op = row.operator(
                VCMP_OT_select_by_color.bl_idname,
                text="",
                icon='RESTRICT_SELECT_OFF',
                emboss=True,
            )
            op.index = index
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.prop(item, "color", text="")


class VCMP_OT_add_color(Operator):
    bl_idname = "vcmp.add_color"
    bl_label = "Add Color"
    bl_description = "新しい用途カラーを.blend内のリストに追加します"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        name = scene.vcmp_new_color_name.strip()

        if not name:
            self.report({'ERROR'}, "カラー項目名を入力してください。")
            return {'CANCELLED'}

        if any(item.name == name for item in scene.vcmp_color_items):
            self.report({'ERROR'}, f"同じ名前のカラーが既にあります: {name}")
            return {'CANCELLED'}

        item = scene.vcmp_color_items.add()
        item.name = name
        item.color = scene.vcmp_new_color
        scene.vcmp_active_index = len(scene.vcmp_color_items) - 1

        return {'FINISHED'}


class VCMP_OT_remove_color(Operator):
    bl_idname = "vcmp.remove_color"
    bl_label = "Remove Color"
    bl_description = "選択中のカラー項目を削除します"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        index = scene.vcmp_active_index

        if index < 0 or index >= len(scene.vcmp_color_items):
            self.report({'ERROR'}, "削除するカラーを選択してください。")
            return {'CANCELLED'}

        scene.vcmp_color_items.remove(index)
        scene.vcmp_active_index = min(index, len(scene.vcmp_color_items) - 1)

        return {'FINISHED'}


class VCMP_OT_move_color(Operator):
    bl_idname = "vcmp.move_color"
    bl_label = "Move Color"
    bl_description = "カラー項目の順序を変更します"
    bl_options = {'REGISTER', 'UNDO'}

    direction: StringProperty(default="UP")

    def execute(self, context):
        scene = context.scene
        index = scene.vcmp_active_index

        if index < 0 or index >= len(scene.vcmp_color_items):
            self.report({'ERROR'}, "移動するカラーを選択してください。")
            return {'CANCELLED'}

        new_index = index - 1 if self.direction == "UP" else index + 1

        if new_index < 0 or new_index >= len(scene.vcmp_color_items):
            return {'CANCELLED'}

        scene.vcmp_color_items.move(index, new_index)
        scene.vcmp_active_index = new_index

        return {'FINISHED'}


class VCMP_OT_export_color_list_json(Operator, ExportHelper):
    bl_idname = "vcmp.export_color_list_json"
    bl_label = "Export JSON"
    bl_description = "Color ListのNameと線形RGBをJSONファイルへ書き出します"

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={'HIDDEN'})

    def invoke(self, context, event):
        if not self.filepath:
            self.filepath = "vertex_color_material_colors.json"
        return super().invoke(context, event)

    def execute(self, context):
        try:
            _write_color_list_json(
                self.filepath,
                context.scene.vcmp_color_items,
            )
        except (OSError, TypeError, ValueError) as error:
            self.report({'ERROR'}, f"JSONを書き出せませんでした: {error}")
            return {'CANCELLED'}

        self.report(
            {'INFO'},
            f"{len(context.scene.vcmp_color_items)}色をJSONへ書き出しました。",
        )
        return {'FINISHED'}


class VCMP_OT_apply_color(Operator):
    bl_idname = "vcmp.apply_color"
    bl_label = "Apply Color"
    bl_description = "Edit Modeでは選択面、Object Modeでは選択中Mesh全体へカラーを塗ります"
    bl_options = {'REGISTER', 'UNDO'}

    index: IntProperty(default=-1)

    def execute(self, context):
        item, error = _get_color_item(context, self.index)

        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}

        attribute_name = _clean_attribute_name(context.scene.vcmp_attribute_name)
        attribute_type = _clean_attribute_type(context.scene.vcmp_attribute_type)

        if context.mode == 'OBJECT':
            objects = _object_mode_mesh_targets(context)

            if not objects:
                self.report({'ERROR'}, "選択中のメッシュオブジェクトがありません。")
                return {'CANCELLED'}

            try:
                object_count, face_count, created_count = _paint_object_mode_meshes(
                    objects=objects,
                    attribute_name=attribute_name,
                    attribute_type=attribute_type,
                    color=item.color,
                )
            except ValueError as error:
                self.report({'ERROR'}, str(error))
                return {'CANCELLED'}

            if face_count == 0:
                self.report({'ERROR'}, "塗れる面を持つメッシュオブジェクトがありません。")
                return {'CANCELLED'}

            self.report(
                {'INFO'},
                (
                    f"{object_count}個のMesh / {face_count}面に '{item.name}' を適用しました。"
                    f" Attribute: {attribute_name}, 作成: {created_count}"
                ),
            )

            return {'FINISHED'}

        obj, error = _active_mesh_edit_object(context)

        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}

        try:
            face_count, created, actual_type = _paint_selected_faces(
                obj=obj,
                attribute_name=attribute_name,
                attribute_type=attribute_type,
                color=item.color,
            )
        except ValueError as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}

        if face_count == 0:
            self.report({'ERROR'}, "選択面がありません。")
            return {'CANCELLED'}

        suffix = " 作成済み" if created else ""
        self.report(
            {'INFO'},
            f"{face_count}面に '{item.name}' を適用しました。Attribute: {attribute_name} ({actual_type}){suffix}",
        )

        return {'FINISHED'}


class VCMP_OT_select_by_color(Operator):
    bl_idname = "vcmp.select_by_color"
    bl_label = "Select Painted Faces"
    bl_description = "Edit Modeで、このカラーが塗られている面を選択します"
    bl_options = {'REGISTER', 'UNDO'}

    index: IntProperty(default=-1)

    def execute(self, context):
        obj, error = _active_mesh_edit_object(context)

        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}

        item, error = _get_color_item(context, self.index)

        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}

        attribute_name = _clean_attribute_name(context.scene.vcmp_attribute_name)

        try:
            selected_count = _select_faces_by_color(
                obj=obj,
                attribute_name=attribute_name,
                color=item.color,
            )
        except ValueError as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}

        context.tool_settings.mesh_select_mode = (False, False, True)

        if selected_count == 0:
            self.report({'WARNING'}, f"'{item.name}' の色で塗られた面は見つかりませんでした。")
            return {'FINISHED'}

        self.report(
            {'INFO'},
            f"'{item.name}' の色で塗られた {selected_count}面を選択しました。",
        )

        return {'FINISHED'}


class VCMP_OT_copy_attribute(Operator):
    bl_idname = "vcmp.copy_attribute"
    bl_label = "Copy Attribute"
    bl_description = "現在のPaint Attribute全体を指定したColor Attributeへコピーします"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        source_name = _clean_attribute_name(context.scene.vcmp_attribute_name)
        target_name = _clean_copy_target_name(context.scene.vcmp_copy_target_name)
        target_type = _clean_attribute_type(context.scene.vcmp_copy_target_type)

        if context.mode == 'OBJECT':
            objects = _object_mode_mesh_targets(context)

            if not objects:
                self.report({'ERROR'}, "選択中のメッシュオブジェクトがありません。")
                return {'CANCELLED'}

            try:
                object_count, face_count, created_count = _copy_object_mode_meshes(
                    objects=objects,
                    source_name=source_name,
                    target_name=target_name,
                    target_type=target_type,
                )
            except ValueError as error:
                self.report({'ERROR'}, str(error))
                return {'CANCELLED'}

            if face_count == 0:
                self.report({'ERROR'}, "コピーできる面を持つメッシュオブジェクトがありません。")
                return {'CANCELLED'}

            self.report(
                {'INFO'},
                (
                    f"{object_count}個のMesh / {face_count}面分を '{source_name}' から "
                    f"'{target_name}' へコピーしました。作成: {created_count}"
                ),
            )

            return {'FINISHED'}

        obj, error = _active_mesh_edit_object(context)

        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}

        try:
            face_count, source_type, actual_target_type, created = _copy_bmesh_color_attribute(
                obj=obj,
                source_name=source_name,
                target_name=target_name,
                target_type=target_type,
            )
        except ValueError as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}

        suffix = " 作成済み" if created else ""
        self.report(
            {'INFO'},
            (
                f"{face_count}面分を '{source_name}' ({source_type}) から "
                f"'{target_name}' ({actual_target_type}) へコピーしました。{suffix}"
            ),
        )

        return {'FINISHED'}


class VCMP_OT_remove_attribute(Operator):
    bl_idname = "vcmp.remove_attribute"
    bl_label = "Remove Matching Attributes"
    bl_description = "選択中のMeshオブジェクトから条件に一致するAttributeを一括削除します"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        preview = _build_remove_preview(context)

        if preview["error"]:
            self.report({'ERROR'}, preview["error"])
            return {'CANCELLED'}

        if preview["attribute_count"] == 0:
            self.report({'ERROR'}, "削除条件に一致する削除可能なAttributeがありません。")
            return {'CANCELLED'}

        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        layout = self.layout
        preview = _build_remove_preview(context)

        layout.label(text="一致するAttributeを一括削除します。", icon='ERROR')
        layout.label(
            text=(
                f"Selected Meshes: {preview['selected_object_count']} / "
                f"Unique Meshes: {preview['unique_mesh_count']}"
            ),
            icon='MESH_DATA',
        )
        layout.label(
            text=f"Attributes: {preview['attribute_count']}",
            icon='GROUP_VCOL',
        )
        if preview["filter_spec"] is not None:
            layout.label(
                text=_remove_filter_description(preview["filter_spec"]),
                icon='FILTER',
            )
        if preview["non_editable_mesh_count"]:
            layout.label(
                text=f"Non-editable Meshes: {preview['non_editable_mesh_count']}",
                icon='LOCKED',
            )
        if preview["protected_attribute_count"]:
            layout.label(
                text=f"Protected Attributes: {preview['protected_attribute_count']}",
                icon='LOCKED',
            )
        if preview["unselected_shared_object_count"]:
            layout.label(
                text=(
                    "共有Meshを使う未選択Object "
                    f"{preview['unselected_shared_object_count']}個にも影響します。"
                ),
                icon='LINKED',
            )

    def execute(self, context):
        try:
            result = _remove_matching_attributes(context)
        except ValueError as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}

        report_type = {'WARNING'} if result["failed_attribute_count"] else {'INFO'}
        self.report(
            report_type,
            (
                f"{result['deleted_attribute_count']} Attribute / "
                f"{result['processed_mesh_count']} Meshから削除しました。"
                f" スキップMesh: {result['skipped_mesh_count']} / "
                f"失敗Attribute: {result['failed_attribute_count']}"
            ),
        )

        return {'FINISHED'}


class VCMP_OT_repair_legacy_edit_colors(Operator):
    bl_idname = "vcmp.repair_legacy_edit_colors"
    bl_label = "Auto Fix Selected Colors"
    bl_description = "Color Listを基準に旧Edit Modeの暗いBYTE_COLORだけを自動判定して補正します"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        attribute_name = _clean_attribute_name(context.scene.vcmp_attribute_name)
        preview = _auto_color_repair_preview(
            context,
            attribute_name,
            analyze_colors=True,
        )

        if context.mode != 'OBJECT':
            self.report({'ERROR'}, "Object Modeで実行してください。")
            return {'CANCELLED'}

        if not preview["object_count"]:
            self.report({'ERROR'}, "選択中またはEdit Mode中のMeshオブジェクトがありません。")
            return {'CANCELLED'}

        if not preview["matching_mesh_count"]:
            self.report(
                {'ERROR'},
                f"修復対象のBYTE_COLOR / CORNER Attributeがありません: {attribute_name}",
            )
            return {'CANCELLED'}

        if not preview["reference_color_count"]:
            self.report({'ERROR'}, "Color Listが空です。自動判定に使う色を登録してください。")
            return {'CANCELLED'}

        return context.window_manager.invoke_props_dialog(self, width=430)

    def draw(self, context):
        layout = self.layout
        attribute_name = _clean_attribute_name(context.scene.vcmp_attribute_name)
        preview = _auto_color_repair_preview(
            context,
            attribute_name,
            analyze_colors=True,
        )

        layout.label(text="Color Listを基準に色を自動判定します。", icon='COLOR')
        layout.label(text="Object Mode専用", icon='OBJECT_DATA')
        layout.label(text=f"Attribute: {attribute_name}", icon='GROUP_VCOL')
        layout.label(
            text=(
                f"Selected Meshes: {preview['object_count']} / "
                f"Target Meshes: {preview['matching_mesh_count']}"
            ),
            icon='MESH_DATA',
        )
        layout.label(
            text=f"Repair: {preview['repair_color_count']} / Correct: {preview['correct_color_count']}",
            icon='FILE_REFRESH',
        )
        layout.label(
            text=(
                f"Skipped Ambiguous: {preview['ambiguous_color_count']} / "
                f"Unknown: {preview['unknown_color_count']}"
            ),
            icon='INFO',
        )

    def execute(self, context):
        attribute_name = _clean_attribute_name(context.scene.vcmp_attribute_name)

        try:
            preview, color_count = _auto_repair_legacy_edit_mode_colors(
                context,
                attribute_name,
            )
        except ValueError as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}

        self.report(
            {'INFO'},
            (
                f"{preview['matching_mesh_count']} Meshを判定し、"
                f"{color_count} ColorをObject Mode基準へ補正しました。"
            ),
        )
        return {'FINISHED'}


class VCMP_OT_ensure_attribute(Operator):
    bl_idname = "vcmp.ensure_attribute"
    bl_label = "Ensure Color Attribute"
    bl_description = "指定名のBYTE_COLOR/FLOAT_COLOR CORNER Attributeを確認または作成します"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object

        if obj is None or obj.type != 'MESH':
            self.report({'ERROR'}, "メッシュオブジェクトをアクティブにしてください。")
            return {'CANCELLED'}

        attribute_name = _clean_attribute_name(context.scene.vcmp_attribute_name)
        attribute_type = _clean_attribute_type(context.scene.vcmp_attribute_type)
        mesh = obj.data

        try:
            if context.mode == 'EDIT_MESH':
                bm = bmesh.from_edit_mesh(mesh)
                _ensure_bmesh_color_attribute(mesh, bm, attribute_name, attribute_type)
                bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
            else:
                _ensure_object_color_attribute(mesh, attribute_name, attribute_type)
        except ValueError as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}

        self.report({'INFO'}, f"Color Attribute を確認しました: {attribute_name}")

        return {'FINISHED'}


class VCMP_PT_panel(Panel):
    bl_label = "Material Vertex Color Painter"
    bl_idname = "VCMP_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "VC Painter"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        obj = context.object

        box = layout.box()
        box.label(text="Paint Attribute", icon='GROUP_VCOL')
        box.prop(scene, "vcmp_attribute_name", text="Name")
        box.prop(scene, "vcmp_attribute_type", text="New Type")
        box.operator(VCMP_OT_ensure_attribute.bl_idname, icon='ADD')

        box = layout.box()
        box.label(text="Color List", icon='COLOR')

        row = box.row()
        row.template_list(
            VCMP_UL_color_items.bl_idname,
            "",
            scene,
            "vcmp_color_items",
            scene,
            "vcmp_active_index",
            rows=5,
        )

        col = row.column(align=True)
        col.operator(VCMP_OT_remove_color.bl_idname, text="", icon='REMOVE')

        op = col.operator(VCMP_OT_move_color.bl_idname, text="", icon='TRIA_UP')
        op.direction = "UP"

        op = col.operator(VCMP_OT_move_color.bl_idname, text="", icon='TRIA_DOWN')
        op.direction = "DOWN"

        apply_row = box.row()
        apply_row.operator(VCMP_OT_apply_color.bl_idname, icon='BRUSH_DATA')
        apply_row.operator(VCMP_OT_select_by_color.bl_idname, icon='RESTRICT_SELECT_OFF')
        box.operator(VCMP_OT_export_color_list_json.bl_idname, icon='EXPORT')

        box = layout.box()
        box.label(text="Add New Color", icon='ADD')
        box.prop(scene, "vcmp_new_color_name", text="Name")
        box.prop(scene, "vcmp_new_color", text="Color")
        box.operator(VCMP_OT_add_color.bl_idname, icon='ADD')

        box = layout.box()
        box.label(text="Attribute Helper", icon='MODIFIER')
        box.label(text="Copy", icon='DUPLICATE')
        box.label(text=f"Source: { _clean_attribute_name(scene.vcmp_attribute_name) }", icon='GROUP_VCOL')
        box.prop(scene, "vcmp_copy_target_name", text="Destination")
        box.prop(scene, "vcmp_copy_target_type", text="New Type")
        box.operator(VCMP_OT_copy_attribute.bl_idname, icon='DUPLICATE')

        box.separator()
        box.label(text="Automatic Color Fix", icon='COLOR')
        repair_preview = _auto_color_repair_preview(
            context,
            _clean_attribute_name(scene.vcmp_attribute_name),
        )
        repair_row = box.row()
        repair_row.enabled = (
            context.mode == 'OBJECT'
            and
            repair_preview["matching_mesh_count"] > 0
            and repair_preview["reference_color_count"] > 0
        )
        repair_row.operator(VCMP_OT_repair_legacy_edit_colors.bl_idname, icon='FILE_REFRESH')

        box.separator()
        box.label(text="Remove", icon='TRASH')
        remove_preview = _build_remove_preview(context)
        box.label(
            text=(
                f"Selected Meshes: {remove_preview['selected_object_count']} / "
                f"Unique Meshes: {remove_preview['unique_mesh_count']}"
            ),
            icon='MESH_DATA',
        )
        box.prop(scene, "vcmp_remove_match_mode", text="Match Mode")

        match_mode = scene.vcmp_remove_match_mode
        active_obj = _active_remove_reference_object(context, remove_preview["objects"])

        if match_mode != 'ALL_REMOVABLE':
            box.prop(scene, "vcmp_remove_filter_source", text="Filter Source")

            if scene.vcmp_remove_filter_source == 'REFERENCE':
                if active_obj is not None:
                    box.prop_search(
                        scene,
                        "vcmp_remove_reference_attribute_name",
                        active_obj.data,
                        "attributes",
                        text="Reference",
                    )
                else:
                    row = box.row()
                    row.enabled = False
                    row.prop(scene, "vcmp_remove_reference_attribute_name", text="Reference")
            elif match_mode == 'SAME_NAME':
                if active_obj is not None:
                    box.prop_search(
                        scene,
                        "vcmp_remove_attribute_name",
                        active_obj.data,
                        "attributes",
                        text="Name",
                    )
                else:
                    box.prop(scene, "vcmp_remove_attribute_name", text="Name")
            else:
                if match_mode in {'DATA_TYPE', 'TYPE_DOMAIN'}:
                    box.prop(scene, "vcmp_remove_data_type", text="Data Type")
                if match_mode in {'DOMAIN', 'TYPE_DOMAIN'}:
                    box.prop(scene, "vcmp_remove_domain", text="Domain")

        if remove_preview["filter_spec"] is not None:
            box.label(
                text=_remove_filter_description(remove_preview["filter_spec"]),
                icon='FILTER',
            )

        remove_row = box.row()
        remove_row.enabled = bool(
            not remove_preview["error"] and remove_preview["attribute_count"] > 0
        )
        remove_row.operator(VCMP_OT_remove_attribute.bl_idname, icon='TRASH')

        if remove_preview["error"]:
            box.label(text=remove_preview["error"], icon='INFO')
        else:
            box.label(
                text=f"Matched Attributes: {remove_preview['attribute_count']}",
                icon='GROUP_VCOL',
            )
        if remove_preview["non_editable_mesh_count"]:
            box.label(
                text=f"編集不可Mesh: {remove_preview['non_editable_mesh_count']}",
                icon='LOCKED',
            )
        if remove_preview["unselected_shared_object_count"]:
            box.label(
                text=(
                    "共有Meshを使う未選択Object "
                    f"{remove_preview['unselected_shared_object_count']}個にも影響します。"
                ),
                icon='LINKED',
            )

        layout.separator()

        if obj is None or obj.type != 'MESH':
            layout.label(text="メッシュを選択してください。", icon='INFO')
        elif context.mode != 'EDIT_MESH':
            mesh_count = len(_object_mode_mesh_targets(context))
            layout.label(text=f"Object Mode: 選択Mesh {mesh_count}個へ全体適用", icon='INFO')
        else:
            layout.label(text=f"Active Mesh: {obj.name}", icon='MESH_DATA')


classes = (
    VCMP_ColorItem,
    VCMP_UL_color_items,
    VCMP_OT_add_color,
    VCMP_OT_remove_color,
    VCMP_OT_move_color,
    VCMP_OT_export_color_list_json,
    VCMP_OT_apply_color,
    VCMP_OT_select_by_color,
    VCMP_OT_copy_attribute,
    VCMP_OT_remove_attribute,
    VCMP_OT_repair_legacy_edit_colors,
    VCMP_OT_ensure_attribute,
    VCMP_PT_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.vcmp_attribute_name = StringProperty(
        name="Color Attribute Name",
        description="選択面へ塗るColor Attribute名",
        default=DEFAULT_ATTRIBUTE_NAME,
    )
    bpy.types.Scene.vcmp_attribute_type = EnumProperty(
        name="Color Attribute Type",
        description="新規作成するPaint Attributeの型。既存Attributeがある場合は既存の型を使います",
        items=COLOR_TYPE_ITEMS,
        default=DEFAULT_ATTRIBUTE_TYPE,
    )
    bpy.types.Scene.vcmp_color_items = CollectionProperty(type=VCMP_ColorItem)
    bpy.types.Scene.vcmp_active_index = IntProperty(default=-1)
    bpy.types.Scene.vcmp_new_color_name = StringProperty(
        name="New Color Name",
        default=DEFAULT_NEW_COLOR_NAME,
    )
    bpy.types.Scene.vcmp_new_color = FloatVectorProperty(
        name="New Color",
        subtype='COLOR',
        size=4,
        min=0.0,
        max=1.0,
        default=DEFAULT_NEW_COLOR,
    )
    bpy.types.Scene.vcmp_copy_target_name = StringProperty(
        name="Copy Target Attribute",
        description="Paint Attributeのコピー先Color Attribute名",
        default=DEFAULT_COPY_TARGET_NAME,
    )
    bpy.types.Scene.vcmp_copy_target_type = EnumProperty(
        name="Copy Target Type",
        description="コピー先を新規作成する場合の型。既存Attributeがある場合は既存の型を使います",
        items=COLOR_TYPE_ITEMS,
        default=DEFAULT_ATTRIBUTE_TYPE,
    )
    bpy.types.Scene.vcmp_remove_match_mode = EnumProperty(
        name="Remove Match Mode",
        description="削除するAttributeの一致条件",
        items=REMOVE_MATCH_MODE_ITEMS,
        default='SAME_NAME',
    )
    bpy.types.Scene.vcmp_remove_filter_source = EnumProperty(
        name="Remove Filter Source",
        description="削除条件を直接指定するか参照Attributeから取得するか",
        items=REMOVE_FILTER_SOURCE_ITEMS,
        default='DIRECT',
    )
    bpy.types.Scene.vcmp_remove_attribute_name = StringProperty(
        name="Remove Attribute",
        description="選択中Meshから完全一致で削除するAttribute名",
        default=DEFAULT_ATTRIBUTE_NAME,
    )
    bpy.types.Scene.vcmp_remove_reference_attribute_name = StringProperty(
        name="Reference Attribute",
        description="削除条件の名前、データ型、ドメインを取得するアクティブMeshのAttribute",
        default=DEFAULT_ATTRIBUTE_NAME,
    )
    bpy.types.Scene.vcmp_remove_data_type = EnumProperty(
        name="Remove Data Type",
        description="削除対象にするAttributeのデータ型",
        items=REMOVE_DATA_TYPE_ITEMS,
        default=DEFAULT_ATTRIBUTE_TYPE,
    )
    bpy.types.Scene.vcmp_remove_domain = EnumProperty(
        name="Remove Domain",
        description="削除対象にするAttributeのドメイン",
        items=REMOVE_DOMAIN_ITEMS,
        default='CORNER',
    )


def unregister():
    for prop_name in (
        "vcmp_remove_domain",
        "vcmp_remove_data_type",
        "vcmp_remove_reference_attribute_name",
        "vcmp_remove_attribute_name",
        "vcmp_remove_filter_source",
        "vcmp_remove_match_mode",
        "vcmp_remove_target_object",
        "vcmp_copy_target_type",
        "vcmp_copy_target_name",
        "vcmp_new_color",
        "vcmp_new_color_name",
        "vcmp_active_index",
        "vcmp_color_items",
        "vcmp_attribute_type",
        "vcmp_attribute_name",
    ):
        if hasattr(bpy.types.Scene, prop_name):
            delattr(bpy.types.Scene, prop_name)

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
