import hashlib
from datetime import datetime

import bpy


CACHE = {}

COLOR_TAG_NAMES = {
    "NONE": "None",
    "COLOR_01": "Red",
    "COLOR_02": "Orange",
    "COLOR_03": "Yellow",
    "COLOR_04": "Green",
    "COLOR_05": "Blue",
    "COLOR_06": "Purple",
    "COLOR_07": "Pink",
    "COLOR_08": "Brown",
}


def clear_cache():
    CACHE.clear()


def iter_collection_objects(collection, recursive):
    if collection is None:
        return []

    collections = [collection]
    if recursive:
        collections.extend(collection.children_recursive)

    objects = []
    seen = set()
    for current in collections:
        for obj in current.objects:
            pointer = obj.as_pointer()
            if pointer in seen:
                continue
            seen.add(pointer)
            objects.append(obj)
    return objects


def iter_collection_mesh_objects(collection, recursive):
    return [
        obj
        for obj in iter_collection_objects(collection, recursive)
        if obj.type == "MESH" and obj.data is not None
    ]


def object_is_in_source(obj, collection, recursive):
    if obj is None or collection is None:
        return False
    pointer = obj.as_pointer()
    return any(
        candidate.as_pointer() == pointer
        for candidate in iter_collection_objects(collection, recursive)
    )


def _rounded_tuple(values, digits=6):
    return tuple(round(float(value), digits) for value in values)


def mesh_signature(mesh):
    vertices = [vertex.co.copy() for vertex in mesh.vertices]
    if vertices:
        minimum = [
            min(co[axis] for co in vertices)
            for axis in range(3)
        ]
        maximum = [
            max(co[axis] for co in vertices)
            for axis in range(3)
        ]
    else:
        minimum = [0.0, 0.0, 0.0]
        maximum = [0.0, 0.0, 0.0]

    center = [
        (minimum[axis] + maximum[axis]) * 0.5
        for axis in range(3)
    ]
    bbox_size = [
        maximum[axis] - minimum[axis]
        for axis in range(3)
    ]

    normalized = []
    for co in vertices:
        normalized.append(
            tuple(
                round(
                    (float(co[axis]) - center[axis]) / bbox_size[axis],
                    6,
                )
                if abs(bbox_size[axis]) > 1.0e-12
                else 0.0
                for axis in range(3)
            )
        )

    sorted_vertices = tuple(sorted(normalized))
    sorted_edges = tuple(
        sorted(
            tuple(sorted((normalized[edge.vertices[0]], normalized[edge.vertices[1]])))
            for edge in mesh.edges
        )
    )
    sorted_polygons = tuple(
        sorted(
            tuple(sorted(normalized[index] for index in polygon.vertices))
            for polygon in mesh.polygons
        )
    )

    payload = (
        len(mesh.vertices),
        len(mesh.edges),
        len(mesh.polygons),
        _rounded_tuple(bbox_size),
        sorted_vertices,
        sorted_edges,
        sorted_polygons,
    )
    digest = hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()

    return {
        "hash": digest,
        "vertex_count": len(mesh.vertices),
        "edge_count": len(mesh.edges),
        "polygon_count": len(mesh.polygons),
        "bbox_size": _rounded_tuple(bbox_size),
    }


def build_cache(collection, recursive):
    source_objects = iter_collection_objects(collection, recursive)
    mesh_objects = [
        obj
        for obj in source_objects
        if obj.type == "MESH" and obj.data is not None
    ]
    signatures = {}

    for obj in sorted(mesh_objects, key=lambda item: item.name.casefold()):
        signature = mesh_signature(obj.data)
        entry = {
            "object_name": obj.name,
            "object_ref": obj,
            "mesh_name": obj.data.name,
            **signature,
        }
        signatures.setdefault(signature["hash"], []).append(entry)

    CACHE.clear()
    CACHE.update(
        {
            "source_collection_name": collection.name,
            "source_collection_ref": collection,
            "source_collection_color_tag": collection.color_tag,
            "source_object_count": len(source_objects),
            "cached_object_count": len(mesh_objects),
            "built_time": datetime.now().strftime("%H:%M"),
            "recursive": recursive,
            "signatures": signatures,
            "unique_mesh_count": len(signatures),
            "duplicated_signature_count": sum(
                1 for entries in signatures.values() if len(entries) > 1
            ),
        }
    )
    return CACHE


def cache_status(collection, recursive):
    if not CACHE:
        return "NOT_BUILT"
    if collection is None:
        return "OUTDATED"
    if CACHE.get("source_collection_ref") != collection:
        return "OUTDATED"
    if CACHE.get("source_collection_name") != collection.name:
        return "OUTDATED"
    if CACHE.get("source_collection_color_tag") != collection.color_tag:
        return "OUTDATED"
    if CACHE.get("recursive") != recursive:
        return "OUTDATED"
    if CACHE.get("source_object_count") != len(
        iter_collection_objects(collection, recursive)
    ):
        return "OUTDATED"
    return "VALID"


def find_candidates(obj):
    if obj is None or obj.type != "MESH" or obj.data is None:
        return None, []
    signature = mesh_signature(obj.data)
    return signature, list(CACHE.get("signatures", {}).get(signature["hash"], ()))


def resolve_source_object(entry):
    source = bpy.data.objects.get(entry.get("object_name", ""))
    if source is not None:
        return source

    source_ref = entry.get("object_ref")
    try:
        if source_ref is not None:
            return bpy.data.objects.get(source_ref.name)
    except ReferenceError:
        pass
    return None


def signatures_match(left, right):
    keys = ("hash", "vertex_count", "edge_count", "polygon_count")
    return all(left.get(key) == right.get(key) for key in keys)


def color_tag_label(collection):
    if collection is None:
        return "None"
    color_tag = collection.color_tag
    return f"{color_tag} / {COLOR_TAG_NAMES.get(color_tag, color_tag)}"
