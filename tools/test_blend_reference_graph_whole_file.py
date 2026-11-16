import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest import mock
import wave

sys.dont_write_bytecode = True
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "_Taiyo_Blender_Extensions_Repo"))
import blend_reference_graph as addon
from blend_reference_graph import operators
from blend_reference_graph.graph import GraphData, build_node_graph, iter_build_node_graph
from blend_reference_graph.graph.graph_exporter import export_graph_data
from blend_reference_graph.scanner import geonodes_scanner, whole_file_scanner
from blend_reference_graph.scanner.id_utils import build_node_id_index, id_key, resolve_node_id
from blend_reference_graph.scanner.object_scanner import add_object_node, object_id
from blend_reference_graph.scanner.path_utils import CollectionPathCache
from blend_reference_graph.scanner.whole_file_scanner import ScanOptions, iter_scan, run_to_end
from blend_reference_graph.version import VERSION, VERSION_TUPLE


def new_object(name, data=None):
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def fixture(folder):
    mesh = bpy.data.meshes.new("WholeMesh")
    obj = new_object("WholeObject", mesh)
    parent = new_object("WholeParent", mesh)
    grandparent = new_object("WholeGrandparent")
    parent.parent = grandparent
    obj.parent = parent
    material = bpy.data.materials.new("WholeMaterial")
    material.use_nodes = True
    image = bpy.data.images.new("WholeImage", 2, 2)
    material.node_tree.nodes.new("ShaderNodeTexImage").image = image
    mesh.materials.append(material)
    orphan = bpy.data.materials.new("WholeOrphan")
    fake = bpy.data.materials.new("WholeFake")
    fake.use_fake_user = True
    collection = bpy.data.collections.new("WholeCollection")
    bpy.context.scene.collection.children.link(collection)
    collection.objects.link(obj)
    scene = bpy.data.scenes.new("WholeScene")
    scene.collection.children.link(collection)
    world = bpy.data.worlds.new("WholeWorld")
    world.use_nodes = True
    scene.world = world
    camera = bpy.data.cameras.new("WholeCamera")
    light = bpy.data.lights.new("WholeLight", "POINT")
    curve = bpy.data.curves.new("WholeCurve", "CURVE")
    text = bpy.data.texts.new("WholeText")
    font_curve = bpy.data.curves.new("WholeFontCurve", "FONT")
    font = font_curve.font
    sound_path = folder / "whole.wav"
    with wave.open(str(sound_path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\0\0" * 80)
    sound = bpy.data.sounds.load(str(sound_path))
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.particle_system_add()
    particle = obj.particle_systems[-1].settings
    particle.name = "WholeParticle"
    obj.select_set(False)
    texture = bpy.data.textures.new("WholeTexture", "IMAGE")
    texture.image = image
    group = bpy.data.node_groups.new("WholeGroup", "GeometryNodeTree")
    group.nodes.new("GeometryNodeObjectInfo").inputs["Object"].default_value = parent
    for owner in (obj, parent):
        owner.modifiers.new("WholeModifier", "NODES").node_group = group
    obj.constraints.new("COPY_LOCATION").target = parent
    obj.animation_data_create()
    action = bpy.data.actions.new("WholeAction")
    obj.animation_data.action = action
    driver = obj.driver_add("scale", 0).driver
    driver.variables.new().targets[0].id = parent

    arm_data = bpy.data.armatures.new("WholeArmatureData")
    arm = new_object("WholeArmatureObject", arm_data)
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    previous = None
    for i in range(4):
        bone = arm_data.edit_bones.new(f"WholeBone{i}")
        bone.head = (0, 0, i)
        bone.tail = (0, 0, i + 1)
        bone.parent = previous
        previous = bone
    bpy.ops.object.mode_set(mode="OBJECT")
    arm.select_set(False)
    bone_driver = parent.driver_add("scale", 1).driver.variables.new()
    bone_driver.type = "TRANSFORMS"
    bone_driver.targets[0].id = arm
    bone_driver.targets[0].bone_target = "WholeBone3"

    local = new_object("WholeSameName")
    linked = []
    for dirname in ("a", "b"):
        directory = folder / dirname
        directory.mkdir()
        library_path = directory / "same.blend"
        bpy.data.libraries.write(str(library_path), {local})
        with bpy.data.libraries.load(str(library_path), link=True) as (_, data_to):
            data_to.objects = [local.name]
        linked_obj = data_to.objects[0]
        bpy.context.scene.collection.objects.link(linked_obj)
        linked.append(linked_obj)

    expected = {
        "OBJECT": "Object:" + obj.name, "MESH": "Mesh:" + mesh.name,
        "ARMATURE": "Armature:" + arm_data.name, "COLLECTION": "Collection:" + collection.name,
        "MATERIAL": "Material:" + material.name, "IMAGE": "Image:" + image.name,
        "NODEGROUP": "NodeGroup:" + group.name, "ACTION": "Action:" + action.name,
        "SCENE": "Scene:" + scene.name, "WORLD": "World:" + world.name,
        "CAMERA": "Camera:" + camera.name, "LIGHT": "Light:" + light.name,
        "CURVE": "Curve:" + curve.name, "TEXT": "Text:" + text.name,
        "FONT": "Font:" + font.name, "SOUND": "Sound:" + sound.name,
        "PARTICLE": "Particle:" + particle.name, "TEXTURE": "Texture:" + texture.name,
    }
    return SimpleNamespace(**locals())


def valid_edges(graph):
    assert all(edge["from"] in graph.nodes and edge["to"] in graph.nodes for edge in graph.edges)


def edge(graph, source, target, relation):
    assert (source, target, relation) in {
        (item["from"], item["to"], item["relation"]) for item in graph.edges
    }, (source, target, relation)


def test_whole(f):
    calls = []

    class DataProxy:
        def __getattr__(self, name):
            return getattr(bpy.data, name)

        def user_map(self):
            calls.append(1)
            return bpy.data.user_map()

    with mock.patch.object(whole_file_scanner, "bpy", SimpleNamespace(data=DataProxy(), types=bpy.types)):
        graph = run_to_end(GraphData(), ScanOptions(include_internals=False))
    assert len(calls) == 1
    for group, node_id in f.expected.items():
        assert node_id in graph.nodes, node_id
        node = graph.nodes[node_id]
        assert node["type"] == group and node["group"] == group
        assert set(("users", "use_fake_user", "orphan")) <= node["details"].keys()
    edge(graph, object_id(f.obj), "Mesh:WholeMesh", "uses_data")
    edge(graph, "Collection:WholeCollection", object_id(f.obj), "contains")
    assert any(item["to"] == "Material:WholeMaterial" and item["from"] in {
        "Mesh:WholeMesh", object_id(f.obj)} for item in graph.edges)
    edge(graph, "Material:WholeMaterial", "Image:WholeImage", "references")
    edge(graph, object_id(f.obj), object_id(f.parent), "child_of")
    edge(graph, "Scene:WholeScene", "Collection:WholeCollection", "child_collection")
    assert graph.nodes["Material:WholeOrphan"]["details"]["orphan"] is True
    assert graph.nodes["Material:WholeFake"]["details"]["orphan"] is False
    index = build_node_id_index()
    ids = {object_id(f.local), *(object_id(obj) for obj in f.linked)}
    assert len(ids) == 3
    assert object_id(f.local) == "Object:WholeSameName"
    for linked in f.linked:
        expected = f"Object:WholeSameName [lib:{linked.library.name}]"
        assert object_id(linked) == expected
        assert expected in graph.nodes
        assert resolve_node_id(expected, index) == linked
        edge(graph, expected, "Library:" + linked.library.filepath, "linked_from_library")
    assert all(not block.is_embedded_data for key, block in index.items() if key in graph.nodes)
    assert all(node["type"] not in {"CONSTRAINT", "MODIFIER", "DRIVER", "BONE"} for node in graph.nodes.values())
    assert all(not key.startswith(("WindowManager:", "WorkSpace:", "Screen:")) for key in graph.nodes)
    assert all(item["from"] != item["to"] for item in graph.edges)
    valid_edges(graph)

    with mock.patch.object(geonodes_scanner, "_add_socket_reference", wraps=geonodes_scanner._add_socket_reference) as sockets:
        full = run_to_end(GraphData(), ScanOptions())
    assert sockets.call_count == sum(len(node.inputs) for node in f.group.nodes)
    assert {"CONSTRAINT", "MODIFIER", "DRIVER"} <= {node["type"] for node in full.nodes.values()}
    assert not any(node["type"] == "BONE" for node in full.nodes.values())
    bones = run_to_end(GraphData(), ScanOptions(include_bones=True, max_bones=2))
    assert sum(node["type"] == "BONE" for node in bones.nodes.values()) == 2
    assert bones.meta["truncated"] == ["BONE: limited to 2 nodes"]
    assert "Armature:WholeArmatureObject" not in bones.nodes
    unlimited = run_to_end(GraphData(), ScanOptions(include_bones=True))
    assert sum(node["type"] == "BONE" for node in unlimited.nodes.values()) == 4
    valid_edges(bones)
    limited = run_to_end(GraphData(), ScanOptions(node_limit_per_type={"OBJECT": 1}))
    assert limited.type_counts["OBJECT"] == 1 and limited.meta["truncated"]
    valid_edges(limited)
    return full


def test_node(f):
    one = build_node_graph(bpy.context, object_id(f.obj), "USES", 1)
    two = build_node_graph(bpy.context, object_id(f.obj), "USES", 2)
    assert object_id(f.parent) in one.nodes
    assert object_id(f.grandparent) not in one.nodes
    assert object_id(f.grandparent) in two.nodes
    incoming = build_node_graph(bpy.context, object_id(f.parent), "USED_BY", 1)
    assert object_id(f.obj) in incoming.nodes
    assert "SafeDelete:" + object_id(f.obj) in one.nodes
    linked = build_node_graph(bpy.context, object_id(f.linked[0]), "USES", 1)
    assert object_id(f.linked[0]) in linked.nodes
    bone = build_node_graph(bpy.context, "Bone:WholeArmatureObject:WholeBone1")
    assert "Bone:WholeArmatureObject:WholeBone1" in bone.nodes
    uses = build_node_graph(bpy.context, "Material:WholeMaterial", "USES", 1)
    used_by = build_node_graph(bpy.context, "Material:WholeMaterial", "USED_BY", 1)
    both = build_node_graph(bpy.context, "Material:WholeMaterial", "BOTH", 2)
    assert "Image:WholeImage" in uses.nodes
    assert "Mesh:WholeMesh" not in uses.nodes
    assert "Mesh:WholeMesh" in used_by.nodes
    assert "Image:WholeImage" not in used_by.nodes
    assert "Mesh:WholeMesh" in both.nodes and "Image:WholeImage" in both.nodes
    for graph in (one, two, incoming, uses, used_by, both, bone):
        assert graph.meta["scope"] == "NODE"
        assert graph.meta["target_id"] in graph.nodes
        valid_edges(graph)
    for node_id in ("Object:DoesNotExist", "Material:DoesNotExist", "Bone:Missing:Bone"):
        try:
            build_node_graph(bpy.context, node_id)
        except ValueError as exc:
            assert str(exc) == f"Node not found: {node_id}"
        else:
            raise AssertionError(node_id)
    iterator = iter_build_node_graph(bpy.context, "Material:WholeMaterial")
    while True:
        try:
            progress, _ = next(iterator)
            assert 0 <= progress <= 1
        except StopIteration as result:
            assert result.value.meta["target_id"] == "Material:WholeMaterial"
            break


def test_cache_and_cancel(f, folder):
    cache = CollectionPathCache()
    assert cache.object_paths(f.obj) == sorted({path for coll in cache.memberships[f.obj] for path in cache.paths.get(coll, ())})
    graph = GraphData()
    add_object_node(graph, f.obj, {}, cache)
    with mock.patch("blend_reference_graph.scanner.object_scanner.object_collection_paths", side_effect=AssertionError("Repeated path traversal")):
        add_object_node(graph, f.obj, {})
    before = sorted(folder.iterdir())
    graph = GraphData()
    iterator = iter_scan(graph)
    for _ in range(3):
        next(iterator)
        valid_edges(graph)
    iterator.close()
    assert sorted(folder.iterdir()) == before


def test_payload(graph, folder):
    _, payload = export_graph_data(graph, {}, folder, compact=True)
    raw = (folder / "graph_data.json").read_text()
    assert json.loads(raw) == payload
    js = (folder / "graph_data.js").read_text()
    assert json.loads(js.removeprefix("window.BRG_GRAPH_DATA = ").removesuffix(";\n")) == payload
    assert len(raw.splitlines()) == 1
    assert all("group" in node for node in payload["nodes"])
    assert payload["meta"]["version"] == VERSION
    assert payload["meta"]["scope"] == "WHOLE_FILE"
    assert payload["meta"]["type_counts"] == dict(graph.type_counts)
    assert payload["meta"]["scan_seconds"] >= 0
    manifest = (Path(addon.__file__).parent / "blender_manifest.toml").read_text()
    version_line = next(line for line in manifest.splitlines() if line.startswith("version = "))
    assert version_line == f'version = "{VERSION}"'
    assert addon.bl_info["version"] == VERSION_TUPLE == tuple(map(int, VERSION.split(".")))


def test_modal(folder):
    cls = operators.BRG_OT_scan_whole_file
    settings = bpy.context.scene.brg_settings
    settings.open_viewer_after_scan = False
    wm = mock.Mock()
    context = SimpleNamespace(scene=bpy.context.scene, window_manager=wm, window=None, area=mock.Mock())

    def instance():
        instance = SimpleNamespace(report=mock.Mock())
        for name in ("_cleanup", "_finish", "cancel"):
            setattr(instance, name, getattr(cls, name).__get__(instance))
        return instance

    for event_type in ("ESC", "RIGHTMOUSE"):
        instance_ = instance()
        with mock.patch.object(operators, "export_graph_data") as export:
            assert cls.invoke(instance_, context, None) == {"RUNNING_MODAL"}
            assert cls.modal(instance_, context, SimpleNamespace(type=event_type)) == {"CANCELLED"}
            export.assert_not_called()
        assert settings.status_message == "Cancelled"
        assert instance_._timer is None and instance_._iterator is None
    instance_ = instance()
    with mock.patch.object(operators, "resolve_output_folder", return_value=folder):
        assert cls.invoke(instance_, context, None) == {"RUNNING_MODAL"}
        for _ in range(10000):
            result = cls.modal(instance_, context, SimpleNamespace(type="TIMER"))
            if result != {"RUNNING_MODAL"}:
                break
        assert result == {"FINISHED"}
    assert settings.scan_progress == 100 and settings.node_count > 0
    assert instance_._timer is None
    assert json.loads((folder / "graph_data.json").read_text())["meta"]["scope"] == "WHOLE_FILE"
    instance_ = instance()
    assert cls.invoke(instance_, context, None) == {"RUNNING_MODAL"}
    with mock.patch.object(operators, "resolve_output_folder", return_value=folder), \
            mock.patch.object(operators, "export_graph_data", side_effect=OSError("test export error")):
        for _ in range(10000):
            result = cls.modal(instance_, context, SimpleNamespace(type="TIMER"))
            if result != {"RUNNING_MODAL"}:
                break
        assert result == {"CANCELLED"}
    assert settings.status_message == "test export error"
    assert instance_._timer is None
    assert wm.progress_begin.call_count == wm.progress_end.call_count == wm.event_timer_remove.call_count


def main():
    addon.register()
    try:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            f = fixture(folder)
            graph = test_whole(f)
            test_node(f)
            test_cache_and_cancel(f, folder)
            test_payload(graph, folder)
            test_modal(folder)
        print("Blend Reference Graph Whole File integration tests passed")
    finally:
        addon.unregister()


main()
