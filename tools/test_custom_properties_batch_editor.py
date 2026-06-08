import sys
import tempfile
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "_Taiyo_Blender_Extensions_Repo"
sys.path.insert(0, str(SOURCE_ROOT))

import custom_properties_batch_editor
from custom_properties_batch_editor import operators, preset_utils


PREFIX = "CPBE_Test_"


def assert_finished(result):
    assert result == {"FINISHED"}, result


def select_only(*objects, active=None):
    for obj in bpy.context.view_layer.objects:
        obj.select_set(False)
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = active or (objects[0] if objects else None)


def selected_names():
    return {obj.name for obj in bpy.context.selected_objects}


def create_fixture(temp_dir):
    shared_mesh = bpy.data.meshes.new(PREFIX + "SharedMesh")
    unique_mesh = bpy.data.meshes.new(PREFIX + "UniqueMesh")

    obj_a = bpy.data.objects.new(PREFIX + "A", shared_mesh)
    obj_b = bpy.data.objects.new(PREFIX + "B", shared_mesh)
    obj_c = bpy.data.objects.new(PREFIX + "C", unique_mesh)
    hidden = bpy.data.objects.new(PREFIX + "Hidden", None)
    disabled = bpy.data.objects.new(PREFIX + "Disabled", None)
    camera_data = bpy.data.cameras.new(PREFIX + "CameraData")
    camera = bpy.data.objects.new(PREFIX + "Camera", camera_data)

    for obj in (obj_a, obj_b, obj_c, hidden, disabled, camera):
        bpy.context.scene.collection.objects.link(obj)

    shared_material = bpy.data.materials.new(PREFIX + "SharedMaterial")
    shared_mesh.materials.append(shared_material)
    unique_mesh.materials.append(shared_material)

    hidden.hide_set(True)
    disabled.hide_viewport = True

    library_source = bpy.data.meshes.new(PREFIX + "LibraryMesh")
    library_path = temp_dir / "cpbe_library.blend"
    bpy.data.libraries.write(str(library_path), {library_source})
    bpy.data.meshes.remove(library_source)
    with bpy.data.libraries.load(str(library_path), link=True) as (data_from, data_to):
        data_to.meshes = [PREFIX + "LibraryMesh"]
    linked_mesh = data_to.meshes[0]
    linked_object = bpy.data.objects.new(PREFIX + "LinkedObject", linked_mesh)
    bpy.context.scene.collection.objects.link(linked_object)

    return {
        "a": obj_a,
        "b": obj_b,
        "c": obj_c,
        "hidden": hidden,
        "disabled": disabled,
        "camera": camera,
        "shared_mesh": shared_mesh,
        "unique_mesh": unique_mesh,
        "material": shared_material,
        "linked_object": linked_object,
        "linked_mesh": linked_mesh,
    }


def apply_property(settings, name, property_type, value, mode="UPSERT"):
    settings.property_name = name
    settings.property_type = property_type
    settings.operation_mode = mode
    setattr(settings, f"{property_type.lower()}_value", value)
    return bpy.ops.cpbe.apply_property()


def configure_selected(settings, target_type="OBJECT"):
    settings.target_type = target_type
    settings.scope = "SELECTED"
    settings.include_hidden = False
    settings.include_disabled_viewport = False
    settings.unique_data_only = True


def test_batch_editing(fixture):
    settings = bpy.context.scene.cpbe_settings
    a, b, c = fixture["a"], fixture["b"], fixture["c"]

    select_only(a, b)
    configure_selected(settings)
    assert_finished(apply_property(settings, "status", "STRING", "alpha"))
    assert a["status"] == "alpha"
    assert b["status"] == "alpha"
    assert settings.result_changed == 2

    assert_finished(apply_property(settings, "status", "STRING", "beta", mode="ADD_ONLY"))
    assert a["status"] == "alpha"
    assert b["status"] == "alpha"
    assert settings.result_skipped == 2

    a["edit_me"] = "old"
    assert_finished(apply_property(settings, "edit_me", "STRING", "new", mode="EDIT_ONLY"))
    assert a["edit_me"] == "new"
    assert "edit_me" not in b

    assert_finished(apply_property(settings, "int_value", "INT", 7))
    assert_finished(apply_property(settings, "float_value", "FLOAT", 1.25))
    assert_finished(apply_property(settings, "bool_value", "BOOL", True))
    assert isinstance(a["int_value"], int) and not isinstance(a["int_value"], bool)
    assert isinstance(a["float_value"], float)
    assert isinstance(a["bool_value"], bool)

    configure_selected(settings, "MESH")
    select_only(a, b)
    assert_finished(apply_property(settings, "asset_type", "STRING", "Wall"))
    assert fixture["shared_mesh"]["asset_type"] == "Wall"
    assert settings.result_changed == 1

    configure_selected(settings, "MATERIAL")
    select_only(a, c)
    assert_finished(apply_property(settings, "surface_type", "STRING", "Wood"))
    assert fixture["material"]["surface_type"] == "Wood"
    assert settings.result_changed == 1

    configure_selected(settings, "MESH")
    select_only(fixture["linked_object"])
    assert_finished(apply_property(settings, "linked_test", "BOOL", True))
    assert "linked_test" not in fixture["linked_mesh"]
    assert settings.result_skipped == 1


def search(settings, name, mode, select=True, property_type="STRING", value=None):
    settings.search_property_name = name
    settings.search_match_mode = mode
    settings.search_property_type = property_type
    if value is not None:
        if mode == "CONTAINS":
            settings.search_string_value = value
        else:
            setattr(settings, f"search_{property_type.lower()}_value", value)
    return bpy.ops.cpbe.search_property(select_results=select)


def test_search_and_scope(fixture):
    settings = bpy.context.scene.cpbe_settings
    a, b, c = fixture["a"], fixture["b"], fixture["c"]

    configure_selected(settings)
    select_only(a, b, c)
    assert_finished(search(settings, "status", "EXISTS"))
    assert selected_names() == {a.name, b.name}

    select_only(a, b, c)
    assert_finished(search(settings, "status", "EQUALS", value="alpha"))
    assert selected_names() == {a.name, b.name}

    select_only(a, b, c)
    settings.case_sensitive = False
    assert_finished(search(settings, "status", "CONTAINS", value="LPH"))
    assert selected_names() == {a.name, b.name}

    c["bool_value"] = False
    select_only(a, b, c)
    assert_finished(
        search(
            settings,
            "bool_value",
            "EQUALS",
            property_type="BOOL",
            value=True,
        )
    )
    assert selected_names() == {a.name, b.name}

    select_only(a, b, c)
    assert_finished(search(settings, "status", "NOT_EXISTS"))
    assert selected_names() == {c.name}

    configure_selected(settings, "MESH")
    select_only(a, b, c)
    assert_finished(search(settings, "asset_type", "EXISTS"))
    assert selected_names() == {a.name, b.name}

    configure_selected(settings, "MATERIAL")
    select_only(a, c)
    assert_finished(search(settings, "surface_type", "EXISTS"))
    assert selected_names() == {a.name, c.name}

    configure_selected(settings)
    settings.scope = "ACTIVE"
    select_only(a, b, active=b)
    assert_finished(apply_property(settings, "active_only", "BOOL", True))
    assert "active_only" not in a
    assert b["active_only"] is True

    settings.scope = "SCENE"
    settings.include_hidden = False
    settings.include_disabled_viewport = False
    assert_finished(apply_property(settings, "scene_visible", "BOOL", True))
    assert "scene_visible" not in fixture["hidden"]
    assert "scene_visible" not in fixture["disabled"]

    settings.include_hidden = True
    settings.include_disabled_viewport = True
    assert_finished(apply_property(settings, "scene_all", "BOOL", True))
    assert fixture["hidden"]["scene_all"] is True
    assert fixture["disabled"]["scene_all"] is True


def test_delete_and_summary(fixture):
    settings = bpy.context.scene.cpbe_settings
    a, b = fixture["a"], fixture["b"]

    configure_selected(settings)
    select_only(a, b)
    settings.delete_property_name = "status"
    settings.delete_mode = "EXISTS"
    settings.confirm_delete = True
    assert_finished(bpy.ops.cpbe.delete_property())
    assert "status" not in a
    assert "status" not in b

    a["conditional"] = 1
    b["conditional"] = 2
    settings.delete_property_name = "conditional"
    settings.delete_mode = "VALUE"
    settings.delete_property_type = "INT"
    settings.delete_int_value = 1
    settings.confirm_delete = True
    assert_finished(bpy.ops.cpbe.delete_property())
    assert "conditional" not in a
    assert b["conditional"] == 2

    a["mixed_property"] = "A"
    b["mixed_property"] = "B"
    settings.property_list_mode = "SELECTED_SUMMARY"
    assert_finished(bpy.ops.cpbe.refresh_property_list())
    summary = next(
        item
        for item in settings.property_summaries
        if item.property_name == "mixed_property"
    )
    assert summary.mixed is True
    assert summary.value_preview == "Mixed"
    assert summary.target_count == 2

    configure_selected(settings, "MESH")
    select_only(a, b)
    settings.delete_property_name = "asset_type"
    settings.delete_mode = "EXISTS"
    settings.confirm_delete = True
    assert_finished(bpy.ops.cpbe.delete_property())
    assert "asset_type" not in fixture["shared_mesh"]


def test_presets(fixture, temp_dir):
    settings = bpy.context.scene.cpbe_settings
    a, b = fixture["a"], fixture["b"]
    preset_utils.USER_PRESET_PATH_OVERRIDE = str(temp_dir / "user_presets.json")

    settings.preset_properties.clear()
    settings.property_name = "preset_label"
    settings.property_type = "STRING"
    settings.string_value = "Environment"
    assert_finished(bpy.ops.cpbe.add_preset_item())
    settings.property_name = "preset_enabled"
    settings.property_type = "BOOL"
    settings.bool_value = True
    assert_finished(bpy.ops.cpbe.add_preset_item())

    settings.preset_name = "Integration Test"
    assert_finished(bpy.ops.cpbe.save_preset())
    saved = preset_utils.find_preset(
        preset_utils.load_presets(),
        "Integration Test",
    )
    assert saved is not None
    assert len(saved["properties"]) == 2

    select_only(a, b)
    configure_selected(settings)
    settings.selected_preset = "Integration Test"
    assert_finished(bpy.ops.cpbe.apply_preset())
    assert a["preset_label"] == "Environment"
    assert b["preset_enabled"] is True

    export_path = temp_dir / "exported_presets.json"
    assert_finished(
        bpy.ops.cpbe.export_presets(
            "EXEC_DEFAULT",
            filepath=str(export_path),
        )
    )
    assert export_path.exists()

    assert_finished(bpy.ops.cpbe.delete_preset("EXEC_DEFAULT"))
    assert preset_utils.find_preset(
        preset_utils.load_presets(),
        "Integration Test",
    ) is None

    assert_finished(
        bpy.ops.cpbe.import_presets(
            "EXEC_DEFAULT",
            filepath=str(export_path),
        )
    )
    assert preset_utils.find_preset(
        preset_utils.load_presets(),
        "Integration Test",
    ) is not None

    settings.selected_preset = "Integration Test"
    assert_finished(bpy.ops.cpbe.load_preset_to_editor())
    assert len(settings.preset_properties) == 2
    assert_finished(bpy.ops.cpbe.copy_log())
    clipboard = bpy.context.window_manager.clipboard.replace("\r\n", "\n")
    if clipboard:
        assert clipboard == settings.log_text.replace("\r\n", "\n")


def main():
    for operator_type in (
        operators.CPBE_OT_apply_property,
        operators.CPBE_OT_search_property,
        operators.CPBE_OT_delete_property,
        operators.CPBE_OT_apply_preset,
    ):
        assert "UNDO" in operator_type.bl_options

    custom_properties_batch_editor.register()
    try:
        with tempfile.TemporaryDirectory(prefix="cpbe_test_") as temp_dir:
            temp_path = Path(temp_dir)
            fixture = create_fixture(temp_path)
            test_batch_editing(fixture)
            test_search_and_scope(fixture)
            test_delete_and_summary(fixture)
            test_presets(fixture, temp_path)
        print("Custom Properties Batch Editor integration tests passed")
    finally:
        preset_utils.USER_PRESET_PATH_OVERRIDE = None
        custom_properties_batch_editor.unregister()


main()
