import json
import os
import re
import uuid

import bpy


SCHEMA_VERSION = 1
USER_PRESET_PATH_OVERRIDE = None
MODULE_TYPES = {
    "TEXT",
    "CHOICE",
    "DIMENSIONS",
    "INDEX",
    "ORIGINAL_NAME",
    "COLLECTION_NAME",
}
AXIS_ORDERS = {"XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX"}
DIMENSION_UNITS = {"M", "CM", "MM"}
ROUND_MODES = {"ROUND", "FLOOR", "CEIL"}
SORT_MODES = {
    "SELECTION",
    "NAME_ASC",
    "NAME_DESC",
    "LOCATION_X",
    "LOCATION_Y",
    "LOCATION_Z",
}
ORIGINAL_MODES = {"FULL", "STRIP", "SPLIT"}
COLLECTION_SOURCES = {"FIRST", "ACTIVE", "PARENT"}
OPTION_FIELDS = (
    "rename_object",
    "rename_mesh_data",
    "strip_blender_numeric_suffix",
    "auto_resolve_duplicates",
    "error_if_name_exists",
    "store_original_name",
    "rename_only_mesh_objects",
    "skip_hidden_objects",
    "skip_locked_objects",
    "replace_spaces",
    "remove_invalid_characters",
)
SAFE_CHOICE_ID_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
UNSAFE_CHOICE_ID_CHARACTER_PATTERN = re.compile(r"[^A-Za-z0-9_]")


def new_id():
    return uuid.uuid4().hex


def new_choice_option_id():
    return f"option_{new_id()}"


def new_option_value():
    return int(uuid.uuid4().hex[:7], 16) + 1


def unique_choice_option_value(existing):
    value = new_option_value()
    while value in existing:
        value = new_option_value()
    return value


def safe_choice_option_id(raw_id, fallback=None):
    value = str(raw_id or "").strip()
    value = UNSAFE_CHOICE_ID_CHARACTER_PATTERN.sub("_", value)
    if not value:
        value = str(fallback or new_choice_option_id())
    if not SAFE_CHOICE_ID_PATTERN.match(value):
        value = f"option_{value}"
    return value


def unique_choice_option_id(raw_id, existing):
    base = safe_choice_option_id(raw_id)
    candidate = base
    suffix = 2
    while candidate in existing:
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


def safe_choice_current(module):
    try:
        return module.choice_current
    except Exception:
        return ""


def repair_choice_module(module):
    if module.module_type != "CHOICE":
        return False

    changed = False
    seen_ids = set()
    seen_values = set()
    option_id_map = {}
    for option in module.choice_options:
        old_id = option.option_id
        new_id = unique_choice_option_id(old_id, seen_ids)
        seen_ids.add(new_id)
        option_id_map[old_id] = new_id
        if old_id != new_id:
            option.option_id = new_id
            changed = True

        old_value = option.option_value
        if old_value < 1 or old_value in seen_values:
            option.option_value = unique_choice_option_value(seen_values)
            changed = True
        seen_values.add(option.option_value)

    current = safe_choice_current(module)
    if current in option_id_map:
        desired = option_id_map[current]
    else:
        option_ids = [option.option_id for option in module.choice_options]
        desired = (
            current
            if current in option_ids
            else (option_ids[0] if option_ids else "__NONE__")
        )

    if desired != current:
        module.choice_current = desired
        changed = True
    return changed


def repair_settings(settings):
    changed = False
    for module in settings.modules:
        changed = repair_choice_module(module) or changed
    return changed


def user_preset_path():
    if USER_PRESET_PATH_OVERRIDE:
        return USER_PRESET_PATH_OVERRIDE
    directory = bpy.utils.user_resource(
        "CONFIG",
        path="modular_asset_renamer",
        create=True,
    )
    return os.path.join(directory, "presets.json")


def _require_type(value, expected, label):
    if not isinstance(value, expected):
        raise ValueError(f"{label} has an invalid type.")
    return value


def _normalize_module(raw_module):
    _require_type(raw_module, dict, "Module")
    module_type = str(raw_module.get("module_type", ""))
    if module_type not in MODULE_TYPES:
        raise ValueError(f"Unsupported module type: {module_type}")

    module_id = str(raw_module.get("module_id", "")).strip()
    if not module_id:
        raise ValueError("Module ID is empty.")

    raw_options = raw_module.get("choice_options", [])
    _require_type(raw_options, list, "Choice options")
    choice_options = []
    seen_raw_option_ids = set()
    seen_option_ids = set()
    option_id_map = {}
    for raw_option in raw_options:
        _require_type(raw_option, dict, "Choice option")
        raw_option_id = str(raw_option.get("option_id", "")).strip()
        if not raw_option_id:
            raise ValueError("Choice option ID is empty.")
        if raw_option_id in seen_raw_option_ids:
            raise ValueError(f"Duplicate choice option ID: {raw_option_id}")
        seen_raw_option_ids.add(raw_option_id)
        option_id = unique_choice_option_id(raw_option_id, seen_option_ids)
        seen_option_ids.add(option_id)
        option_id_map[raw_option_id] = option_id
        choice_options.append(
            {
                "option_id": option_id,
                "option_value": int(
                    raw_option.get("option_value", new_option_value())
                ),
                "value": str(raw_option.get("value", "")),
            }
        )
    option_values = [option["option_value"] for option in choice_options]
    if any(value < 1 for value in option_values):
        raise ValueError("Choice option values must be positive integers.")
    if len(option_values) != len(set(option_values)):
        raise ValueError("Choice option values must be unique within a module.")

    raw_choice_current = str(raw_module.get("choice_current", "")).strip()
    normalized = {
        "module_id": module_id,
        "module_type": module_type,
        "enabled": bool(raw_module.get("enabled", True)),
        "display_name": str(raw_module.get("display_name", "")),
        "separator_after": str(raw_module.get("separator_after", "_")),
        "text_value": str(raw_module.get("text_value", "")),
        "choice_label": str(raw_module.get("choice_label", "Choice")),
        "choice_options": choice_options,
        "choice_current": option_id_map.get(raw_choice_current, raw_choice_current),
        "axis_order": str(raw_module.get("axis_order", "XYZ")),
        "dimension_unit": str(raw_module.get("dimension_unit", "CM")),
        "axis_separator": str(raw_module.get("axis_separator", "x")),
        "decimal_places": int(raw_module.get("decimal_places", 0)),
        "round_mode": str(raw_module.get("round_mode", "ROUND")),
        "add_unit_suffix": bool(raw_module.get("add_unit_suffix", True)),
        "add_axis_labels": bool(raw_module.get("add_axis_labels", False)),
        "remove_trailing_zeros": bool(raw_module.get("remove_trailing_zeros", False)),
        "start_number": int(raw_module.get("start_number", 1)),
        "padding": int(raw_module.get("padding", 3)),
        "sort_mode": str(raw_module.get("sort_mode", "SELECTION")),
        "original_mode": str(raw_module.get("original_mode", "FULL")),
        "original_strip_suffix": bool(raw_module.get("original_strip_suffix", False)),
        "original_delimiter": str(raw_module.get("original_delimiter", "_")),
        "original_part_index": int(raw_module.get("original_part_index", 1)),
        "collection_source": str(raw_module.get("collection_source", "FIRST")),
        "collection_strip_suffix": bool(
            raw_module.get("collection_strip_suffix", False)
        ),
    }
    if normalized["axis_order"] not in AXIS_ORDERS:
        raise ValueError(f"Invalid axis order: {normalized['axis_order']}")
    if normalized["dimension_unit"] not in DIMENSION_UNITS:
        raise ValueError(f"Invalid dimension unit: {normalized['dimension_unit']}")
    if normalized["round_mode"] not in ROUND_MODES:
        raise ValueError(f"Invalid round mode: {normalized['round_mode']}")
    if normalized["sort_mode"] not in SORT_MODES:
        raise ValueError(f"Invalid sort mode: {normalized['sort_mode']}")
    if normalized["original_mode"] not in ORIGINAL_MODES:
        raise ValueError(f"Invalid original-name mode: {normalized['original_mode']}")
    if normalized["collection_source"] not in COLLECTION_SOURCES:
        raise ValueError(
            f"Invalid collection source: {normalized['collection_source']}"
        )
    if not 0 <= normalized["decimal_places"] <= 4:
        raise ValueError("Decimal places must be between 0 and 4.")
    if not 1 <= normalized["padding"] <= 12:
        raise ValueError("Index padding must be between 1 and 12.")
    if normalized["original_part_index"] < 1:
        raise ValueError("Original-name part index must be 1 or greater.")
    option_ids = {option["option_id"] for option in choice_options}
    if module_type == "CHOICE":
        if not choice_options:
            raise ValueError("Choice module must contain at least one option.")
        if normalized["choice_current"] in {"", "__NONE__"}:
            raise ValueError("Current choice option is empty.")
    if (
        normalized["choice_current"]
        and normalized["choice_current"] != "__NONE__"
        and normalized["choice_current"] not in option_ids
    ):
        raise ValueError("Current choice option does not exist in the option list.")
    return normalized


def _normalize_preset(raw_preset):
    _require_type(raw_preset, dict, "Preset")
    name = str(raw_preset.get("name", "")).strip()
    if not name:
        raise ValueError("Preset name is empty.")
    raw_modules = raw_preset.get("modules")
    _require_type(raw_modules, list, f"Preset '{name}' modules")
    modules = [_normalize_module(module) for module in raw_modules]
    module_ids = [module["module_id"] for module in modules]
    if len(module_ids) != len(set(module_ids)):
        raise ValueError(f"Preset '{name}' contains duplicate module IDs.")

    raw_options = raw_preset.get("options")
    _require_type(raw_options, dict, f"Preset '{name}' options")
    options = {
        field: bool(raw_options.get(field, True if field in {
            "rename_object",
            "rename_mesh_data",
            "strip_blender_numeric_suffix",
            "auto_resolve_duplicates",
            "store_original_name",
            "replace_spaces",
            "remove_invalid_characters",
        } else False))
        for field in OPTION_FIELDS
    }
    return {"name": name, "modules": modules, "options": options}


def validate_payload(payload):
    _require_type(payload, dict, "Preset JSON root")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Unsupported preset schema: {payload.get('schema_version')}")
    raw_presets = payload.get("presets")
    _require_type(raw_presets, list, "'presets'")

    presets = []
    names = set()
    for raw_preset in raw_presets:
        preset = _normalize_preset(raw_preset)
        if preset["name"] in names:
            raise ValueError(f"Duplicate preset name: {preset['name']}")
        names.add(preset["name"])
        presets.append(preset)
    return presets


def read_preset_file(filepath):
    with open(filepath, "r", encoding="utf-8") as handle:
        return validate_payload(json.load(handle))


def write_preset_file(filepath, presets):
    validated = validate_payload(
        {"schema_version": SCHEMA_VERSION, "presets": presets}
    )
    parent = os.path.dirname(filepath)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(filepath, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(
            {"schema_version": SCHEMA_VERSION, "presets": validated},
            handle,
            ensure_ascii=False,
            indent=2,
        )
        handle.write("\n")


def load_presets(filepath=None):
    filepath = filepath or user_preset_path()
    if not os.path.exists(filepath):
        return []
    return read_preset_file(filepath)


def save_presets(presets, filepath=None):
    write_preset_file(filepath or user_preset_path(), presets)


def find_preset(presets, name):
    return next((preset for preset in presets if preset["name"] == name), None)


def upsert_preset(presets, preset):
    normalized = _normalize_preset(preset)
    result = [item for item in presets if item["name"] != normalized["name"]]
    result.append(normalized)
    result.sort(key=lambda item: item["name"].casefold())
    return result


def delete_preset(presets, name):
    return [preset for preset in presets if preset["name"] != name]


def merge_presets(existing, imported):
    merged = list(existing)
    for preset in imported:
        merged = upsert_preset(merged, preset)
    return merged


def module_to_dict(module):
    return {
        "module_id": module.module_id,
        "module_type": module.module_type,
        "enabled": module.enabled,
        "display_name": module.display_name,
        "separator_after": module.separator_after,
        "text_value": module.text_value,
        "choice_label": module.choice_label,
        "choice_options": [
            {
                "option_id": option.option_id,
                "option_value": option.option_value,
                "value": option.value,
            }
            for option in module.choice_options
        ],
        "choice_current": safe_choice_current(module),
        "axis_order": module.axis_order,
        "dimension_unit": module.dimension_unit,
        "axis_separator": module.axis_separator,
        "decimal_places": module.decimal_places,
        "round_mode": module.round_mode,
        "add_unit_suffix": module.add_unit_suffix,
        "add_axis_labels": module.add_axis_labels,
        "remove_trailing_zeros": module.remove_trailing_zeros,
        "start_number": module.start_number,
        "padding": module.padding,
        "sort_mode": module.sort_mode,
        "original_mode": module.original_mode,
        "original_strip_suffix": module.original_strip_suffix,
        "original_delimiter": module.original_delimiter,
        "original_part_index": module.original_part_index,
        "collection_source": module.collection_source,
        "collection_strip_suffix": module.collection_strip_suffix,
    }


def settings_to_preset(settings, name):
    return {
        "name": name.strip(),
        "modules": [module_to_dict(module) for module in settings.modules],
        "options": {field: getattr(settings, field) for field in OPTION_FIELDS},
    }


def load_preset_into_settings(settings, preset):
    normalized = _normalize_preset(preset)
    settings.modules.clear()
    for raw_module in normalized["modules"]:
        module = settings.modules.add()
        for field, value in raw_module.items():
            if field in {"choice_options", "choice_current"}:
                continue
            setattr(module, field, value)
        for raw_option in raw_module["choice_options"]:
            option = module.choice_options.add()
            option.option_id = raw_option["option_id"]
            option.option_value = raw_option["option_value"]
            option.value = raw_option["value"]
        current = raw_module["choice_current"]
        option_ids = {option.option_id for option in module.choice_options}
        if current in option_ids:
            module.choice_current = current
        elif module.choice_options:
            module.choice_current = module.choice_options[0].option_id
    for field, value in normalized["options"].items():
        setattr(settings, field, value)
    settings.module_index = min(
        settings.module_index,
        max(0, len(settings.modules) - 1),
    )
    settings.preview_items.clear()
