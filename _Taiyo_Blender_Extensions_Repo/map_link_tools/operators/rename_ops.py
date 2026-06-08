import bpy
from bpy.types import Operator

from ..utils.naming import (
    has_blender_numeric_suffix,
    remove_blender_numeric_suffix,
    short_list,
)


def _report_result(operator, label, changed, skipped, skipped_names):
    if skipped:
        message = f"{label}: changed {changed}, skipped {skipped}. {short_list(skipped_names)}"
        operator.report({"WARNING"}, message)
    else:
        operator.report({"INFO"}, f"{label}: changed {changed}, skipped 0.")


class MAPLINK_OT_remove_suffix_selected(Operator):
    bl_idname = "maplink.remove_suffix_selected"
    bl_label = "Remove .001 From Selected Objects"
    bl_description = "Remove Blender .001 style suffixes from selected object names; collisions are skipped"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        existing_names = {obj.name for obj in bpy.data.objects}
        changed = 0
        skipped = 0
        skipped_names = []

        for obj in context.selected_objects:
            if not has_blender_numeric_suffix(obj.name):
                skipped += 1
                continue

            target_name = remove_blender_numeric_suffix(obj.name)
            existing_names.discard(obj.name)
            if target_name in existing_names:
                skipped += 1
                skipped_names.append(f"{obj.name} -> {target_name}")
                existing_names.add(obj.name)
                continue

            obj.name = target_name
            existing_names.add(target_name)
            changed += 1

        _report_result(self, "Remove suffix", changed, skipped, skipped_names)
        return {"FINISHED"}


class MAPLINK_OT_object_name_to_mesh_name(Operator):
    bl_idname = "maplink.object_name_to_mesh_name"
    bl_label = "Object Name -> Mesh Name"
    bl_description = "Rename selected mesh data-blocks to match their object names; collisions are skipped"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        existing_mesh_names = {mesh.name for mesh in bpy.data.meshes}
        processed_meshes = set()
        changed = 0
        skipped = 0
        skipped_names = []

        for obj in context.selected_objects:
            if obj.type != "MESH" or obj.data is None:
                skipped += 1
                continue

            mesh = obj.data
            mesh_key = mesh.as_pointer()
            if mesh_key in processed_meshes:
                skipped += 1
                continue
            processed_meshes.add(mesh_key)

            target_name = obj.name
            if mesh.name == target_name:
                skipped += 1
                continue

            existing_mesh_names.discard(mesh.name)
            if target_name in existing_mesh_names:
                skipped += 1
                skipped_names.append(f"{mesh.name} -> {target_name}")
                existing_mesh_names.add(mesh.name)
                continue

            mesh.name = target_name
            existing_mesh_names.add(target_name)
            changed += 1

        _report_result(self, "Object to mesh name", changed, skipped, skipped_names)
        return {"FINISHED"}


class MAPLINK_OT_mesh_name_to_object_name(Operator):
    bl_idname = "maplink.mesh_name_to_object_name"
    bl_label = "Mesh Name -> Object Name"
    bl_description = "Rename selected mesh objects to match their mesh data names; collisions are skipped"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        existing_object_names = {obj.name for obj in bpy.data.objects}
        changed = 0
        skipped = 0
        skipped_names = []

        for obj in context.selected_objects:
            if obj.type != "MESH" or obj.data is None:
                skipped += 1
                continue

            target_name = obj.data.name
            if obj.name == target_name:
                skipped += 1
                continue

            existing_object_names.discard(obj.name)
            if target_name in existing_object_names:
                skipped += 1
                skipped_names.append(f"{obj.name} -> {target_name}")
                existing_object_names.add(obj.name)
                continue

            obj.name = target_name
            existing_object_names.add(target_name)
            changed += 1

        _report_result(self, "Mesh to object name", changed, skipped, skipped_names)
        return {"FINISHED"}
