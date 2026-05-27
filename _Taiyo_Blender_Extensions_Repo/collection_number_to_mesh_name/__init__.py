bl_info = {
    "name": "Collection Number To Mesh Name",
    "author": "Taiyo",
    "version": (1, 0, 1),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Taiyo Tools",
    "description": "Assign numbers to collections and rename mesh data as number_collection name",
    "category": "Object",
}

import bpy
from bpy.props import BoolProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup


# -----------------------------------------------------------------------------
# Utility
# -----------------------------------------------------------------------------

def get_scene_collections_in_order(scene):
    """
    シーン内のコレクションを階層順に取得する。
    scene.collection はマスターコレクションなので除外する。
    """
    result = []

    def walk_collection(collection):
        result.append(collection)

        for child in collection.children:
            walk_collection(child)

    for child_collection in scene.collection.children:
        walk_collection(child_collection)

    return result


def restore_selection(context, old_selected, old_active):
    """
    実行前の選択状態を復元する。
    """
    view_layer = context.view_layer

    bpy.ops.object.select_all(action='DESELECT')

    for obj in old_selected:
        if obj and obj.name in bpy.data.objects:
            try:
                obj.select_set(True)
            except Exception:
                pass

    if old_active and old_active.name in bpy.data.objects:
        try:
            view_layer.objects.active = old_active
        except Exception:
            pass


def realize_collection_instances(context):
    """
    Collection Instance / Object Instance を可能な範囲で実体化する。

    対象:
    - Collection Instance
    - Vertex Instance
    - Face Instance など

    注意:
    - Geometry Nodes内部のInstanceはこの処理では完全には実体化しません。
    - 非表示、選択不可、ViewLayer外のオブジェクトは処理できない場合があります。
    """
    scene = context.scene
    view_layer = context.view_layer

    old_selected = list(context.selected_objects)
    old_active = view_layer.objects.active

    bpy.ops.object.select_all(action='DESELECT')

    instancer_objects = []

    for obj in scene.objects:
        if getattr(obj, "instance_type", 'NONE') != 'NONE':
            if obj.visible_get() and not obj.hide_select:
                obj.select_set(True)
                instancer_objects.append(obj)

    if not instancer_objects:
        restore_selection(context, old_selected, old_active)
        return 0

    view_layer.objects.active = instancer_objects[0]

    realized_count = 0

    try:
        bpy.ops.object.duplicates_make_real(
            use_base_parent=False,
            use_hierarchy=True,
        )

        realized_count = len(context.selected_objects)

    except Exception as error:
        print("[Collection Number To Mesh Name] Failed to realize instances:")
        print(error)

    restore_selection(context, old_selected, old_active)

    return realized_count


def make_mesh_single_user(obj):
    """
    Meshデータが複数オブジェクトで共有されている場合、
    obj専用のMeshデータにコピーする。

    これにより、インスタンス状態のMeshでも個別に名前を変更できる。
    """
    if obj.type != 'MESH':
        return False

    if obj.data is None:
        return False

    if obj.data.users > 1:
        obj.data = obj.data.copy()
        return True

    return False


def make_mesh_name(number, digits, collection_name, prefix, suffix):
    """
    Mesh名を作成する。

    例:
    number = 1
    digits = 3
    collection_name = Roof_A_Wood_UnderKawara

    結果:
    001_Roof_A_Wood_UnderKawara
    """
    number_text = f"{number:0{digits}d}"
    return f"{prefix}{number_text}_{collection_name}{suffix}"


# -----------------------------------------------------------------------------
# Properties
# -----------------------------------------------------------------------------

class CNTMN_Properties(PropertyGroup):
    start_number: IntProperty(
        name="Start Number",
        description="最初のコレクション番号",
        default=1,
        min=0,
    )

    digits: IntProperty(
        name="Digits",
        description="番号の桁数。3なら001, 002のようになります",
        default=3,
        min=1,
        max=10,
    )

    prefix: StringProperty(
        name="Prefix",
        description="Mesh名の先頭につける文字。通常は空でOKです",
        default="",
    )

    suffix: StringProperty(
        name="Suffix",
        description="Mesh名の末尾につける文字。通常は空でOKです",
        default="",
    )

    realize_instances: BoolProperty(
        name="Realize Instances First",
        description="Collection Instanceなどを先に実体化します",
        default=True,
    )

    make_mesh_single_user: BoolProperty(
        name="Make Mesh Single User",
        description="共有Meshデータをオブジェクトごとにコピーしてからリネームします",
        default=True,
    )

    include_empty_collections: BoolProperty(
        name="Number Empty Collections",
        description="空のコレクションにも番号を割り振ります",
        default=True,
    )


# -----------------------------------------------------------------------------
# Operator
# -----------------------------------------------------------------------------

class CNTMN_OT_rename_mesh_by_collection_number(Operator):
    bl_idname = "object.cntmn_rename_mesh_by_collection_number"
    bl_label = "Rename Mesh By Collection Number"
    bl_description = "コレクションごとに番号を割り振り、その番号と元のコレクション名をMeshデータ名にします"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.cntmn_props
        scene = context.scene

        realized_count = 0

        if props.realize_instances:
            realized_count = realize_collection_instances(context)

        collections = get_scene_collections_in_order(scene)

        if not collections:
            self.report({'WARNING'}, "シーン内に子コレクションがありません")
            return {'CANCELLED'}

        collection_number_map = {}
        current_number = props.start_number

        for collection in collections:
            mesh_objects = [
                obj for obj in collection.objects
                if obj.type == 'MESH'
            ]

            if not mesh_objects and not props.include_empty_collections:
                continue

            collection_number_map[collection.name] = current_number
            current_number += 1

        renamed_mesh_count = 0
        single_user_count = 0
        skipped_count = 0

        processed_objects = set()

        for collection in collections:
            if collection.name not in collection_number_map:
                continue

            number = collection_number_map[collection.name]

            new_mesh_name = make_mesh_name(
                number=number,
                digits=props.digits,
                collection_name=collection.name,
                prefix=props.prefix,
                suffix=props.suffix,
            )

            for obj in collection.objects:
                if obj.type != 'MESH':
                    skipped_count += 1
                    continue

                # 複数コレクション所属の場合は階層順で最初の名前を優先する。
                if obj.name in processed_objects:
                    continue

                if props.make_mesh_single_user:
                    if make_mesh_single_user(obj):
                        single_user_count += 1

                # Object名ではなくMeshデータ名だけを変更する。
                obj.data.name = new_mesh_name

                processed_objects.add(obj.name)
                renamed_mesh_count += 1

        self.report(
            {'INFO'},
            (
                f"Done: Collections={len(collection_number_map)}, "
                f"Meshes={renamed_mesh_count}, "
                f"SingleUser={single_user_count}, "
                f"Realized={realized_count}"
            ),
        )

        print("======================================")
        print("Collection Number To Mesh Name Result")
        print("======================================")
        print(f"Collections numbered : {len(collection_number_map)}")
        print(f"Meshes renamed       : {renamed_mesh_count}")
        print(f"Meshes single-user   : {single_user_count}")
        print(f"Instances realized   : {realized_count}")
        print(f"Skipped non-mesh     : {skipped_count}")
        print("======================================")

        return {'FINISHED'}


# -----------------------------------------------------------------------------
# Panel
# -----------------------------------------------------------------------------

class CNTMN_PT_panel(Panel):
    bl_label = "Collection Mesh Renamer"
    bl_idname = "CNTMN_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Taiyo Tools"

    def draw(self, context):
        layout = self.layout
        props = context.scene.cntmn_props

        layout.label(text="Mesh Name Format:")
        layout.label(text="001_CollectionName")

        layout.separator()

        box = layout.box()
        box.label(text="Number Settings")
        box.prop(props, "start_number")
        box.prop(props, "digits")

        box = layout.box()
        box.label(text="Optional Text")
        box.prop(props, "prefix")
        box.prop(props, "suffix")

        box = layout.box()
        box.label(text="Instance / Mesh Settings")
        box.prop(props, "realize_instances")
        box.prop(props, "make_mesh_single_user")
        box.prop(props, "include_empty_collections")

        layout.separator()

        layout.operator(
            CNTMN_OT_rename_mesh_by_collection_number.bl_idname,
            icon='OUTLINER_COLLECTION',
        )

        layout.separator()

        layout.label(text="Example:")
        layout.label(text="Collection: Roof_A")
        layout.label(text="Mesh: 001_Roof_A")


# -----------------------------------------------------------------------------
# Register
# -----------------------------------------------------------------------------

classes = (
    CNTMN_Properties,
    CNTMN_OT_rename_mesh_by_collection_number,
    CNTMN_PT_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.cntmn_props = PointerProperty(type=CNTMN_Properties)


def unregister():
    if hasattr(bpy.types.Scene, "cntmn_props"):
        del bpy.types.Scene.cntmn_props

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
