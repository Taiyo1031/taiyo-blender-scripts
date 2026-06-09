from pathlib import Path

import bpy


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


def add_library_links_for_graph(graph, filters):
    for node in list(graph.nodes.values()):
        datablock = _resolve_node_datablock(node)
        if datablock:
            add_id_library_link(graph, node["id"], datablock, filters)


def _resolve_node_datablock(node):
    node_id = node["id"]
    name = node["name"]
    node_type = node["type"]
    if node_type == "OBJECT":
        return bpy.data.objects.get(name)
    if node_type == "MESH":
        return bpy.data.meshes.get(name)
    if node_type == "COLLECTION":
        return bpy.data.collections.get(name)
    if node_type == "MATERIAL":
        return bpy.data.materials.get(name)
    if node_type == "IMAGE":
        return bpy.data.images.get(name)
    if node_type == "NODEGROUP":
        return bpy.data.node_groups.get(name)
    if node_type == "ACTION":
        return bpy.data.actions.get(name)
    if node_type == "ARMATURE" and node_id.startswith("Armature:"):
        obj_name = node_id.split(":", 1)[1]
        obj = bpy.data.objects.get(obj_name)
        return obj.data if obj and obj.type == "ARMATURE" else None
    return None
