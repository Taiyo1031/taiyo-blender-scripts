from collections import defaultdict


RESERVED_PROPERTY_NAMES = {"_RNA_UI"}
SUPPORTED_TYPES = {"STRING", "INT", "FLOAT", "BOOL"}


def normalize_property_name(name):
    return (name or "").strip()


def validate_property_name(name):
    normalized = normalize_property_name(name)
    if not normalized:
        return False, "Property name is empty."
    if normalized in RESERVED_PROPERTY_NAMES:
        return False, f"'{normalized}' is reserved by Blender."
    return True, normalized


def get_typed_value(container, property_type, prefix=""):
    if property_type == "STRING":
        return getattr(container, f"{prefix}string_value")
    if property_type == "INT":
        return int(getattr(container, f"{prefix}int_value"))
    if property_type == "FLOAT":
        return float(getattr(container, f"{prefix}float_value"))
    if property_type == "BOOL":
        return bool(getattr(container, f"{prefix}bool_value"))
    raise ValueError(f"Unsupported property type: {property_type}")


def set_item_typed_value(item, property_type, value):
    item.property_type = property_type
    if property_type == "STRING":
        item.string_value = str(value)
    elif property_type == "INT":
        item.int_value = int(value)
    elif property_type == "FLOAT":
        item.float_value = float(value)
    elif property_type == "BOOL":
        item.bool_value = bool(value)
    else:
        raise ValueError(f"Unsupported property type: {property_type}")


def get_item_typed_value(item):
    return get_typed_value(item, item.property_type)


def property_type_name(value):
    if isinstance(value, bool):
        return "BOOL"
    if isinstance(value, int):
        return "INT"
    if isinstance(value, float):
        return "FLOAT"
    if isinstance(value, str):
        return "STRING"
    return type(value).__name__.upper()


def format_value(value, max_length=48):
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, float):
        text = f"{value:.6g}"
    else:
        text = str(value)
    if len(text) > max_length:
        return text[: max_length - 3] + "..."
    return text


def is_target_editable(target):
    if not getattr(target, "is_editable", True):
        return False
    if getattr(target, "library", None) is not None and getattr(target, "override_library", None) is None:
        return False
    return True


def has_custom_property(target, name):
    return name in target.keys()


def set_custom_property(target, name, value):
    target[name] = value


def delete_custom_property(target, name):
    del target[name]


def values_equal(actual, expected, property_type, case_sensitive=True):
    actual_type = property_type_name(actual)
    if actual_type != property_type:
        return False
    if property_type == "STRING" and not case_sensitive:
        return actual.casefold() == expected.casefold()
    return actual == expected


def property_matches(target, name, match_mode, expected=None, property_type="STRING", case_sensitive=False):
    exists = has_custom_property(target, name)
    if match_mode == "EXISTS":
        return exists
    if match_mode == "NOT_EXISTS":
        return not exists
    if not exists:
        return False

    actual = target[name]
    if match_mode == "CONTAINS":
        if not isinstance(actual, str):
            return False
        needle = str(expected)
        if case_sensitive:
            return needle in actual
        return needle.casefold() in actual.casefold()
    return values_equal(actual, expected, property_type, case_sensitive=case_sensitive)


def build_property_summaries(records):
    values_by_name = defaultdict(list)
    for record in records:
        for name in record.target.keys():
            if name in RESERVED_PROPERTY_NAMES:
                continue
            values_by_name[name].append(record.target[name])

    summaries = []
    for name in sorted(values_by_name, key=str.casefold):
        values = values_by_name[name]
        first = values[0]
        first_type = property_type_name(first)
        mixed = any(
            property_type_name(value) != first_type or value != first
            for value in values[1:]
        )
        summaries.append(
            {
                "name": name,
                "type": "MIXED" if mixed and any(property_type_name(v) != first_type for v in values[1:]) else first_type,
                "value": "Mixed" if mixed else format_value(first),
                "count": len(values),
                "mixed": mixed,
            }
        )
    return summaries
