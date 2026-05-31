bl_info = {
    "name": "Vertex Color Material Painter",
    "author": "Taiyo",
    "version": (1, 0, 0),
    "blender": (4, 5, 9),
    "location": "View3D > Sidebar > VC Painter",
    "description": "Paint selected edit-mode faces with scene-saved material ID colors",
    "category": "Mesh",
}

import bmesh
import bpy
from bpy.props import CollectionProperty, FloatVectorProperty, IntProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup, UIList


DEFAULT_ATTRIBUTE_NAME = "mat_color"
DEFAULT_NEW_COLOR_NAME = "Wood"
DEFAULT_NEW_COLOR = (0.45, 0.24, 0.09, 1.0)
COLOR_MATCH_TOLERANCE = 0.0001


def _active_mesh_edit_object(context):
    obj = context.object

    if obj is None or obj.type != 'MESH':
        return None, "メッシュオブジェクトをアクティブにしてください。"

    if context.mode != 'EDIT_MESH':
        return None, "Edit Mode で実行してください。"

    return obj, None


def _clean_attribute_name(name):
    return name.strip() or DEFAULT_ATTRIBUTE_NAME


def _get_color_item(context, index):
    items = context.scene.vcmp_color_items

    if not items:
        return None, "カラーリストが空です。"

    if index < 0:
        index = context.scene.vcmp_active_index

    if index < 0 or index >= len(items):
        return None, "カラーを選択してください。"

    return items[index], None


def _ensure_float_corner_attribute(mesh, bm, attribute_name):
    layer = bm.loops.layers.float_color.get(attribute_name)

    if layer is not None:
        return layer, False

    attribute = mesh.color_attributes.get(attribute_name)

    if attribute is None:
        try:
            mesh.color_attributes.new(
                name=attribute_name,
                type='FLOAT_COLOR',
                domain='CORNER',
            )
        except RuntimeError:
            # Edit Mode can reject mesh data API edits in some contexts.
            # Creating the BMesh float color layer below produces the same attribute.
            pass
    elif attribute.domain != 'CORNER' or attribute.data_type != 'FLOAT_COLOR':
        raise ValueError(
            f"'{attribute_name}' は FLOAT_COLOR / CORNER ではありません。"
        )

    layer = bm.loops.layers.float_color.get(attribute_name)

    if layer is None:
        layer = bm.loops.layers.float_color.new(attribute_name)

    return layer, True


def _ensure_object_color_attribute(mesh, attribute_name):
    attribute = mesh.color_attributes.get(attribute_name)

    if attribute is None:
        attribute = mesh.color_attributes.new(
            name=attribute_name,
            type='FLOAT_COLOR',
            domain='CORNER',
        )
        return attribute, True

    if attribute.domain != 'CORNER' or attribute.data_type != 'FLOAT_COLOR':
        raise ValueError(
            f"'{attribute_name}' は FLOAT_COLOR / CORNER ではありません。"
        )

    return attribute, False


def _paint_selected_faces(obj, attribute_name, color):
    mesh = obj.data
    bm = bmesh.from_edit_mesh(mesh)
    bm.faces.ensure_lookup_table()
    selected_faces = [face for face in bm.faces if face.select]

    if not selected_faces:
        return 0, False

    color_layer, created = _ensure_float_corner_attribute(mesh, bm, attribute_name)

    for face in selected_faces:
        for loop in face.loops:
            loop[color_layer] = color

    bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)

    return len(selected_faces), created


def _colors_match(color_a, color_b):
    return all(
        abs(float(color_a[index]) - float(color_b[index])) <= COLOR_MATCH_TOLERANCE
        for index in range(4)
    )


def _select_faces_by_color(obj, attribute_name, color):
    mesh = obj.data
    attribute = mesh.color_attributes.get(attribute_name)

    if attribute is None:
        raise ValueError(f"Color Attribute がありません: {attribute_name}")

    if attribute.domain != 'CORNER' or attribute.data_type != 'FLOAT_COLOR':
        raise ValueError(
            f"'{attribute_name}' は FLOAT_COLOR / CORNER ではありません。"
        )

    bm = bmesh.from_edit_mesh(mesh)
    bm.faces.ensure_lookup_table()
    color_layer = bm.loops.layers.float_color.get(attribute_name)

    if color_layer is None:
        raise ValueError(f"Color Attribute がありません: {attribute_name}")

    selected_count = 0

    for face in bm.faces:
        face_matches = bool(face.loops) and all(
            _colors_match(loop[color_layer], color)
            for loop in face.loops
        )
        face.select_set(face_matches)

        if face_matches:
            selected_count += 1

    bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)

    return selected_count


def _object_mode_mesh_targets(context):
    selected_objects = getattr(context, "selected_editable_objects", None)

    if selected_objects is None:
        selected_objects = context.selected_objects

    return [
        obj for obj in selected_objects
        if obj is not None and obj.type == 'MESH' and obj.data is not None
    ]


def _paint_object_mode_meshes(objects, attribute_name, color):
    targets = [obj for obj in objects if len(obj.data.polygons) > 0]

    if not targets:
        return 0, 0, 0

    for obj in targets:
        attribute = obj.data.color_attributes.get(attribute_name)

        if attribute is not None:
            if attribute.domain != 'CORNER' or attribute.data_type != 'FLOAT_COLOR':
                raise ValueError(
                    f"{obj.name}: '{attribute_name}' は FLOAT_COLOR / CORNER ではありません。"
                )

    object_count = 0
    face_count = 0
    created_count = 0

    for obj in targets:
        mesh = obj.data
        attribute, created = _ensure_object_color_attribute(mesh, attribute_name)

        for polygon in mesh.polygons:
            for loop_index in polygon.loop_indices:
                attribute.data[loop_index].color = color

        mesh.update()
        object_count += 1
        face_count += len(mesh.polygons)

        if created:
            created_count += 1

    return object_count, face_count, created_count


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

        if context.mode == 'OBJECT':
            objects = _object_mode_mesh_targets(context)

            if not objects:
                self.report({'ERROR'}, "選択中のメッシュオブジェクトがありません。")
                return {'CANCELLED'}

            try:
                object_count, face_count, created_count = _paint_object_mode_meshes(
                    objects=objects,
                    attribute_name=attribute_name,
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
            face_count, created = _paint_selected_faces(
                obj=obj,
                attribute_name=attribute_name,
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
            f"{face_count}面に '{item.name}' を適用しました。Attribute: {attribute_name}{suffix}",
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


class VCMP_OT_ensure_attribute(Operator):
    bl_idname = "vcmp.ensure_attribute"
    bl_label = "Ensure Color Attribute"
    bl_description = "指定名のFLOAT_COLOR/CORNER Color Attributeを確認または作成します"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object

        if obj is None or obj.type != 'MESH':
            self.report({'ERROR'}, "メッシュオブジェクトをアクティブにしてください。")
            return {'CANCELLED'}

        attribute_name = _clean_attribute_name(context.scene.vcmp_attribute_name)
        mesh = obj.data

        if context.mode == 'EDIT_MESH':
            bm = bmesh.from_edit_mesh(mesh)
            try:
                _ensure_float_corner_attribute(mesh, bm, attribute_name)
            except ValueError as error:
                self.report({'ERROR'}, str(error))
                return {'CANCELLED'}
            bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
        else:
            attribute = mesh.color_attributes.get(attribute_name)

            if attribute is None:
                mesh.color_attributes.new(
                    name=attribute_name,
                    type='FLOAT_COLOR',
                    domain='CORNER',
                )
            elif attribute.domain != 'CORNER' or attribute.data_type != 'FLOAT_COLOR':
                self.report(
                    {'ERROR'},
                    f"'{attribute_name}' は FLOAT_COLOR / CORNER ではありません。",
                )
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
        box.label(text="Color Attribute", icon='GROUP_VCOL')
        box.prop(scene, "vcmp_attribute_name", text="Name")
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


def unregister():
    for prop_name in (
        "vcmp_new_color",
        "vcmp_new_color_name",
        "vcmp_active_index",
        "vcmp_color_items",
        "vcmp_attribute_name",
    ):
        if hasattr(bpy.types.Scene, prop_name):
            delattr(bpy.types.Scene, prop_name)

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
