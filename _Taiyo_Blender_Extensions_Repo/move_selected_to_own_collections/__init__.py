bl_info = {
    "name": "Move Objects to Own Collections",
    "author": "Taiyo",
    "version": (1, 5, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar (N) > Collection Tools",
    "description": "Move each selected object into a child collection named after the object.",
    "category": "Object",
}

DOCUMENTATION_URL = "https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/_Taiyo_Blender_Extensions_Repo/move_selected_to_own_collections/Move_Objects_to_Own_Collections_%E4%BD%BF%E7%94%A8%E6%9B%B8.md"

import bpy
from bpy.props import EnumProperty, PointerProperty


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
    ("KEEP", "Keep", "Do not change existing collection color", "BLANK1", 0),
    ("NONE", "None", "Clear the collection color tag", "X", 1),
    ("COLOR_01", "1", "Use collection color tag 1", "COLLECTION_COLOR_01", 2),
    ("COLOR_02", "2", "Use collection color tag 2", "COLLECTION_COLOR_02", 3),
    ("COLOR_03", "3", "Use collection color tag 3", "COLLECTION_COLOR_03", 4),
    ("COLOR_04", "4", "Use collection color tag 4", "COLLECTION_COLOR_04", 5),
    ("COLOR_05", "5", "Use collection color tag 5", "COLLECTION_COLOR_05", 6),
    ("COLOR_06", "6", "Use collection color tag 6", "COLLECTION_COLOR_06", 7),
    ("COLOR_07", "7", "Use collection color tag 7", "COLLECTION_COLOR_07", 8),
    ("COLOR_08", "8", "Use collection color tag 8", "COLLECTION_COLOR_08", 9),
)


NAME_SOURCE_ITEMS = (
    ("OBJECT", "Object Name", "Create destination collections from object names"),
    ("MESH", "Mesh Name", "Create destination collections from mesh data names"),
)


def target_collection_name(obj, name_source):
    if name_source == "MESH" and obj.type == "MESH" and obj.data is not None:
        return obj.data.name
    return obj.name


class MSOC_Settings(bpy.types.PropertyGroup):
    name_source: EnumProperty(
        name="Name Mode",
        description="Name source for destination collections",
        items=NAME_SOURCE_ITEMS,
        default="OBJECT",
    )
    collection_color_tag: EnumProperty(
        name="Collection Color",
        description="Color tag assigned to destination collections",
        items=COLLECTION_COLOR_ITEMS,
        default="KEEP",
    )


class OBJECT_OT_move_selected_to_own_collections(bpy.types.Operator):
    bl_idname = "object.move_selected_to_own_collections"
    bl_label = "Move to Own Collections"
    bl_description = "Move each selected object into a child collection named from the object or mesh"
    bl_options = {"REGISTER", "UNDO"}

    name_source: EnumProperty(
        name="Name Source",
        description="Name source for destination collections",
        items=NAME_SOURCE_ITEMS,
        default="OBJECT",
    )

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
            collection_name = target_collection_name(obj, self.name_source)
            target_collection = get_or_create_target_collection(
                original_collection,
                collection_name,
            )
            if settings.collection_color_tag != "KEEP":
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
                f"Moved {moved_count} object(s) by {self.name_source.lower()} name. Skipped {skipped_count} object(s) without a collection.",
            )
        else:
            self.report(
                {"INFO"},
                f"Moved {moved_count} object(s) by {self.name_source.lower()} name.",
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

        mode_box = layout.box()
        mode_box.label(text="Name Mode")
        mode_box.prop(settings, "name_source", expand=True)

        color_box = layout.box()
        color_box.label(text="Collection Color")
        row = color_box.row(align=True)
        row.prop_enum(settings, "collection_color_tag", "KEEP", text="Keep")
        row.prop_enum(settings, "collection_color_tag", "NONE", text="None", icon="X")
        grid = color_box.grid_flow(
            columns=4,
            row_major=True,
            even_columns=True,
            even_rows=True,
            align=True,
        )
        for index in range(1, 9):
            color_id = f"COLOR_{index:02d}"
            grid.prop_enum(
                settings,
                "collection_color_tag",
                color_id,
                text=str(index),
                icon=f"COLLECTION_COLOR_{index:02d}",
            )

        op = layout.operator(
            OBJECT_OT_move_selected_to_own_collections.bl_idname,
            text="Move to Own Collections",
            icon="OUTLINER_COLLECTION",
        )
        op.name_source = settings.name_source


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
