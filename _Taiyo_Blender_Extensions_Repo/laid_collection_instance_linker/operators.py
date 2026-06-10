import bpy
from bpy.props import StringProperty

from . import core


def _validate_source_collections(operator, settings):
    if settings.laid_map_collection is None:
        operator.report({"ERROR"}, "Laid_MAP collection is not valid")
        return False
    if settings.individual_root is None:
        operator.report(
            {"ERROR"},
            "Laid_Individual root collection is not valid",
        )
        return False
    return True


def _fill_preview_item(item, result):
    item.status = result["status"]
    item.object_name = result["object_name"]
    item.match_key = result["match_key"]
    item.source_name_field = result["source_name_field"]
    item.target_collection = result["target_collection"]
    item.target_path = result["target_path"]
    item.color_tag = result["color_tag"]
    item.detail = result["detail"]


class LCIL_OT_preview_link(bpy.types.Operator):
    bl_idname = "lcil.preview_link"
    bl_label = "Preview / Link"
    bl_description = "Match Laid_MAP objects to target collections and store link properties"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.lcil_settings
        if not _validate_source_collections(self, settings):
            return {"CANCELLED"}

        target_index, _path_map, targets = core.build_target_index(
            settings.individual_root,
            settings.ignore_numeric_suffix,
        )
        if not targets:
            self.report(
                {"ERROR"},
                "No target collections found. Target collections must directly contain mesh objects.",
            )
            return {"CANCELLED"}

        settings.preview_items.clear()
        counts = {
            "LINKED": 0,
            "MISSING": 0,
            "DUPLICATE": 0,
            "SKIPPED": 0,
        }
        for obj in core.walk_objects(settings.laid_map_collection):
            result = core.match_object(obj, settings, target_index)
            core.store_match_properties(obj, result)
            item = settings.preview_items.add()
            _fill_preview_item(item, result)
            counts[result["status"]] += 1

        settings.preview_linked = counts["LINKED"]
        settings.preview_missing = counts["MISSING"]
        settings.preview_duplicate = counts["DUPLICATE"]
        settings.preview_skipped = counts["SKIPPED"]
        settings.preview_index = 0

        self.report(
            {"INFO"},
            (
                f"Linked {counts['LINKED']}, Missing {counts['MISSING']}, "
                f"Duplicate {counts['DUPLICATE']}, Skipped {counts['SKIPPED']}"
            ),
        )
        return {"FINISHED"}


def _select_objects(context, objects):
    for obj in context.view_layer.objects:
        obj.select_set(False)

    selected = []
    for obj in objects:
        obj.hide_viewport = False
        try:
            obj.hide_set(False)
            obj.select_set(True)
        except RuntimeError:
            continue
        selected.append(obj)

    if selected:
        context.view_layer.objects.active = selected[-1]
    return selected


class LCIL_OT_select_object(bpy.types.Operator):
    bl_idname = "lcil.select_object"
    bl_label = "Select Object"
    bl_description = "Select the source object for this preview row"

    object_name: StringProperty()

    def execute(self, context):
        obj = bpy.data.objects.get(self.object_name)
        if obj is None:
            self.report({"WARNING"}, f"Object not found: {self.object_name}")
            return {"CANCELLED"}
        selected = _select_objects(context, [obj])
        if not selected:
            self.report(
                {"WARNING"},
                "Object is not available in the current view layer",
            )
            return {"CANCELLED"}
        return {"FINISHED"}


class LCIL_OT_select_issue_objects(bpy.types.Operator):
    bl_idname = "lcil.select_issue_objects"
    bl_label = "Select All Issue Objects"
    bl_description = "Select all missing and duplicate source objects"

    def execute(self, context):
        settings = context.scene.lcil_settings
        issue_objects = []
        for item in settings.preview_items:
            if item.status not in {"MISSING", "DUPLICATE"}:
                continue
            obj = bpy.data.objects.get(item.object_name)
            if obj is not None:
                issue_objects.append(obj)

        selected = _select_objects(context, issue_objects)
        if not selected:
            self.report({"WARNING"}, "No issue objects are selectable")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Selected {len(selected)} issue object(s)")
        return {"FINISHED"}


class LCIL_OT_generate_instances(bpy.types.Operator):
    bl_idname = "lcil.generate_instances"
    bl_label = "Generate Collection Instances"
    bl_description = "Generate collection instances from saved link properties"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.lcil_settings
        if not _validate_source_collections(self, settings):
            return {"CANCELLED"}

        output_name = settings.output_collection_name.strip()
        if not output_name:
            self.report({"ERROR"}, "Output collection name is empty")
            return {"CANCELLED"}

        _target_index, path_map, targets = core.build_target_index(
            settings.individual_root,
            settings.ignore_numeric_suffix,
        )
        if not targets:
            self.report(
                {"ERROR"},
                "No target collections found. Target collections must directly contain mesh objects.",
            )
            return {"CANCELLED"}

        linked_sources = [
            obj
            for obj in core.walk_objects(settings.laid_map_collection)
            if obj.get("LCIL_link_status") == "LINKED"
        ]
        if not linked_sources:
            self.report(
                {"ERROR"},
                "No linked objects found. Run Preview / Link first.",
            )
            return {"CANCELLED"}

        output = core.get_or_create_output_collection(context.scene, output_name)
        core.remove_generated_content(output)

        generated = 0
        skipped = 0
        for source_obj in linked_sources:
            target_path = source_obj.get("LCIL_link_collection_path", "")
            target_collection = path_map.get(target_path)
            if target_collection is None:
                skipped += 1
                continue

            destination = output
            if settings.group_by_target:
                destination = core.get_or_create_group(output, target_collection)
            core.create_collection_instance(
                source_obj,
                target_collection,
                target_path,
                destination,
                settings.instance_prefix,
            )
            generated += 1

        if not generated:
            self.report(
                {"ERROR"},
                "No valid linked target collections were found",
            )
            return {"CANCELLED"}

        message = f"Generated {generated} collection instance(s)"
        if skipped:
            message += f"; skipped {skipped} stale link(s)"
        self.report({"INFO"}, message)
        return {"FINISHED"}


def _get_output(operator, context):
    settings = context.scene.lcil_settings
    output_name = settings.output_collection_name.strip()
    if not output_name:
        operator.report({"ERROR"}, "Output collection name is empty")
        return None
    output = bpy.data.collections.get(output_name)
    if output is None:
        operator.report({"WARNING"}, f"Output collection not found: {output_name}")
        return None
    return output


class LCIL_OT_realize_instances(bpy.types.Operator):
    bl_idname = "lcil.realize_instances"
    bl_label = "Realize Generated Instances"
    bl_description = "Duplicate instance contents as real objects and remove generated empties"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        output = _get_output(self, context)
        if output is None:
            return {"CANCELLED"}

        empties = core.generated_instance_empties(output)
        if not empties:
            self.report(
                {"WARNING"},
                "No generated collection instance empties found",
            )
            return {"CANCELLED"}

        realized_count = 0
        for empty in empties:
            realized_count += len(core.realize_instance(empty, output))
            bpy.data.objects.remove(empty, do_unlink=True)

        self.report(
            {"INFO"},
            f"Realized {len(empties)} instance(s) as {realized_count} object(s)",
        )
        return {"FINISHED"}


class LCIL_OT_delete_generated_empties(bpy.types.Operator):
    bl_idname = "lcil.delete_generated_empties"
    bl_label = "Delete Generated Empty Instances"
    bl_description = "Delete only generated collection instance empties"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        output = _get_output(self, context)
        if output is None:
            return {"CANCELLED"}

        empties = core.generated_instance_empties(output)
        if not empties:
            self.report(
                {"WARNING"},
                "No generated collection instance empties found",
            )
            return {"CANCELLED"}

        for empty in empties:
            bpy.data.objects.remove(empty, do_unlink=True)
        self.report({"INFO"}, f"Deleted {len(empties)} generated empty instance(s)")
        return {"FINISHED"}
