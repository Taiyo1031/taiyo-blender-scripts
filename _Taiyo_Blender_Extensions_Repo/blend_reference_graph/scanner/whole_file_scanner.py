from dataclasses import dataclass
import time

import bpy

from . import animation_scanner, constraint_scanner, geonodes_scanner, library_scanner, object_scanner
from .id_utils import datablock_node_id, iter_id_collections
from .path_utils import CollectionPathCache


@dataclass
class ScanOptions:
    include_internals: bool = True
    include_bones: bool = False
    max_bones: int = 2000
    node_limit_per_type: dict | int | None = None


def _embedded_ids(owner):
    for name in ("node_tree", "compositing_node_group", "collection", "grease_pencil", "grease_pencils"):
        block = getattr(owner, name, None)
        if isinstance(block, bpy.types.ID) and block.is_embedded_data:
            yield block


def _owner(block, embedded_owner):
    seen = set()
    while block in embedded_owner and block not in seen:
        seen.add(block)
        block = embedded_owner[block]
    return block


def _relation(user, block):
    if isinstance(user, bpy.types.Object):
        if user.data == block:
            return "uses_data", "uses data"
        if user.parent == block:
            return "child_of", "parent"
        if isinstance(block, bpy.types.Material):
            return "uses_material", "uses material"
    if isinstance(user, bpy.types.Collection):
        if isinstance(block, bpy.types.Object):
            return "contains", "contains"
        if isinstance(block, bpy.types.Collection):
            return "child_collection", "child collection"
    if isinstance(user, bpy.types.Scene):
        if isinstance(block, bpy.types.Collection):
            return "child_collection", "collection"
        if isinstance(block, bpy.types.Object):
            return "contains", "contains"
    return "references", "uses"


def _steps(graph, options):
    cache = graph.path_cache = CollectionPathCache(build=False)
    for _ in cache.iter_build():
        yield 0.05, "Collection paths"

    embedded_owner = graph.embedded_owner = {}
    index = {}
    blocks = graph.datablock_ids = {}
    for group, prefix, collection in iter_id_collections():
        for block in collection:
            if not isinstance(block, bpy.types.ID):
                continue
            for embedded in _embedded_ids(block):
                embedded_owner[embedded] = block
            if block.is_embedded_data or block in blocks:
                yield 0.2, "Embedded IDs"
                continue
            node_id = datablock_node_id(block, prefix)
            blocks[block] = node_id
            index[node_id] = block
            limit = options.node_limit_per_type
            if isinstance(limit, int):
                graph.node_limits[group] = max(0, limit)
            details = {"users": block.users, "use_fake_user": block.use_fake_user,
                       "orphan": block.users == 0 and not block.use_fake_user}
            if block.library:
                details["library"] = block.library.name
            paths = []
            if group == "OBJECT":
                paths = cache.object_paths(block)
                details.update(object_type=block.type, collections=paths)
            elif group == "COLLECTION":
                paths = cache.collection_paths(block)
                details["paths"] = paths
            graph.add_node(node_id, group, block.name, path=paths[0] if paths else "",
                           details=details, group=group)
            yield 0.25, f"Nodes: {group}"

    yield 0.3, "Building user map"
    users = bpy.data.user_map()
    yield 0.4, "User map ready"
    for raw_block, raw_users in users.items():
        block = _owner(raw_block, embedded_owner)
        to_id = blocks.get(block)
        for raw_user in raw_users:
            user = _owner(raw_user, embedded_owner)
            from_id = blocks.get(user)
            if from_id and to_id and from_id != to_id:
                relation, label = _relation(user, block)
                graph.add_edge(from_id, to_id, relation, label)
            yield 0.5, "References"
        yield 0.5, "References"
    del users

    filters = {"BONE": options.include_bones}
    if options.include_internals:
        visited_groups = set()
        visited_data = set()
        total = max(1, len(bpy.data.objects))
        for i, obj in enumerate(bpy.data.objects):
            progress = 0.55 + 0.3 * i / total
            for iterator in (
                constraint_scanner.iter_object_constraints(graph, obj, filters),
                geonodes_scanner.iter_geometry_nodes_modifiers(graph, obj, filters, visited_groups),
                animation_scanner.iter_object_animation_refs(graph, obj, filters, visited_data),
            ):
                for _ in iterator:
                    yield progress, "Object internals"
            yield progress, "Object internals"
    if options.include_bones:
        for obj in bpy.data.objects:
            for _ in object_scanner.iter_armature_and_bones(graph, obj, filters):
                yield 0.9, "Bones"
            yield 0.9, "Bones"

    for _ in library_scanner.iter_library_links_for_graph(graph, filters, index):
        yield 0.95, "Library links"


def iter_scan(graph, options=None):
    options = options or ScanOptions()
    started = time.perf_counter()
    graph.meta.update(scope="WHOLE_FILE", truncated=[])
    if isinstance(options.node_limit_per_type, dict):
        graph.node_limits.update(options.node_limit_per_type)
    bone_limit = max(0, options.max_bones) if options.include_bones else 0
    graph.node_limits["BONE"] = min(graph.node_limits.get("BONE", bone_limit), bone_limit)
    last_yield = started
    yield 0.0, "Starting Whole File scan"
    for i, (progress, message) in enumerate(_steps(graph, options)):
        now = time.perf_counter()
        if i % 128 == 0 or now - last_yield >= 0.005:
            yield progress, message
            last_yield = time.perf_counter()
    graph.meta.update(scan_seconds=time.perf_counter() - started, type_counts=dict(graph.type_counts))
    yield 1.0, "Whole File scan complete"
    return graph


def run_to_end(graph, options=None):
    for _ in iter_scan(graph, options):
        pass
    return graph
