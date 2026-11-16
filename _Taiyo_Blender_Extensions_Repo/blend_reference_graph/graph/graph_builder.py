import time
from collections import defaultdict, deque
from dataclasses import replace

import bpy

from ..scanner import (
    animation_scanner,
    collection_scanner,
    constraint_scanner,
    geonodes_scanner,
    library_scanner,
    object_scanner,
    safe_delete_scanner,
)
from ..scanner.id_utils import id_key, iter_node_id_index, resolve_node_id
from ..scanner.path_utils import CollectionPathCache
from ..scanner.whole_file_scanner import ScanOptions, iter_scan
from .graph_model import GraphData


ALL_FILTERS = {
    "OBJECT": True,
    "MESH": True,
    "COLLECTION": True,
    "ARMATURE": True,
    "BONE": True,
    "CONSTRAINT": True,
    "MODIFIER": True,
    "GEONODES": True,
    "NODEGROUP": True,
    "MATERIAL": True,
    "IMAGE": True,
    "ACTION": True,
    "DRIVER": True,
    "LIBRARY": True,
    "SAFE_DELETE": True,
    "WARNING": True,
    **dict.fromkeys(("SCENE", "WORLD", "CAMERA", "LIGHT", "CURVE", "TEXT",
                     "FONT", "SOUND", "PARTICLE", "TEXTURE", "OTHER"), True),
}


def _find_target(settings):
    if getattr(settings, "target_id", ""):
        resolved = resolve_node_id(settings.target_id)
        if isinstance(resolved, tuple):
            return ("BONE", *resolved)
        if isinstance(resolved, bpy.types.Object):
            return ("OBJECT", resolved, "")
    if settings.target_type == "BONE" and settings.target_name:
        armature_name, _, bone_name = settings.target_name.partition(" / ")
        obj = bpy.data.objects.get(armature_name)
        if obj and obj.type == "ARMATURE":
            return ("BONE", obj, bone_name)
    if settings.target_name:
        obj = bpy.data.objects.get(settings.target_name)
        if obj:
            return ("OBJECT", obj, "")
    obj = bpy.context.object
    if obj:
        return ("OBJECT", obj, "")
    return ("SCENE", None, "")


def _allowed(filters, node_type):
    return filters.get(node_type, True)


def build_graph(context, settings):
    graph = GraphData()
    started = time.perf_counter()
    filters = ALL_FILTERS
    mode = settings.scan_mode
    depth = max(1, settings.depth)
    target_kind, target_obj, target_bone = _find_target(settings)

    if target_kind == "BONE":
        object_scanner.add_object_node(graph, target_obj, filters)
        object_scanner.add_armature_and_bones(graph, target_obj, filters, include_all_bones=False)
        object_scanner.add_selected_bone_context(graph, target_obj, target_bone, filters)
        _expand_pose_bone_constraints(graph, target_obj, target_bone, filters)
        animation_scanner.add_object_animation_refs(graph, target_obj, filters)
        _finalize_graph(graph, settings.target_id, filters)
        graph.meta["scan_seconds"] = time.perf_counter() - started
        return graph

    if not target_obj:
        graph.add_node(
            "Warning:NoTarget",
            "WARNING",
            "No target selected",
            "WARN No target selected",
            details={"message": "Select an object and run Use Selected."},
        )
        return graph

    visited = set()
    _expand_object(graph, target_obj, filters, mode, depth, visited)
    target_id = settings.target_id or object_scanner.object_id(target_obj)
    _finalize_graph(graph, target_id, filters)
    graph.meta["scan_seconds"] = time.perf_counter() - started
    return graph


def _expand_object(graph, obj, filters, mode, depth, visited):
    for _ in _iter_expand_object(graph, obj, filters, mode, depth, visited, set()):
        pass


def _iter_expand_object(graph, obj, filters, mode, depth, visited, visited_groups):
    if depth < 0 or id_key(obj) in visited:
        object_scanner.add_object_node(graph, obj, filters)
        return
    visited.add(id_key(obj))
    object_scanner.add_object_node(graph, obj, filters)
    yield None
    if mode in {"USES", "BOTH"}:
        if obj.type == "MESH" and obj.data:
            object_scanner.add_object_data_refs(graph, obj, filters)
        collection_scanner.add_object_collections(graph, obj, filters)
        yield None
        if filters.get("_internals", True):
            yield from constraint_scanner.iter_object_constraints(graph, obj, filters)
            yield from geonodes_scanner.iter_geometry_nodes_modifiers(graph, obj, filters, visited_groups)
        yield from object_scanner.iter_armature_and_bones(graph, obj, filters)
        if filters.get("_internals", True):
            yield from animation_scanner.iter_object_animation_refs(graph, obj, filters)
        if obj.parent and _allowed(filters, "OBJECT"):
            object_scanner.add_object_node(graph, obj.parent, filters)
            graph.add_edge(object_scanner.object_id(obj), object_scanner.object_id(obj.parent), "child_of", "parent")
            if depth > 1:
                yield from _iter_expand_object(graph, obj.parent, filters, "USES", depth - 1, visited, visited_groups)
    if mode in {"USED_BY", "BOTH"}:
        if obj.type == "MESH" and obj.data:
            object_scanner.add_mesh_node(graph, obj.data, filters)
            for user in bpy.data.objects:
                if user != obj and user.data == obj.data:
                    object_scanner.add_object_node(graph, user, filters)
                    graph.add_edge(object_scanner.mesh_id(obj.data), object_scanner.object_id(user), "used_by_object", "used by")
                yield None
        for child in obj.children:
            object_scanner.add_object_node(graph, child, filters)
            graph.add_edge(object_scanner.object_id(obj), object_scanner.object_id(child), "parent_of", "child")
            if depth > 1:
                yield from _iter_expand_object(graph, child, filters, "USES", depth - 1, visited, visited_groups)
            yield None
        if filters.get("_internals", True):
            yield from animation_scanner.iter_incoming_driver_users(graph, obj, filters)


def _expand_pose_bone_constraints(graph, armature_obj, bone_name, filters):
    if not _allowed(filters, "CONSTRAINT"):
        return
    pose_bone = armature_obj.pose.bones.get(bone_name) if armature_obj.pose else None
    if not pose_bone:
        return
    constraint_scanner.add_pose_bone_constraints(graph, armature_obj, pose_bone, filters)


def _finalize_graph(graph, target_id, filters):
    library_scanner.add_library_links_for_graph(graph, filters)
    safe_delete_scanner.add_safe_delete_preview(graph, target_id, filters)


def _node_steps(context, node_id, mode, depth, options):
    graph = GraphData()
    if node_id.startswith(("Object:", "Bone:")):
        index = {}
        for _ in iter_node_id_index(index):
            yield 0.05, "Resolving node"
        target = resolve_node_id(node_id, index)
        if target is None:
            raise ValueError(f"Node not found: {node_id}")
        graph.path_cache = CollectionPathCache(build=False)
        for _ in graph.path_cache.iter_build():
            yield 0.1, "Collection paths"
        filters = ALL_FILTERS.copy()
        filters["BONE"] = options.include_bones or node_id.startswith("Bone:")
        filters["_internals"] = options.include_internals
        if isinstance(options.node_limit_per_type, dict):
            graph.node_limits.update(options.node_limit_per_type)
        elif isinstance(options.node_limit_per_type, int):
            graph.node_limits.update(dict.fromkeys(ALL_FILTERS, max(0, options.node_limit_per_type)))
        if not options.include_internals:
            filters.update(CONSTRAINT=False, MODIFIER=False, DRIVER=False)
        graph.node_limits["BONE"] = min(graph.node_limits.get("BONE", options.max_bones), max(0, options.max_bones))
        if isinstance(target, tuple):
            obj, bone_name = target
            object_scanner.add_object_node(graph, obj, filters)
            object_scanner.add_armature_and_bones(graph, obj, filters, include_all_bones=False)
            object_scanner.add_selected_bone_context(graph, obj, bone_name, filters)
            if options.include_internals:
                _expand_pose_bone_constraints(graph, obj, bone_name, filters)
                for _ in animation_scanner.iter_object_animation_refs(graph, obj, filters):
                    yield 0.5, "Bone references"
        else:
            for _ in _iter_expand_object(graph, target, filters, mode, depth, set(), set()):
                yield 0.5, "Object references"
        for _ in library_scanner.iter_library_links_for_graph(graph, filters, index):
            yield 0.9, "Library links"
    else:
        whole = GraphData()
        for progress, message in iter_scan(whole, replace(options, include_internals=False, include_bones=False)):
            yield progress * 0.7, message
        if node_id not in whole.nodes:
            raise ValueError(f"Node not found: {node_id}")
        adjacency = defaultdict(list)
        for edge in whole.edges:
            if mode in {"USES", "BOTH"}:
                adjacency[edge["from"]].append(edge["to"])
            if mode in {"USED_BY", "BOTH"}:
                adjacency[edge["to"]].append(edge["from"])
            yield 0.75, "Indexing references"
        selected = {node_id}
        queue = deque([(node_id, 0)])
        while queue:
            current, distance = queue.popleft()
            if distance < depth:
                for neighbor in adjacency[current]:
                    if neighbor not in selected:
                        selected.add(neighbor)
                        queue.append((neighbor, distance + 1))
                    yield 0.8, "Following references"
            yield 0.8, "Following references"
        for key in selected:
            node = whole.nodes[key]
            graph.add_node(key, node["type"], node["name"], node["label"], node["path"], node["details"], node["group"])
            yield 0.85, "Selecting nodes"
        for edge in whole.edges:
            graph.add_edge(edge["from"], edge["to"], edge["relation"], edge["label"])
            yield 0.9, "Selecting edges"
        graph.meta["truncated"] = whole.meta["truncated"]
    if node_id not in graph.nodes:
        raise ValueError(f"Node not found: {node_id}")
    safe_delete_scanner.add_safe_delete_preview(graph, node_id, ALL_FILTERS)
    graph.meta.update(scope="NODE", target_id=node_id, mode=mode, depth=depth)
    return graph


def iter_build_node_graph(context, node_id, mode="BOTH", depth=1, options=None):
    if mode not in {"USES", "USED_BY", "BOTH"}:
        raise ValueError(f"Invalid mode: {mode}")
    depth = max(1, min(5, depth))
    started = last_yield = time.perf_counter()
    steps = _node_steps(context, node_id, mode, depth, options or ScanOptions())
    yield 0.0, "Starting node scan"
    count = 0
    while True:
        try:
            progress = next(steps)
        except StopIteration as result:
            graph = result.value
            graph.meta.update(scan_seconds=time.perf_counter() - started, type_counts=dict(graph.type_counts))
            yield 1.0, "Node scan complete"
            return graph
        count += 1
        if count % 128 == 0 or time.perf_counter() - last_yield >= 0.005:
            yield progress
            last_yield = time.perf_counter()


def build_node_graph(context, node_id, mode="BOTH", depth=1, options=None):
    iterator = iter_build_node_graph(context, node_id, mode, depth, options)
    while True:
        try:
            next(iterator)
        except StopIteration as result:
            return result.value
