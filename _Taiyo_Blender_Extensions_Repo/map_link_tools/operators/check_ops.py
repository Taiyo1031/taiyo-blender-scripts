from bpy.props import EnumProperty
from bpy.types import Operator

from ..utils.collections import (
    mesh_data_set,
    mesh_objects_in_collection,
    select_objects,
)


def _collections_from_settings(context):
    settings = context.scene.maplink_settings
    return settings.collection_a, settings.collection_b


class MAPLINK_OT_check_collection_mesh_links(Operator):
    bl_idname = "maplink.check_collection_mesh_links"
    bl_label = "Check Mesh Links"
    bl_description = "Check whether Collection A and B contain objects sharing the same mesh data"
    bl_options = {"REGISTER"}

    def execute(self, context):
        settings = context.scene.maplink_settings
        collection_a, collection_b = _collections_from_settings(context)
        if collection_a is None or collection_b is None:
            self.report({"WARNING"}, "Set Collection A and Collection B.")
            return {"CANCELLED"}

        mesh_set_a = mesh_data_set(collection_a)
        mesh_set_b = mesh_data_set(collection_b)
        shared_meshes = mesh_set_a.intersection(mesh_set_b)
        linked_a = [
            obj for obj in mesh_objects_in_collection(collection_a)
            if obj.data in shared_meshes
        ]
        linked_b = [
            obj for obj in mesh_objects_in_collection(collection_b)
            if obj.data in shared_meshes
        ]

        message = (
            f"Shared mesh data: {len(shared_meshes)}. "
            f"A linked objects: {len(linked_a)}, B linked objects: {len(linked_b)}."
        )
        settings.check_result_message = message
        self.report({"INFO"}, message)
        return {"FINISHED"}


class MAPLINK_OT_select_unlinked_in_collection(Operator):
    bl_idname = "maplink.select_unlinked_in_collection"
    bl_label = "Select Unlinked"
    bl_description = "Select mesh objects in this collection that do not share mesh data with the other collection"
    bl_options = {"REGISTER", "UNDO"}

    side: EnumProperty(
        items=(
            ("A", "Collection A", "Use Collection A as the selection target"),
            ("B", "Collection B", "Use Collection B as the selection target"),
        ),
        default="A",
    )

    def execute(self, context):
        collection_a, collection_b = _collections_from_settings(context)
        if collection_a is None or collection_b is None:
            self.report({"WARNING"}, "Set Collection A and Collection B.")
            return {"CANCELLED"}

        target_collection = collection_a if self.side == "A" else collection_b
        other_collection = collection_b if self.side == "A" else collection_a
        other_meshes = mesh_data_set(other_collection)
        unlinked = [
            obj for obj in mesh_objects_in_collection(target_collection)
            if obj.data not in other_meshes
        ]
        selected, skipped = select_objects(context, unlinked)
        self.report(
            {"INFO"},
            f"Selected {selected} unlinked object(s) from Collection {self.side}; skipped {skipped}.",
        )
        return {"FINISHED"}
