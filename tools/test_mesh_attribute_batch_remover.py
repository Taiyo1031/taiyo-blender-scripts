import importlib.util
import tempfile
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
ADDON_PATH = (
    ROOT
    / "_Taiyo_Blender_Extensions_Repo"
    / "mesh_attribute_batch_remover"
    / "__init__.py"
)
PREFIX = "MABR_Test_"


def load_addon():
    module_name = "mesh_attribute_batch_remover_test"
    spec = importlib.util.spec_from_file_location(module_name, ADDON_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reset_scene():
    if bpy.context.mode != "OBJECT" and bpy.context.object is not None:
        bpy.ops.object.mode_set(mode="OBJECT")

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            try:
                bpy.data.meshes.remove(mesh)
            except RuntimeError:
                pass


def new_mesh_object(name, *, scene=None, mesh=None, hidden=False):
    scene = scene or bpy.context.scene
    if mesh is None:
        mesh = bpy.data.meshes.new(name + "Mesh")
        mesh.from_pydata(
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            [],
            [(0, 1, 2)],
        )
        mesh.update()

    obj = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(obj)
    if hidden:
        obj.hide_set(True)
        obj.hide_viewport = True
    return obj


def select_only(*objects, active=None):
    for obj in bpy.context.view_layer.objects:
        if obj is not None:
            obj.select_set(False)
    for obj in objects:
        obj.hide_set(False)
        obj.hide_viewport = False
        obj.select_set(True)
    bpy.context.view_layer.objects.active = active or (objects[0] if objects else None)


def assert_finished(result):
    assert result == {"FINISHED"}, result


def assert_remove_cancelled():
    try:
        result = bpy.ops.mabr.remove_attribute("EXEC_DEFAULT")
    except RuntimeError:
        return
    assert result == {"CANCELLED"}, result


def test_selected_scope(addon):
    reset_scene()
    selected = new_mesh_object(PREFIX + "Selected")
    unselected = new_mesh_object(PREFIX + "Unselected")
    empty = bpy.data.objects.new(PREFIX + "Empty", None)
    bpy.context.scene.collection.objects.link(empty)

    selected.data.attributes.new("remove_me", "FLOAT", "POINT")
    selected.data.attributes.new("keep_me", "INT", "POINT")
    selected.data.attributes.new("Remove_Me", "FLOAT", "POINT")
    unselected.data.attributes.new("remove_me", "FLOAT", "POINT")

    select_only(selected, empty, active=selected)
    settings = bpy.context.scene.mabr_settings
    settings.scope = "SELECTED"
    settings.attribute_name = "remove_me"

    preview = addon._build_preview(bpy.context)
    assert preview["target_object_count"] == 1, preview
    assert preview["unique_mesh_count"] == 1, preview
    assert preview["attribute_count"] == 1, preview

    assert_finished(bpy.ops.mabr.remove_attribute("EXEC_DEFAULT"))
    assert selected.data.attributes.get("remove_me") is None
    assert selected.data.attributes.get("keep_me") is not None
    assert selected.data.attributes.get("Remove_Me") is not None
    assert unselected.data.attributes.get("remove_me") is not None

    settings.attribute_name = "REMOVE_ME"
    assert_remove_cancelled()
    assert selected.data.attributes.get("Remove_Me") is not None


def test_scene_scope_and_hidden(addon):
    reset_scene()
    visible = new_mesh_object(PREFIX + "Visible")
    hidden = new_mesh_object(PREFIX + "Hidden", hidden=True)
    visible.data.attributes.new("scene_remove", "FLOAT", "POINT")
    hidden.data.attributes.new("scene_remove", "INT", "FACE")

    select_only(visible)
    hidden.hide_set(True)
    hidden.hide_viewport = True

    settings = bpy.context.scene.mabr_settings
    settings.scope = "SCENE"
    settings.attribute_name = "scene_remove"

    preview = addon._build_preview(bpy.context)
    assert preview["target_object_count"] == 2, preview
    assert preview["attribute_count"] == 2, preview

    assert_finished(bpy.ops.mabr.remove_attribute("EXEC_DEFAULT"))
    assert visible.data.attributes.get("scene_remove") is None
    assert hidden.data.attributes.get("scene_remove") is None


def test_shared_mesh_warning_and_unique_processing(addon):
    reset_scene()
    shared_mesh = bpy.data.meshes.new(PREFIX + "SharedMesh")
    shared_mesh.from_pydata(
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        [],
        [(0, 1, 2)],
    )
    shared_mesh.attributes.new("shared_remove", "FLOAT", "POINT")

    selected_a = new_mesh_object(PREFIX + "SharedA", mesh=shared_mesh)
    selected_b = new_mesh_object(PREFIX + "SharedB", mesh=shared_mesh)
    outside = new_mesh_object(PREFIX + "SharedOutside", mesh=shared_mesh)

    select_only(selected_a, selected_b, active=selected_a)
    settings = bpy.context.scene.mabr_settings
    settings.scope = "SELECTED"
    settings.attribute_name = "shared_remove"

    preview = addon._build_preview(bpy.context)
    assert preview["target_object_count"] == 2, preview
    assert preview["unique_mesh_count"] == 1, preview
    assert preview["attribute_count"] == 1, preview
    assert preview["shared_mesh_count"] == 1, preview
    assert preview["outside_shared_object_count"] == 1, preview

    result = addon._remove_named_attribute(bpy.context)
    assert result["deleted_attribute_count"] == 1, result
    assert shared_mesh.attributes.get("shared_remove") is None
    assert outside.data == shared_mesh


def test_protected_attributes(addon):
    reset_scene()
    obj = new_mesh_object(PREFIX + "Protected")
    select_only(obj)
    settings = bpy.context.scene.mabr_settings
    settings.scope = "SELECTED"

    position = obj.data.attributes.get("position")
    assert position is not None
    assert position.is_required or position.is_internal
    settings.attribute_name = "position"
    preview = addon._build_preview(bpy.context)
    assert preview["attribute_count"] == 0, preview
    assert preview["protected_attribute_count"] == 1, preview
    assert_remove_cancelled()
    assert obj.data.attributes.get("position") is not None

    internal = next(
        attribute
        for attribute in obj.data.attributes
        if attribute.is_internal and not attribute.is_required
    )
    settings.attribute_name = internal.name
    preview = addon._build_preview(bpy.context)
    assert preview["attribute_count"] == 0, preview
    assert preview["protected_attribute_count"] == 1, preview
    assert_remove_cancelled()
    assert obj.data.attributes.get(internal.name) is not None


def test_empty_and_missing_name(addon):
    reset_scene()
    obj = new_mesh_object(PREFIX + "EmptyName")
    obj.data.attributes.new("keep_me", "FLOAT", "POINT")
    select_only(obj)
    settings = bpy.context.scene.mabr_settings
    settings.scope = "SELECTED"

    settings.attribute_name = "   "
    preview = addon._build_preview(bpy.context)
    assert preview["error"]
    assert_remove_cancelled()
    assert obj.data.attributes.get("keep_me") is not None

    settings.attribute_name = "missing"
    assert_remove_cancelled()
    assert obj.data.attributes.get("keep_me") is not None


def test_non_editable_linked_mesh(addon, temp_dir):
    reset_scene()
    source_mesh = bpy.data.meshes.new(PREFIX + "LinkedMesh")
    source_mesh.from_pydata(
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        [],
        [(0, 1, 2)],
    )
    source_mesh.attributes.new("linked_remove", "FLOAT", "POINT")
    library_path = temp_dir / "mabr_library.blend"
    bpy.data.libraries.write(str(library_path), {source_mesh})
    bpy.data.meshes.remove(source_mesh)

    with bpy.data.libraries.load(str(library_path), link=True) as (
        data_from,
        data_to,
    ):
        data_to.meshes = [PREFIX + "LinkedMesh"]

    linked_mesh = data_to.meshes[0]
    linked_object = bpy.data.objects.new(PREFIX + "LinkedObject", linked_mesh)
    bpy.context.scene.collection.objects.link(linked_object)

    editable = new_mesh_object(PREFIX + "Editable")
    editable.data.attributes.new("linked_remove", "FLOAT", "POINT")
    select_only(linked_object, editable, active=editable)

    settings = bpy.context.scene.mabr_settings
    settings.scope = "SELECTED"
    settings.attribute_name = "linked_remove"
    preview = addon._build_preview(bpy.context)
    assert preview["non_editable_mesh_count"] == 1, preview
    assert preview["attribute_count"] == 1, preview

    assert_finished(bpy.ops.mabr.remove_attribute("EXEC_DEFAULT"))
    assert editable.data.attributes.get("linked_remove") is None
    assert linked_mesh.attributes.get("linked_remove") is not None


def main():
    addon = load_addon()
    assert "UNDO" in addon.MABR_OT_remove_attribute.bl_options
    addon.register()
    try:
        assert hasattr(bpy.types.Scene, "mabr_settings")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            test_selected_scope(addon)
            test_scene_scope_and_hidden(addon)
            test_shared_mesh_warning_and_unique_processing(addon)
            test_protected_attributes(addon)
            test_empty_and_missing_name(addon)
            test_non_editable_linked_mesh(addon, temp_path)
    finally:
        reset_scene()
        addon.unregister()

    assert not hasattr(bpy.types.Scene, "mabr_settings")
    print("Mesh Attribute Batch Remover integration tests passed.")


if __name__ == "__main__":
    main()
