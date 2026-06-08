import bpy
from bpy.props import BoolProperty
from bpy.types import Operator
from bpy_extras.io_utils import ExportHelper, ImportHelper

from . import preset_utils, property_utils, target_utils


DETAIL_LIMIT = 1000


def _set_result(settings, scanned, changed, skipped, failed, details):
    settings.result_target_type = settings.target_type
    settings.result_scanned = scanned
    settings.result_changed = changed
    settings.result_skipped = skipped
    settings.result_failed = failed

    header = (
        f"Target Type: {settings.target_type}\n"
        f"Scanned: {scanned}\n"
        f"Changed: {changed}\n"
        f"Skipped: {skipped}\n"
        f"Failed: {failed}"
    )
    if scanned > DETAIL_LIMIT or len(details) > DETAIL_LIMIT:
        detail_text = f"[Info] Detailed log omitted for {max(scanned, len(details))} entries."
    else:
        detail_text = "\n".join(details)
    settings.log_text = header if not detail_text else f"{header}\n{detail_text}"


def _record_skip(details, record, reason):
    details.append(f"[Skipped] {record.label}: {reason}")


def _record_failure(details, record, error):
    details.append(f"[Failed] {record.label}: {error}")


def _preset_from_editor(settings):
    properties = []
    for item in settings.preset_properties:
        valid, value = property_utils.validate_property_name(item.property_name)
        if not valid:
            raise ValueError(value)
        properties.append(
            {
                "name": value,
                "type": item.property_type,
                "value": property_utils.get_item_typed_value(item),
            }
        )
    return {
        "name": settings.preset_name.strip(),
        "properties": properties,
    }


def _load_preset_into_editor(settings, preset):
    settings.preset_name = preset["name"]
    settings.preset_properties.clear()
    for entry in preset["properties"]:
        item = settings.preset_properties.add()
        item.property_name = entry["name"]
        property_utils.set_item_typed_value(item, entry["type"], entry["value"])
    settings.preset_property_index = 0


class CPBE_OT_apply_property(Operator):
    bl_idname = "cpbe.apply_property"
    bl_label = "Apply Property"
    bl_description = "Add or edit the property on all current targets"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.cpbe_settings
        valid, name_or_error = property_utils.validate_property_name(settings.property_name)
        if not valid:
            self.report({"ERROR"}, name_or_error)
            return {"CANCELLED"}

        name = name_or_error
        value = property_utils.get_typed_value(settings, settings.property_type)
        records, details = target_utils.get_target_records(context, settings)
        scanned = len(records) + len(details)
        changed = 0
        skipped = len(details)
        failed = 0

        for record in records:
            if not property_utils.is_target_editable(record.target):
                skipped += 1
                _record_skip(details, record, "read-only or linked data")
                continue

            exists = property_utils.has_custom_property(record.target, name)
            if settings.operation_mode == "ADD_ONLY" and exists:
                skipped += 1
                _record_skip(details, record, "property already exists")
                continue
            if settings.operation_mode == "EDIT_ONLY" and not exists:
                skipped += 1
                _record_skip(details, record, "property does not exist")
                continue

            try:
                property_utils.set_custom_property(record.target, name, value)
                changed += 1
                details.append(
                    f"[Changed] {record.label}: {name} = {property_utils.format_value(value)}"
                )
            except Exception as exc:
                failed += 1
                _record_failure(details, record, exc)

        _set_result(settings, scanned, changed, skipped, failed, details)
        if not records:
            self.report({"WARNING"}, "No valid target found.")
        else:
            self.report({"INFO"}, f"Changed {changed}, skipped {skipped}, failed {failed}.")
        return {"FINISHED"}


class CPBE_OT_search_property(Operator):
    bl_idname = "cpbe.search_property"
    bl_label = "Search Property"
    bl_description = "Search current targets and optionally select their owning objects"
    bl_options = {"REGISTER", "UNDO"}

    select_results: BoolProperty(default=False)

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"

    def execute(self, context):
        settings = context.scene.cpbe_settings
        valid, name_or_error = property_utils.validate_property_name(
            settings.search_property_name
        )
        if not valid:
            self.report({"ERROR"}, name_or_error)
            return {"CANCELLED"}

        name = name_or_error
        expected = None
        if settings.search_match_mode == "CONTAINS":
            expected = settings.search_string_value
        elif settings.search_match_mode == "EQUALS":
            expected = property_utils.get_typed_value(
                settings,
                settings.search_property_type,
                prefix="search_",
            )

        records, details = target_utils.get_target_records(context, settings)
        scanned = len(records) + len(details)
        skipped = len(details)
        failed = 0
        matched_records = []

        for record in records:
            try:
                if property_utils.property_matches(
                    record.target,
                    name,
                    settings.search_match_mode,
                    expected=expected,
                    property_type=settings.search_property_type,
                    case_sensitive=settings.case_sensitive,
                ):
                    matched_records.append(record)
                    details.append(f"[Matched] {record.label}")
            except Exception as exc:
                failed += 1
                _record_failure(details, record, exc)

        matched_owners = []
        seen = set()
        for record in matched_records:
            for obj in record.owners:
                key = obj.as_pointer()
                if key not in seen:
                    seen.add(key)
                    matched_owners.append(obj)

        selection_failures = 0
        if self.select_results:
            for obj in context.view_layer.objects:
                try:
                    obj.select_set(False)
                except Exception:
                    pass
            selected = []
            for obj in matched_owners:
                try:
                    if obj.name not in context.view_layer.objects:
                        continue
                    obj.select_set(True)
                    selected.append(obj)
                except Exception as exc:
                    selection_failures += 1
                    details.append(f"[Failed] {obj.name}: could not select ({exc})")
            context.view_layer.objects.active = selected[0] if selected else None
            failed += selection_failures

        _set_result(
            settings,
            scanned,
            len(matched_records),
            skipped,
            failed,
            details,
        )
        self.report(
            {"INFO"},
            f"Matched {len(matched_records)} target(s), {len(matched_owners)} object(s).",
        )
        return {"FINISHED"}


class CPBE_OT_delete_property(Operator):
    bl_idname = "cpbe.delete_property"
    bl_label = "Delete Property"
    bl_description = "Delete the property from current targets"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.cpbe_settings
        if not settings.confirm_delete:
            self.report({"ERROR"}, "Enable Confirm Delete before deleting.")
            return {"CANCELLED"}

        valid, name_or_error = property_utils.validate_property_name(
            settings.delete_property_name
        )
        if not valid:
            self.report({"ERROR"}, name_or_error)
            return {"CANCELLED"}

        name = name_or_error
        expected = None
        if settings.delete_mode == "VALUE":
            expected = property_utils.get_typed_value(
                settings,
                settings.delete_property_type,
                prefix="delete_",
            )

        records, details = target_utils.get_target_records(context, settings)
        scanned = len(records) + len(details)
        changed = 0
        skipped = len(details)
        failed = 0

        for record in records:
            if not property_utils.is_target_editable(record.target):
                skipped += 1
                _record_skip(details, record, "read-only or linked data")
                continue

            if not property_utils.has_custom_property(record.target, name):
                skipped += 1
                _record_skip(details, record, "property does not exist")
                continue
            if settings.delete_mode == "VALUE" and not property_utils.values_equal(
                record.target[name],
                expected,
                settings.delete_property_type,
                case_sensitive=True,
            ):
                skipped += 1
                _record_skip(details, record, "value does not match")
                continue

            try:
                property_utils.delete_custom_property(record.target, name)
                changed += 1
                details.append(f"[Changed] {record.label}: deleted {name}")
            except Exception as exc:
                failed += 1
                _record_failure(details, record, exc)

        settings.confirm_delete = False
        _set_result(settings, scanned, changed, skipped, failed, details)
        self.report({"INFO"}, f"Deleted {changed}, skipped {skipped}, failed {failed}.")
        return {"FINISHED"}


class CPBE_OT_refresh_property_list(Operator):
    bl_idname = "cpbe.refresh_property_list"
    bl_label = "Refresh Property List"
    bl_description = "Refresh the custom property summary"

    def execute(self, context):
        settings = context.scene.cpbe_settings
        records, skipped_details = target_utils.records_for_property_list(context, settings)
        summaries = property_utils.build_property_summaries(records)
        settings.property_summaries.clear()
        for summary in summaries:
            item = settings.property_summaries.add()
            item.property_name = summary["name"]
            item.value_type = summary["type"]
            item.value_preview = summary["value"]
            item.target_count = summary["count"]
            item.mixed = summary["mixed"]
        settings.property_summary_index = 0
        self.report(
            {"INFO"},
            f"Found {len(summaries)} properties; skipped {len(skipped_details)} object(s).",
        )
        return {"FINISHED"}


class CPBE_OT_copy_log(Operator):
    bl_idname = "cpbe.copy_log"
    bl_label = "Copy Log"
    bl_description = "Copy the latest operation log to the clipboard"

    def execute(self, context):
        context.window_manager.clipboard = context.scene.cpbe_settings.log_text
        self.report({"INFO"}, "Log copied to clipboard.")
        return {"FINISHED"}


class CPBE_OT_add_preset_item(Operator):
    bl_idname = "cpbe.add_preset_item"
    bl_label = "Add Current Property"
    bl_description = "Add or replace the current property in the preset editor"

    def execute(self, context):
        settings = context.scene.cpbe_settings
        valid, name_or_error = property_utils.validate_property_name(settings.property_name)
        if not valid:
            self.report({"ERROR"}, name_or_error)
            return {"CANCELLED"}

        name = name_or_error
        existing = next(
            (item for item in settings.preset_properties if item.property_name == name),
            None,
        )
        item = existing or settings.preset_properties.add()
        item.property_name = name
        value = property_utils.get_typed_value(settings, settings.property_type)
        property_utils.set_item_typed_value(item, settings.property_type, value)
        settings.preset_property_index = list(settings.preset_properties).index(item)
        self.report({"INFO"}, f"Added '{name}' to the preset editor.")
        return {"FINISHED"}


class CPBE_OT_remove_preset_item(Operator):
    bl_idname = "cpbe.remove_preset_item"
    bl_label = "Remove Preset Property"

    def execute(self, context):
        settings = context.scene.cpbe_settings
        index = settings.preset_property_index
        if not (0 <= index < len(settings.preset_properties)):
            return {"CANCELLED"}
        settings.preset_properties.remove(index)
        settings.preset_property_index = min(
            index,
            max(0, len(settings.preset_properties) - 1),
        )
        return {"FINISHED"}


class CPBE_OT_clear_preset_items(Operator):
    bl_idname = "cpbe.clear_preset_items"
    bl_label = "Clear Preset Editor"

    def execute(self, context):
        settings = context.scene.cpbe_settings
        settings.preset_properties.clear()
        settings.preset_property_index = 0
        return {"FINISHED"}


class CPBE_OT_load_preset_to_editor(Operator):
    bl_idname = "cpbe.load_preset_to_editor"
    bl_label = "Load Into Editor"

    def execute(self, context):
        settings = context.scene.cpbe_settings
        presets = preset_utils.load_presets()
        preset = preset_utils.find_preset(presets, settings.selected_preset)
        if preset is None:
            self.report({"ERROR"}, "Preset not found.")
            return {"CANCELLED"}
        _load_preset_into_editor(settings, preset)
        return {"FINISHED"}


class CPBE_OT_save_preset(Operator):
    bl_idname = "cpbe.save_preset"
    bl_label = "Save Preset"

    def execute(self, context):
        settings = context.scene.cpbe_settings
        if not settings.preset_name.strip():
            self.report({"ERROR"}, "Preset name is empty.")
            return {"CANCELLED"}
        if not settings.preset_properties:
            self.report({"ERROR"}, "Preset editor is empty.")
            return {"CANCELLED"}
        try:
            preset = _preset_from_editor(settings)
            presets = preset_utils.upsert_preset(preset_utils.load_presets(), preset)
            preset_utils.save_presets(presets)
            settings.selected_preset = preset["name"]
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Saved preset '{preset['name']}'.")
        return {"FINISHED"}


class CPBE_OT_apply_preset(Operator):
    bl_idname = "cpbe.apply_preset"
    bl_label = "Apply Preset"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.cpbe_settings
        preset = preset_utils.find_preset(
            preset_utils.load_presets(),
            settings.selected_preset,
        )
        if preset is None:
            self.report({"ERROR"}, "Preset not found.")
            return {"CANCELLED"}

        records, details = target_utils.get_target_records(context, settings)
        scanned = len(records) + len(details)
        changed = 0
        skipped = len(details)
        failed = 0

        for record in records:
            if not property_utils.is_target_editable(record.target):
                skipped += 1
                _record_skip(details, record, "read-only or linked data")
                continue
            for entry in preset["properties"]:
                try:
                    property_utils.set_custom_property(
                        record.target,
                        entry["name"],
                        entry["value"],
                    )
                    changed += 1
                    details.append(
                        f"[Changed] {record.label}: {entry['name']} = "
                        f"{property_utils.format_value(entry['value'])}"
                    )
                except Exception as exc:
                    failed += 1
                    _record_failure(details, record, exc)

        _set_result(settings, scanned, changed, skipped, failed, details)
        self.report({"INFO"}, f"Applied {changed} preset value(s).")
        return {"FINISHED"}


class CPBE_OT_delete_preset(Operator):
    bl_idname = "cpbe.delete_preset"
    bl_label = "Delete Preset"

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        settings = context.scene.cpbe_settings
        name = settings.selected_preset
        presets = preset_utils.load_presets()
        if preset_utils.find_preset(presets, name) is None:
            self.report({"ERROR"}, "Preset not found.")
            return {"CANCELLED"}
        remaining = preset_utils.delete_preset(presets, name)
        preset_utils.save_presets(remaining)
        if remaining:
            settings.selected_preset = remaining[0]["name"]
        self.report({"INFO"}, f"Deleted preset '{name}'.")
        return {"FINISHED"}


class CPBE_OT_import_presets(Operator, ImportHelper):
    bl_idname = "cpbe.import_presets"
    bl_label = "Import Presets"

    filename_ext = ".json"
    filter_glob: bpy.props.StringProperty(default="*.json", options={"HIDDEN"})

    def execute(self, context):
        try:
            imported = preset_utils.read_preset_file(self.filepath)
            merged = preset_utils.merge_presets(preset_utils.load_presets(), imported)
            preset_utils.save_presets(merged)
            if imported:
                context.scene.cpbe_settings.selected_preset = imported[0]["name"]
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Imported {len(imported)} preset(s).")
        return {"FINISHED"}


class CPBE_OT_export_presets(Operator, ExportHelper):
    bl_idname = "cpbe.export_presets"
    bl_label = "Export Presets"

    filename_ext = ".json"
    filter_glob: bpy.props.StringProperty(default="*.json", options={"HIDDEN"})

    def invoke(self, context, event):
        if not self.filepath:
            self.filepath = "custom_properties_presets.json"
        return super().invoke(context, event)

    def execute(self, _context):
        try:
            preset_utils.write_preset_file(
                self.filepath,
                preset_utils.load_presets(),
            )
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Exported presets to {self.filepath}.")
        return {"FINISHED"}
