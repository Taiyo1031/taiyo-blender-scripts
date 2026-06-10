import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP

import bpy


INVALID_CHARACTER_PATTERN = re.compile(r'[/\\:*?"<>|]')
BLENDER_SUFFIX_PATTERN = re.compile(r"\.\d{3}$")

STATUS_OK = "OK"
STATUS_DUPLICATE = "Duplicate"
STATUS_EMPTY = "Empty Name"
STATUS_INVALID = "Invalid Character"
STATUS_SKIPPED = "Skipped"


@dataclass
class RenameRecord:
    obj: bpy.types.Object
    old_name: str
    new_name: str = ""
    status: str = STATUS_OK
    message: str = ""
    rename_object: bool = False
    rename_mesh: bool = False


def strip_blender_numeric_suffix(value):
    return BLENDER_SUFFIX_PATTERN.sub("", value or "")


def sanitize_name(value, settings):
    result = value
    if settings.replace_spaces:
        result = re.sub(r"\s+", "_", result)
    if settings.remove_invalid_characters:
        result = INVALID_CHARACTER_PATTERN.sub("_", result)
    return result


def _format_number(value, decimal_places, round_mode, remove_trailing_zeros):
    decimal_value = Decimal(str(value))
    quantum = Decimal(1).scaleb(-decimal_places)
    scaled = decimal_value / quantum
    epsilon = (
        Decimal("1e-7")
        * max(Decimal(1), abs(scaled))
        * quantum
    )
    if round_mode == "FLOOR":
        rounded = (decimal_value + epsilon).quantize(
            quantum,
            rounding=ROUND_FLOOR,
        )
    elif round_mode == "CEIL":
        rounded = (decimal_value - epsilon).quantize(
            quantum,
            rounding=ROUND_CEILING,
        )
    else:
        rounded = decimal_value.quantize(quantum, rounding=ROUND_HALF_UP)

    text = f"{rounded:.{decimal_places}f}"
    if remove_trailing_zeros and "." in text:
        text = text.rstrip("0").rstrip(".")
    if text == "-0":
        return "0"
    return text


def _first_collection(obj):
    collections = sorted(obj.users_collection, key=lambda item: item.name.casefold())
    return collections[0] if collections else None


def _find_collection_parent(root, target):
    for child in root.children:
        if child == target:
            return root
        found = _find_collection_parent(child, target)
        if found is not None:
            return found
    return None


def collection_name_for_object(context, obj, module):
    source = module.collection_source
    collection = None
    if source == "ACTIVE":
        collection = getattr(context, "collection", None)
    else:
        first = _first_collection(obj)
        if source == "FIRST":
            collection = first
        elif source == "PARENT" and first is not None:
            collection = _find_collection_parent(context.scene.collection, first)

    value = collection.name if collection is not None else ""
    if module.collection_strip_suffix:
        value = strip_blender_numeric_suffix(value)
    return value


def _choice_value(module):
    current = module.choice_current
    for option in module.choice_options:
        if option.option_id == current:
            return option.value
    return ""


def _choice_module_error(module):
    if module.module_type != "CHOICE" or not module.enabled:
        return ""
    label = module.choice_label or "Choice"
    if not module.choice_options:
        return f"Choice module '{label}' has no options."
    current = module.choice_current
    for option in module.choice_options:
        if option.option_id == current:
            if not option.value:
                return f"Choice module '{label}' selected option is empty."
            return ""
    return f"Choice module '{label}' has no selected option."


def _dimension_module_error(module):
    if (
        module.module_type == "DIMENSIONS"
        and module.enabled
        and not module.dimension_parts
    ):
        return f"Dimensions module '{module.display_name or 'Dimensions'}' has no parts."
    return ""


def _module_configuration_error(settings):
    for module in settings.modules:
        error = _choice_module_error(module) or _dimension_module_error(module)
        if error:
            return error
    return ""


def evaluate_module(context, settings, module, obj, index_value):
    module_type = module.module_type
    if module_type == "TEXT":
        return module.text_value
    if module_type == "CHOICE":
        return _choice_value(module)
    if module_type == "DIMENSIONS":
        axis_values = {
            "X": obj.dimensions.x,
            "Y": obj.dimensions.y,
            "Z": obj.dimensions.z,
        }
        multiplier = {"M": 1.0, "CM": 100.0, "MM": 1000.0}[module.dimension_unit]
        unit_suffix = {"M": "m", "CM": "cm", "MM": "mm"}[module.dimension_unit]
        values = []
        for part in module.dimension_parts:
            axis = part.axis
            if axis == "LARGEST":
                axis = max(("X", "Y", "Z"), key=lambda item: axis_values[item])
            text = _format_number(
                axis_values[axis] * multiplier,
                module.decimal_places,
                module.round_mode,
                module.remove_trailing_zeros,
            )
            values.append(
                f"{axis}{text}" if module.add_axis_labels else text
            )
            values.append(part.separator_after)
        result = "".join(values)
        if module.add_unit_suffix:
            result += unit_suffix
        return result
    if module_type == "INDEX":
        value = module.start_number + index_value
        return f"{value:0{module.padding}d}"
    if module_type == "ORIGINAL_NAME":
        value = obj.name
        if (
            settings.strip_blender_numeric_suffix
            or module.original_strip_suffix
            or module.original_mode == "STRIP"
        ):
            value = strip_blender_numeric_suffix(value)
        if module.original_mode == "SPLIT":
            parts = value.split(module.original_delimiter) if module.original_delimiter else [value]
            part_index = module.original_part_index - 1
            return parts[part_index] if 0 <= part_index < len(parts) else ""
        return value
    if module_type == "COLLECTION_NAME":
        value = collection_name_for_object(context, obj, module)
        if settings.strip_blender_numeric_suffix:
            value = strip_blender_numeric_suffix(value)
        return value
    return ""


def module_summary(module):
    if module.module_type == "TEXT":
        return module.text_value or "(empty)"
    if module.module_type == "CHOICE":
        return f"{module.choice_label}: {_choice_value(module) or '(empty)'}"
    if module.module_type == "DIMENSIONS":
        unit = {"M": "m", "CM": "cm", "MM": "mm"}[module.dimension_unit]
        axes = "".join(
            "Max" if part.axis == "LARGEST" else part.axis
            for part in module.dimension_parts
        )
        return (
            f"{axes or '(empty)'} / {unit} / "
            f"{module.decimal_places} decimals"
        )
    if module.module_type == "INDEX":
        return f"Start {module.start_number} / Padding {module.padding}"
    if module.module_type == "ORIGINAL_NAME":
        return {
            "FULL": "Full Original Name",
            "STRIP": "Strip Numeric Suffix",
            "SPLIT": f"Part {module.original_part_index} by '{module.original_delimiter}'",
        }[module.original_mode]
    if module.module_type == "COLLECTION_NAME":
        return {
            "FIRST": "First Collection",
            "ACTIVE": "Active Collection",
            "PARENT": "Parent Collection",
        }[module.collection_source]
    return ""


def _first_index_module(settings):
    return next(
        (
            module
            for module in settings.modules
            if module.enabled and module.module_type == "INDEX"
        ),
        None,
    )


def _selection_order(context):
    selected = list(context.selected_objects)
    active = context.view_layer.objects.active
    if active in selected:
        selected.remove(active)
        selected.insert(0, active)
    return selected


def _sorted_objects(context, settings, objects):
    index_module = _first_index_module(settings)
    if index_module is None or index_module.sort_mode == "SELECTION":
        selection_positions = {
            obj.as_pointer(): index
            for index, obj in enumerate(_selection_order(context))
        }
        return sorted(
            objects,
            key=lambda obj: selection_positions.get(obj.as_pointer(), len(selection_positions)),
        )
    if index_module.sort_mode == "NAME_ASC":
        return sorted(objects, key=lambda obj: obj.name.casefold())
    if index_module.sort_mode == "NAME_DESC":
        return sorted(objects, key=lambda obj: obj.name.casefold(), reverse=True)
    axis = {"LOCATION_X": 0, "LOCATION_Y": 1, "LOCATION_Z": 2}[index_module.sort_mode]
    return sorted(objects, key=lambda obj: (obj.matrix_world.translation[axis], obj.name.casefold()))


def _is_editable(data_block):
    if data_block is None:
        return False
    return bool(getattr(data_block, "is_editable", getattr(data_block, "library", None) is None))


def _filter_reason(obj, settings):
    if not settings.rename_object and not settings.rename_mesh_data:
        return "Both rename options are disabled."
    if settings.rename_only_mesh_objects and obj.type != "MESH":
        return "Not a mesh object."
    if settings.skip_hidden_objects and (obj.hide_get() or obj.hide_viewport):
        return "Hidden object."
    if settings.skip_locked_objects and obj.hide_select:
        return "Selection-locked object."
    if settings.rename_object and not _is_editable(obj):
        return "Object is linked or read-only."
    if settings.rename_mesh_data and not settings.rename_object:
        if obj.type != "MESH" or obj.data is None:
            return "Object has no mesh data to rename."
        if not _is_editable(obj.data):
            return "Mesh data is linked or read-only."
    return ""


def _build_raw_name(context, settings, obj, index_value):
    parts = []
    for module in settings.modules:
        if not module.enabled:
            continue
        output = evaluate_module(context, settings, module, obj, index_value)
        parts.append(output)
        parts.append(module.separator_after)
    return "".join(parts)


def _allocate_unique_name(base_name, reserved):
    if base_name not in reserved:
        return base_name
    suffix = 1
    while True:
        candidate = f"{base_name}_{suffix:03d}"
        if candidate not in reserved:
            return candidate
        suffix += 1


def _assign_mesh_ownership(records, settings):
    claimed_meshes = set()
    shared_count = 0
    for record in records:
        if record.status != STATUS_OK:
            continue
        record.rename_object = settings.rename_object
        if (
            settings.rename_mesh_data
            and record.obj.type == "MESH"
            and record.obj.data is not None
            and _is_editable(record.obj.data)
        ):
            pointer = record.obj.data.as_pointer()
            if pointer not in claimed_meshes:
                claimed_meshes.add(pointer)
                record.rename_mesh = True
            else:
                shared_count += 1
        if not record.rename_object and not record.rename_mesh:
            record.status = STATUS_SKIPPED
            record.message = "Shared mesh data is already handled by an earlier object."
    return shared_count


def _apply_duplicate_policy(records, settings):
    valid = [record for record in records if record.status == STATUS_OK]
    if settings.auto_resolve_duplicates and not settings.error_if_name_exists:
        reserved = set()
        valid_objects = {
            record.obj.as_pointer()
            for record in valid
            if record.rename_object
        }
        valid_meshes = {
            record.obj.data.as_pointer()
            for record in valid
            if record.rename_mesh
        }
        if settings.rename_object:
            reserved.update(
                obj.name
                for obj in bpy.data.objects
                if obj.as_pointer() not in valid_objects
            )
        if settings.rename_mesh_data:
            reserved.update(
                mesh.name
                for mesh in bpy.data.meshes
                if mesh.as_pointer() not in valid_meshes
            )
        for record in valid:
            record.new_name = _allocate_unique_name(record.new_name, reserved)
            reserved.add(record.new_name)
        return

    reserved = set()
    if settings.rename_object:
        reserved.update(obj.name for obj in bpy.data.objects)
    if settings.rename_mesh_data:
        reserved.update(mesh.name for mesh in bpy.data.meshes)

    for record in valid:
        own_names = set()
        if record.rename_object:
            own_names.add(record.old_name)
        if record.rename_mesh:
            own_names.add(record.obj.data.name)
        conflict = record.new_name in (reserved - own_names)
        if conflict:
            record.status = STATUS_DUPLICATE
            record.message = "Generated name conflicts with an existing object or mesh."
            continue
        reserved.difference_update(own_names)
        reserved.add(record.new_name)


def build_rename_plan(context, settings):
    configuration_error = _module_configuration_error(settings)
    original_order = _selection_order(context)
    eligible = []
    skipped = []
    for obj in original_order:
        reason = _filter_reason(obj, settings)
        if reason:
            skipped.append(
                RenameRecord(
                    obj=obj,
                    old_name=obj.name,
                    status=STATUS_SKIPPED,
                    message=reason,
                )
            )
        else:
            eligible.append(obj)

    ordered = _sorted_objects(context, settings, eligible)
    records = []
    for index_value, obj in enumerate(ordered):
        if configuration_error:
            records.append(
                RenameRecord(
                    obj=obj,
                    old_name=obj.name,
                    status=STATUS_EMPTY,
                    message=configuration_error,
                )
            )
            continue
        raw_name = _build_raw_name(context, settings, obj, index_value)
        sanitized = sanitize_name(raw_name, settings)
        record = RenameRecord(obj=obj, old_name=obj.name, new_name=sanitized)
        if not sanitized:
            record.status = STATUS_EMPTY
            record.message = "The enabled modules generated an empty name."
        elif INVALID_CHARACTER_PATTERN.search(sanitized):
            record.status = STATUS_INVALID
            record.message = "The generated name contains an unsafe character."
        records.append(record)

    shared_count = _assign_mesh_ownership(records, settings)
    _apply_duplicate_policy(records, settings)
    records.extend(skipped)

    warnings = []
    if shared_count:
        warnings.append(
            f"{shared_count} selected object(s) share mesh data; each mesh is renamed once."
        )
    read_only_meshes = sum(
        1
        for record in records
        if (
            record.status == STATUS_OK
            and settings.rename_mesh_data
            and record.obj.type == "MESH"
            and record.obj.data is not None
            and not _is_editable(record.obj.data)
        )
    )
    if read_only_meshes:
        warnings.append(
            f"{read_only_meshes} linked/read-only mesh data-block(s) will not be renamed."
        )
    return records, " ".join(warnings)
