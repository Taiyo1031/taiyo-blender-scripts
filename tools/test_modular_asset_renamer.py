import json
import sys
import tempfile
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "_Taiyo_Blender_Extensions_Repo"
sys.path.insert(0, str(SOURCE_ROOT))

import modular_asset_renamer
from modular_asset_renamer import naming, operators, preset_utils, props


PREFIX = "MAR_Test_"


def assert_finished(result):
    assert result == {"FINISHED"}, result


def assert_operator_error(operator_call, expected_message):
    try:
        result = operator_call()
    except RuntimeError as exc:
        assert expected_message in str(exc)
    else:
        assert result == {"CANCELLED"}, result


def reset_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)


def create_mesh(name):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(
        [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (1.0, 1.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            (1.0, 0.0, 1.0),
            (1.0, 1.0, 1.0),
            (0.0, 1.0, 1.0),
        ],
        [],
        [
            (0, 1, 2, 3),
            (4, 7, 6, 5),
            (0, 4, 5, 1),
            (1, 5, 6, 2),
            (2, 6, 7, 3),
            (4, 0, 3, 7),
        ],
    )
    mesh.update()
    return mesh


def create_object(name, mesh, collection):
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


def select_only(*objects, active=None):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.hide_set(False)
        obj.hide_select = False
        obj.select_set(True)
    bpy.context.view_layer.objects.active = active or (objects[0] if objects else None)


def add_module(module_type):
    assert_finished(bpy.ops.mar.add_module(module_type=module_type))
    return bpy.context.scene.mar_settings.modules[-1]


def test_module_editing():
    settings = bpy.context.scene.mar_settings
    settings.modules.clear()

    choice = add_module("CHOICE")
    assert choice.choice_options[0].option_id.startswith("option_")
    assert choice.choice_current == choice.choice_options[0].option_id
    choice.choice_options[0].value = "Wood"
    assert_finished(bpy.ops.mar.add_choice_option())
    choice.choice_options[1].value = "Metal"
    choice.choice_current = choice.choice_options[1].option_id
    current_id = choice.choice_current
    enum_items = props.choice_enum_items(choice, bpy.context)
    assert all(len(item) == 3 for item in enum_items)
    data_path = "scene.mar_settings.modules[0].choice_current"
    assert_finished(
        bpy.ops.wm.context_set_enum(
            data_path=data_path,
            value=choice.choice_options[0].option_id,
        )
    )
    assert choice.choice_current == choice.choice_options[0].option_id
    assert_finished(
        bpy.ops.wm.context_set_enum(
            data_path=data_path,
            value=choice.choice_options[1].option_id,
        )
    )
    assert choice.choice_current == current_id

    move = bpy.ops.mar.move_choice_option
    assert_finished(move(direction="UP"))
    assert choice.choice_current == current_id
    assert choice.choice_options[0].value == "Metal"

    assert_finished(bpy.ops.mar.duplicate_module())
    duplicate = settings.modules[1]
    assert duplicate.module_type == "CHOICE"
    assert duplicate.module_id != choice.module_id
    assert duplicate.choice_current != choice.choice_current
    assert naming.evaluate_module(
        bpy.context,
        settings,
        duplicate,
        bpy.context.active_object,
        0,
    ) == "Metal"

    assert_finished(bpy.ops.mar.toggle_module())
    assert duplicate.enabled is False
    separator = bpy.ops.mar.set_separator
    assert_finished(separator(value="-"))
    assert duplicate.separator_after == "-"
    assert_finished(bpy.ops.mar.move_module(direction="UP"))
    assert settings.module_index == 0
    assert_finished(bpy.ops.mar.remove_module())
    assert len(settings.modules) == 1

    only_choice = settings.modules[0]
    while len(only_choice.choice_options) > 1:
        only_choice.choice_option_index = 0
        assert_finished(bpy.ops.mar.remove_choice_option())
    assert_operator_error(
        bpy.ops.mar.remove_choice_option,
        "Choice must contain at least one option.",
    )
    assert len(only_choice.choice_options) == 1

    only_choice.choice_options[0].option_id = "123legacy"
    only_choice.choice_current = "123legacy"
    assert_finished(
        bpy.ops.mar.repair_choice_modules(module_id=only_choice.module_id)
    )
    assert only_choice.choice_options[0].option_id == "option_123legacy"
    assert only_choice.choice_current == "option_123legacy"


def test_module_outputs(parent, child, obj):
    settings = bpy.context.scene.mar_settings
    settings.modules.clear()
    settings.strip_blender_numeric_suffix = True

    text = add_module("TEXT")
    text.text_value = "SM"
    text.separator_after = "_"

    choice = add_module("CHOICE")
    choice.choice_label = "Material Type"
    choice.choice_options[0].value = "Wood"
    choice.separator_after = "_"
    assert_finished(bpy.ops.mar.add_choice_option())
    choice.choice_options[1].value = "Plaster"
    choice.choice_current = choice.choice_options[1].option_id
    assert naming.evaluate_module(
        bpy.context,
        settings,
        choice,
        obj,
        0,
    ) == "Plaster"

    dimensions = add_module("DIMENSIONS")
    dimensions.axis_order = "XYZ"
    dimensions.dimension_unit = "CM"
    dimensions.axis_separator = "x"
    dimensions.decimal_places = 0
    dimensions.round_mode = "ROUND"
    dimensions.add_unit_suffix = True
    dimensions.separator_after = "_"
    obj.dimensions = (1.8, 2.4, 0.3)
    bpy.context.view_layer.update()
    assert naming.evaluate_module(
        bpy.context,
        settings,
        dimensions,
        obj,
        0,
    ) == "180x240x30cm"

    dimensions.axis_order = "ZYX"
    dimensions.dimension_unit = "M"
    dimensions.decimal_places = 2
    dimensions.round_mode = "FLOOR"
    dimensions.add_axis_labels = True
    dimensions.axis_separator = "_"
    dimensions.remove_trailing_zeros = True
    dimensions.add_unit_suffix = False
    dimension_label_output = naming.evaluate_module(
        bpy.context,
        settings,
        dimensions,
        obj,
        0,
    )
    assert dimension_label_output == "Z0.3_Y2.4_X1.8", dimension_label_output

    index = add_module("INDEX")
    index.start_number = 7
    index.padding = 4
    assert naming.evaluate_module(
        bpy.context,
        settings,
        index,
        obj,
        2,
    ) == "0009"

    original = add_module("ORIGINAL_NAME")
    original.original_mode = "SPLIT"
    original.original_delimiter = "_"
    original.original_part_index = 2
    obj.name = "SM_Wall_Outer.001"
    assert naming.evaluate_module(
        bpy.context,
        settings,
        original,
        obj,
        0,
    ) == "Wall"

    collection = add_module("COLLECTION_NAME")
    collection.collection_source = "FIRST"
    assert naming.evaluate_module(
        bpy.context,
        settings,
        collection,
        obj,
        0,
    ) == child.name
    collection.collection_source = "PARENT"
    assert naming.evaluate_module(
        bpy.context,
        settings,
        collection,
        obj,
        0,
    ) == parent.name


def test_sort_preview_apply_revert(child):
    settings = bpy.context.scene.mar_settings
    settings.modules.clear()
    settings.rename_object = True
    settings.rename_mesh_data = True
    settings.auto_resolve_duplicates = True
    settings.store_original_name = True
    settings.replace_spaces = True
    settings.remove_invalid_characters = True
    settings.rename_only_mesh_objects = False
    settings.skip_hidden_objects = False
    settings.skip_locked_objects = False

    text = add_module("TEXT")
    text.text_value = "Asset Name/Bad"
    text.separator_after = "_"
    index = add_module("INDEX")
    index.start_number = 1
    index.padding = 3
    index.sort_mode = "SELECTION"
    index.separator_after = ""

    shared_mesh = create_mesh(PREFIX + "SharedMesh")
    first = create_object(PREFIX + "First", shared_mesh, child)
    second = create_object(PREFIX + "Second", shared_mesh, child)
    old_first = first.name
    old_second = second.name
    old_mesh = shared_mesh.name
    select_only(first, second, active=second)

    assert_finished(bpy.ops.mar.preview())
    assert first.name == old_first
    assert second.name == old_second
    assert settings.preview_items[0].object_ref == second
    assert settings.preview_items[0].new_name == "Asset_Name_Bad_001"
    assert settings.preview_items[1].new_name == "Asset_Name_Bad_002"
    assert all(item.status == naming.STATUS_OK for item in settings.preview_items)
    assert "share mesh data" in settings.last_warning

    assert_finished(bpy.ops.mar.apply())
    assert second.name == "Asset_Name_Bad_001"
    assert first.name == "Asset_Name_Bad_002"
    assert shared_mesh.name == second.name
    assert second["original_name_before_modular_renamer"] == old_second
    assert shared_mesh["original_name_before_modular_renamer"] == old_mesh
    assert len(settings.history_items) == 3

    assert_finished(bpy.ops.mar.revert())
    assert first.name == old_first
    assert second.name == old_second
    assert shared_mesh.name == old_mesh
    assert "original_name_before_modular_renamer" in second
    assert len(settings.history_items) == 0

    index.sort_mode = "NAME_ASC"
    select_only(first, second, active=second)
    records, _warning = naming.build_rename_plan(bpy.context, settings)
    assert records[0].obj.name < records[1].obj.name


def test_duplicate_invalid_and_filter(child):
    settings = bpy.context.scene.mar_settings
    settings.modules.clear()
    settings.rename_object = True
    settings.rename_mesh_data = False
    settings.auto_resolve_duplicates = False
    settings.error_if_name_exists = False
    settings.remove_invalid_characters = True

    text = add_module("TEXT")
    text.text_value = PREFIX + "Taken"
    text.separator_after = ""

    blocker = create_object(PREFIX + "Taken", create_mesh(PREFIX + "BlockerMesh"), child)
    target = create_object(PREFIX + "Target", create_mesh(PREFIX + "TargetMesh"), child)
    select_only(target)
    records, _warning = naming.build_rename_plan(bpy.context, settings)
    assert records[0].status == naming.STATUS_DUPLICATE
    assert target.name == PREFIX + "Target"

    text.text_value = "Bad/Name"
    settings.remove_invalid_characters = False
    records, _warning = naming.build_rename_plan(bpy.context, settings)
    assert records[0].status == naming.STATUS_INVALID

    settings.remove_invalid_characters = True
    settings.rename_only_mesh_objects = True
    empty = bpy.data.objects.new(PREFIX + "Empty", None)
    child.objects.link(empty)
    select_only(empty)
    records, _warning = naming.build_rename_plan(bpy.context, settings)
    assert records[0].status == naming.STATUS_SKIPPED

    settings.rename_only_mesh_objects = False
    settings.auto_resolve_duplicates = True
    settings.error_if_name_exists = True
    text.text_value = PREFIX + "Taken"
    select_only(target)
    records, _warning = naming.build_rename_plan(bpy.context, settings)
    assert records[0].status == naming.STATUS_DUPLICATE
    assert records[0].new_name == PREFIX + "Taken"

    settings.error_if_name_exists = False
    text.text_value = PREFIX + "Repeated"
    duplicate_a = create_object(
        PREFIX + "DuplicateA",
        create_mesh(PREFIX + "DuplicateMeshA"),
        child,
    )
    duplicate_b = create_object(
        PREFIX + "DuplicateB",
        create_mesh(PREFIX + "DuplicateMeshB"),
        child,
    )
    select_only(duplicate_a, duplicate_b)
    records, _warning = naming.build_rename_plan(bpy.context, settings)
    assert [record.new_name for record in records] == [
        PREFIX + "Repeated",
        PREFIX + "Repeated_001",
    ]

    bpy.data.objects.remove(blocker, do_unlink=True)


def test_choice_empty_errors(obj):
    settings = bpy.context.scene.mar_settings
    settings.modules.clear()
    settings.rename_only_mesh_objects = False
    select_only(obj)

    choice = add_module("CHOICE")
    choice.choice_options[0].value = ""
    records, _warning = naming.build_rename_plan(bpy.context, settings)
    assert records[0].status == naming.STATUS_EMPTY
    assert "selected option is empty" in records[0].message

    choice.choice_options.clear()
    choice.choice_current = "__NONE__"
    records, _warning = naming.build_rename_plan(bpy.context, settings)
    assert records[0].status == naming.STATUS_EMPTY
    assert "has no options" in records[0].message

    empty_choice_preset = preset_utils.settings_to_preset(settings, "Empty Choice")
    try:
        preset_utils.upsert_preset([], empty_choice_preset)
    except ValueError as exc:
        assert "must contain at least one option" in str(exc)
    else:
        raise AssertionError("Empty Choice preset should be rejected")

    legacy = empty_choice_preset
    legacy["modules"][0]["choice_options"] = [
        {"option_id": "123legacy", "option_value": 1, "value": "Legacy"}
    ]
    legacy["modules"][0]["choice_current"] = "123legacy"
    normalized = preset_utils.upsert_preset([], legacy)[0]
    normalized_option = normalized["modules"][0]["choice_options"][0]
    assert normalized_option["option_id"] == "option_123legacy"
    assert normalized["modules"][0]["choice_current"] == "option_123legacy"


def test_preview_copy_and_same_name_selection(child, obj):
    settings = bpy.context.scene.mar_settings
    settings.modules.clear()
    settings.rename_object = True
    settings.rename_mesh_data = True
    settings.rename_only_mesh_objects = False
    settings.auto_resolve_duplicates = True
    settings.error_if_name_exists = False

    text = add_module("TEXT")
    text.text_value = PREFIX + "PreviewClipboard"
    text.separator_after = ""
    select_only(obj)
    assert_finished(bpy.ops.mar.preview())
    assert len(settings.preview_items) == 1
    preview_name = settings.preview_items[0].new_name

    assert operators._active_preview_name(settings) == preview_name
    assert_finished(bpy.ops.mar.copy_preview_name())
    assert operators._all_preview_names_text(settings) == preview_name
    assert_finished(bpy.ops.mar.copy_all_preview_names())

    object_match = create_object(
        preview_name,
        create_mesh(PREFIX + "ObjectMatchMesh"),
        child,
    )
    mesh_match = create_object(
        PREFIX + "MeshMatchObject",
        create_mesh(preview_name),
        child,
    )
    assert_finished(bpy.ops.mar.select_preview_name_matches())
    selected = set(bpy.context.selected_objects)
    assert selected == {object_match, mesh_match}
    assert bpy.context.view_layer.objects.active in selected

    bpy.data.objects.remove(object_match, do_unlink=True)
    bpy.data.objects.remove(mesh_match, do_unlink=True)
    select_only(obj)


def test_presets(temp_dir):
    settings = bpy.context.scene.mar_settings
    preset_utils.USER_PRESET_PATH_OVERRIDE = str(temp_dir / "presets.json")
    assert preset_utils.load_presets() == []
    assert not Path(preset_utils.USER_PRESET_PATH_OVERRIDE).exists()

    settings.modules.clear()
    settings.rename_only_mesh_objects = False
    settings.error_if_name_exists = True
    text = add_module("TEXT")
    text.text_value = "PresetText"
    choice = add_module("CHOICE")
    choice.choice_options[0].value = "Wood"
    assert_finished(bpy.ops.mar.add_choice_option())
    choice.choice_options[1].value = "Metal"
    choice.choice_current = choice.choice_options[0].option_id

    first_items = props.choice_enum_items(choice, bpy.context)
    second_items = props.choice_enum_items(choice, bpy.context)
    assert first_items is second_items

    assert_finished(
        bpy.ops.mar.save_preset_as(
            "EXEC_DEFAULT",
            preset_name="Integration Test",
        )
    )
    saved = preset_utils.find_preset(
        preset_utils.load_presets(),
        "Integration Test",
    )
    assert saved is not None
    assert len(saved["modules"]) == 2
    assert saved["options"]["error_if_name_exists"] is True
    choice.choice_current = choice.choice_options[1].option_id
    assert choice.choice_current == choice.choice_options[1].option_id

    text.text_value = "Updated"
    settings.selected_preset = "Integration Test"
    assert_finished(bpy.ops.mar.save_preset())
    settings.modules.clear()
    assert_finished(bpy.ops.mar.load_preset())
    assert settings.modules[0].text_value == "Updated"
    assert settings.error_if_name_exists is True
    loaded_choice = settings.modules[1]
    assert len(loaded_choice.choice_options) == 2
    loaded_items = props.choice_enum_items(loaded_choice, bpy.context)
    assert {item[0] for item in loaded_items} == {
        option.option_id for option in loaded_choice.choice_options
    }
    loaded_choice.choice_current = loaded_choice.choice_options[1].option_id
    assert loaded_choice.choice_current == loaded_choice.choice_options[1].option_id
    assert naming.evaluate_module(
        bpy.context,
        settings,
        loaded_choice,
        bpy.context.active_object,
        0,
    ) == "Metal"

    export_path = temp_dir / "export.json"
    assert_finished(
        bpy.ops.mar.export_presets(
            "EXEC_DEFAULT",
            filepath=str(export_path),
        )
    )
    assert export_path.exists()

    assert_finished(bpy.ops.mar.delete_preset("EXEC_DEFAULT"))
    assert preset_utils.load_presets() == []
    assert_finished(
        bpy.ops.mar.import_presets(
            "EXEC_DEFAULT",
            filepath=str(export_path),
        )
    )
    assert preset_utils.find_preset(
        preset_utils.load_presets(),
        "Integration Test",
    ) is not None

    invalid_path = temp_dir / "invalid.json"
    invalid_path.write_text(
        json.dumps({"schema_version": 999, "presets": []}),
        encoding="utf-8",
    )
    try:
        result = bpy.ops.mar.import_presets(
            "EXEC_DEFAULT",
            filepath=str(invalid_path),
        )
    except RuntimeError as exc:
        assert "Unsupported preset schema" in str(exc)
    else:
        assert result == {"CANCELLED"}


def main():
    modular_asset_renamer.register()
    try:
        reset_scene()
        settings = bpy.context.scene.mar_settings
        assert len(settings.modules) == 0

        parent = bpy.data.collections.new(PREFIX + "Parent")
        child = bpy.data.collections.new(PREFIX + "Child")
        bpy.context.scene.collection.children.link(parent)
        parent.children.link(child)
        sample = create_object(
            PREFIX + "Sample",
            create_mesh(PREFIX + "SampleMesh"),
            child,
        )
        select_only(sample)

        test_module_editing()
        test_module_outputs(parent, child, sample)
        test_sort_preview_apply_revert(child)
        test_duplicate_invalid_and_filter(child)
        test_choice_empty_errors(sample)
        test_preview_copy_and_same_name_selection(child, sample)
        with tempfile.TemporaryDirectory(prefix="mar_test_") as temp_dir:
            test_presets(Path(temp_dir))
        print("Modular Asset Renamer integration tests passed")
    finally:
        preset_utils.USER_PRESET_PATH_OVERRIDE = None
        modular_asset_renamer.unregister()


main()
