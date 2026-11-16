"""Integration test for Reimport Selected Meshes.

blender --background --factory-startup --python-exit-code 1 --python tools/test_reimport_selected_meshes.py
"""
import importlib.util
import math
import os
import tempfile
from pathlib import Path

import bmesh
import bpy

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "_Taiyo_Blender_Extensions_Repo" / "reimport_selected_meshes" / "__init__.py"


def load_addon():
    spec = importlib.util.spec_from_file_location("reimport_selected_meshes_under_test", ADDON)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reset():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for kind in ("meshes", "materials", "images", "collections"):
        for item in list(getattr(bpy.data, kind)):
            getattr(bpy.data, kind).remove(item)
    s = bpy.context.scene.rsm_settings
    s.fbx_folder, s.recursive, s.prefer_folder = "", True, False
    s.bake_transform = s.keep_materials = s.linear_colors = True


def cube_mesh(name, size, material=None, color=None):
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=size)
    bm.to_mesh(mesh)
    bm.free()
    if material:
        mesh.materials.append(material)
    if color:
        attr = mesh.color_attributes.new("Col", "FLOAT_COLOR", "CORNER")
        for item in attr.data:
            item.color = color
    return mesh


def add_object(name, mesh):
    ob = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def select(*objects):
    bpy.context.view_layer.update()
    for ob in list(bpy.context.view_layer.objects):
        if ob is not None:
            ob.select_set(False)
    for ob in objects:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]


def export_fbx(path, objects, **options):
    select(*objects)
    options.setdefault("use_selection", True)
    bpy.ops.export_scene.fbx(filepath=str(path), **options)


def make_fbx(path, items, **options):
    """items: [(name, size, material name or None)]. The temporary data is removed again."""
    before = {k: set(getattr(bpy.data, k)) for k in ("objects", "meshes", "materials")}
    objects = []
    for name, size, mat in items:
        material = bpy.data.materials.new(mat) if mat else None
        objects.append(add_object(name, cube_mesh(name, size, material)))
    export_fbx(path, objects, **options)
    for ob in list(bpy.data.objects):
        if ob not in before["objects"]:
            bpy.data.objects.remove(ob)
    for kind in ("meshes", "materials"):
        for item in list(getattr(bpy.data, kind)):
            if item not in before[kind]:
                getattr(bpy.data, kind).remove(item)


def extent(mesh):
    return addon.max_extent(mesh)


def approx(a, b, tolerance=1e-3):
    return math.isclose(a, b, abs_tol=tolerance)


def run(**kwargs):
    return bpy.ops.rsm.reimport("EXEC_DEFAULT", **kwargs)


def counts():
    return {k: len(getattr(bpy.data, k)) for k in ("objects", "meshes", "materials", "images", "collections")}


def test_folder_search_linked_users_materials(tmp):
    reset()
    make_fbx(tmp / "Rock.fbx", [("Rock", 1.5, "Stone")])
    stone = bpy.data.materials.new("Stone")
    mesh = cube_mesh("Rock", 1.0, stone)
    obs = [add_object(n, mesh) for n in ("Rock", "Rock.001", "Rock.002")]
    other = add_object("Other", cube_mesh("Other", 1.0))
    bpy.context.scene.rsm_settings.fbx_folder = str(tmp)
    select(obs[0])
    before = counts()
    assert run() == {"FINISHED"}
    assert counts() == before, (counts(), before)
    assert {ob.data for ob in obs} == {bpy.data.meshes["Rock"]}, [ob.data.name for ob in obs]
    new = bpy.data.meshes["Rock"]
    assert approx(extent(new), 1.5), extent(new)
    assert [m.name for m in new.materials] == ["Stone"], [m.name for m in new.materials]
    assert new.materials[0] is stone
    assert approx(extent(other.data), 1.0)
    assert new.get(addon.SRC_KEY) == str(tmp / "Rock.fbx")
    assert [o.name for o in bpy.data.objects] == ["Rock", "Rock.001", "Rock.002", "Other"] or len(bpy.data.objects) == 4
    assert obs[0].select_get() and not other.select_get()


def test_multi_geometry_by_name_and_remembered_path(tmp):
    reset()
    multi = tmp / "Multi.fbx"
    make_fbx(multi, [("B", 3.0, None), ("C", 5.0, None)])
    b, c, e = (cube_mesh(n, 1.0) for n in ("B", "C", "E"))
    ob_b, ob_c, ob_e = add_object("B", b), add_object("C", c), add_object("E", e)
    select(ob_b, ob_c, ob_e)
    assert run(filepath=str(multi)) == {"FINISHED"}
    assert approx(extent(bpy.data.meshes["B"]), 3.0)
    assert approx(extent(bpy.data.meshes["C"]), 5.0)
    assert approx(extent(bpy.data.meshes["E"]), 1.0)  # not in the FBX: untouched
    assert bpy.data.meshes["E"].get(addon.SRC_KEY) is None
    assert len(bpy.data.meshes) == 3 and len(bpy.data.objects) == 3, counts()
    # The FBX changes; the recorded path is used without any folder or file argument.
    make_fbx(multi, [("B", 4.0, None), ("C", 5.0, None)])
    select(ob_b)
    assert run() == {"FINISHED"}
    assert approx(extent(bpy.data.meshes["B"]), 4.0)
    assert approx(extent(bpy.data.meshes["C"]), 5.0)
    # One target against a multi mesh FBX still needs a name match.
    select(ob_e)
    assert run(filepath=str(multi)) == {"CANCELLED"}
    assert approx(extent(bpy.data.meshes["E"]), 1.0)


def test_unresolved_and_ambiguous(tmp):
    reset()
    ob = add_object("Lonely", cube_mesh("Lonely", 1.0))
    select(ob)
    before = counts()
    assert run() == {"CANCELLED"}
    assert counts() == before
    (tmp / "a").mkdir(exist_ok=True)
    (tmp / "b").mkdir(exist_ok=True)
    make_fbx(tmp / "a" / "Twin.fbx", [("Twin", 2.0, None)])
    make_fbx(tmp / "b" / "Twin.fbx", [("Twin", 4.0, None)])
    twin = add_object("Twin", cube_mesh("Twin", 1.0))
    bpy.context.scene.rsm_settings.fbx_folder = str(tmp)
    select(twin)
    plan = addon.make_plan(bpy.context, bpy.context.scene.rsm_settings)
    assert [t.mesh.name for t in plan.unresolved] == ["Twin"] and plan.warnings, (plan.unresolved, plan.warnings)
    assert run() == {"CANCELLED"}
    assert approx(extent(bpy.data.meshes["Twin"]), 1.0)
    bpy.context.scene.rsm_settings.recursive = False
    plan = addon.make_plan(bpy.context, bpy.context.scene.rsm_settings)
    assert len(plan.unresolved) == 1 and not plan.warnings


def test_rollback(tmp):
    reset()
    make_fbx(tmp / "Roll.fbx", [("Roll", 2.0, "Paint")])
    mesh = cube_mesh("Roll", 1.0)
    ob = add_object("Roll", mesh)
    bpy.context.scene.rsm_settings.fbx_folder = str(tmp)
    select(ob)
    before = counts()
    original = addon.max_extent
    calls = {"n": 0}

    def failing(mesh_):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom")
        return original(mesh_)

    addon.max_extent = failing
    try:
        try:
            run()  # an ERROR report raises RuntimeError when called from Python
            raise AssertionError("the failure was not reported")
        except RuntimeError as exc:
            assert "rolled back" in str(exc), exc
    finally:
        addon.max_extent = original
    assert counts() == before, (counts(), before)
    assert ob.data is mesh and approx(extent(mesh), 1.0)
    assert ob.select_get()


def test_bake_transform_and_size_warning(tmp):
    reset()
    # A centimetre mesh under an object with scale 0.01, like a Houdini FBX.
    mesh = cube_mesh("Cm", 200.0)
    ob = add_object("Cm", mesh)
    ob.scale = (0.01, 0.01, 0.01)
    ob.rotation_euler = (math.radians(90), 0, 0)
    path = tmp / "Cm.fbx"
    export_fbx(path, [ob])
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(mesh)
    old = cube_mesh("Cm", 2.0)
    target = add_object("Cm", old)
    select(target)
    bpy.context.scene.rsm_settings.fbx_folder = str(tmp)
    assert run() == {"FINISHED"}
    assert approx(extent(bpy.data.meshes["Cm"]), 2.0, 0.02), extent(bpy.data.meshes["Cm"])
    assert len(bpy.data.objects) == 1 and len(bpy.data.meshes) == 1
    # A wrong size is reported through the result (checked on the data function).
    reset()
    make_fbx(tmp / "Big.fbx", [("Big", 100.0, None)])
    target = add_object("Big", cube_mesh("Big", 1.0))
    select(target)
    bpy.context.scene.rsm_settings.fbx_folder = str(tmp)
    plan = addon.make_plan(bpy.context, bpy.context.scene.rsm_settings)
    result = addon.reimport(bpy.context, bpy.context.scene.rsm_settings, plan)
    assert any("size changed" in w for w in result.warnings), result.warnings


def test_vertex_colors_linear(tmp):
    reset()
    color = (0.2, 0.4, 0.6, 1.0)
    reference = cube_mesh("Col", 1.0, color=color)
    ob = add_object("Col", reference)
    export_fbx(tmp / "Col.fbx", [ob], colors_type="LINEAR")
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(reference)
    for linear, expected in ((True, color[:3]), (False, None)):
        reset()
        target = add_object("Col", cube_mesh("Col", 1.0))
        select(target)
        bpy.context.scene.rsm_settings.fbx_folder = str(tmp)
        bpy.context.scene.rsm_settings.linear_colors = linear
        assert run() == {"FINISHED"}
        attrs = bpy.data.meshes["Col"].color_attributes
        assert len(attrs) >= 1
        got = tuple(attrs[0].data[0].color)[:3]
        if linear:
            assert all(approx(g, e, 0.01) for g, e in zip(got, expected)), got
        else:
            print("vertex color without Linear:", got)


def test_undo(tmp):
    reset()
    make_fbx(tmp / "Undo.fbx", [("Undo", 3.0, None)])
    mesh = cube_mesh("Undo", 1.0)
    ob = add_object("Undo", mesh)
    bpy.context.scene.rsm_settings.fbx_folder = str(tmp)
    select(ob)
    bpy.ops.ed.undo_push(message="before")
    assert bpy.ops.rsm.reimport("EXEC_DEFAULT", True) == {"FINISHED"}
    assert approx(extent(bpy.data.objects["Undo"].data), 3.0)
    bpy.ops.ed.undo()
    assert approx(extent(bpy.data.objects["Undo"].data), 1.0), extent(bpy.data.objects["Undo"].data)
    bpy.ops.ed.redo()
    assert approx(extent(bpy.data.objects["Undo"].data), 3.0)


def main():
    global addon
    addon = load_addon()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    addon.register()
    try:
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            for test in (test_folder_search_linked_users_materials, test_multi_geometry_by_name_and_remembered_path,
                         test_unresolved_and_ambiguous, test_rollback, test_bake_transform_and_size_warning,
                         test_vertex_colors_linear, test_undo):
                test(tmp)
                print("ok", test.__name__)
    finally:
        addon.unregister()
    assert not hasattr(bpy.types.Scene, "rsm_settings")
    print("Reimport Selected Meshes: all tests passed")


if __name__ == "__main__":
    main()
