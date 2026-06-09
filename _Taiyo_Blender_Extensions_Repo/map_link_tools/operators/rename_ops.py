import bpy
from bpy.types import Operator

from ..utils.naming import (
    has_blender_numeric_suffix,
    remove_blender_numeric_suffix,
    short_list,
    unique_temporary_name,
)


def _report_result(operator, label, changed, skipped, skipped_names):
    if skipped:
        message = f"{label}: changed {changed}, skipped {skipped}. {short_list(skipped_names)}"
        operator.report({"WARNING"}, message)
    else:
        operator.report({"INFO"}, f"{label}: changed {changed}, skipped 0.")


def _report_remove_suffix_result(operator, changed, skipped, renamed_conflicts, skipped_names):
    status = f"Remove suffix: changed {changed}, renamed unselected conflicts {renamed_conflicts}, skipped {skipped}."
    if skipped_names:
        status = f"{status} {short_list(skipped_names)}"
    operator.report({"WARNING"} if skipped_names else {"INFO"}, status)


def _rename_exact(obj, name):
    obj.name = name
    return obj.name == name


def _replace_name(name_to_object, existing_names, old_name, new_name, obj):
    name_to_object.pop(old_name, None)
    existing_names.discard(old_name)
    name_to_object[new_name] = obj
    existing_names.add(new_name)


def _swap_with_unselected_conflict(obj, blocker, target_name, name_to_object, existing_names):
    old_name = obj.name
    blocker_name = blocker.name
    temp_name = unique_temporary_name(existing_names)

    if not _rename_exact(obj, temp_name):
        return False
    _replace_name(name_to_object, existing_names, old_name, temp_name, obj)

    if not _rename_exact(blocker, old_name):
        return False
    _replace_name(name_to_object, existing_names, blocker_name, old_name, blocker)

    if not _rename_exact(obj, target_name):
        return False
    _replace_name(name_to_object, existing_names, temp_name, target_name, obj)
    return True


class MAPLINK_OT_remove_suffix_selected(Operator):
    bl_idname = "maplink.remove_suffix_selected"
    bl_label = "Remove .001 From Selected Objects"
    bl_description = "Remove Blender .001 style suffixes from selected object names"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.maplink_settings
        selected_objects = list(context.selected_objects)
        selected_pointers = {obj.as_pointer() for obj in selected_objects}
        name_to_object = {obj.name: obj for obj in bpy.data.objects}
        existing_names = set(name_to_object)
        changed = 0
        skipped = 0
        skipped_names = []
        renamed_conflicts = 0

        for obj in selected_objects:
            if not has_blender_numeric_suffix(obj.name):
                skipped += 1
                continue

            old_name = obj.name
            target_name = remove_blender_numeric_suffix(obj.name)
            blocker = name_to_object.get(target_name)
            if blocker is not None and blocker != obj:
                if blocker.as_pointer() in selected_pointers:
                    skipped += 1
                    skipped_names.append(f"{old_name} -> {target_name} (selected conflict)")
                    continue
                if not settings.rename_unselected_conflicts:
                    skipped += 1
                    skipped_names.append(f"{old_name} -> {target_name} (unselected conflict)")
                    continue
                if not _swap_with_unselected_conflict(obj, blocker, target_name, name_to_object, existing_names):
                    skipped += 1
                    skipped_names.append(f"{old_name} -> {target_name} (rename failed)")
                    continue

                renamed_conflicts += 1
                changed += 1
                continue

            name_to_object.pop(old_name, None)
            existing_names.discard(old_name)
            obj.name = target_name
            name_to_object[target_name] = obj
            existing_names.add(target_name)
            changed += 1

        _report_remove_suffix_result(self, changed, skipped, renamed_conflicts, skipped_names)
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
