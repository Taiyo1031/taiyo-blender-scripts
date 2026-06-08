from dataclasses import dataclass


@dataclass
class TargetRecord:
    target: object
    owners: tuple
    label: str


def _object_is_allowed(obj, settings):
    if not settings.include_hidden:
        try:
            if obj.hide_get():
                return False, "hidden"
        except Exception:
            pass
    if not settings.include_disabled_viewport and getattr(obj, "hide_viewport", False):
        return False, "disabled in viewport"
    return True, ""


def get_scope_objects(context, settings, scope_override=None):
    scope = scope_override or settings.scope
    if scope == "ACTIVE":
        objects = [context.active_object] if context.active_object else []
    elif scope == "SCENE":
        objects = list(context.scene.objects)
    else:
        objects = list(context.selected_objects)

    accepted = []
    skipped = []
    for obj in objects:
        if obj is None:
            continue
        allowed, reason = _object_is_allowed(obj, settings)
        if allowed:
            accepted.append(obj)
        else:
            skipped.append(f"[Skipped] {obj.name}: {reason}")
    return accepted, skipped


def _target_key(target):
    try:
        return target.as_pointer()
    except Exception:
        return id(target)


def get_target_records(context, settings, scope_override=None):
    objects, skipped = get_scope_objects(context, settings, scope_override=scope_override)

    if settings.target_type == "OBJECT":
        return [
            TargetRecord(target=obj, owners=(obj,), label=obj.name)
            for obj in objects
        ], skipped

    records_by_key = {}
    repeated_records = []

    if settings.target_type == "MESH":
        for obj in objects:
            if obj.type != "MESH" or obj.data is None:
                skipped.append(f"[Skipped] {obj.name}: not a Mesh object")
                continue
            mesh = obj.data
            key = _target_key(mesh)
            if settings.unique_data_only:
                record = records_by_key.get(key)
                if record is None:
                    records_by_key[key] = TargetRecord(
                        target=mesh,
                        owners=(obj,),
                        label=mesh.name,
                    )
                else:
                    record.owners = record.owners + (obj,)
            else:
                repeated_records.append(
                    TargetRecord(target=mesh, owners=(obj,), label=mesh.name)
                )
        if settings.unique_data_only:
            return list(records_by_key.values()), skipped
        return repeated_records, skipped

    for obj in objects:
        materials = [
            slot.material
            for slot in getattr(obj, "material_slots", ())
            if slot.material is not None
        ]
        if not materials:
            skipped.append(f"[Skipped] {obj.name}: no assigned material")
            continue
        for material in materials:
            key = _target_key(material)
            record = records_by_key.get(key)
            if record is None:
                records_by_key[key] = TargetRecord(
                    target=material,
                    owners=(obj,),
                    label=material.name,
                )
            elif obj not in record.owners:
                record.owners = record.owners + (obj,)

    return list(records_by_key.values()), skipped


def records_for_property_list(context, settings):
    if settings.property_list_mode == "ACTIVE_ONLY":
        return get_target_records(context, settings, scope_override="ACTIVE")
    if settings.property_list_mode == "SELECTED_SUMMARY":
        return get_target_records(context, settings, scope_override="SELECTED")
    return get_target_records(context, settings)
