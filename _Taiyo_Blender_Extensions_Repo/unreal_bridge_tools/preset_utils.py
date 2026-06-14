import json
import os

import bpy


SCHEMA_VERSION = 1
USER_PRESET_PATH_OVERRIDE = None
VALID_SCOPES = {"direct", "recursive", "all"}
VALID_NAME_MODES = {"keep_raw", "numeric_suffix", "trim_after_dot"}
VALID_FILTER_MODES = {"include", "exclude"}


def user_preset_path():
    if USER_PRESET_PATH_OVERRIDE:
        return USER_PRESET_PATH_OVERRIDE
    directory = bpy.utils.user_resource(
        "CONFIG",
        path="unreal_bridge_tools",
        create=True,
    )
    return os.path.join(directory, "presets.json")


def _require_type(value, expected, label):
    if not isinstance(value, expected):
        raise ValueError(f"{label} has an invalid type.")
    return value


def _normalize_filter(raw_filter):
    _require_type(raw_filter, dict, "Filter")
    mode = str(raw_filter.get("mode", "include"))
    if mode not in VALID_FILTER_MODES:
        raise ValueError(f"Unsupported filter mode: {mode}")
    return {
        "mode": mode,
        "text": str(raw_filter.get("text", "")),
    }


def _normalize_preset(raw_preset):
    _require_type(raw_preset, dict, "Preset")
    name = str(raw_preset.get("name", "")).strip()
    if not name:
        raise ValueError("Preset name is empty.")

    scope = str(raw_preset.get("scope", "recursive"))
    if scope not in VALID_SCOPES:
        raise ValueError(f"Unsupported scope: {scope}")

    name_mode = str(raw_preset.get("name_mode", "keep_raw"))
    if name_mode not in VALID_NAME_MODES:
        raise ValueError(f"Unsupported name mode: {name_mode}")

    raw_filters = raw_preset.get("filters", [])
    _require_type(raw_filters, list, f"Preset '{name}' filters")

    return {
        "name": name,
        "scope": scope,
        "collection_name": str(raw_preset.get("collection_name", "")),
        "export_path": str(raw_preset.get("export_path", "")),
        "name_mode": name_mode,
        "select_visible_only": bool(raw_preset.get("select_visible_only", True)),
        "case_sensitive": bool(raw_preset.get("case_sensitive", False)),
        "filters": [_normalize_filter(item) for item in raw_filters],
    }


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


def settings_to_preset(settings, name):
    return {
        "name": name.strip(),
        "scope": settings.scope,
        "collection_name": settings.collection.name if settings.collection else "",
        "export_path": settings.export_path,
        "name_mode": settings.name_mode,
        "select_visible_only": settings.select_visible_only,
        "case_sensitive": settings.case_sensitive,
        "filters": [
            {
                "mode": item.mode,
                "text": item.text,
            }
            for item in settings.filters
        ],
    }


def load_preset_into_settings(settings, preset):
    normalized = _normalize_preset(preset)
    settings.scope = normalized["scope"]
    settings.export_path = normalized["export_path"]
    settings.name_mode = normalized["name_mode"]
    settings.select_visible_only = normalized["select_visible_only"]
    settings.case_sensitive = normalized["case_sensitive"]

    missing_collection = ""
    if normalized["collection_name"]:
        collection = bpy.data.collections.get(normalized["collection_name"])
        if collection is not None:
            settings.collection = collection
        else:
            settings.collection = None
            missing_collection = normalized["collection_name"]
    else:
        settings.collection = None

    settings.filters.clear()
    for raw_filter in normalized["filters"]:
        item = settings.filters.add()
        item.mode = raw_filter["mode"]
        item.text = raw_filter["text"]
    settings.filters_index = min(
        settings.filters_index,
        max(0, len(settings.filters) - 1),
    )
    return missing_collection
