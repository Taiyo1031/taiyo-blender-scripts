from .id_utils import id_key
from .path_utils import object_collection_paths


def object_id(obj):
    return f"Object:{id_key(obj)}"


def mesh_id(mesh):
    return f"Mesh:{id_key(mesh)}"


def armature_id(obj):
    return f"Armature:{id_key(obj)}"


def bone_id(armature_obj, bone_name):
    return f"Bone:{id_key(armature_obj)}:{bone_name}"


def _allowed(filters, node_type):
    return filters.get(node_type, True)


def add_object_node(graph, obj, filters, path_cache=None):
    if object_id(obj) in graph.nodes or not _allowed(filters, "OBJECT"):
        return
    path_cache = path_cache or getattr(graph, "path_cache", None)
    paths = path_cache.object_paths(obj) if path_cache else object_collection_paths(obj)
    details = {
        "object_type": obj.type,
        "data": obj.data.name if obj.data else "",
        "parent": obj.parent.name if obj.parent else "",
        "collections": paths,
        "modifiers": [modifier.name for modifier in obj.modifiers],
        "constraints": [constraint.name for constraint in obj.constraints],
    }
    graph.add_node(
        object_id(obj),
        "OBJECT",
        obj.name,
        f"OBJ {obj.name}",
        path=paths[0] if paths else "",
        details=details,
    )


def add_mesh_node(graph, mesh, filters):
    if not mesh or mesh_id(mesh) in graph.nodes or not _allowed(filters, "MESH"):
        return
    details = {
        "users": mesh.users,
        "materials": [material.name for material in mesh.materials if material],
        "uv_maps": [uv.name for uv in mesh.uv_layers],
        "color_attributes": [attribute.name for attribute in mesh.color_attributes],
    }
    graph.add_node(mesh_id(mesh), "MESH", mesh.name, f"MESH {mesh.name}", details=details)


def add_object_data_refs(graph, obj, filters):
    if obj.type == "MESH" and obj.data:
        add_mesh_node(graph, obj.data, filters)
        graph.add_edge(object_id(obj), mesh_id(obj.data), "uses_mesh", "uses mesh")
    elif obj.type == "ARMATURE":
        add_armature_and_bones(graph, obj, filters)


def add_armature_and_bones(graph, obj, filters, include_all_bones=True):
    for _ in iter_armature_and_bones(graph, obj, filters, include_all_bones):
        pass


def iter_armature_and_bones(graph, obj, filters, include_all_bones=True):
    if obj.type != "ARMATURE" or not obj.data:
        return
    data_id = getattr(graph, "datablock_ids", {}).get(obj.data, armature_id(obj))
    if _allowed(filters, "ARMATURE"):
        graph.add_node(data_id, "ARMATURE", obj.name, f"ARM {obj.name}")
        graph.add_edge(object_id(obj), data_id, "uses_armature", "uses armature")
    if not _allowed(filters, "BONE"):
        return
    bones = obj.data.bones if include_all_bones else []
    for bone in bones:
        add_bone_node(graph, obj, bone.name)
        graph.add_edge(data_id, bone_id(obj, bone.name), "contains_bone", "bone")
        if bone.parent:
            add_bone_node(graph, obj, bone.parent.name)
            graph.add_edge(bone_id(obj, bone.parent.name), bone_id(obj, bone.name), "parent_of", "child bone")
        yield None


def add_bone_node(graph, armature_obj, bone_name):
    graph.add_node(
        bone_id(armature_obj, bone_name),
        "BONE",
        bone_name,
        f"BONE {armature_obj.name} / {bone_name}",
        details={"armature": armature_obj.name, "bone": bone_name},
    )


def add_selected_bone_context(graph, armature_obj, bone_name, filters):
    if not _allowed(filters, "BONE"):
        return
    bone = armature_obj.data.bones.get(bone_name)
    if not bone:
        return
    add_bone_node(graph, armature_obj, bone.name)
    graph.add_edge(armature_id(armature_obj), bone_id(armature_obj, bone.name), "contains_bone", "bone")
    if bone.parent:
        add_bone_node(graph, armature_obj, bone.parent.name)
        graph.add_edge(
            bone_id(armature_obj, bone.parent.name),
            bone_id(armature_obj, bone.name),
            "parent_of",
            "child bone",
        )
    for child in bone.children:
        add_bone_node(graph, armature_obj, child.name)
        graph.add_edge(
            bone_id(armature_obj, bone.name),
            bone_id(armature_obj, child.name),
            "parent_of",
            "child bone",
        )
