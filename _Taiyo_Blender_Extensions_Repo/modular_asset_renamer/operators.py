import uuid

import bpy
from bpy.props import EnumProperty, IntProperty, StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ExportHelper, ImportHelper

from . import naming, preset_utils
from .props import DIMENSION_AXIS_ITEMS, MODULE_TYPE_ITEMS


def _settings(context):
    return context.scene.mar_settings


def _active_module(settings):
    if not settings.modules:
        return None
    index = min(settings.module_index, len(settings.modules) - 1)
    settings.module_index = index
    return settings.modules[index]


def _module_by_id(settings, module_id):
    if not module_id:
        return None
    return next(
        (module for module in settings.modules if module.module_id == module_id),
        None,
    )


def _active_or_target_module(settings, module_id):
    return _module_by_id(settings, module_id) or _active_module(settings)


def _add_default_choice(module):
    option = module.choice_options.add()
    option.option_id = preset_utils.new_choice_option_id()
    option.option_value = preset_utils.new_option_value()
    option.value = "Option"
    module.choice_current = option.option_id


def _add_dimension_part(module, axis, separator_after=""):
    part = module.dimension_parts.add()
    part.axis = axis
    part.separator_after = separator_after
    return part


def _add_default_dimension_parts(module):
    _add_dimension_part(module, "X", "x")
    _add_dimension_part(module, "Y", "x")
    _add_dimension_part(module, "Z", "")
    module.dimension_part_index = 0
    module.dimension_parts_migrated = True


def _initialize_module(module, module_type):
    module.module_id = preset_utils.new_id()
    module.module_type = module_type
    module.enabled = True
    module.display_name = dict(
        (identifier, label)
        for identifier, label, _description in MODULE_TYPE_ITEMS
    )[module_type]
    module.separator_after = "" if module_type == "INDEX" else "_"
    if module_type == "CHOICE":
        module.choice_label = "Choice"
        _add_default_choice(module)
    elif module_type == "DIMENSIONS":
        _add_default_dimension_parts(module)


def _copy_module(source, target):
    preset_utils.repair_dimension_module(source)
    raw = preset_utils.module_to_dict(source)
    option_id_map = {}
    for field, value in raw.items():
        if field in {
            "module_id",
            "choice_options",
            "choice_current",
            "dimension_parts",
        }:
            continue
        setattr(target, field, value)
    target.module_id = preset_utils.new_id()
    for raw_option in raw["choice_options"]:
        option = target.choice_options.add()
        option.option_id = preset_utils.new_choice_option_id()
        option.option_value = preset_utils.new_option_value()
        option.value = raw_option["value"]
        option_id_map[raw_option["option_id"]] = option.option_id
    current = option_id_map.get(raw["choice_current"])
    if current:
        target.choice_current = current
    elif target.choice_options:
        target.choice_current = target.choice_options[0].option_id
    for raw_part in raw["dimension_parts"]:
        _add_dimension_part(
            target,
            raw_part["axis"],
            raw_part["separator_after"],
        )
    target.dimension_part_index = min(
        source.dimension_part_index,
        max(0, len(target.dimension_parts) - 1),
    )


def _fill_preview(settings, records):
    settings.preview_items.clear()
    for record in records:
        item = settings.preview_items.add()
        item.object_ref = record.obj
        item.old_name = record.old_name
        item.new_name = record.new_name
        item.status = record.status
        item.message = record.message
    settings.preview_index = 0
    settings.last_target_count = sum(
        record.status == naming.STATUS_OK for record in records
    )


def _selected_preset(settings):
    if settings.selected_preset == "__NONE__":
        return None
    return preset_utils.find_preset(
        preset_utils.load_presets(),
        settings.selected_preset,
    )


def _active_preview_item(settings):
    if not settings.preview_items:
        return None
    index = min(settings.preview_index, len(settings.preview_items) - 1)
    return settings.preview_items[index]


def _active_preview_name(settings):
    item = _active_preview_item(settings)
    return item.new_name if item is not None else ""


def _all_preview_names_text(settings):
    return "\n".join(
        item.new_name
        for item in settings.preview_items
        if item.new_name
    )


class MAR_OT_add_module(Operator):
    bl_idname = "mar.add_module"
    bl_label = "Add Naming Module"
    bl_options = {"REGISTER", "UNDO"}

    module_type: EnumProperty(name="Module Type", items=MODULE_TYPE_ITEMS)

    def execute(self, context):
        settings = _settings(context)
        module = settings.modules.add()
        _initialize_module(module, self.module_type)
        settings.module_index = len(settings.modules) - 1
        settings.preview_items.clear()
        return {"FINISHED"}


class MAR_OT_remove_module(Operator):
    bl_idname = "mar.remove_module"
    bl_label = "Remove Module"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = _settings(context)
        if not settings.modules:
            return {"CANCELLED"}
        settings.modules.remove(settings.module_index)
        settings.module_index = min(
            settings.module_index,
            max(0, len(settings.modules) - 1),
        )
        settings.preview_items.clear()
        return {"FINISHED"}


class MAR_OT_move_module(Operator):
    bl_idname = "mar.move_module"
    bl_label = "Move Module"
    bl_options = {"REGISTER", "UNDO"}

    direction: EnumProperty(
        items=(("UP", "Up", "Move up"), ("DOWN", "Down", "Move down"))
    )

    def execute(self, context):
        settings = _settings(context)
        index = settings.module_index
        target = index - 1 if self.direction == "UP" else index + 1
        if not (0 <= index < len(settings.modules) and 0 <= target < len(settings.modules)):
            return {"CANCELLED"}
        settings.modules.move(index, target)
        settings.module_index = target
        settings.preview_items.clear()
        return {"FINISHED"}


class MAR_OT_duplicate_module(Operator):
    bl_idname = "mar.duplicate_module"
    bl_label = "Duplicate Module"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = _settings(context)
        source = _active_module(settings)
        if source is None:
            return {"CANCELLED"}
        target = settings.modules.add()
        _copy_module(source, target)
        new_index = len(settings.modules) - 1
        settings.modules.move(new_index, settings.module_index + 1)
        settings.module_index += 1
        settings.preview_items.clear()
        return {"FINISHED"}


class MAR_OT_toggle_module(Operator):
    bl_idname = "mar.toggle_module"
    bl_label = "Enable / Disable Module"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = _settings(context)
        module = _active_module(settings)
        if module is None:
            return {"CANCELLED"}
        module.enabled = not module.enabled
        settings.preview_items.clear()
        return {"FINISHED"}


class MAR_OT_set_separator(Operator):
    bl_idname = "mar.set_separator"
    bl_label = "Set Separator"
    bl_options = {"REGISTER", "UNDO"}

    value: StringProperty(name="Separator", default="")

    def execute(self, context):
        module = _active_module(_settings(context))
        if module is None:
            return {"CANCELLED"}
        module.separator_after = self.value
        return {"FINISHED"}


class MAR_OT_add_choice_option(Operator):
    bl_idname = "mar.add_choice_option"
    bl_label = "Add Option"
    bl_options = {"REGISTER", "UNDO"}

    module_id: StringProperty(name="Module ID", default="")

    def execute(self, context):
        module = _active_or_target_module(_settings(context), self.module_id)
        if module is None or module.module_type != "CHOICE":
            return {"CANCELLED"}
        option = module.choice_options.add()
        option.option_id = preset_utils.new_choice_option_id()
        option.option_value = preset_utils.new_option_value()
        option.value = f"Option {len(module.choice_options)}"
        module.choice_option_index = len(module.choice_options) - 1
        module.choice_current = option.option_id
        return {"FINISHED"}


class MAR_OT_remove_choice_option(Operator):
    bl_idname = "mar.remove_choice_option"
    bl_label = "Remove Option"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        module = _active_module(_settings(context))
        if module is None or not module.choice_options:
            return {"CANCELLED"}
        if len(module.choice_options) == 1:
            self.report({"ERROR"}, "Choice must contain at least one option.")
            return {"CANCELLED"}
        index = min(module.choice_option_index, len(module.choice_options) - 1)
        removed_id = module.choice_options[index].option_id
        current = module.choice_current
        module.choice_options.remove(index)
        module.choice_option_index = min(
            index,
            max(0, len(module.choice_options) - 1),
        )
        if current == removed_id:
            module.choice_current = (
                module.choice_options[module.choice_option_index].option_id
                if module.choice_options
                else "__NONE__"
            )
        return {"FINISHED"}


class MAR_OT_move_choice_option(Operator):
    bl_idname = "mar.move_choice_option"
    bl_label = "Move Option"
    bl_options = {"REGISTER", "UNDO"}

    direction: EnumProperty(
        items=(("UP", "Up", "Move up"), ("DOWN", "Down", "Move down"))
    )

    def execute(self, context):
        module = _active_module(_settings(context))
        if module is None:
            return {"CANCELLED"}
        index = module.choice_option_index
        target = index - 1 if self.direction == "UP" else index + 1
        if not (
            0 <= index < len(module.choice_options)
            and 0 <= target < len(module.choice_options)
        ):
            return {"CANCELLED"}
        current = preset_utils.safe_choice_current(module)
        module.choice_options.move(index, target)
        module.choice_option_index = target
        option_ids = {option.option_id for option in module.choice_options}
        if current in option_ids:
            module.choice_current = current
        return {"FINISHED"}


class MAR_OT_add_dimension_part(Operator):
    bl_idname = "mar.add_dimension_part"
    bl_label = "Add Dimension Part"
    bl_options = {"REGISTER", "UNDO"}

    axis: EnumProperty(name="Dimension", items=DIMENSION_AXIS_ITEMS, default="X")

    def execute(self, context):
        settings = _settings(context)
        module = _active_module(settings)
        if module is None or module.module_type != "DIMENSIONS":
            return {"CANCELLED"}
        _add_dimension_part(module, self.axis)
        module.dimension_part_index = len(module.dimension_parts) - 1
        module.dimension_parts_migrated = True
        settings.preview_items.clear()
        return {"FINISHED"}


class MAR_OT_remove_dimension_part(Operator):
    bl_idname = "mar.remove_dimension_part"
    bl_label = "Remove Dimension Part"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = _settings(context)
        module = _active_module(settings)
        if (
            module is None
            or module.module_type != "DIMENSIONS"
            or not module.dimension_parts
        ):
            return {"CANCELLED"}
        index = min(
            module.dimension_part_index,
            len(module.dimension_parts) - 1,
        )
        module.dimension_parts.remove(index)
        module.dimension_part_index = min(
            index,
            max(0, len(module.dimension_parts) - 1),
        )
        module.dimension_parts_migrated = True
        settings.preview_items.clear()
        return {"FINISHED"}


class MAR_OT_move_dimension_part(Operator):
    bl_idname = "mar.move_dimension_part"
    bl_label = "Move Dimension Part"
    bl_options = {"REGISTER", "UNDO"}

    direction: EnumProperty(
        items=(("UP", "Up", "Move up"), ("DOWN", "Down", "Move down"))
    )

    def execute(self, context):
        settings = _settings(context)
        module = _active_module(settings)
        if module is None or module.module_type != "DIMENSIONS":
            return {"CANCELLED"}
        index = module.dimension_part_index
        target = index - 1 if self.direction == "UP" else index + 1
        if not (
            0 <= index < len(module.dimension_parts)
            and 0 <= target < len(module.dimension_parts)
        ):
            return {"CANCELLED"}
        module.dimension_parts.move(index, target)
        module.dimension_part_index = target
        settings.preview_items.clear()
        return {"FINISHED"}


class MAR_OT_repair_choice_modules(Operator):
    bl_idname = "mar.repair_choice_modules"
    bl_label = "Repair Choice Data"
    bl_options = {"REGISTER", "UNDO"}

    module_id: StringProperty(name="Module ID", default="")

    def execute(self, context):
        settings = _settings(context)
        if self.module_id:
            module = _module_by_id(settings, self.module_id)
            if module is None:
                self.report({"ERROR"}, "Choice module not found.")
                return {"CANCELLED"}
            changed = preset_utils.repair_choice_module(module)
            count = 1 if changed else 0
        else:
            count = sum(
                1
                for module in settings.modules
                if preset_utils.repair_choice_module(module)
            )
        self.report({"INFO"}, f"Repaired {count} choice module(s).")
        return {"FINISHED"}


class MAR_OT_preview(Operator):
    bl_idname = "mar.preview"
    bl_label = "Preview Selected"

    def execute(self, context):
        settings = _settings(context)
        preset_utils.repair_settings(settings)
        records, warning = naming.build_rename_plan(context, settings)
        _fill_preview(settings, records)
        settings.last_warning = warning
        if not records:
            self.report({"WARNING"}, "No selected objects.")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Previewed {len(records)} selected object(s).")
        return {"FINISHED"}


class MAR_OT_apply(Operator):
    bl_idname = "mar.apply"
    bl_label = "Apply Rename"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        if len(context.selected_objects) > 1000:
            return context.window_manager.invoke_confirm(
                self,
                event,
                message=(
                    f"You are about to rename {len(context.selected_objects)} "
                    "objects. Continue?"
                ),
            )
        return self.execute(context)

    def execute(self, context):
        settings = _settings(context)
        preset_utils.repair_settings(settings)
        records, warning = naming.build_rename_plan(context, settings)
        settings.last_warning = warning
        valid = [record for record in records if record.status == naming.STATUS_OK]
        _fill_preview(settings, records)
        if not records:
            self.report({"WARNING"}, "No selected objects.")
            return {"CANCELLED"}
        if not valid:
            self.report({"WARNING"}, "No objects can be renamed. Check Preview.")
            return {"CANCELLED"}

        settings.history_items.clear()
        object_records = [record for record in valid if record.rename_object]
        mesh_records = [record for record in valid if record.rename_mesh]

        for record in object_records:
            item = settings.history_items.add()
            item.item_type = "OBJECT"
            item.object_ref = record.obj
            item.old_name = record.obj.name
            item.new_name = record.new_name
            if settings.store_original_name:
                record.obj["original_name_before_modular_renamer"] = record.obj.name

        for record in mesh_records:
            mesh = record.obj.data
            item = settings.history_items.add()
            item.item_type = "MESH"
            item.mesh_ref = mesh
            item.old_name = mesh.name
            item.new_name = record.new_name
            if settings.store_original_name:
                mesh["original_name_before_modular_renamer"] = mesh.name

        operation_id = uuid.uuid4().hex
        window_manager = context.window_manager
        total = len(object_records) + len(mesh_records)
        window_manager.progress_begin(0, max(1, total))
        try:
            for index, record in enumerate(object_records):
                record.obj.name = f"__MAR_OBJECT_{operation_id}_{index}"
            for index, record in enumerate(mesh_records):
                record.obj.data.name = f"__MAR_MESH_{operation_id}_{index}"

            progress = 0
            for record in object_records:
                record.obj.name = record.new_name
                record.new_name = record.obj.name
                progress += 1
                window_manager.progress_update(progress)
            for record in mesh_records:
                record.obj.data.name = record.new_name
                if not record.rename_object:
                    record.new_name = record.obj.data.name
                progress += 1
                window_manager.progress_update(progress)
        finally:
            window_manager.progress_end()

        for item in settings.history_items:
            if item.item_type == "OBJECT" and item.object_ref is not None:
                item.new_name = item.object_ref.name
            elif item.item_type == "MESH" and item.mesh_ref is not None:
                item.new_name = item.mesh_ref.name

        _fill_preview(settings, records)
        self.report(
            {"INFO"},
            f"Renamed {len(object_records)} object(s) and {len(mesh_records)} mesh data-block(s).",
        )
        return {"FINISHED"}


class MAR_OT_revert(Operator):
    bl_idname = "mar.revert"
    bl_label = "Revert Last Rename"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = _settings(context)
        history = list(settings.history_items)
        if not history:
            self.report({"WARNING"}, "No rename history is available.")
            return {"CANCELLED"}

        operation_id = uuid.uuid4().hex
        restored = 0
        for index, item in enumerate(history):
            if item.item_type == "OBJECT" and item.object_ref is not None:
                item.object_ref.name = f"__MAR_REVERT_OBJECT_{operation_id}_{index}"
            elif item.item_type == "MESH" and item.mesh_ref is not None:
                item.mesh_ref.name = f"__MAR_REVERT_MESH_{operation_id}_{index}"

        for item in history:
            if item.item_type == "OBJECT" and item.object_ref is not None:
                item.object_ref.name = item.old_name
                restored += 1
            elif item.item_type == "MESH" and item.mesh_ref is not None:
                item.mesh_ref.name = item.old_name
                restored += 1

        settings.history_items.clear()
        settings.preview_items.clear()
        settings.last_warning = ""
        self.report({"INFO"}, f"Restored {restored} name(s).")
        return {"FINISHED"}


class MAR_OT_clear_preview(Operator):
    bl_idname = "mar.clear_preview"
    bl_label = "Clear Preview"

    def execute(self, context):
        settings = _settings(context)
        settings.preview_items.clear()
        settings.last_target_count = 0
        return {"FINISHED"}


class MAR_OT_copy_preview_name(Operator):
    bl_idname = "mar.copy_preview_name"
    bl_label = "Copy Preview Name"

    def execute(self, context):
        name = _active_preview_name(_settings(context))
        if not name:
            self.report({"ERROR"}, "The selected preview name is empty.")
            return {"CANCELLED"}
        context.window_manager.clipboard = name
        self.report({"INFO"}, f"Copied preview name: {name}")
        return {"FINISHED"}


class MAR_OT_copy_all_preview_names(Operator):
    bl_idname = "mar.copy_all_preview_names"
    bl_label = "Copy All Preview Names"

    def execute(self, context):
        settings = _settings(context)
        text = _all_preview_names_text(settings)
        if not text:
            self.report({"ERROR"}, "No preview names are available to copy.")
            return {"CANCELLED"}
        context.window_manager.clipboard = text
        count = sum(bool(item.new_name) for item in settings.preview_items)
        self.report({"INFO"}, f"Copied {count} preview name(s).")
        return {"FINISHED"}


class MAR_OT_select_preview_name_matches(Operator):
    bl_idname = "mar.select_preview_name_matches"
    bl_label = "Select Same Name"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        item = _active_preview_item(_settings(context))
        if item is None or not item.new_name:
            self.report({"ERROR"}, "The selected preview name is empty.")
            return {"CANCELLED"}

        target_name = item.new_name
        source = item.object_ref
        source_mesh = (
            source.data
            if source is not None and source.type == "MESH"
            else None
        )
        matches = []
        for obj in context.view_layer.objects:
            object_match = obj != source and obj.name == target_name
            mesh_match = (
                obj.type == "MESH"
                and obj.data is not None
                and obj.data != source_mesh
                and obj.data.name == target_name
            )
            if object_match or mesh_match:
                matches.append(obj)

        if not matches:
            self.report(
                {"WARNING"},
                f"No Object or Mesh uses the name '{target_name}' in this View Layer.",
            )
            return {"CANCELLED"}

        previous_selected = list(context.selected_objects)
        previous_active = context.view_layer.objects.active
        for obj in previous_selected:
            obj.select_set(False)

        selected = []
        for obj in matches:
            try:
                obj.select_set(True)
            except RuntimeError:
                continue
            if obj.select_get():
                selected.append(obj)

        context.view_layer.objects.active = selected[0] if selected else None
        if not selected:
            for obj in previous_selected:
                try:
                    obj.select_set(True)
                except RuntimeError:
                    continue
            context.view_layer.objects.active = previous_active
            self.report(
                {"WARNING"},
                f"No selectable Object or Mesh uses the name '{target_name}'.",
            )
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            f"Selected {len(selected)} object(s) matching '{target_name}'.",
        )
        return {"FINISHED"}


class MAR_OT_clear_history(Operator):
    bl_idname = "mar.clear_history"
    bl_label = "Clear Rename History"

    def execute(self, context):
        _settings(context).history_items.clear()
        return {"FINISHED"}


class MAR_OT_load_preset(Operator):
    bl_idname = "mar.load_preset"
    bl_label = "Load Preset"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = _settings(context)
        preset = _selected_preset(settings)
        if preset is None:
            self.report({"ERROR"}, "Preset not found.")
            return {"CANCELLED"}
        try:
            preset_utils.load_preset_into_settings(settings, preset)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        settings.preset_name = preset["name"]
        self.report({"INFO"}, f"Loaded preset '{preset['name']}'.")
        return {"FINISHED"}


class MAR_OT_save_preset(Operator):
    bl_idname = "mar.save_preset"
    bl_label = "Save Preset"

    def execute(self, context):
        settings = _settings(context)
        preset = _selected_preset(settings)
        if preset is None:
            self.report({"ERROR"}, "Select a preset or use Save As New.")
            return {"CANCELLED"}
        name = preset["name"]
        try:
            preset_utils.repair_settings(settings)
            presets = preset_utils.upsert_preset(
                preset_utils.load_presets(),
                preset_utils.settings_to_preset(settings, name),
            )
            preset_utils.save_presets(presets)
            settings.selected_preset = name
            settings.preset_name = name
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Saved preset '{name}'.")
        return {"FINISHED"}


class MAR_OT_save_preset_as(Operator):
    bl_idname = "mar.save_preset_as"
    bl_label = "Save As New"

    preset_name: StringProperty(name="Preset Name", default="")

    def invoke(self, context, _event):
        self.preset_name = _settings(context).preset_name
        return context.window_manager.invoke_props_dialog(self, width=360)

    def draw(self, _context):
        self.layout.prop(self, "preset_name")

    def execute(self, context):
        settings = _settings(context)
        name = self.preset_name.strip()
        if not name:
            self.report({"ERROR"}, "Preset name is empty.")
            return {"CANCELLED"}
        try:
            existing = preset_utils.load_presets()
            if preset_utils.find_preset(existing, name) is not None:
                self.report(
                    {"ERROR"},
                    "A preset with this name already exists. Use Save to update it.",
                )
                return {"CANCELLED"}
            preset_utils.repair_settings(settings)
            presets = preset_utils.upsert_preset(
                existing,
                preset_utils.settings_to_preset(settings, name),
            )
            preset_utils.save_presets(presets)
            settings.selected_preset = name
            settings.preset_name = name
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Saved preset '{name}'.")
        return {"FINISHED"}


class MAR_OT_delete_preset(Operator):
    bl_idname = "mar.delete_preset"
    bl_label = "Delete Preset"

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        settings = _settings(context)
        name = settings.selected_preset
        presets = preset_utils.load_presets()
        if name == "__NONE__" or preset_utils.find_preset(presets, name) is None:
            self.report({"ERROR"}, "Preset not found.")
            return {"CANCELLED"}
        remaining = preset_utils.delete_preset(presets, name)
        preset_utils.save_presets(remaining)
        settings.selected_preset = remaining[0]["name"] if remaining else "__NONE__"
        settings.preset_name = ""
        self.report({"INFO"}, f"Deleted preset '{name}'.")
        return {"FINISHED"}


class MAR_OT_import_presets(Operator, ImportHelper):
    bl_idname = "mar.import_presets"
    bl_label = "Import JSON"

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    def execute(self, context):
        try:
            imported = preset_utils.read_preset_file(self.filepath)
            merged = preset_utils.merge_presets(
                preset_utils.load_presets(),
                imported,
            )
            preset_utils.save_presets(merged)
            if imported:
                settings = _settings(context)
                settings.selected_preset = imported[0]["name"]
                settings.preset_name = imported[0]["name"]
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Imported {len(imported)} preset(s).")
        return {"FINISHED"}


class MAR_OT_export_presets(Operator, ExportHelper):
    bl_idname = "mar.export_presets"
    bl_label = "Export JSON"

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    def invoke(self, context, event):
        if not self.filepath:
            self.filepath = "modular_asset_renamer_presets.json"
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
