from .id_utils import id_key
import bpy

from .collection_scanner import add_collection_node, collection_id
from .object_scanner import object_id


def modifier_id(obj, modifier):
    return f"Modifier:{id_key(obj)}:{modifier.name}"


def node_group_id(node_group):
    return f"NodeGroup:{id_key(node_group)}"


def _allowed(filters, node_type):
    return filters.get(node_type, True)


def add_geometry_nodes_modifiers(graph, obj, filters, visited=None):
    for _ in iter_geometry_nodes_modifiers(graph, obj, filters, visited):
        pass


def iter_geometry_nodes_modifiers(graph, obj, filters, visited=None):
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
            yield from iter_node_group_internal_refs(graph, modifier.node_group, filters, visited)
        else:
            warning_id = f"Warning:{mod_id}:MissingNodeGroup"
            graph.add_node(warning_id, "WARNING", "Missing Node Group", "WARN Missing Node Group")
            graph.add_edge(mod_id, warning_id, "missing_reference", "missing node group")

        yield None


def add_node_group_node(graph, node_group, filters):
    if node_group_id(node_group) in graph.nodes or not _allowed(filters, "NODEGROUP"):
        return
    graph.add_node(
        node_group_id(node_group),
        "NODEGROUP",
        node_group.name,
        f"NODE {node_group.name}",
        details={"type": node_group.bl_idname},
    )


def add_node_group_internal_refs(graph, node_group, filters, visited=None):
    for _ in iter_node_group_internal_refs(graph, node_group, filters, visited):
        pass


def iter_node_group_internal_refs(graph, node_group, filters, visited=None):
    visited = set() if visited is None else visited
    stack = [node_group]
    while stack:
        group = stack.pop()
        if not group or node_group_id(group) in visited:
            continue
        visited.add(node_group_id(group))
        for node in getattr(group, "nodes", ()):
            for socket in getattr(node, "inputs", ()):
                value = getattr(socket, "default_value", None)
                _add_socket_reference(graph, group, node, socket, value, filters)
                yield None
            sub_group = getattr(node, "node_tree", None)
            if sub_group and sub_group != group:
                add_node_group_node(graph, sub_group, filters)
                graph.add_edge(node_group_id(group), node_group_id(sub_group), "uses_node_group", node.name)
                stack.append(sub_group)
            yield None


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
        target_id = f"Material:{id_key(value)}"
        graph.add_node(target_id, "MATERIAL", value.name, f"MAT {value.name}")
        graph.add_edge(node_group_id(node_group), target_id, "uses_material", edge_label)
    elif isinstance(value, bpy.types.Image) and _allowed(filters, "IMAGE"):
        target_id = f"Image:{id_key(value)}"
        graph.add_node(target_id, "IMAGE", value.name, f"IMG {value.name}")
        graph.add_edge(node_group_id(node_group), target_id, "uses_image", edge_label)
