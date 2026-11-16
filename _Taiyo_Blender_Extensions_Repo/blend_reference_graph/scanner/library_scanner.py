from pathlib import Path

import bpy

from .id_utils import build_node_id_index


def library_id(library):
    return f"Library:{library.filepath}"


def _allowed(filters, node_type):
    return filters.get(node_type, True)


def add_id_library_link(graph, owner_node_id, datablock, filters):
    library = getattr(datablock, "library", None)
    if not library or not _allowed(filters, "LIBRARY"):
        return
    node_id = library_id(library)
    filepath = bpy.path.abspath(library.filepath)
    graph.add_node(
        node_id,
        "LIBRARY",
        Path(filepath).name or library.name,
        f"LIB {Path(filepath).name or library.name}",
        path=filepath,
        details={
            "filepath": filepath,
            "library_name": library.name,
            "datablock": getattr(datablock, "name", ""),
            "datablock_type": type(datablock).__name__,
        },
    )
    graph.add_edge(owner_node_id, node_id, "linked_from_library", "linked library")


def add_library_links_for_graph(graph, filters, index=None):
    for _ in iter_library_links_for_graph(graph, filters, index):
        pass


def iter_library_links_for_graph(graph, filters, index=None):
    index = build_node_id_index() if index is None else index
    for node in list(graph.nodes.values()):
        if hasattr(graph, "datablock_ids"):
            datablock = index.get(node["id"])
        else:
            datablock = _resolve_node_datablock(node, index)
        if datablock:
            add_id_library_link(graph, node["id"], datablock, filters)
        yield None


def _resolve_node_datablock(node, index=None):
    index = build_node_id_index() if index is None else index
    # Target graphs historically name armature nodes after their Object.
    if node["type"] == "ARMATURE":
        obj = index.get("Object:" + node["id"].split(":", 1)[1])
        if obj and obj.type == "ARMATURE":
            return obj.data
    return index.get(node["id"])
