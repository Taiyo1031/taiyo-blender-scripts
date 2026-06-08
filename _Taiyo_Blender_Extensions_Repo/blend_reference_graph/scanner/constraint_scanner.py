from .object_scanner import bone_id, object_id


def constraint_id(owner_id, constraint):
    return f"Constraint:{owner_id}:{constraint.name}"


def _allowed(filters, node_type):
    return filters.get(node_type, True)


def add_constraint_node(graph, owner_id, constraint, filters, owner_name):
    if not _allowed(filters, "CONSTRAINT"):
        return ""
    node_id = constraint_id(owner_id, constraint)
    graph.add_node(
        node_id,
        "CONSTRAINT",
        constraint.name,
        f"CON {constraint.name}",
        details={
            "owner": owner_name,
            "type": constraint.type,
            "target": constraint.target.name if getattr(constraint, "target", None) else "",
            "subtarget": getattr(constraint, "subtarget", ""),
            "influence": getattr(constraint, "influence", 0.0),
            "mute": getattr(constraint, "mute", False),
        },
    )
    graph.add_edge(owner_id, node_id, "has_constraint", "has constraint")
    return node_id


def add_object_constraints(graph, obj, filters):
    for constraint in obj.constraints:
        node_id = add_constraint_node(graph, object_id(obj), constraint, filters, obj.name)
        _add_constraint_targets(graph, node_id, constraint, filters)


def add_pose_bone_constraints(graph, armature_obj, pose_bone, filters):
    owner_id = bone_id(armature_obj, pose_bone.name)
    for constraint in pose_bone.constraints:
        node_id = add_constraint_node(
            graph,
            owner_id,
            constraint,
            filters,
            f"{armature_obj.name} / {pose_bone.name}",
        )
        _add_constraint_targets(graph, node_id, constraint, filters)


def _add_constraint_targets(graph, constraint_node_id, constraint, filters):
    if not constraint_node_id:
        return
    if not hasattr(constraint, "target"):
        return
    target = getattr(constraint, "target", None)
    if target:
        if _allowed(filters, "OBJECT"):
            graph.add_node(
                object_id(target),
                "OBJECT",
                target.name,
                f"OBJ {target.name}",
                details={"object_type": target.type},
            )
            graph.add_edge(constraint_node_id, object_id(target), "constraint_target", "target")
        subtarget = getattr(constraint, "subtarget", "")
        if subtarget and target.type == "ARMATURE" and _allowed(filters, "BONE"):
            graph.add_node(bone_id(target, subtarget), "BONE", subtarget, f"BONE {target.name} / {subtarget}")
            graph.add_edge(constraint_node_id, bone_id(target, subtarget), "constraint_subtarget", "subtarget")
    else:
        warning_id = f"Warning:{constraint_node_id}:MissingTarget"
        graph.add_node(warning_id, "WARNING", "Missing Constraint Target", "WARN Missing Target")
        graph.add_edge(constraint_node_id, warning_id, "missing_reference", "missing target")

    pole_target = getattr(constraint, "pole_target", None)
    if pole_target and _allowed(filters, "OBJECT"):
        graph.add_node(
            object_id(pole_target),
            "OBJECT",
            pole_target.name,
            f"OBJ {pole_target.name}",
            details={"object_type": pole_target.type},
        )
        graph.add_edge(constraint_node_id, object_id(pole_target), "constraint_pole_target", "pole target")
        pole_subtarget = getattr(constraint, "pole_subtarget", "")
        if pole_subtarget and pole_target.type == "ARMATURE" and _allowed(filters, "BONE"):
            graph.add_node(
                bone_id(pole_target, pole_subtarget),
                "BONE",
                pole_subtarget,
                f"BONE {pole_target.name} / {pole_subtarget}",
            )
            graph.add_edge(
                constraint_node_id,
                bone_id(pole_target, pole_subtarget),
                "constraint_subtarget",
                "pole subtarget",
            )
