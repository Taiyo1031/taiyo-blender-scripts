bl_info = {
    "name": "Move Objects to Own Collections",
    "author": "Taiyo",
    "version": (1, 3, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar (N) > Collection Tools",
    "description": "Move each selected object into a child collection named after the object.",
    "category": "Object",
}

DOCUMENTATION_URL = "https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/_Taiyo_Blender_Extensions_Repo/move_selected_to_own_collections/Move_Objects_to_Own_Collections_%E4%BD%BF%E7%94%A8%E6%9B%B8.md"

import bpy
from bpy.props import BoolProperty, EnumProperty, PointerProperty


def collection_contains(collection, target_collection):
    for child_collection in collection.children:
        if child_collection == target_collection:
            return True
        if collection_contains(child_collection, target_collection):
            return True
    return False


def get_or_create_target_collection(parent_collection, collection_name):
    target_collection = parent_collection.children.get(collection_name)
    if target_collection is not None:
        return target_collection

    target_collection = bpy.data.collections.get(collection_name)
    if target_collection is not None and (
        target_collection == parent_collection
        or collection_contains(target_collection, parent_collection)
    ):
        target_collection = None

    if target_collection is None:
        target_collection = bpy.data.collections.new(collection_name)

    if target_collection.name not in parent_collection.children:
        parent_collection.children.link(target_collection)

    return target_collection


COLLECTION_COLOR_ITEMS = (
    ("NONE", "None", "Do not show a color tag"),
    ("COLOR_01", "Color 1", "Use collection color tag 1"),
    ("COLOR_02", "Color 2", "Use collection color tag 2"),
    ("COLOR_03", "Color 3", "Use collection color tag 3"),
    ("COLOR_04", "Color 4", "Use collection color tag 4"),
    ("COLOR_05", "Color 5", "Use collection color tag 5"),
    ("COLOR_06", "Color 6", "Use collection color tag 6"),
    ("COLOR_07", "Color 7", "Use collection color tag 7"),
    ("COLOR_08", "Color 8", "Use collection color tag 8"),
)


class MSOC_Settings(bpy.types.PropertyGroup):
    apply_collection_color: BoolProperty(
        name="Set Collection Color",
        description="Apply a color tag to each destination collection",
        default=False,
    )
    collection_color_tag: EnumProperty(
        name="Collection Color",
        description="Color tag assigned to destination collections",
        items=COLLECTION_COLOR_ITEMS,
        default="COLOR_03",
    )


class OBJECT_OT_move_selected_to_own_collections(bpy.types.Operator):
    bl_idname = "object.move_selected_to_own_collections"
    bl_label = "Move to Own Collections"
    bl_description = "Move each selected object into a child collection with the same name as the object"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        selected_objects = list(context.selected_objects)
        settings = context.scene.msoc_settings

        if not selected_objects:
            self.report({"WARNING"}, "No objects selected.")
            return {"CANCELLED"}

        moved_count = 0
        skipped_count = 0

        for obj in selected_objects:
            if not obj.users_collection:
                skipped_count += 1
                continue

            original_collection = obj.users_collection[0]
            target_collection = get_or_create_target_collection(
                original_collection,
                obj.name,
            )
            if settings.apply_collection_color:
                target_collection.color_tag = settings.collection_color_tag

            if obj.name not in target_collection.objects:
                target_collection.objects.link(obj)

            for collection in list(obj.users_collection):
                if collection != target_collection:
                    collection.objects.unlink(obj)

            moved_count += 1

        if skipped_count:
            self.report(
                {"INFO"},
                f"Moved {moved_count} object(s). Skipped {skipped_count} object(s) without a collection.",
            )
        else:
            self.report(
                {"INFO"},
                f"Moved {moved_count} object(s) to matching collection(s).",
            )

        return {"FINISHED"}


class VIEW3D_PT_collection_tools(bpy.types.Panel):
    bl_label = "Collection Tools"
    bl_idname = "VIEW3D_PT_collection_tools"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Collection Tools"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.msoc_settings

        color_box = layout.box()
        color_box.prop(settings, "apply_collection_color")
        row = color_box.row()
        row.enabled = settings.apply_collection_color
        row.prop(settings, "collection_color_tag")

        layout.operator(
            OBJECT_OT_move_selected_to_own_collections.bl_idname,
            text="Move to Own Collections",
            icon="OUTLINER_COLLECTION",
        )


class MSOC_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__ or __name__

    def draw(self, context):
        layout = self.layout
        layout.label(text="Documentation")
        op = layout.operator("wm.url_open", text="Open User Guide on GitHub", icon="URL")
        op.url = DOCUMENTATION_URL


classes = (
    MSOC_AddonPreferences,
    MSOC_Settings,
    OBJECT_OT_move_selected_to_own_collections,
    VIEW3D_PT_collection_tools,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.msoc_settings = PointerProperty(type=MSOC_Settings)


def unregister():
    del bpy.types.Scene.msoc_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
