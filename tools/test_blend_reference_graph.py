import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import bpy


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "_Taiyo_Blender_Extensions_Repo"
sys.path.insert(0, str(SOURCE_ROOT))

import blend_reference_graph
from blend_reference_graph.graph import build_graph
from blend_reference_graph.graph.graph_exporter import resolve_output_folder


PREFIX = "BRG_Test_"


def assert_node(graph, node_id):
    assert node_id in graph.nodes, f"Missing node: {node_id}"


def assert_edge(graph, from_id, to_id, relation):
    key = (from_id, to_id, relation)
    actual = {(edge["from"], edge["to"], edge["relation"]) for edge in graph.edges}
    assert key in actual, f"Missing edge: {key}"


def assert_no_dangling_edges(graph):
    for edge in graph.edges:
        assert edge["from"] in graph.nodes, f"Dangling edge source: {edge}"
        assert edge["to"] in graph.nodes, f"Dangling edge target: {edge}"


def new_object(name, data=None):
    obj = bpy.data.objects.new(PREFIX + name, data)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def create_fixture():
    parent = new_object("Parent")
    target = new_object("ConstraintTarget")

    mesh = bpy.data.meshes.new(PREFIX + "SharedMesh")
    source = new_object("Source", mesh)
    shared_user = new_object("SharedUser", mesh)
    source.parent = parent

    child_mesh = bpy.data.meshes.new(PREFIX + "ChildMesh")
    child = new_object("Child", child_mesh)
    child.parent = source

    parent_collection_a = bpy.data.collections.new(PREFIX + "ParentA")
    parent_collection_b = bpy.data.collections.new(PREFIX + "ParentB")
    collection = bpy.data.collections.new(PREFIX + "Collection")
    bpy.context.scene.collection.children.link(parent_collection_a)
    bpy.context.scene.collection.children.link(parent_collection_b)
    parent_collection_a.children.link(collection)
    parent_collection_b.children.link(collection)
    collection.objects.link(source)
    second_scene = bpy.data.scenes.new(PREFIX + "SecondScene")
    second_scene.collection.children.link(collection)

    constraint = source.constraints.new("COPY_LOCATION")
    constraint.name = PREFIX + "CopyLocation"
    constraint.target = target
    limit_constraint = source.constraints.new("LIMIT_LOCATION")
    limit_constraint.name = PREFIX + "LimitLocation"

    material = bpy.data.materials.new(PREFIX + "Material")
    image = bpy.data.images.new(PREFIX + "Image", width=8, height=8)
    referenced_object = new_object("GNObject")
    nested_object = new_object("GNNestedObject")
    referenced_collection = bpy.data.collections.new(PREFIX + "GNCollection")
    bpy.context.scene.collection.children.link(referenced_collection)

    sub_group = bpy.data.node_groups.new(PREFIX + "SubGroup", "GeometryNodeTree")
    sub_object_info = sub_group.nodes.new("GeometryNodeObjectInfo")
    sub_object_info.inputs["Object"].default_value = nested_object
    node_group = bpy.data.node_groups.new(PREFIX + "NodeGroup", "GeometryNodeTree")
    node_group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    node_group.nodes.new("NodeGroupOutput")

    object_info = node_group.nodes.new("GeometryNodeObjectInfo")
    object_info.inputs["Object"].default_value = referenced_object
    collection_info = node_group.nodes.new("GeometryNodeCollectionInfo")
    collection_info.inputs["Collection"].default_value = referenced_collection
    set_material = node_group.nodes.new("GeometryNodeSetMaterial")
    set_material.inputs["Material"].default_value = material
    image_texture = node_group.nodes.new("GeometryNodeImageTexture")
    image_texture.inputs["Image"].default_value = image
    group_node = node_group.nodes.new("GeometryNodeGroup")
    group_node.node_tree = sub_group

    modifier = source.modifiers.new(PREFIX + "GeometryNodes", "NODES")
    modifier.node_group = node_group

    armature_data = bpy.data.armatures.new(PREFIX + "ArmatureData")
    armature = new_object("Armature", armature_data)
    pole_target = new_object("PoleTarget")
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    root_bone = armature_data.edit_bones.new(PREFIX + "RootBone")
    root_bone.tail = (0.0, 0.0, 1.0)
    child_bone = armature_data.edit_bones.new(PREFIX + "ChildBone")
    child_bone.head = root_bone.tail
    child_bone.tail = (0.0, 0.0, 2.0)
    child_bone.parent = root_bone
    root_bone_name = root_bone.name
    child_bone_name = child_bone.name
    bpy.ops.object.mode_set(mode="POSE")
    bone_constraint = armature.pose.bones[child_bone_name].constraints.new("COPY_LOCATION")
    bone_constraint.name = PREFIX + "BoneCopyLocation"
    bone_constraint.target = target
    ik_constraint = armature.pose.bones[child_bone_name].constraints.new("IK")
    ik_constraint.name = PREFIX + "IK"
    ik_constraint.target = target
    ik_constraint.pole_target = pole_target
    bpy.ops.object.mode_set(mode="OBJECT")
    armature.select_set(False)

    return {
        "source": source,
        "parent": parent,
        "target": target,
        "child": child,
        "shared_user": shared_user,
        "mesh": mesh,
        "child_mesh": child_mesh,
        "collection": collection,
        "parent_collection_a": parent_collection_a,
        "parent_collection_b": parent_collection_b,
        "second_scene": second_scene,
        "node_group": node_group,
        "sub_group": sub_group,
        "material": material,
        "image": image,
        "referenced_object": referenced_object,
        "nested_object": nested_object,
        "referenced_collection": referenced_collection,
        "armature": armature,
        "pole_target": pole_target,
        "root_bone": root_bone_name,
        "child_bone": child_bone_name,
    }


def configure(settings, target, depth=1):
    settings.target_type = "OBJECT"
    settings.target_name = target.name
    settings.target_id = f"Object:{target.name}"
    settings.scan_mode = "BOTH"
    settings.depth = depth


def test_object_graph(fixture):
    settings = bpy.context.scene.brg_settings
    configure(settings, fixture["source"], depth=1)
    graph = build_graph(bpy.context, settings)

    source_id = f"Object:{fixture['source'].name}"
    mesh_id = f"Mesh:{fixture['mesh'].name}"
    parent_id = f"Object:{fixture['parent'].name}"
    child_id = f"Object:{fixture['child'].name}"
    constraint_id = f"Constraint:{source_id}:{PREFIX}CopyLocation"
    modifier_id = f"Modifier:{fixture['source'].name}:{PREFIX}GeometryNodes"
    node_group_id = f"NodeGroup:{fixture['node_group'].name}"
    collection_id = f"Collection:{fixture['collection'].name}"

    for node_id in (
        source_id,
        mesh_id,
        parent_id,
        child_id,
        constraint_id,
        modifier_id,
        node_group_id,
        f"Object:{fixture['target'].name}",
        f"Object:{fixture['shared_user'].name}",
        f"Object:{fixture['referenced_object'].name}",
        f"Object:{fixture['nested_object'].name}",
        f"Collection:{fixture['referenced_collection'].name}",
        f"Material:{fixture['material'].name}",
        f"Image:{fixture['image'].name}",
        f"NodeGroup:{fixture['sub_group'].name}",
        collection_id,
    ):
        assert_node(graph, node_id)

    assert_edge(graph, source_id, mesh_id, "uses_mesh")
    assert_edge(graph, source_id, parent_id, "child_of")
    assert_edge(graph, source_id, child_id, "parent_of")
    assert_edge(graph, constraint_id, f"Object:{fixture['target'].name}", "constraint_target")
    assert_edge(graph, modifier_id, node_group_id, "uses_node_group")
    assert_edge(
        graph,
        f"NodeGroup:{fixture['sub_group'].name}",
        f"Object:{fixture['nested_object'].name}",
        "references_object",
    )
    assert_edge(graph, mesh_id, f"Object:{fixture['shared_user'].name}", "used_by_object")
    collection_node = graph.nodes[collection_id]
    expected_paths = {
        " / ".join((
            bpy.context.scene.name,
            bpy.context.scene.collection.name,
            fixture["parent_collection_a"].name,
            fixture["collection"].name,
        )),
        " / ".join((
            bpy.context.scene.name,
            bpy.context.scene.collection.name,
            fixture["parent_collection_b"].name,
            fixture["collection"].name,
        )),
        " / ".join((
            fixture["second_scene"].name,
            fixture["second_scene"].collection.name,
            fixture["collection"].name,
        )),
    }
    assert set(collection_node["details"]["paths"]) == expected_paths
    assert collection_node["path"] == sorted(expected_paths)[0]
    source_node = graph.nodes[source_id]
    assert expected_paths.issubset(set(source_node["details"]["collections"]))
    assert f"Warning:Constraint:{source_id}:{PREFIX}LimitLocation:MissingTarget" not in graph.nodes
    assert f"Mesh:{fixture['child_mesh'].name}" not in graph.nodes, "Depth 1 expanded child references"
    assert_no_dangling_edges(graph)

    configure(settings, fixture["source"], depth=2)
    graph = build_graph(bpy.context, settings)
    assert_node(graph, f"Mesh:{fixture['child_mesh'].name}")
    assert_no_dangling_edges(graph)


def test_removed_filters_and_full_scan(fixture):
    settings = bpy.context.scene.brg_settings
    configure(settings, fixture["source"], depth=1)
    graph = build_graph(bpy.context, settings)
    for property_name in (
        "include_objects",
        "include_meshes",
        "include_collections",
        "include_materials",
        "include_images",
        "output_folder",
        "viewer_file",
    ):
        assert not hasattr(settings, property_name), f"Removed property still exists: {property_name}"
    assert f"Material:{fixture['material'].name}" in graph.nodes
    assert f"Image:{fixture['image'].name}" in graph.nodes
    assert_no_dangling_edges(graph)


def test_bone_graph(fixture):
    settings = bpy.context.scene.brg_settings
    settings.target_type = "BONE"
    settings.target_name = f"{fixture['armature'].name} / {fixture['child_bone']}"
    settings.target_id = f"Bone:{fixture['armature'].name}:{fixture['child_bone']}"
    graph = build_graph(bpy.context, settings)

    bone_id = f"Bone:{fixture['armature'].name}:{fixture['child_bone']}"
    root_bone_id = f"Bone:{fixture['armature'].name}:{fixture['root_bone']}"
    armature_id = f"Armature:{fixture['armature'].name}"
    constraint_id = f"Constraint:{bone_id}:{PREFIX}BoneCopyLocation"
    ik_constraint_id = f"Constraint:{bone_id}:{PREFIX}IK"
    assert_node(graph, bone_id)
    assert_node(graph, root_bone_id)
    assert_node(graph, constraint_id)
    assert_node(graph, ik_constraint_id)
    assert_edge(graph, armature_id, bone_id, "contains_bone")
    assert_edge(graph, root_bone_id, bone_id, "parent_of")
    assert_edge(graph, constraint_id, f"Object:{fixture['target'].name}", "constraint_target")
    assert_edge(
        graph,
        ik_constraint_id,
        f"Object:{fixture['pole_target'].name}",
        "constraint_pole_target",
    )
    assert_no_dangling_edges(graph)


def test_output_folders():
    temp_preferences = SimpleNamespace(output_mode="TEMP", custom_output_folder="")
    output = resolve_output_folder(bpy.context, temp_preferences)
    expected = Path(tempfile.gettempdir()).resolve() / "blend_reference_graph" / str(os.getpid())
    assert output == expected
    assert output.is_dir()
    result = bpy.ops.brg.update_graph_data()
    assert "FINISHED" in result
    assert Path(bpy.context.scene.brg_settings.resolved_output_path) == expected
    for filename in ("graph_data.js", "viewer.html", "viewer.css", "viewer.js"):
        assert (expected / filename).is_file(), f"Missing generated viewer file: {filename}"
    viewer_js = (expected / "viewer.js").read_text(encoding="utf-8")
    viewer_css = (expected / "viewer.css").read_text(encoding="utf-8")
    viewer_html = (expected / "viewer.html").read_text(encoding="utf-8")
    assert 'class: "edge-label"' in viewer_js
    assert 'class: "node-selected-badge"' in viewer_js
    assert "githubUrl" in viewer_js
    assert ".node.selected .node-selection-halo" in viewer_css
    assert 'id="github"' in viewer_html
    assert 'id="shortcuts"' in viewer_html

    with tempfile.TemporaryDirectory() as custom_directory:
        custom_preferences = SimpleNamespace(
            output_mode="CUSTOM",
            custom_output_folder=custom_directory,
        )
        custom_output = resolve_output_folder(bpy.context, custom_preferences)
        assert custom_output == Path(custom_directory).resolve()

    empty_preferences = SimpleNamespace(output_mode="CUSTOM", custom_output_folder="")
    try:
        resolve_output_folder(bpy.context, empty_preferences)
    except ValueError as exc:
        assert "not set" in str(exc)
    else:
        raise AssertionError("Empty custom output folder did not fail")

    with tempfile.TemporaryDirectory() as custom_directory:
        file_path = Path(custom_directory) / "not_a_directory"
        file_path.write_text("x", encoding="utf-8")
        invalid_preferences = SimpleNamespace(
            output_mode="CUSTOM",
            custom_output_folder=str(file_path),
        )
        try:
            resolve_output_folder(bpy.context, invalid_preferences)
        except OSError as exc:
            assert "not writable" in str(exc)
        else:
            raise AssertionError("Non-directory custom output path did not fail")


def main():
    blend_reference_graph.register()
    try:
        fixture = create_fixture()
        test_object_graph(fixture)
        test_removed_filters_and_full_scan(fixture)
        test_bone_graph(fixture)
        test_output_folders()
        print("Blend Reference Graph integration tests passed")
    finally:
        blend_reference_graph.unregister()


main()
