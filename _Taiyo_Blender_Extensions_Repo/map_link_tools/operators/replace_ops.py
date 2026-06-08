import bpy
from bpy.types import Operator

from ..utils.collections import (
    active_layer_collection,
    iter_collection_objects,
    replace_object_keep_layout,
)
from ..utils.naming import remove_blender_numeric_suffix, short_list


class MAPLINK_OT_set_replace_collection_from_active_layer(Operator):
    bl_idname = "maplink.set_replace_collection_from_active_layer"
    bl_label = "Set From Active Layer Collection"
    bl_description = "Set the instance collection picker from the active layer collection"
    bl_options = {"REGISTER"}

    def execute(self, context):
        collection = active_layer_collection(context)
        if collection is None:
            self.report({"WARNING"}, "No active layer collection found.")
            return {"CANCELLED"}
        context.scene.maplink_settings.replace_collection = collection
        self.report({"INFO"}, f"Instance Collection set to {collection.name}.")
        return {"FINISHED"}


class MAPLINK_OT_replace_selected_with_active_object(Operator):
    bl_idname = "maplink.replace_selected_with_active_object"
    bl_label = "Replace Selected With Active Object"
    bl_description = "Replace selected objects with the active mesh object while preserving transform, name, and collections"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        active = context.view_layer.objects.active
        if active is None or active.type != "MESH" or active.data is None:
            self.report({"WARNING"}, "Active object must be a mesh object.")
            return {"CANCELLED"}

        settings = context.scene.maplink_settings
        targets = [obj for obj in context.selected_objects if obj != active]
        if not targets:
            self.report({"WARNING"}, "Select at least one object besides the active object.")
            return {"CANCELLED"}

        replaced = []
        skipped = []
        for target in targets:
            try:
                mesh_data = active.data if settings.use_mesh_instance else active.data.copy()
                new_obj = replace_object_keep_layout(context, target, replacement_data=mesh_data)
                replaced.append(new_obj)
            except Exception as exc:
                skipped.append(f"{target.name}: {exc}")

        for obj in replaced:
            obj.select_set(True)
        if replaced:
            context.view_layer.objects.active = replaced[-1]

        if skipped:
            self.report({"WARNING"}, f"Replaced {len(replaced)}, skipped {len(skipped)}. {short_list(skipped)}")
        else:
            self.report({"INFO"}, f"Replaced {len(replaced)} object(s).")
        return {"FINISHED"}


class MAPLINK_OT_replace_selected_with_collection_instance(Operator):
    bl_idname = "maplink.replace_selected_with_collection_instance"
    bl_label = "Replace Selected With Collection Instance"
    bl_description = "Replace selected objects with collection instance empties while preserving transform, name, and collections"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        collection = context.scene.maplink_settings.replace_collection
        if collection is None:
            self.report({"WARNING"}, "Set an Instance Collection.")
            return {"CANCELLED"}

        targets = list(context.selected_objects)
        if not targets:
            self.report({"WARNING"}, "Select at least one object.")
            return {"CANCELLED"}

        replaced = []
        skipped = []
        for target in targets:
            try:
                new_obj = replace_object_keep_layout(context, target, instance_collection=collection)
                replaced.append(new_obj)
            except Exception as exc:
                skipped.append(f"{target.name}: {exc}")

        for obj in replaced:
            obj.select_set(True)
        if replaced:
            context.view_layer.objects.active = replaced[-1]

        if skipped:
            self.report({"WARNING"}, f"Replaced {len(replaced)}, skipped {len(skipped)}. {short_list(skipped)}")
        else:
            self.report({"INFO"}, f"Replaced {len(replaced)} object(s) with collection instances.")
        return {"FINISHED"}


def _matching_mesh_objects_by_base_name(collection):
    by_name = {}
    for obj in iter_collection_objects(collection):
        if obj.type != "MESH" or obj.data is None:
            continue
        base_name = remove_blender_numeric_suffix(obj.name)
        by_name.setdefault(base_name, []).append(obj)
    return by_name


class MAPLINK_OT_replace_collection_instances_with_matching_mesh(Operator):
    bl_idname = "maplink.replace_collection_instances_with_matching_mesh"
    bl_label = "Replace Collection Instances With Matching Mesh"
    bl_description = "Replace selected collection instances with mesh objects matched by name without .001 suffixes"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        collection = context.scene.maplink_settings.matching_mesh_collection
        if collection is None:
            self.report({"WARNING"}, "Set a Matching Mesh Collection.")
            return {"CANCELLED"}

        selected_instances = [
            obj for obj in context.selected_objects
            if obj.type == "EMPTY"
            and obj.instance_type == "COLLECTION"
            and obj.instance_collection is not None
        ]
        if not selected_instances:
            self.report({"WARNING"}, "Select one or more collection instance objects.")
            return {"CANCELLED"}

        by_base_name = _matching_mesh_objects_by_base_name(collection)
        replaced = []
        skipped = []

        for target in selected_instances:
            base_name = remove_blender_numeric_suffix(target.name)
            matches = by_base_name.get(base_name, [])
            if len(matches) == 0:
                skipped.append(f"{target.name}: no mesh named {base_name}")
                continue
            if len(matches) > 1:
                skipped.append(f"{target.name}: multiple meshes named {base_name}")
                continue

            try:
                match = matches[0]
                new_obj = replace_object_keep_layout(context, target, replacement_data=match.data)
                replaced.append(new_obj)
            except Exception as exc:
                skipped.append(f"{target.name}: {exc}")

        for obj in replaced:
            obj.select_set(True)
        if replaced:
            context.view_layer.objects.active = replaced[-1]

        if skipped:
            self.report({"WARNING"}, f"Replaced {len(replaced)}, skipped {len(skipped)}. {short_list(skipped)}")
        else:
            self.report({"INFO"}, f"Replaced {len(replaced)} collection instance(s).")
        return {"FINISHED"}
