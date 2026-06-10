import re

import bpy


LINK_PROPERTY_KEYS = (
    "LCIL_link_collection_name",
    "LCIL_link_collection_path",
    "LCIL_link_collection_color_tag",
    "LCIL_link_match_key",
    "LCIL_link_status",
    "LCIL_link_source_name_field",
)

GENERATED_KEY = "LCIL_generated"
GENERATED_KIND_KEY = "LCIL_generated_kind"
INSTANCE_KIND = "COLLECTION_INSTANCE_EMPTY"
GROUP_KIND = "GROUP_COLLECTION"
REALIZED_KIND = "REALIZED_OBJECT"

NUMERIC_SUFFIX_RE = re.compile(r"\.\d+$")

COLOR_TAG_RGBA = {
    "NONE": (0.8, 0.8, 0.8, 1.0),
    "COLOR_01": (0.55, 0.18, 0.18, 1.0),
    "COLOR_02": (0.85, 0.35, 0.12, 1.0),
    "COLOR_03": (0.85, 0.7, 0.12, 1.0),
    "COLOR_04": (0.25, 0.65, 0.2, 1.0),
    "COLOR_05": (0.15, 0.55, 0.75, 1.0),
    "COLOR_06": (0.25, 0.35, 0.8, 1.0),
    "COLOR_07": (0.55, 0.25, 0.75, 1.0),
    "COLOR_08": (0.75, 0.3, 0.55, 1.0),
}


def normalize_name(name, ignore_numeric_suffix):
    value = (name or "").strip()
    if ignore_numeric_suffix:
        value = NUMERIC_SUFFIX_RE.sub("", value)
    return value


def walk_collections(root):
    visited = set()

    def visit(collection, path):
        pointer = collection.as_pointer()
        if pointer in visited:
            return
        visited.add(pointer)
        yield collection, path
        for child in sorted(collection.children, key=lambda item: item.name.casefold()):
            yield from visit(child, f"{path}/{child.name}")

    yield from visit(root, root.name)


def walk_objects(root):
    seen = set()
    for collection, _path in walk_collections(root):
        for obj in sorted(collection.objects, key=lambda item: item.name.casefold()):
            pointer = obj.as_pointer()
            if pointer in seen:
                continue
            seen.add(pointer)
            yield obj


def collection_contains(root, target):
    target_pointer = target.as_pointer()
    return any(
        collection.as_pointer() == target_pointer
        for collection, _path in walk_collections(root)
    )


def build_target_index(individual_root, ignore_numeric_suffix):
    index = {}
    path_map = {}
    targets = []
    for collection, path in walk_collections(individual_root):
        path_map[path] = collection
        if not any(obj.type == "MESH" for obj in collection.objects):
            continue
        key = normalize_name(collection.name, ignore_numeric_suffix)
        if not key:
            continue
        candidate = {
            "collection": collection,
            "name": collection.name,
            "path": path,
            "color_tag": collection.color_tag,
        }
        index.setdefault(key, []).append(candidate)
        targets.append(candidate)
    return index, path_map, targets


def _name_attempts(obj, name_source, ignore_numeric_suffix):
    object_key = normalize_name(obj.name, ignore_numeric_suffix)
    mesh_key = ""
    if obj.type == "MESH" and obj.data is not None:
        mesh_key = normalize_name(obj.data.name, ignore_numeric_suffix)

    if name_source == "OBJECT_ONLY":
        return [("OBJECT_NAME", object_key)]
    if name_source == "MESH_ONLY":
        return [("MESH_DATA_NAME", mesh_key)]
    return [
        ("OBJECT_NAME", object_key),
        ("MESH_DATA_NAME", mesh_key),
    ]


def match_object(obj, settings, target_index):
    if settings.only_mesh_objects and obj.type != "MESH":
        return {
            "status": "SKIPPED",
            "object_name": obj.name,
            "match_key": "",
            "source_name_field": "",
            "target_collection": "",
            "target_path": "",
            "color_tag": "NONE",
            "detail": "Only Mesh Objects is enabled",
        }

    attempts = _name_attempts(
        obj,
        settings.name_source,
        settings.ignore_numeric_suffix,
    )
    valid_attempts = [(field, key) for field, key in attempts if key]
    if not valid_attempts:
        return {
            "status": "SKIPPED",
            "object_name": obj.name,
            "match_key": "",
            "source_name_field": "",
            "target_collection": "",
            "target_path": "",
            "color_tag": "NONE",
            "detail": "No valid name is available",
        }

    last_field, last_key = valid_attempts[-1]
    for source_field, key in valid_attempts:
        candidates = target_index.get(key, [])
        if not candidates:
            continue
        if len(candidates) == 1:
            candidate = candidates[0]
            return {
                "status": "LINKED",
                "object_name": obj.name,
                "match_key": key,
                "source_name_field": source_field,
                "target_collection": candidate["name"],
                "target_path": candidate["path"],
                "color_tag": candidate["color_tag"],
                "detail": candidate["path"],
            }
        return {
            "status": "DUPLICATE",
            "object_name": obj.name,
            "match_key": key,
            "source_name_field": source_field,
            "target_collection": "",
            "target_path": "",
            "color_tag": "NONE",
            "detail": " | ".join(candidate["path"] for candidate in candidates),
        }

    return {
        "status": "MISSING",
        "object_name": obj.name,
        "match_key": last_key,
        "source_name_field": last_field,
        "target_collection": "",
        "target_path": "",
        "color_tag": "NONE",
        "detail": "No matching target collection",
    }


def clear_link_properties(obj):
    for key in LINK_PROPERTY_KEYS:
        if key in obj:
            del obj[key]


def store_match_properties(obj, result):
    clear_link_properties(obj)
    obj["LCIL_link_status"] = result["status"]
    if result["match_key"]:
        obj["LCIL_link_match_key"] = result["match_key"]
    if result["source_name_field"]:
        obj["LCIL_link_source_name_field"] = result["source_name_field"]
    if result["status"] != "LINKED":
        return
    obj["LCIL_link_collection_name"] = result["target_collection"]
    obj["LCIL_link_collection_path"] = result["target_path"]
    obj["LCIL_link_collection_color_tag"] = result["color_tag"]


def get_or_create_output_collection(scene, collection_name):
    output = bpy.data.collections.get(collection_name)
    if output is None:
        output = bpy.data.collections.new(collection_name)
    if not collection_contains(scene.collection, output):
        scene.collection.children.link(output)
    return output


def remove_generated_content(output):
    for obj in list(walk_objects(output)):
        if bool(obj.get(GENERATED_KEY, False)):
            bpy.data.objects.remove(obj, do_unlink=True)

    descendants = list(walk_collections(output))[1:]
    for collection, _path in reversed(descendants):
        if not bool(collection.get(GENERATED_KEY, False)):
            continue
        if len(collection.objects) or len(collection.children):
            continue
        bpy.data.collections.remove(collection, do_unlink=True)


def get_or_create_group(output, target_collection):
    group_name = f"GRP_{target_collection.name}"
    group = output.children.get(group_name)
    if group is None:
        group = bpy.data.collections.new(group_name)
        output.children.link(group)
        group[GENERATED_KEY] = True
        group[GENERATED_KIND_KEY] = GROUP_KIND
    group.color_tag = target_collection.color_tag
    return group


def mark_generated_instance(empty, source_obj, target_collection, target_path):
    empty[GENERATED_KEY] = True
    empty[GENERATED_KIND_KEY] = INSTANCE_KIND
    empty["LCIL_source_object"] = source_obj.name
    empty["LCIL_target_collection"] = target_collection.name
    empty["LCIL_target_collection_path"] = target_path


def create_collection_instance(
    source_obj,
    target_collection,
    target_path,
    destination,
    instance_prefix,
):
    empty = bpy.data.objects.new(f"{instance_prefix}{source_obj.name}", None)
    empty.instance_type = "COLLECTION"
    empty.instance_collection = target_collection
    empty.matrix_world = source_obj.matrix_world.copy()
    empty.color = COLOR_TAG_RGBA.get(
        target_collection.color_tag,
        COLOR_TAG_RGBA["NONE"],
    )
    destination.objects.link(empty)
    mark_generated_instance(empty, source_obj, target_collection, target_path)
    return empty


def generated_instance_empties(output):
    return [
        obj
        for obj in walk_objects(output)
        if bool(obj.get(GENERATED_KEY, False))
        and obj.get(GENERATED_KIND_KEY) == INSTANCE_KIND
        and obj.type == "EMPTY"
        and obj.instance_type == "COLLECTION"
        and obj.instance_collection is not None
    ]


def output_collection_for_object(output, obj):
    output_collections = {
        collection.as_pointer(): collection
        for collection, _path in walk_collections(output)
    }
    candidates = [
        collection
        for collection in obj.users_collection
        if collection.as_pointer() in output_collections
    ]
    if not candidates:
        return output
    return sorted(candidates, key=lambda item: item.name.casefold())[0]


def realize_instance(empty, output):
    target_collection = empty.instance_collection
    destination = output_collection_for_object(output, empty)
    realized = []
    for source_part in walk_objects(target_collection):
        copy = source_part.copy()
        copy.parent = None
        copy.matrix_parent_inverse.identity()
        copy.name = f"REAL_{empty.name}__{source_part.name}"
        destination.objects.link(copy)
        copy.matrix_world = empty.matrix_world @ source_part.matrix_world
        copy[GENERATED_KEY] = True
        copy[GENERATED_KIND_KEY] = REALIZED_KIND
        copy["LCIL_source_object"] = empty.get("LCIL_source_object", "")
        copy["LCIL_source_part_object"] = source_part.name
        copy["LCIL_target_collection"] = empty.get(
            "LCIL_target_collection",
            target_collection.name,
        )
        copy["LCIL_target_collection_path"] = empty.get(
            "LCIL_target_collection_path",
            "",
        )
        realized.append(copy)
    return realized
