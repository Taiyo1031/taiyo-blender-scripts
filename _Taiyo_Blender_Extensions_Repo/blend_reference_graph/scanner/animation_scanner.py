from .id_utils import id_key
import bpy

from . import library_scanner
from .collection_scanner import add_collection_node, collection_id
from .geonodes_scanner import add_node_group_node, node_group_id
from .object_scanner import (
    add_armature_and_bones,
    add_bone_node,
    add_mesh_node,
    add_object_node,
    armature_id,
    bone_id,
    mesh_id,
    object_id,
)


def action_id(action):
    return f"Action:{id_key(action)}"


def driver_id(owner_id, fcurve):
    return f"Driver:{owner_id}:{fcurve.data_path}:{fcurve.array_index}"


def _allowed(filters, node_type):
    return filters.get(node_type, True)


def add_action_node(graph, action, filters):
    if not action or not _allowed(filters, "ACTION"):
        return ""
    node_id = action_id(action)
    if node_id in graph.nodes:
        return node_id
    graph.add_node(
        node_id,
        "ACTION",
        action.name,
        f"ACT {action.name}",
        details={
            "frame_range": [round(value, 3) for value in action.frame_range],
            "fcurves": len(getattr(action, "fcurves", ())),
            "groups": [group.name for group in getattr(action, "groups", ())],
            "users": action.users,
        },
    )
    library_scanner.add_id_library_link(graph, node_id, action, filters)
    return node_id


def add_object_animation_refs(graph, obj, filters, visited=None):
    for _ in iter_object_animation_refs(graph, obj, filters, visited):
        pass


def iter_object_animation_refs(graph, obj, filters, visited=None):
    yield from iter_animation_data_refs(graph, obj, object_id(obj), obj.name, filters)
    if visited is not None:
        if obj.data in visited:
            return
        visited.add(obj.data)
    if not obj.data:
        return
    if obj.type == "MESH":
        add_mesh_node(graph, obj.data, filters)
        yield from iter_animation_data_refs(graph, obj.data, mesh_id(obj.data), obj.data.name, filters)
    elif obj.type == "ARMATURE":
        data_id = getattr(graph, "datablock_ids", {}).get(obj.data, armature_id(obj))
        yield from iter_animation_data_refs(graph, obj.data, data_id, obj.data.name, filters)


def add_animation_data_refs(graph, owner, owner_id, owner_name, filters):
    for _ in iter_animation_data_refs(graph, owner, owner_id, owner_name, filters):
        pass


def iter_animation_data_refs(graph, owner, owner_id, owner_name, filters):
    animation_data = getattr(owner, "animation_data", None)
    if not animation_data:
        return
    _add_action_ref(graph, owner_id, owner_name, animation_data.action, "uses_action", "action", filters)
    for track in animation_data.nla_tracks:
        for strip in track.strips:
            _add_action_ref(
                graph,
                owner_id,
                owner_name,
                strip.action,
                "uses_nla_action",
                f"NLA {track.name}",
                filters,
            )
            yield None
    for fcurve in animation_data.drivers:
        add_driver_ref(graph, owner_id, owner_name, fcurve, filters)
        yield None


def add_driver_ref(graph, owner_id, owner_name, fcurve, filters):
    if not _allowed(filters, "DRIVER"):
        return
    node_id = driver_id(owner_id, fcurve)
    driver = fcurve.driver
    variables = []
    for variable in driver.variables:
        target_descriptions = []
        for target in variable.targets:
            target_descriptions.append(_driver_target_description(target))
        variables.append(f"{variable.name} ({variable.type}): {', '.join(target_descriptions)}")
    graph.add_node(
        node_id,
        "DRIVER",
        fcurve.data_path,
        f"DRV {owner_name}",
        details={
            "owner": owner_name,
            "data_path": fcurve.data_path,
            "array_index": fcurve.array_index,
            "expression": driver.expression,
            "type": driver.type,
            "variables": variables,
            "mute": fcurve.mute,
        },
    )
    graph.add_edge(owner_id, node_id, "has_driver", "driver")
    _add_driver_targets(graph, node_id, driver, filters)


def add_incoming_driver_users(graph, target_datablock, filters):
    for _ in iter_incoming_driver_users(graph, target_datablock, filters):
        pass


def iter_incoming_driver_users(graph, target_datablock, filters):
    target_node_id = _add_datablock_node(graph, target_datablock, filters)
    if not target_node_id:
        return
    for owner, owner_id, owner_name, owner_node_source in _iter_animation_owners():
        animation_data = getattr(owner, "animation_data", None)
        if not animation_data:
            yield None
            continue
        for fcurve in animation_data.drivers:
            if _driver_targets_datablock(fcurve.driver, target_datablock):
                _add_owner_node(graph, owner_node_source, filters)
                add_driver_ref(graph, owner_id, owner_name, fcurve, filters)
            yield None
        yield None


def _add_action_ref(graph, owner_id, owner_name, action, relation, label, filters):
    action_node_id = add_action_node(graph, action, filters)
    if not action_node_id:
        return
    graph.add_edge(owner_id, action_node_id, relation, label)


def _add_driver_targets(graph, driver_node_id, driver, filters):
    for variable in driver.variables:
        for target in variable.targets:
            target_id = _add_datablock_node(graph, target.id, filters)
            if target_id:
                if target.bone_target and getattr(target.id, "type", "") == "ARMATURE" and _allowed(filters, "BONE"):
                    add_bone_node(graph, target.id, target.bone_target)
                    graph.add_edge(driver_node_id, bone_id(target.id, target.bone_target), "driver_bone_target", "driver bone")
                else:
                    graph.add_edge(driver_node_id, target_id, "driver_target", "driver target")
            else:
                warning_id = f"Warning:{driver_node_id}:{variable.name}:MissingDriverTarget"
                graph.add_node(
                    warning_id,
                    "WARNING",
                    "Missing Driver Target",
                    "WARN Missing Driver Target",
                    details={"driver": driver_node_id, "variable": variable.name},
                )
                graph.add_edge(driver_node_id, warning_id, "missing_reference", "missing driver target")


def _add_datablock_node(graph, datablock, filters):
    if not datablock:
        return ""
    if hasattr(graph, "datablock_ids"):
        owner = getattr(graph, "embedded_owner", {}).get(datablock, datablock)
        return graph.datablock_ids.get(owner, "")
    if isinstance(datablock, bpy.types.Object):
        add_object_node(graph, datablock, filters)
        return object_id(datablock)
    if isinstance(datablock, bpy.types.Mesh):
        add_mesh_node(graph, datablock, filters)
        return mesh_id(datablock)
    if isinstance(datablock, bpy.types.Collection):
        add_collection_node(graph, datablock, filters)
        return collection_id(datablock)
    if isinstance(datablock, bpy.types.Material) and _allowed(filters, "MATERIAL"):
        node_id = f"Material:{id_key(datablock)}"
        graph.add_node(node_id, "MATERIAL", datablock.name, f"MAT {datablock.name}")
        library_scanner.add_id_library_link(graph, node_id, datablock, filters)
        return node_id
    if isinstance(datablock, bpy.types.Image) and _allowed(filters, "IMAGE"):
        node_id = f"Image:{id_key(datablock)}"
        graph.add_node(node_id, "IMAGE", datablock.name, f"IMG {datablock.name}")
        library_scanner.add_id_library_link(graph, node_id, datablock, filters)
        return node_id
    if isinstance(datablock, bpy.types.NodeTree):
        add_node_group_node(graph, datablock, filters)
        return node_group_id(datablock)
    if isinstance(datablock, bpy.types.Action):
        return add_action_node(graph, datablock, filters)
    return ""


def _iter_animation_owners():
    for obj in bpy.data.objects:
        yield obj, object_id(obj), obj.name, obj
        if obj.data and obj.type == "MESH":
            yield obj.data, mesh_id(obj.data), obj.data.name, obj.data
        elif obj.data and obj.type == "ARMATURE":
            yield obj.data, armature_id(obj), obj.data.name, obj


def _add_owner_node(graph, owner, filters):
    if isinstance(owner, bpy.types.Object):
        add_object_node(graph, owner, filters)
        if owner.type == "ARMATURE":
            add_armature_and_bones(graph, owner, filters, include_all_bones=False)
    elif isinstance(owner, bpy.types.Mesh):
        add_mesh_node(graph, owner, filters)


def _driver_targets_datablock(driver, datablock):
    for variable in driver.variables:
        for target in variable.targets:
            if target.id == datablock:
                return True
    return False


def _driver_target_description(target):
    if not target.id:
        return "missing"
    name = target.id.name
    if target.bone_target:
        name = f"{name} / {target.bone_target}"
    if target.data_path:
        name = f"{name} [{target.data_path}]"
    return name
