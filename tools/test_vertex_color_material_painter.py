import json
import importlib.util
import sys
import tempfile
from pathlib import Path

import bpy
import bmesh
from mathutils import Color


ROOT = Path(__file__).resolve().parents[1]
ADDON_DIR = ROOT / "_Taiyo_Blender_Extensions_Repo" / "vertex_color_material_painter"
ADDON_PATH = ADDON_DIR / "__init__.py"


def load_addon():
    module_name = "vertex_color_material_painter_test"
    spec = importlib.util.spec_from_file_location(
        module_name,
        ADDON_PATH,
        submodule_search_locations=[str(ADDON_DIR)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def reset_scene():
    if bpy.context.object is not None and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)


def new_mesh(name):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        [],
        [(0, 1, 2)],
    )
    return mesh


def new_mesh_object(name, mesh=None):
    mesh = mesh or new_mesh(f"{name}Mesh")
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def select_only(*objects, active=None):
    if bpy.context.object is not None and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    for candidate in bpy.context.view_layer.objects:
        candidate.select_set(False)

    for obj in objects:
        obj.select_set(True)

    bpy.context.view_layer.objects.active = active or (objects[0] if objects else None)


def configure_remove(
    scene,
    match_mode,
    source='DIRECT',
    name="mat_color",
    data_type='BYTE_COLOR',
    domain='CORNER',
    reference="mat_color",
):
    scene.vcmp_remove_match_mode = match_mode
    scene.vcmp_remove_filter_source = source
    scene.vcmp_remove_attribute_name = name
    scene.vcmp_remove_data_type = data_type
    scene.vcmp_remove_domain = domain
    scene.vcmp_remove_reference_attribute_name = reference


def assert_finished(result):
    assert result == {'FINISHED'}, result


def assert_color_close(actual, expected, tolerance=0.005):
    assert all(
        abs(float(actual[index]) - float(expected[index])) <= tolerance
        for index in range(4)
    ), (tuple(actual), tuple(expected))


def test_color_list_json_export(addon):
    reset_scene()
    scene = bpy.context.scene
    first = scene.vcmp_color_items.add()
    first.name = "木材"
    first.color = (0.45, 0.24, 0.09, 0.25)
    second = scene.vcmp_color_items.add()
    second.name = "Glass"
    second.color = (0.1, 0.2, 0.3, 0.75)

    with tempfile.TemporaryDirectory(prefix="vcmp_json_") as temp_dir:
        filepath = Path(temp_dir) / "colors.json"
        assert_finished(
            bpy.ops.vcmp.export_color_list_json(filepath=str(filepath))
        )
        content = filepath.read_text(encoding="utf-8")
        payload = json.loads(content)

        assert content.endswith("\n")
        assert "木材" in content
        assert payload == [
            {
                "Name": "木材",
                "Color": [
                    float(first.color[0]),
                    float(first.color[1]),
                    float(first.color[2]),
                ],
            },
            {
                "Name": "Glass",
                "Color": [
                    float(second.color[0]),
                    float(second.color[1]),
                    float(second.color[2]),
                ],
            },
        ]
        assert all(len(item["Color"]) == 3 for item in payload)

        scene.vcmp_color_items.clear()
        empty_filepath = Path(temp_dir) / "empty.json"
        assert_finished(
            bpy.ops.vcmp.export_color_list_json(filepath=str(empty_filepath))
        )
        assert empty_filepath.read_text(encoding="utf-8") == "[]\n"

        invalid_filepath = Path(temp_dir) / "missing" / "colors.json"
        try:
            bpy.ops.vcmp.export_color_list_json(filepath=str(invalid_filepath))
        except RuntimeError as error:
            assert "JSONを書き出せませんでした" in str(error)
        else:
            raise AssertionError("Invalid export path should report an error.")


def test_remove_helper_default_disabled(addon):
    reset_scene()
    assert bpy.context.scene.vcmp_remove_helper_enabled is False


def test_paint_color_consistency(addon):
    for attribute_type in ('BYTE_COLOR', 'FLOAT_COLOR'):
        reset_scene()
        color = (0.45, 0.24, 0.09, 1.0)
        object_mode_obj = new_mesh_object(f"ObjectPaint{attribute_type}")
        edit_mode_obj = new_mesh_object(f"EditPaint{attribute_type}")

        object_count, face_count, created_count = addon._paint_object_mode_meshes(
            [object_mode_obj],
            "paint_color",
            attribute_type,
            color,
        )
        assert (object_count, face_count, created_count) == (1, 1, 1)

        select_only(edit_mode_obj)
        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(edit_mode_obj.data)
        for face in bm.faces:
            face.select_set(True)
        bmesh.update_edit_mesh(edit_mode_obj.data, loop_triangles=False, destructive=False)

        painted_faces, created, actual_type = addon._paint_selected_faces(
            edit_mode_obj,
            "paint_color",
            attribute_type,
            color,
        )
        assert painted_faces == 1
        assert created is True
        assert actual_type == attribute_type

        selected_faces = addon._select_faces_by_color(
            edit_mode_obj,
            "paint_color",
            color,
        )
        assert selected_faces == 1
        bpy.ops.object.mode_set(mode='OBJECT')

        object_color = object_mode_obj.data.color_attributes["paint_color"].data[0].color
        edit_color = edit_mode_obj.data.color_attributes["paint_color"].data[0].color
        assert_color_close(edit_color, object_color)
        assert_color_close(edit_color, color)


def test_edit_mode_color_copy_consistency(addon):
    reset_scene()
    color = (0.45, 0.24, 0.09, 1.0)
    obj = new_mesh_object("EditCopy")
    addon._paint_object_mode_meshes([obj], "byte_source", 'BYTE_COLOR', color)

    select_only(obj)
    bpy.ops.object.mode_set(mode='EDIT')
    copied_faces, source_type, target_type, created = addon._copy_bmesh_color_attribute(
        obj,
        "byte_source",
        "float_target",
        'FLOAT_COLOR',
    )
    assert copied_faces == 1
    assert source_type == 'BYTE_COLOR'
    assert target_type == 'FLOAT_COLOR'
    assert created is True
    bpy.ops.object.mode_set(mode='OBJECT')

    source_color = obj.data.color_attributes["byte_source"].data[0].color
    target_color = obj.data.color_attributes["float_target"].data[0].color
    assert_color_close(target_color, source_color)
    assert_color_close(target_color, color)


def test_automatic_legacy_color_repair(addon):
    reset_scene()
    scene = bpy.context.scene
    scene.vcmp_color_items.clear()
    desired_color = (0.45, 0.24, 0.09, 1.0)
    correct_color = (0.08, 0.32, 0.7, 1.0)
    ambiguous_color = (0.0, 0.0, 0.0, 1.0)
    unknown_color = (0.28, 0.3, 0.33, 1.0)
    wrong_rgb = Color(desired_color[:3]).from_srgb_to_scene_linear()
    wrong_color = (*wrong_rgb, desired_color[3])

    shared_mesh = new_mesh("LegacySharedMesh")
    selected_a = new_mesh_object("LegacySelectedA", shared_mesh)
    selected_b = new_mesh_object("LegacySelectedB", shared_mesh)
    attribute = shared_mesh.color_attributes.new(
        name="mat_color",
        type='BYTE_COLOR',
        domain='CORNER',
    )
    attribute.data[0].color = wrong_color
    attribute.data[1].color = correct_color
    attribute.data[2].color = ambiguous_color

    unknown_obj = new_mesh_object("LegacyUnknown")
    unknown_attribute = unknown_obj.data.color_attributes.new(
        name="mat_color",
        type='BYTE_COLOR',
        domain='CORNER',
    )
    for data in unknown_attribute.data:
        data.color = unknown_color

    select_only(selected_a, selected_b, unknown_obj, active=selected_a)
    scene.vcmp_attribute_name = "mat_color"
    empty_preview = addon._auto_color_repair_preview(
        bpy.context,
        "mat_color",
        analyze_colors=True,
    )
    assert empty_preview["reference_color_count"] == 0, empty_preview

    for name, color in (
        ("Brown", desired_color),
        ("Blue", correct_color),
        ("Black", ambiguous_color),
    ):
        item = scene.vcmp_color_items.add()
        item.name = name
        item.color = color

    preview = addon._auto_color_repair_preview(
        bpy.context,
        "mat_color",
        analyze_colors=True,
    )
    assert preview["object_count"] == 3, preview
    assert preview["unique_mesh_count"] == 2, preview
    assert preview["matching_mesh_count"] == 2, preview
    assert preview["reference_color_count"] == 3, preview
    assert preview["repair_color_count"] == 1, preview
    assert preview["correct_color_count"] == 1, preview
    assert preview["ambiguous_color_count"] == 1, preview
    assert preview["unknown_color_count"] == 3, preview

    assert_finished(bpy.ops.vcmp.repair_legacy_edit_colors('EXEC_DEFAULT'))
    assert_color_close(attribute.data[0].color, desired_color)
    assert_color_close(attribute.data[1].color, correct_color)
    assert_color_close(attribute.data[2].color, ambiguous_color)
    for data in unknown_attribute.data:
        assert_color_close(data.color, unknown_color)


def test_same_name(addon):
    reset_scene()
    scene = bpy.context.scene
    obj_a = new_mesh_object("SameNameA")
    obj_b = new_mesh_object("SameNameB")

    obj_a.data.attributes.new("remove_me", 'FLOAT', 'POINT')
    obj_a.data.attributes.new("keep_a", 'INT', 'POINT')
    obj_b.data.attributes.new("remove_me", 'BYTE_COLOR', 'CORNER')
    obj_b.data.attributes.new("keep_b", 'BOOLEAN', 'FACE')

    select_only(obj_a, obj_b, active=obj_a)
    configure_remove(scene, 'SAME_NAME', name="remove_me")

    preview = addon._build_remove_preview(bpy.context)
    assert preview["selected_object_count"] == 2, preview
    assert preview["unique_mesh_count"] == 2, preview
    assert preview["attribute_count"] == 2, preview

    assert_finished(bpy.ops.vcmp.remove_attribute('EXEC_DEFAULT'))
    assert obj_a.data.attributes.get("remove_me") is None
    assert obj_b.data.attributes.get("remove_me") is None
    assert obj_a.data.attributes.get("keep_a") is not None
    assert obj_b.data.attributes.get("keep_b") is not None

    reference_a = new_mesh_object("SameNameReferenceA")
    reference_b = new_mesh_object("SameNameReferenceB")
    reference_a.data.attributes.new("reference_name", 'FLOAT', 'POINT')
    reference_b.data.attributes.new("reference_name", 'INT', 'FACE')

    select_only(reference_a, reference_b, active=reference_a)
    configure_remove(
        scene,
        'SAME_NAME',
        source='REFERENCE',
        reference="reference_name",
    )
    preview = addon._build_remove_preview(bpy.context)
    assert preview["filter_spec"]["name"] == "reference_name", preview
    assert preview["attribute_count"] == 2, preview
    assert_finished(bpy.ops.vcmp.remove_attribute('EXEC_DEFAULT'))
    assert reference_a.data.attributes.get("reference_name") is None
    assert reference_b.data.attributes.get("reference_name") is None


def test_data_type_direct_and_reference(addon):
    reset_scene()
    scene = bpy.context.scene
    direct_a = new_mesh_object("DirectTypeA")
    direct_b = new_mesh_object("DirectTypeB")

    direct_a.data.attributes.new("float_a", 'FLOAT', 'POINT')
    direct_a.data.attributes.new("int_a", 'INT', 'POINT')
    direct_b.data.attributes.new("float_b", 'FLOAT', 'FACE')
    direct_b.data.attributes.new("int_b", 'INT', 'FACE')

    select_only(direct_a, direct_b, active=direct_a)
    configure_remove(scene, 'DATA_TYPE', data_type='FLOAT')
    assert addon._build_remove_preview(bpy.context)["attribute_count"] == 2
    assert_finished(bpy.ops.vcmp.remove_attribute('EXEC_DEFAULT'))
    assert direct_a.data.attributes.get("float_a") is None
    assert direct_b.data.attributes.get("float_b") is None
    assert direct_a.data.attributes.get("int_a") is not None
    assert direct_b.data.attributes.get("int_b") is not None

    reference_a = new_mesh_object("ReferenceTypeA")
    reference_b = new_mesh_object("ReferenceTypeB")
    reference_a.data.attributes.new("type_reference", 'FLOAT', 'POINT')
    reference_a.data.attributes.new("float_c", 'FLOAT', 'FACE')
    reference_a.data.attributes.new("int_c", 'INT', 'POINT')
    reference_b.data.attributes.new("float_d", 'FLOAT', 'CORNER')
    reference_b.data.attributes.new("int_d", 'INT', 'FACE')

    select_only(reference_a, reference_b, active=reference_a)
    configure_remove(
        scene,
        'DATA_TYPE',
        source='REFERENCE',
        reference="type_reference",
    )
    preview = addon._build_remove_preview(bpy.context)
    assert preview["filter_spec"]["data_type"] == 'FLOAT', preview
    assert preview["attribute_count"] == 3, preview
    assert_finished(bpy.ops.vcmp.remove_attribute('EXEC_DEFAULT'))
    assert reference_a.data.attributes.get("type_reference") is None
    assert reference_a.data.attributes.get("float_c") is None
    assert reference_b.data.attributes.get("float_d") is None
    assert reference_a.data.attributes.get("int_c") is not None
    assert reference_b.data.attributes.get("int_d") is not None


def test_domain_and_type_domain(addon):
    reset_scene()
    scene = bpy.context.scene
    domain_a = new_mesh_object("DomainA")
    domain_b = new_mesh_object("DomainB")

    domain_a.data.attributes.new("face_float", 'FLOAT', 'FACE')
    domain_a.data.attributes.new("point_float", 'FLOAT', 'POINT')
    domain_b.data.attributes.new("face_int", 'INT', 'FACE')
    domain_b.data.attributes.new("point_int", 'INT', 'POINT')

    select_only(domain_a, domain_b, active=domain_a)
    configure_remove(scene, 'DOMAIN', domain='FACE')
    assert addon._build_remove_preview(bpy.context)["attribute_count"] >= 2
    assert_finished(bpy.ops.vcmp.remove_attribute('EXEC_DEFAULT'))
    assert domain_a.data.attributes.get("face_float") is None
    assert domain_b.data.attributes.get("face_int") is None
    assert domain_a.data.attributes.get("point_float") is not None
    assert domain_b.data.attributes.get("point_int") is not None

    combo_a = new_mesh_object("ComboA")
    combo_b = new_mesh_object("ComboB")
    combo_a.data.attributes.new("combo_reference", 'FLOAT', 'POINT')
    combo_a.data.attributes.new("float_face", 'FLOAT', 'FACE')
    combo_a.data.attributes.new("int_point", 'INT', 'POINT')
    combo_b.data.attributes.new("float_point", 'FLOAT', 'POINT')
    combo_b.data.attributes.new("float_corner", 'FLOAT', 'CORNER')

    select_only(combo_a, combo_b, active=combo_a)
    configure_remove(
        scene,
        'TYPE_DOMAIN',
        source='REFERENCE',
        reference="combo_reference",
    )
    preview = addon._build_remove_preview(bpy.context)
    assert preview["filter_spec"]["data_type"] == 'FLOAT', preview
    assert preview["filter_spec"]["domain"] == 'POINT', preview
    assert preview["attribute_count"] == 2, preview
    assert_finished(bpy.ops.vcmp.remove_attribute('EXEC_DEFAULT'))
    assert combo_a.data.attributes.get("combo_reference") is None
    assert combo_b.data.attributes.get("float_point") is None
    assert combo_a.data.attributes.get("float_face") is not None
    assert combo_a.data.attributes.get("int_point") is not None
    assert combo_b.data.attributes.get("float_corner") is not None


def test_all_removable_protects_internal_and_required(addon):
    reset_scene()
    scene = bpy.context.scene
    obj = new_mesh_object("AllRemovable")
    mesh = obj.data
    mesh.attributes.new("custom_float", 'FLOAT', 'POINT')
    mesh.attributes.new("custom_color", 'BYTE_COLOR', 'CORNER')

    select_only(obj)
    configure_remove(scene, 'ALL_REMOVABLE')
    preview = addon._build_remove_preview(bpy.context)
    assert preview["attribute_count"] >= 2, preview
    assert preview["protected_attribute_count"] >= 1, preview

    assert_finished(bpy.ops.vcmp.remove_attribute('EXEC_DEFAULT'))
    assert mesh.attributes.get("custom_float") is None
    assert mesh.attributes.get("custom_color") is None
    assert mesh.attributes.get("position") is not None
    assert all(
        attribute.is_internal or attribute.is_required
        for attribute in mesh.attributes
    ), [(attribute.name, attribute.is_internal, attribute.is_required) for attribute in mesh.attributes]


def test_shared_mesh_preview_and_unique_processing(addon):
    reset_scene()
    scene = bpy.context.scene
    shared_mesh = new_mesh("SharedMesh")
    selected_a = new_mesh_object("SharedSelectedA", shared_mesh)
    selected_b = new_mesh_object("SharedSelectedB", shared_mesh)
    unselected = new_mesh_object("SharedUnselected", shared_mesh)
    shared_mesh.attributes.new("shared_remove", 'FLOAT', 'POINT')

    select_only(selected_a, selected_b, active=selected_a)
    configure_remove(scene, 'SAME_NAME', name="shared_remove")
    preview = addon._build_remove_preview(bpy.context)
    assert preview["selected_object_count"] == 2, preview
    assert preview["unique_mesh_count"] == 1, preview
    assert preview["attribute_count"] == 1, preview
    assert preview["unselected_shared_object_count"] == 1, preview

    result = addon._remove_matching_attributes(bpy.context)
    assert result["deleted_attribute_count"] == 1, result
    assert result["processed_mesh_count"] == 1, result
    assert result["skipped_mesh_count"] == 0, result
    assert unselected.data.attributes.get("shared_remove") is None


def test_multi_object_edit_mode(addon):
    reset_scene()
    scene = bpy.context.scene
    obj_a = new_mesh_object("EditA")
    obj_b = new_mesh_object("EditB")
    obj_a.data.attributes.new("edit_remove", 'FLOAT_COLOR', 'CORNER')
    obj_b.data.attributes.new("edit_remove", 'FLOAT_COLOR', 'CORNER')

    select_only(obj_a, obj_b, active=obj_a)
    bpy.ops.object.mode_set(mode='EDIT')
    configure_remove(scene, 'SAME_NAME', name="edit_remove")

    preview = addon._build_remove_preview(bpy.context)
    assert preview["selected_object_count"] == 2, preview
    assert preview["unique_mesh_count"] == 2, preview
    assert preview["attribute_count"] == 2, preview
    assert_finished(bpy.ops.vcmp.remove_attribute('EXEC_DEFAULT'))
    assert obj_a.data.attributes.get("edit_remove") is None
    assert obj_b.data.attributes.get("edit_remove") is None
    bpy.ops.object.mode_set(mode='OBJECT')


def test_empty_and_non_editable_targets(addon):
    reset_scene()
    scene = bpy.context.scene
    configure_remove(scene, 'SAME_NAME', name="missing")
    select_only()
    preview = addon._build_remove_preview(bpy.context)
    assert preview["error"], preview

    with tempfile.TemporaryDirectory(prefix="vcmp_test_") as temp_dir:
        source_mesh = new_mesh("LinkedSourceMesh")
        source_mesh.attributes.new("linked_remove", 'FLOAT', 'POINT')
        library_path = Path(temp_dir) / "linked_mesh.blend"
        bpy.data.libraries.write(str(library_path), {source_mesh})
        bpy.data.meshes.remove(source_mesh)

        with bpy.data.libraries.load(str(library_path), link=True) as (data_from, data_to):
            data_to.meshes = ["LinkedSourceMesh"]

        linked_mesh = data_to.meshes[0]
        linked_obj = new_mesh_object("LinkedObject", linked_mesh)
        editable_obj = new_mesh_object("EditableObject")
        editable_obj.data.attributes.new("linked_remove", 'FLOAT', 'POINT')
        select_only(linked_obj, editable_obj, active=editable_obj)
        configure_remove(scene, 'SAME_NAME', name="linked_remove")
        preview = addon._build_remove_preview(bpy.context)
        assert preview["non_editable_mesh_count"] == 1, preview
        assert preview["attribute_count"] == 1, preview
        result = addon._remove_matching_attributes(bpy.context)
        assert result["deleted_attribute_count"] == 1, result
        assert result["processed_mesh_count"] == 1, result
        assert result["skipped_mesh_count"] == 1, result
        assert linked_mesh.attributes.get("linked_remove") is not None


def main():
    addon = load_addon()
    addon.register()

    try:
        test_color_list_json_export(addon)
        test_remove_helper_default_disabled(addon)
        test_paint_color_consistency(addon)
        test_edit_mode_color_copy_consistency(addon)
        test_automatic_legacy_color_repair(addon)
        test_same_name(addon)
        test_data_type_direct_and_reference(addon)
        test_domain_and_type_domain(addon)
        test_all_removable_protects_internal_and_required(addon)
        test_shared_mesh_preview_and_unique_processing(addon)
        test_multi_object_edit_mode(addon)
        test_empty_and_non_editable_targets(addon)
        print("Vertex Color Material Painter integration tests passed.")
    finally:
        addon.unregister()
        reset_scene()


if __name__ == "__main__":
    main()
