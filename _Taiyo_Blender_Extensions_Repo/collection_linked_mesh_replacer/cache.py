import hashlib
from datetime import datetime

import bpy


CACHE = {}
THOROUGH_TOLERANCE = 1.0e-4

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


def _digest(payload):
    return hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()


def _ratio_tuple(values):
    largest = max((abs(float(value)) for value in values), default=0.0)
    if largest <= 1.0e-12:
        return (0.0, 0.0, 0.0)
    return tuple(round(float(value) / largest, 5) for value in values)


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
    proportional = []
    largest_size = max((abs(value) for value in bbox_size), default=0.0)
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
        proportional.append(
            tuple(
                round((float(co[axis]) - center[axis]) / largest_size, 5)
                if largest_size > 1.0e-12
                else 0.0
                for axis in range(3)
            )
        )

    sorted_vertices = tuple(sorted(normalized))
    sorted_proportional_vertices = tuple(sorted(proportional))
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
    sorted_proportional_edges = tuple(
        sorted(
            tuple(sorted((proportional[edge.vertices[0]], proportional[edge.vertices[1]])))
            for edge in mesh.edges
        )
    )
    sorted_proportional_polygons = tuple(
        sorted(
            tuple(sorted(proportional[index] for index in polygon.vertices))
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
    proportional_payload = (
        len(mesh.vertices),
        len(mesh.edges),
        len(mesh.polygons),
        _ratio_tuple(bbox_size),
        sorted_proportional_vertices,
        sorted_proportional_edges,
        sorted_proportional_polygons,
    )
    vertex_payload = (
        len(mesh.vertices),
        _ratio_tuple(bbox_size),
        sorted_proportional_vertices,
    )

    return {
        "hash": _digest(payload),
        "proportional_hash": _digest(proportional_payload),
        "vertex_shape_hash": _digest(vertex_payload),
        "vertex_count": len(mesh.vertices),
        "edge_count": len(mesh.edges),
        "polygon_count": len(mesh.polygons),
        "bbox_size": _rounded_tuple(bbox_size),
        "bbox_ratio": _ratio_tuple(bbox_size),
    }


def build_cache(collection, recursive):
    source_objects = iter_collection_objects(collection, recursive)
    mesh_objects = [
        obj
        for obj in source_objects
        if obj.type == "MESH" and obj.data is not None
    ]
    signatures = {}
    proportional_signatures = {}
    vertex_shape_signatures = {}

    for obj in sorted(mesh_objects, key=lambda item: item.name.casefold()):
        signature = mesh_signature(obj.data)
        entry = {
            "object_name": obj.name,
            "object_ref": obj,
            "mesh_name": obj.data.name,
            **signature,
        }
        signatures.setdefault(signature["hash"], []).append(entry)
        proportional_signatures.setdefault(
            signature["proportional_hash"],
            [],
        ).append(entry)
        vertex_shape_signatures.setdefault(
            signature["vertex_shape_hash"],
            [],
        ).append(entry)

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
            "proportional_signatures": proportional_signatures,
            "vertex_shape_signatures": vertex_shape_signatures,
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
    exact = list(CACHE.get("signatures", {}).get(signature["hash"], ()))
    if exact:
        return signature, _annotate_candidates(exact, "EXACT", "Exact")

    proportional = list(
        CACHE.get("proportional_signatures", {}).get(
            signature["proportional_hash"],
            (),
        )
    )
    if proportional:
        return signature, _annotate_candidates(
            proportional,
            "PROPORTIONAL",
            "Shape Match",
        )

    vertex_shape = list(
        CACHE.get("vertex_shape_signatures", {}).get(
            signature["vertex_shape_hash"],
            (),
        )
    )
    if vertex_shape:
        return signature, _annotate_candidates(
            vertex_shape,
            "VERTEX_SHAPE",
            "Vertex Shape Match",
        )

    return signature, []


def _normalized_geometry(mesh):
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
    largest_size = max((abs(value) for value in bbox_size), default=0.0)
    if largest_size <= 1.0e-12:
        normalized = [(0.0, 0.0, 0.0) for _vertex in vertices]
    else:
        normalized = [
            tuple(
                (float(co[axis]) - center[axis]) / largest_size
                for axis in range(3)
            )
            for co in vertices
        ]

    return {
        "vertices": normalized,
        "bbox_ratio": tuple(
            float(value) / largest_size
            if largest_size > 1.0e-12
            else 0.0
            for value in bbox_size
        ),
        "edges": {
            tuple(sorted((edge.vertices[0], edge.vertices[1])))
            for edge in mesh.edges
        },
        "polygons": sorted(
            tuple(sorted(polygon.vertices))
            for polygon in mesh.polygons
        ),
    }


def _values_close(left, right, tolerance):
    return len(left) == len(right) and all(
        abs(float(a) - float(b)) <= tolerance
        for a, b in zip(left, right)
    )


def _match_vertex_mapping(target_vertices, source_vertices, tolerance):
    if len(target_vertices) != len(source_vertices):
        return None

    unmatched = set(range(len(source_vertices)))
    mapping = {}
    target_order = sorted(
        range(len(target_vertices)),
        key=lambda index: tuple(target_vertices[index]),
    )
    for target_index in target_order:
        target_co = target_vertices[target_index]
        best_source = None
        best_distance = None
        for source_index in unmatched:
            source_co = source_vertices[source_index]
            distance = max(
                abs(float(target_co[axis]) - float(source_co[axis]))
                for axis in range(3)
            )
            if distance > tolerance:
                continue
            if best_distance is None or distance < best_distance:
                best_source = source_index
                best_distance = distance
        if best_source is None:
            return None
        mapping[target_index] = best_source
        unmatched.remove(best_source)
    return mapping


def thorough_mesh_match_kind(target_mesh, source_mesh, tolerance=THOROUGH_TOLERANCE):
    target_signature = mesh_signature(target_mesh)
    source_signature = mesh_signature(source_mesh)
    if signatures_match(target_signature, source_signature, "EXACT"):
        return "EXACT"
    if signatures_match(target_signature, source_signature, "PROPORTIONAL"):
        return "PROPORTIONAL"
    if signatures_match(target_signature, source_signature, "VERTEX_SHAPE"):
        return "VERTEX_SHAPE"

    target = _normalized_geometry(target_mesh)
    source = _normalized_geometry(source_mesh)
    if not _values_close(
        target["bbox_ratio"],
        source["bbox_ratio"],
        tolerance,
    ):
        return None

    mapping = _match_vertex_mapping(
        target["vertices"],
        source["vertices"],
        tolerance,
    )
    if mapping is None:
        return None

    mapped_edges = {
        tuple(sorted((mapping[start], mapping[end])))
        for start, end in target["edges"]
    }
    mapped_polygons = sorted(
        tuple(sorted(mapping[index] for index in polygon))
        for polygon in target["polygons"]
    )
    if (
        mapped_edges == source["edges"]
        and mapped_polygons == source["polygons"]
    ):
        return "THOROUGH_SHAPE"
    return "THOROUGH_VERTEX_SHAPE"


def find_candidates_thorough(obj, collection, recursive):
    if obj is None or obj.type != "MESH" or obj.data is None:
        return None, []

    signature = mesh_signature(obj.data)
    candidates = []
    confidence_labels = {
        "EXACT": "Thorough Exact",
        "PROPORTIONAL": "Thorough Shape",
        "VERTEX_SHAPE": "Thorough Vertex Shape",
        "THOROUGH_SHAPE": "Thorough Tolerant Shape",
        "THOROUGH_VERTEX_SHAPE": "Thorough Tolerant Vertex Shape",
    }
    for source in sorted(
        iter_collection_mesh_objects(collection, recursive),
        key=lambda item: item.name.casefold(),
    ):
        match_kind = thorough_mesh_match_kind(obj.data, source.data)
        if match_kind is None:
            continue
        source_signature = mesh_signature(source.data)
        candidates.append(
            {
                "object_name": source.name,
                "object_ref": source,
                "mesh_name": source.data.name,
                **source_signature,
                "match_kind": match_kind,
                "confidence": confidence_labels[match_kind],
            }
        )
    return signature, candidates


def _annotate_candidates(entries, match_kind, confidence):
    annotated = []
    for entry in entries:
        candidate = dict(entry)
        candidate["match_kind"] = match_kind
        candidate["confidence"] = confidence
        annotated.append(candidate)
    return annotated


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


def signatures_match(left, right, match_kind="EXACT"):
    if match_kind == "PROPORTIONAL":
        keys = ("proportional_hash", "vertex_count", "edge_count", "polygon_count")
    elif match_kind == "VERTEX_SHAPE":
        keys = ("vertex_shape_hash", "vertex_count")
    else:
        keys = ("hash", "vertex_count", "edge_count", "polygon_count")
    return all(left.get(key) == right.get(key) for key in keys)


def color_tag_label(collection):
    if collection is None:
        return "None"
    color_tag = collection.color_tag
    return f"{color_tag} / {COLOR_TAG_NAMES.get(color_tag, color_tag)}"
