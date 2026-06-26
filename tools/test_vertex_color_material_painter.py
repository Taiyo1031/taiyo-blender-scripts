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


def new_three_face_mesh(name):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(
        [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (1.0, 1.0, 0.0),
            (2.0, 1.0, 0.0),
        ],
        [],
        [
            (0, 1, 2),
            (1, 3, 2),
            (1, 4, 3),
        ],
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


def paint_polygon(attribute, polygon, color):
    for loop_index in polygon.loop_indices:
        attribute.data[loop_index].color = color


def add_color_list_item(scene, name, color):
    item = scene.vcmp_color_items.add()
    item.name = name
    item.color = color
    return item


def color_list_snapshot(scene):
    return [
        (item.name, tuple(round(float(channel), 6) for channel in item.color))
        for item in scene.vcmp_color_items
    ]


def write_json_file(filepath, payload):
    filepath.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def assert_import_fails_without_change(filepath, expected_snapshot):
    try:
        result = bpy.ops.vcmp.import_color_list_json(filepath=str(filepath))
    except RuntimeError as error:
        assert "JSON" in str(error)
    else:
        assert result == {'CANCELLED'}, result

    assert color_list_snapshot(bpy.context.scene) == expected_snapshot


def test_color_list_hex_csv_export(addon):
    reset_scene()
    scene = bpy.context.scene
    first = scene.vcmp_color_items.add()
    first.name = "Wood"
    first.color = (0.45, 0.24, 0.09, 0.25)
    second = scene.vcmp_color_items.add()
    second.name = "Glass"
    second.color = (0.1, 0.2, 0.3, 0.75)

    with tempfile.TemporaryDirectory(prefix="vcmp_csv_") as temp_dir:
        filepath = Path(temp_dir) / "colors.csv"
        assert_finished(
            bpy.ops.vcmp.export_color_list_csv(filepath=str(filepath))
        )
        content = filepath.read_text(encoding="utf-8-sig")
        first_hex = addon._color_to_srgb_hex(first.color)
        second_hex = addon._color_to_srgb_hex(second.color)

        assert content == (
            "Name,HexCode\n"
            f"Wood,{first_hex}\n"
            f"Glass,{second_hex}\n"
        )
        assert first_hex.startswith("#") and len(first_hex) == 7
        assert second_hex.startswith("#") and len(second_hex) == 7

        scene.vcmp_color_items.clear()
        empty_filepath = Path(temp_dir) / "empty.csv"
        assert_finished(
            bpy.ops.vcmp.export_color_list_csv(filepath=str(empty_filepath))
        )
        assert empty_filepath.read_text(encoding="utf-8-sig") == "Name,HexCode\n"

        invalid_filepath = Path(temp_dir) / "missing" / "colors.csv"
        try:
            bpy.ops.vcmp.export_color_list_csv(filepath=str(invalid_filepath))
        except RuntimeError as error:
            assert "CSV" in str(error)
        else:
            raise AssertionError("Invalid export path should report an error.")


def test_color_list_json_import(addon):
    reset_scene()
    scene = bpy.context.scene
    add_color_list_item(scene, "Old", (0.9, 0.8, 0.7, 0.6))

    with tempfile.TemporaryDirectory(prefix="vcmp_json_") as temp_dir:
        temp_path = Path(temp_dir)
        array_path = temp_path / "array.json"
        write_json_file(
            array_path,
            [
                {"Name": "木材", "Color": [0.45, 0.24, 0.09]},
                {"Name": "Glass", "Color": [0.1, 0.2, 0.3]},
            ],
        )

        assert_finished(
            bpy.ops.vcmp.import_color_list_json(filepath=str(array_path))
        )
        assert color_list_snapshot(scene) == [
            ("木材", (0.45, 0.24, 0.09, 1.0)),
            ("Glass", (0.1, 0.2, 0.3, 1.0)),
        ]
        assert scene.vcmp_active_index == 0

        structured_path = temp_path / "template.json"
        write_json_file(
            structured_path,
            {
                "schema_version": 1,
                "name": "Material ID Template",
                "colors": [
                    {"Name": "Metal", "Color": [0.6, 0.6, 0.6]},
                ],
            },
        )
        assert_finished(
            bpy.ops.vcmp.import_color_list_json(filepath=str(structured_path))
        )
        assert color_list_snapshot(scene) == [
            ("Metal", (0.6, 0.6, 0.6, 1.0)),
        ]

        empty_path = temp_path / "empty.json"
        write_json_file(empty_path, [])
        assert_finished(
            bpy.ops.vcmp.import_color_list_json(filepath=str(empty_path))
        )
        assert color_list_snapshot(scene) == []
        assert scene.vcmp_active_index == -1

        template_path = ADDON_DIR / "templates" / "color_list_template.json"
        template_colors = addon._read_color_list_json(template_path)
        assert [item["name"] for item in template_colors] == [
            "Wood",
            "Glass",
            "Metal",
        ]


def test_color_list_json_import_validation(addon):
    reset_scene()
    scene = bpy.context.scene
    add_color_list_item(scene, "Keep", (0.2, 0.3, 0.4, 0.5))

    invalid_payloads = [
        [
            {"Name": "A", "Color": [0.1, 0.2, 0.3]},
            {"Name": "A", "Color": [0.4, 0.5, 0.6]},
        ],
        {"schema_version": 999, "colors": []},
        [{"Color": [0.1, 0.2, 0.3]}],
        [{"Name": "Missing Color"}],
        [{"Name": "RGBA", "Color": [0.1, 0.2, 0.3, 1.0]}],
        [{"Name": "Out Of Range", "Color": [0.1, -0.2, 0.3]}],
        [{"Name": "Boolean", "Color": [0.1, True, 0.3]}],
    ]

    with tempfile.TemporaryDirectory(prefix="vcmp_json_invalid_") as temp_dir:
        temp_path = Path(temp_dir)
        for index, payload in enumerate(invalid_payloads):
            filepath = temp_path / f"invalid_{index}.json"
            write_json_file(filepath, payload)
            assert_import_fails_without_change(filepath, [("Keep", (0.2, 0.3, 0.4, 0.5))])

        broken_json_path = temp_path / "broken.json"
        broken_json_path.write_text("{", encoding="utf-8")
        assert_import_fails_without_change(
            broken_json_path,
            [("Keep", (0.2, 0.3, 0.4, 0.5))],
        )


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


def test_object_mode_select_painted_faces_scan_is_chunked(addon):
    reset_scene()
    scene = bpy.context.scene
    scene.vcmp_color_items.clear()
    scene.vcmp_attribute_name = "mat_color"
    target_color = (0.45, 0.24, 0.09, 1.0)
    other_color = (0.08, 0.32, 0.7, 1.0)
    add_color_list_item(scene, "Target", target_color)
    scene.vcmp_active_index = 0
    obj_a = new_mesh_object("ObjectSelectA", new_three_face_mesh("ObjectSelectMeshA"))
    obj_b = new_mesh_object("ObjectSelectB", new_three_face_mesh("ObjectSelectMeshB"))

    for obj in (obj_a, obj_b):
        attribute = obj.data.color_attributes.new(
            name="mat_color",
            type='BYTE_COLOR',
            domain='CORNER',
        )
        for polygon in obj.data.polygons:
            paint_polygon(
                attribute,
                polygon,
                target_color if polygon.index in {0, 2} else other_color,
            )

    select_only(obj_a, obj_b, active=obj_a)
    scan = addon._build_object_color_selection_scan(
        [obj_a, obj_b],
        "mat_color",
    )
    assert len(scan["targets"]) == 2, scan
    assert scan["total_face_count"] == 6, scan

    done = addon._scan_object_color_selection_step(scan, target_color, 2)
    assert done is False
    assert scan["processed_face_count"] == 2, scan

    tick_count = 1
    while not done:
        done = addon._scan_object_color_selection_step(scan, target_color, 2)
        tick_count += 1

    assert tick_count == 3, scan
    assert scan["selected_face_count"] == 4, scan
    assert [polygon.select for polygon in obj_a.data.polygons] == [True, False, True]
    assert [polygon.select for polygon in obj_b.data.polygons] == [True, False, True]

    select_only(obj_a, obj_b, active=obj_a)
    assert_finished(bpy.ops.vcmp.select_by_color('EXEC_DEFAULT'))
    assert bpy.context.mode == 'OBJECT'
    assert [polygon.select for polygon in obj_a.data.polygons] == [True, False, True]
    assert [polygon.select for polygon in obj_b.data.polygons] == [True, False, True]


def test_object_mode_select_unknown_color_objects(addon):
    reset_scene()
    scene = bpy.context.scene
    scene.vcmp_color_items.clear()
    scene.vcmp_attribute_name = "mat_color"
    known_color = (0.45, 0.24, 0.09, 1.0)
    second_known_color = (0.08, 0.32, 0.7, 1.0)
    unknown_color = (0.28, 0.3, 0.33, 1.0)
    add_color_list_item(scene, "Known", known_color)
    add_color_list_item(scene, "SecondKnown", second_known_color)

    known_obj = new_mesh_object("KnownObject", new_three_face_mesh("KnownObjectMesh"))
    known_attr = known_obj.data.color_attributes.new(
        name="mat_color",
        type='BYTE_COLOR',
        domain='CORNER',
    )
    for polygon in known_obj.data.polygons:
        paint_polygon(known_attr, polygon, known_color)

    unknown_byte_obj = new_mesh_object(
        "UnknownByteObject",
        new_three_face_mesh("UnknownByteObjectMesh"),
    )
    unknown_byte_attr = unknown_byte_obj.data.color_attributes.new(
        name="mat_color",
        type='BYTE_COLOR',
        domain='CORNER',
    )
    for polygon in unknown_byte_obj.data.polygons:
        paint_polygon(
            unknown_byte_attr,
            polygon,
            unknown_color if polygon.index == 1 else known_color,
        )

    unknown_float_obj = new_mesh_object(
        "UnknownFloatObject",
        new_three_face_mesh("UnknownFloatObjectMesh"),
    )
    unknown_float_attr = unknown_float_obj.data.color_attributes.new(
        name="mat_color",
        type='FLOAT_COLOR',
        domain='CORNER',
    )
    for polygon in unknown_float_obj.data.polygons:
        paint_polygon(
            unknown_float_attr,
            polygon,
            unknown_color if polygon.index == 2 else second_known_color,
        )

    shared_mesh = new_three_face_mesh("UnknownSharedMesh")
    shared_a = new_mesh_object("UnknownSharedA", shared_mesh)
    shared_b = new_mesh_object("UnknownSharedB", shared_mesh)
    shared_attr = shared_mesh.color_attributes.new(
        name="mat_color",
        type='BYTE_COLOR',
        domain='CORNER',
    )
    for polygon in shared_mesh.polygons:
        paint_polygon(shared_attr, polygon, unknown_color)

    missing_attr_obj = new_mesh_object("MissingAttributeObject")
    invalid_attr_obj = new_mesh_object("InvalidAttributeObject")
    invalid_attr_obj.data.color_attributes.new(
        name="mat_color",
        type='BYTE_COLOR',
        domain='POINT',
    )
    empty_obj = new_mesh_object("EmptyObject", bpy.data.meshes.new("EmptyMesh"))

    select_only(
        known_obj,
        unknown_byte_obj,
        unknown_float_obj,
        shared_a,
        shared_b,
        missing_attr_obj,
        invalid_attr_obj,
        empty_obj,
        active=known_obj,
    )
    reference_colors = [tuple(item.color) for item in scene.vcmp_color_items]
    scan = addon._build_unknown_color_object_scan(
        bpy.context,
        "mat_color",
        reference_colors,
    )
    assert len(scan["targets"]) == 4, scan
    assert scan["skipped_duplicate"] == 1, scan
    assert scan["skipped_missing"] == 1, scan
    assert scan["skipped_invalid"] == 1, scan
    assert scan["skipped_empty"] == 1, scan

    done = addon._scan_unknown_color_objects_step(scan, 1)
    assert done is False
    while not done:
        done = addon._scan_unknown_color_objects_step(scan, 1)

    assert scan["unknown_mesh_count"] == 3, scan
    assert scan["unknown_object_count"] == 4, scan

    select_only(
        known_obj,
        unknown_byte_obj,
        unknown_float_obj,
        shared_a,
        shared_b,
        missing_attr_obj,
        invalid_attr_obj,
        empty_obj,
        active=known_obj,
    )
    assert_finished(bpy.ops.vcmp.select_unknown_color_objects('EXEC_DEFAULT'))
    assert bpy.context.mode == 'OBJECT'
    selected_names = {obj.name for obj in bpy.context.selected_objects}
    assert selected_names == {
        "UnknownByteObject",
        "UnknownFloatObject",
        "UnknownSharedA",
        "UnknownSharedB",
    }, selected_names

    scene.vcmp_color_items.clear()
    select_only(known_obj, unknown_byte_obj, active=known_obj)
    assert_finished(bpy.ops.vcmp.select_unknown_color_objects('EXEC_DEFAULT'))
    assert {obj.name for obj in bpy.context.selected_objects} == {
        "KnownObject",
        "UnknownByteObject",
    }


def test_edit_mode_select_unknown_color_objects_uses_bmesh(addon):
    reset_scene()
    scene = bpy.context.scene
    scene.vcmp_color_items.clear()
    scene.vcmp_attribute_name = "mat_color"
    known_color = (0.45, 0.24, 0.09, 1.0)
    unknown_color = (0.28, 0.3, 0.33, 1.0)
    add_color_list_item(scene, "Known", known_color)

    known_obj = new_mesh_object("EditKnown", new_three_face_mesh("EditKnownMesh"))
    unknown_obj = new_mesh_object("EditUnknown", new_three_face_mesh("EditUnknownMesh"))

    for obj in (known_obj, unknown_obj):
        attr = obj.data.color_attributes.new(
            name="mat_color",
            type='BYTE_COLOR',
            domain='CORNER',
        )
        for polygon in obj.data.polygons:
            paint_polygon(attr, polygon, known_color)

    select_only(known_obj, unknown_obj, active=known_obj)
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(unknown_obj.data)
    bm.faces.ensure_lookup_table()
    layer = bm.loops.layers.color.get("mat_color")
    bm.faces[0].loops[0][layer] = addon._scene_linear_to_bmesh_color(
        unknown_color,
        'BYTE_COLOR',
    )

    assert_finished(bpy.ops.vcmp.select_unknown_color_objects('EXEC_DEFAULT'))
    assert bpy.context.mode == 'EDIT_MESH'
    assert {obj.name for obj in bpy.context.objects_in_mode} == {"EditUnknown"}


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
        test_color_list_hex_csv_export(addon)
        test_color_list_json_import(addon)
        test_color_list_json_import_validation(addon)
        test_remove_helper_default_disabled(addon)
        test_paint_color_consistency(addon)
        test_edit_mode_color_copy_consistency(addon)
        test_object_mode_select_painted_faces_scan_is_chunked(addon)
        test_object_mode_select_unknown_color_objects(addon)
        test_edit_mode_select_unknown_color_objects_uses_bmesh(addon)
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
