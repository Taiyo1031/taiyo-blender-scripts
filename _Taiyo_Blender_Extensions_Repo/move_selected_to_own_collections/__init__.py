bl_info = {
    "name": "Move Objects to Own Collections",
    "author": "Taiyo",
    "version": (1, 2, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar (N) > Collection Tools",
    "description": "Move each selected object into a child collection named after the object.",
    "category": "Object",
}

import bpy


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


class OBJECT_OT_move_selected_to_own_collections(bpy.types.Operator):
    bl_idname = "object.move_selected_to_own_collections"
    bl_label = "Move to Own Collections"
    bl_description = "Move each selected object into a child collection with the same name as the object"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        selected_objects = list(context.selected_objects)

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
        layout.operator(
            OBJECT_OT_move_selected_to_own_collections.bl_idname,
            text="Move to Own Collections",
            icon="OUTLINER_COLLECTION",
        )


classes = (
    OBJECT_OT_move_selected_to_own_collections,
    VIEW3D_PT_collection_tools,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
