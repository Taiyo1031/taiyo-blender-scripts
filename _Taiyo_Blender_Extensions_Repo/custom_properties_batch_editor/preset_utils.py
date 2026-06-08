import json
import os

import bpy


SCHEMA_VERSION = 1
PROPERTY_TYPES = {"STRING", "INT", "FLOAT", "BOOL"}
USER_PRESET_PATH_OVERRIDE = None


def default_preset_path():
    return os.path.join(os.path.dirname(__file__), "presets", "default_presets.json")


def user_preset_path():
    if USER_PRESET_PATH_OVERRIDE:
        return USER_PRESET_PATH_OVERRIDE
    directory = bpy.utils.user_resource(
        "CONFIG",
        path="custom_properties_batch_editor",
        create=True,
    )
    return os.path.join(directory, "presets.json")


def _coerce_value(property_type, value):
    if property_type == "STRING":
        return str(value)
    if property_type == "INT":
        if isinstance(value, bool):
            raise ValueError("Boolean values are not valid integers.")
        return int(value)
    if property_type == "FLOAT":
        if isinstance(value, bool):
            raise ValueError("Boolean values are not valid floats.")
        return float(value)
    if property_type == "BOOL":
        if not isinstance(value, bool):
            raise ValueError("Boolean preset values must be true or false.")
        return value
    raise ValueError(f"Unsupported property type: {property_type}")


def validate_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("Preset JSON root must be an object.")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Unsupported preset schema: {payload.get('schema_version')}")
    raw_presets = payload.get("presets")
    if not isinstance(raw_presets, list):
        raise ValueError("'presets' must be an array.")

    presets = []
    seen_names = set()
    for raw_preset in raw_presets:
        if not isinstance(raw_preset, dict):
            raise ValueError("Each preset must be an object.")
        name = str(raw_preset.get("name", "")).strip()
        if not name:
            raise ValueError("Preset name is empty.")
        if name in seen_names:
            raise ValueError(f"Duplicate preset name: {name}")
        seen_names.add(name)

        raw_properties = raw_preset.get("properties")
        if not isinstance(raw_properties, list):
            raise ValueError(f"Preset '{name}' properties must be an array.")

        properties = []
        seen_properties = set()
        for raw_property in raw_properties:
            if not isinstance(raw_property, dict):
                raise ValueError(f"Preset '{name}' contains an invalid property.")
            property_name = str(raw_property.get("name", "")).strip()
            property_type = str(raw_property.get("type", "")).upper()
            if not property_name:
                raise ValueError(f"Preset '{name}' contains an empty property name.")
            if property_name == "_RNA_UI":
                raise ValueError("'_RNA_UI' is reserved by Blender.")
            if property_type not in PROPERTY_TYPES:
                raise ValueError(f"Preset '{name}' has unsupported type '{property_type}'.")
            if property_name in seen_properties:
                raise ValueError(f"Preset '{name}' repeats property '{property_name}'.")
            seen_properties.add(property_name)
            properties.append(
                {
                    "name": property_name,
                    "type": property_type,
                    "value": _coerce_value(property_type, raw_property.get("value")),
                }
            )
        presets.append({"name": name, "properties": properties})
    return presets


def read_preset_file(filepath):
    with open(filepath, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return validate_payload(payload)


def write_preset_file(filepath, presets):
    validated = validate_payload(
        {
            "schema_version": SCHEMA_VERSION,
            "presets": presets,
        }
    )
    parent = os.path.dirname(filepath)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(filepath, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(
            {
                "schema_version": SCHEMA_VERSION,
                "presets": validated,
            },
            handle,
            ensure_ascii=False,
            indent=2,
        )
        handle.write("\n")


def load_presets(filepath=None):
    filepath = filepath or user_preset_path()
    if not os.path.exists(filepath):
        presets = read_preset_file(default_preset_path())
        write_preset_file(filepath, presets)
        return presets
    return read_preset_file(filepath)


def save_presets(presets, filepath=None):
    write_preset_file(filepath or user_preset_path(), presets)


def find_preset(presets, name):
    return next((preset for preset in presets if preset["name"] == name), None)


def upsert_preset(presets, preset):
    validated = validate_payload(
        {
            "schema_version": SCHEMA_VERSION,
            "presets": [preset],
        }
    )[0]
    result = [item for item in presets if item["name"] != validated["name"]]
    result.append(validated)
    result.sort(key=lambda item: item["name"].casefold())
    return result


def delete_preset(presets, name):
    return [preset for preset in presets if preset["name"] != name]


def merge_presets(existing, imported):
    merged = list(existing)
    for preset in imported:
        merged = upsert_preset(merged, preset)
    return merged
