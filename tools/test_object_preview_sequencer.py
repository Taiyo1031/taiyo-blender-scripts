import importlib.util
import os
import tempfile
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
ADDON_PATH = ROOT / "_Taiyo_Blender_Extensions_Repo" / "object_preview_sequencer" / "__init__.py"


def load_addon():
    spec = importlib.util.spec_from_file_location("object_preview_sequencer_test", ADDON_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reset_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)


def make_object(name, collection):
    mesh = bpy.data.meshes.new(name + "Mesh")
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


def select_only(objects, active=None):
    for obj in bpy.context.view_layer.objects:
        obj.select_set(False)
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = active or (objects[-1] if objects else None)


def make_fixture():
    reset_scene()
    root = bpy.context.scene.collection
    collection_a = bpy.data.collections.new("A_Collection")
    collection_b = bpy.data.collections.new("B_Collection")
    root.children.link(collection_a)
    root.children.link(collection_b)

    first = make_object("First", collection_a)
    second = make_object("Second", collection_b)
    unregistered = make_object("Unregistered", collection_b)

    bpy.context.view_layer.update()
    return first, second, unregistered


def assert_visibility(frame, visible, hidden):
    bpy.context.scene.frame_set(frame)
    bpy.context.view_layer.update()
    assert not visible.hide_viewport, f"{visible.name} should be visible on frame {frame}"
    assert not visible.hide_render, f"{visible.name} should render on frame {frame}"
    for obj in hidden:
        assert obj.hide_viewport, f"{obj.name} should be hidden on frame {frame}"
        assert obj.hide_render, f"{obj.name} should be render-hidden on frame {frame}"


def assert_all_hidden(frame, objects):
    bpy.context.scene.frame_set(frame)
    bpy.context.view_layer.update()
    for obj in objects:
        assert obj.hide_viewport, f"{obj.name} should be hidden on frame {frame}"
        assert obj.hide_render, f"{obj.name} should be render-hidden on frame {frame}"


def action_fcurve_paths(action):
    paths = {fcurve.data_path for fcurve in getattr(action, "fcurves", [])}
    for layer in getattr(action, "layers", []):
        for strip in getattr(layer, "strips", []):
            for channelbag in getattr(strip, "channelbags", []):
                paths.update(fcurve.data_path for fcurve in channelbag.fcurves)
    return paths


def test_register_build_restore(addon):
    first, second, unregistered = make_fixture()
    original_action = bpy.data.actions.new("Original_First_Action")
    first.animation_data_create()
    first.animation_data.action = original_action

    second.hide_render = True
    unregistered.hide_viewport = False
    unregistered.hide_render = False

    scene = bpy.context.scene
    scene.frame_start = 10
    scene.frame_end = 100
    scene.frame_set(42)

    select_only([second, first], active=second)
    result = bpy.ops.opseq.register_selected()
    assert result == {"FINISHED"}, result

    settings = scene.opseq_settings
    registered_names = [item.object.name for item in settings.registered_objects]
    assert registered_names == ["First", "Second"], registered_names

    result = bpy.ops.opseq.build_sequence()
    assert result == {"FINISHED"}, result
    assert settings.sequence_active
    assert scene.frame_start == 42
    assert scene.frame_end == 43
    assert scene.frame_current == 42

    temp_action = first.animation_data.action
    assert temp_action is not original_action
    assert temp_action.name.startswith(addon.TEMP_ACTION_PREFIX)
    assert temp_action.get(addon.TEMP_ACTION_MARKER)
    assert action_fcurve_paths(temp_action) == {"hide_viewport", "hide_render"}

    assert_visibility(42, first, [second, unregistered])
    assert_visibility(43, second, [first, unregistered])
    assert_all_hidden(44, [first, second, unregistered])

    assert scene.get(addon.RESTORE_STATE_KEY), "Expected restore data to be saved in the .blend scene"
    addon._clear_collection(settings.restore_items)
    settings.sequence_active = False
    settings.sequence_start = 0
    settings.sequence_end = 0
    addon._sync_scene_from_persistent_state(scene)
    assert settings.sequence_active, "Expected saved restore data to re-enable restore mode"

    result = bpy.ops.opseq.restore_sequence()
    assert result == {"FINISHED"}, result
    assert not settings.sequence_active
    assert addon.RESTORE_STATE_KEY not in scene
    assert first.animation_data.action == original_action
    assert second.animation_data is None or second.animation_data.action is None
    assert scene.frame_start == 10
    assert scene.frame_end == 100
    assert scene.frame_current == 42
    assert not first.hide_viewport
    assert not first.hide_render
    assert not second.hide_viewport
    assert second.hide_render
    assert not unregistered.hide_viewport
    assert not unregistered.hide_render
    assert second.select_get()
    assert first.select_get()
    assert bpy.context.view_layer.objects.active == second
    assert not [action for action in bpy.data.actions if action.name.startswith(addon.TEMP_ACTION_PREFIX)]


def test_start_frame_is_clamped_to_one(addon):
    first, second, _unregistered = make_fixture()
    scene = bpy.context.scene
    scene.frame_start = -20
    scene.frame_end = 20
    scene.frame_set(0)
    original_frame_start = scene.frame_start
    original_frame_end = scene.frame_end
    select_only([first, second], active=second)

    result = bpy.ops.opseq.register_selected()
    assert result == {"FINISHED"}, result
    result = bpy.ops.opseq.build_sequence()
    assert result == {"FINISHED"}, result

    settings = scene.opseq_settings
    assert settings.sequence_active
    assert scene.frame_start == 1
    assert scene.frame_end == 2
    assert_visibility(1, first, [second])
    assert_visibility(2, second, [first])

    result = bpy.ops.opseq.restore_sequence()
    assert result == {"FINISHED"}, result
    assert scene.frame_start == original_frame_start
    assert scene.frame_end == original_frame_end
    assert scene.frame_current == 0


def test_restore_after_save_and_reopen(addon):
    first, second, _unregistered = make_fixture()
    original_action = bpy.data.actions.new("Original_Reopen_Action")
    first.animation_data_create()
    first.animation_data.action = original_action

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 80
    scene.frame_set(5)
    select_only([first, second], active=first)

    assert bpy.ops.opseq.register_selected() == {"FINISHED"}
    assert bpy.ops.opseq.build_sequence() == {"FINISHED"}
    assert scene.get(addon.RESTORE_STATE_KEY)

    handle = tempfile.NamedTemporaryFile(suffix=".blend", delete=False)
    filepath = handle.name
    handle.close()
    try:
        bpy.ops.wm.save_as_mainfile(filepath=filepath)
        bpy.ops.wm.open_mainfile(filepath=filepath)
        addon._sync_all_scenes_from_persistent_state()

        reopened_scene = bpy.context.scene
        settings = reopened_scene.opseq_settings
        assert settings.sequence_active
        assert bpy.ops.opseq.restore_sequence() == {"FINISHED"}

        reopened_first = bpy.data.objects["First"]
        reopened_second = bpy.data.objects["Second"]
        assert reopened_first.animation_data.action.name == "Original_Reopen_Action"
        assert reopened_scene.frame_start == 1
        assert reopened_scene.frame_end == 80
        assert reopened_scene.frame_current == 5
        assert reopened_first.select_get()
        assert reopened_second.select_get()
        assert bpy.context.view_layer.objects.active == reopened_first
        assert addon.RESTORE_STATE_KEY not in reopened_scene
        assert not [action for action in bpy.data.actions if action.name.startswith(addon.TEMP_ACTION_PREFIX)]
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)


def test_deleted_registered_object_is_skipped(addon):
    first, second, _unregistered = make_fixture()
    scene = bpy.context.scene
    scene.frame_set(7)
    select_only([first, second], active=second)

    result = bpy.ops.opseq.register_selected()
    assert result == {"FINISHED"}, result
    bpy.data.objects.remove(second, do_unlink=True)
    bpy.context.view_layer.update()

    result = bpy.ops.opseq.build_sequence()
    assert result == {"FINISHED"}, result
    settings = scene.opseq_settings
    assert settings.sequence_active
    assert scene.frame_start == 7
    assert scene.frame_end == 7
    assert not first.hide_viewport

    result = bpy.ops.opseq.restore_sequence()
    assert result == {"FINISHED"}, result
    assert not settings.sequence_active


def main():
    addon = load_addon()
    addon.register()
    try:
        test_register_build_restore(addon)
        test_start_frame_is_clamped_to_one(addon)
        test_restore_after_save_and_reopen(addon)
        test_deleted_registered_object_is_skipped(addon)
    finally:
        if hasattr(bpy.types.Scene, "opseq_settings"):
            settings = getattr(bpy.context.scene, "opseq_settings", None)
            if settings is not None and settings.sequence_active:
                addon.restore_sequence(bpy.context, settings)
        addon.unregister()
        assert not hasattr(bpy.types.Scene, "opseq_settings")
        reset_scene()


if __name__ == "__main__":
    main()
