import bpy

from .collection_scanner import add_collection_node, collection_id
from .object_scanner import object_id


def modifier_id(obj, modifier):
    return f"Modifier:{obj.name}:{modifier.name}"


def node_group_id(node_group):
    return f"NodeGroup:{node_group.name}"


def _allowed(filters, node_type):
    return filters.get(node_type, True)


def add_geometry_nodes_modifiers(graph, obj, filters):
    for modifier in obj.modifiers:
        if modifier.type != "NODES":
            continue
        mod_id = modifier_id(obj, modifier)
        if _allowed(filters, "MODIFIER"):
            graph.add_node(
                mod_id,
                "MODIFIER",
                modifier.name,
                f"GN {modifier.name}",
                details={
                    "owner": obj.name,
                    "show_viewport": modifier.show_viewport,
                    "show_render": modifier.show_render,
                    "node_group": modifier.node_group.name if modifier.node_group else "",
                },
            )
            graph.add_edge(object_id(obj), mod_id, "has_modifier", "has modifier")
        if modifier.node_group:
            add_node_group_node(graph, modifier.node_group, filters)
            graph.add_edge(mod_id, node_group_id(modifier.node_group), "uses_node_group", "uses node group")
            add_node_group_internal_refs(graph, modifier.node_group, filters)
        else:
            warning_id = f"Warning:{mod_id}:MissingNodeGroup"
            graph.add_node(warning_id, "WARNING", "Missing Node Group", "WARN Missing Node Group")
            graph.add_edge(mod_id, warning_id, "missing_reference", "missing node group")


def add_node_group_node(graph, node_group, filters):
    if not _allowed(filters, "NODEGROUP"):
        return
    graph.add_node(
        node_group_id(node_group),
        "NODEGROUP",
        node_group.name,
        f"NODE {node_group.name}",
        details={"type": node_group.bl_idname},
    )


def add_node_group_internal_refs(graph, node_group, filters, visited=None):
    if not node_group or not getattr(node_group, "nodes", None):
        return
    if visited is None:
        visited = set()
    if node_group.name in visited:
        return
    visited.add(node_group.name)
    for node in node_group.nodes:
        for socket in getattr(node, "inputs", ()):
            value = getattr(socket, "default_value", None)
            _add_socket_reference(graph, node_group, node, socket, value, filters)
        sub_group = getattr(node, "node_tree", None)
        if sub_group and sub_group != node_group:
            add_node_group_node(graph, sub_group, filters)
            graph.add_edge(node_group_id(node_group), node_group_id(sub_group), "uses_node_group", node.name)
            add_node_group_internal_refs(graph, sub_group, filters, visited)


def _add_socket_reference(graph, node_group, node, socket, value, filters):
    edge_label = f"{node.name}: {socket.name}"
    if isinstance(value, bpy.types.Object) and _allowed(filters, "OBJECT"):
        graph.add_node(
            object_id(value),
            "OBJECT",
            value.name,
            f"OBJ {value.name}",
            details={"object_type": value.type},
        )
        graph.add_edge(node_group_id(node_group), object_id(value), "references_object", edge_label)
    elif isinstance(value, bpy.types.Collection) and _allowed(filters, "COLLECTION"):
        target_id = collection_id(value)
        add_collection_node(graph, value, filters)
        graph.add_edge(node_group_id(node_group), target_id, "references_collection", edge_label)
    elif isinstance(value, bpy.types.Material) and _allowed(filters, "MATERIAL"):
        target_id = f"Material:{value.name}"
        graph.add_node(target_id, "MATERIAL", value.name, f"MAT {value.name}")
        graph.add_edge(node_group_id(node_group), target_id, "uses_material", edge_label)
    elif isinstance(value, bpy.types.Image) and _allowed(filters, "IMAGE"):
        target_id = f"Image:{value.name}"
        graph.add_node(target_id, "IMAGE", value.name, f"IMG {value.name}")
        graph.add_edge(node_group_id(node_group), target_id, "uses_image", edge_label)
