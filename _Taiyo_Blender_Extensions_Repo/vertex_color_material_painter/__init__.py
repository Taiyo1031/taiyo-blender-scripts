bl_info = {
    "name": "Vertex Color Material Painter",
    "author": "Taiyo",
    "version": (1, 0, 1),
    "blender": (4, 5, 9),
    "location": "View3D > Sidebar > VC Painter",
    "description": "Paint selected edit-mode faces with scene-saved material ID colors",
    "category": "Mesh",
}

import bmesh
import bpy
from bpy.props import (
    CollectionProperty,
    EnumProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import Operator, Panel, PropertyGroup, UIList


DEFAULT_ATTRIBUTE_NAME = "mat_color"
DEFAULT_COPY_TARGET_NAME = "mat_color_copy"
DEFAULT_ATTRIBUTE_TYPE = "BYTE_COLOR"
DEFAULT_NEW_COLOR_NAME = "Wood"
DEFAULT_NEW_COLOR = (0.45, 0.24, 0.09, 1.0)
FLOAT_COLOR_MATCH_TOLERANCE = 0.0001
BYTE_COLOR_MATCH_TOLERANCE = (1.0 / 255.0) + 0.0001
SUPPORTED_COLOR_TYPES = {'BYTE_COLOR', 'FLOAT_COLOR'}
COLOR_TYPE_ITEMS = (
    ('BYTE_COLOR', "Byte Color", "軽量な8bit Color Attributeを作成します"),
    ('FLOAT_COLOR', "Float Color", "高精度なFloat Color Attributeを作成します"),
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


def _mesh_object_poll(_self, obj):
    return obj is not None and obj.type == 'MESH' and obj.data is not None


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

    for face in selected_faces:
        for loop in face.loops:
            loop[color_layer] = color

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
            _colors_match(loop[color_layer], color, attribute_type)
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
            loop[target_layer] = tuple(loop[source_layer])

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


def _remove_mesh_attribute(obj, attribute_name):
    mesh = obj.data
    attribute = mesh.attributes.get(attribute_name)

    if attribute is None:
        raise ValueError(f"Attribute がありません: {attribute_name}")

    if not getattr(mesh, "is_editable", True):
        raise ValueError(f"Meshデータを編集できません: {mesh.name}")

    try:
        mesh.attributes.remove(attribute)
    except RuntimeError as error:
        raise ValueError(f"Attributeを削除できません: {attribute_name}") from error

    mesh.update()

    return sum(1 for candidate in bpy.data.objects if candidate.data == mesh)


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
    bl_label = "Remove Attribute"
    bl_description = "指定したMeshオブジェクトから指定Attribute全体を削除します"
    bl_options = {'REGISTER', 'UNDO'}

    @staticmethod
    def _target_and_attribute(context):
        scene = context.scene
        obj = scene.vcmp_remove_target_object
        attribute_name = scene.vcmp_remove_attribute_name.strip()

        if obj is None or obj.type != 'MESH' or obj.data is None:
            return None, "", "削除対象のMeshオブジェクトを指定してください。"

        if not attribute_name:
            return None, "", "削除するAttributeを指定してください。"

        if obj.data.attributes.get(attribute_name) is None:
            return None, "", f"{obj.name} に Attribute がありません: {attribute_name}"

        return obj, attribute_name, None

    def invoke(self, context, event):
        _obj, _attribute_name, error = self._target_and_attribute(context)

        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}

        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        layout = self.layout
        obj, attribute_name, _error = self._target_and_attribute(context)

        if obj is None:
            return

        layout.label(text="このAttributeを削除します。", icon='ERROR')
        layout.label(text=f"Object: {obj.name}", icon='OBJECT_DATA')
        layout.label(text=f"Attribute: {attribute_name}", icon='GROUP_VCOL')

        object_user_count = sum(
            1 for candidate in bpy.data.objects
            if candidate.data == obj.data
        )
        if object_user_count > 1:
            layout.label(
                text=f"共有Meshのため {object_user_count}個のオブジェクトへ影響します。",
                icon='LINKED',
            )

    def execute(self, context):
        obj, attribute_name, error = self._target_and_attribute(context)

        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}

        try:
            object_user_count = _remove_mesh_attribute(obj, attribute_name)
        except ValueError as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}

        suffix = (
            f" 共有Meshを使用する{object_user_count}個のオブジェクトへ反映されます。"
            if object_user_count > 1
            else ""
        )
        self.report(
            {'INFO'},
            f"{obj.name} から Attribute '{attribute_name}' を削除しました。{suffix}",
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
        box.label(text="Remove", icon='TRASH')
        box.prop(scene, "vcmp_remove_target_object", text="Object")

        remove_target = scene.vcmp_remove_target_object
        if remove_target is not None and remove_target.type == 'MESH' and remove_target.data is not None:
            box.prop_search(
                scene,
                "vcmp_remove_attribute_name",
                remove_target.data,
                "attributes",
                text="Attribute",
            )
        else:
            row = box.row()
            row.enabled = False
            row.prop(scene, "vcmp_remove_attribute_name", text="Attribute")

        remove_row = box.row()
        remove_row.enabled = bool(
            remove_target is not None
            and remove_target.type == 'MESH'
            and remove_target.data is not None
            and remove_target.data.attributes.get(scene.vcmp_remove_attribute_name.strip()) is not None
        )
        remove_row.operator(VCMP_OT_remove_attribute.bl_idname, icon='TRASH')

        if (
            remove_target is not None
            and remove_target.type == 'MESH'
            and remove_target.data is not None
            and sum(1 for candidate in bpy.data.objects if candidate.data == remove_target.data) > 1
        ):
            box.label(text="共有Meshを使う全オブジェクトへ影響します。", icon='LINKED')

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
    VCMP_OT_apply_color,
    VCMP_OT_select_by_color,
    VCMP_OT_copy_attribute,
    VCMP_OT_remove_attribute,
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
    bpy.types.Scene.vcmp_remove_target_object = PointerProperty(
        name="Remove Target Object",
        description="Attributeを削除するMeshオブジェクト",
        type=bpy.types.Object,
        poll=_mesh_object_poll,
    )
    bpy.types.Scene.vcmp_remove_attribute_name = StringProperty(
        name="Remove Attribute",
        description="指定Meshオブジェクトから削除するAttribute名",
        default=DEFAULT_ATTRIBUTE_NAME,
    )


def unregister():
    for prop_name in (
        "vcmp_remove_attribute_name",
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
