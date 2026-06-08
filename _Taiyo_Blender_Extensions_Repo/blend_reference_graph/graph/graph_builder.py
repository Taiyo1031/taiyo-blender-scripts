import bpy

from ..scanner import collection_scanner, constraint_scanner, geonodes_scanner, object_scanner
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
    "WARNING": True,
}


def _find_target(settings):
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
    filters = ALL_FILTERS
    mode = settings.scan_mode
    depth = max(1, settings.depth)
    target_kind, target_obj, target_bone = _find_target(settings)

    if target_kind == "BONE":
        object_scanner.add_object_node(graph, target_obj, filters)
        object_scanner.add_armature_and_bones(graph, target_obj, filters, include_all_bones=False)
        object_scanner.add_selected_bone_context(graph, target_obj, target_bone, filters)
        _expand_pose_bone_constraints(graph, target_obj, target_bone, filters)
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
    return graph


def _expand_object(graph, obj, filters, mode, depth, visited):
    if depth < 0 or obj.name in visited:
        object_scanner.add_object_node(graph, obj, filters)
        return
    visited.add(obj.name)

    object_scanner.add_object_node(graph, obj, filters)

    if mode in {"USES", "BOTH"}:
        object_scanner.add_object_data_refs(graph, obj, filters)
        collection_scanner.add_object_collections(graph, obj, filters)
        constraint_scanner.add_object_constraints(graph, obj, filters)
        geonodes_scanner.add_geometry_nodes_modifiers(graph, obj, filters)
        object_scanner.add_armature_and_bones(graph, obj, filters)

        if obj.parent and _allowed(filters, "OBJECT"):
            object_scanner.add_object_node(graph, obj.parent, filters)
            graph.add_edge(object_scanner.object_id(obj), object_scanner.object_id(obj.parent), "child_of", "parent")
            if depth > 1:
                _expand_object(graph, obj.parent, filters, "USES", depth - 1, visited)

    if mode in {"USED_BY", "BOTH"}:
        if obj.type == "MESH" and obj.data:
            object_scanner.add_mesh_node(graph, obj.data, filters)
            for user in bpy.data.objects:
                if user != obj and user.data == obj.data:
                    object_scanner.add_object_node(graph, user, filters)
                    graph.add_edge(object_scanner.mesh_id(obj.data), object_scanner.object_id(user), "used_by_object", "used by")
        for child in obj.children:
            object_scanner.add_object_node(graph, child, filters)
            graph.add_edge(object_scanner.object_id(obj), object_scanner.object_id(child), "parent_of", "child")
            if depth > 1:
                _expand_object(graph, child, filters, "USES", depth - 1, visited)


def _expand_pose_bone_constraints(graph, armature_obj, bone_name, filters):
    if not _allowed(filters, "CONSTRAINT"):
        return
    pose_bone = armature_obj.pose.bones.get(bone_name) if armature_obj.pose else None
    if not pose_bone:
        return
    constraint_scanner.add_pose_bone_constraints(graph, armature_obj, pose_bone, filters)
