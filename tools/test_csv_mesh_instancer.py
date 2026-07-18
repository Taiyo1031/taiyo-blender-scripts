"""Blender regression and scale tests for CSV Mesh Instancer.

Run correctness tests:
  blender --background --factory-startup --python tools/test_csv_mesh_instancer.py

Run the 60,569-row scale test:
  blender --background --factory-startup --python tools/test_csv_mesh_instancer.py -- --stress
"""

import csv
import math
import sys
import tempfile
import time
from pathlib import Path

import bpy
from mathutils import Euler, Matrix


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "_Taiyo_Blender_Extensions_Repo"
sys.path.insert(0, str(SOURCE_ROOT))

import csv_mesh_instancer as csvmi  # noqa: E402


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def matrix_error(a, b):
    return sum(abs(a[row][column] - b[row][column]) for row in range(3) for column in range(3))


def expect_operator_cancel(callable_operator, message):
    try:
        result = callable_operator()
    except RuntimeError:
        return
    check(result == {'CANCELLED'}, message)


def reset_data():
    for scene in list(bpy.data.scenes):
        if scene != bpy.context.scene:
            bpy.data.scenes.remove(scene)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    csvmi.clear_csv_cache(bpy.context.scene)


def make_mesh(name, offset=0.0):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(
        [(offset, 0.0, 0.0), (offset + 1.0, 0.0, 0.0), (offset, 1.0, 0.0)],
        [],
        [(0, 1, 2)],
    )
    mesh.update()
    return mesh


def make_object(name, mesh, collection):
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


def write_csv(path, rows, fieldnames=None):
    fieldnames = fieldnames or ["ptnum", "sx", "sy", "sz", "rx", "ry", "rz", "objname", "tx", "ty", "tz"]
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def drain_task(task, budget=csvmi.TIME_BUDGET_SECONDS):
    ticks = 0
    phase_seconds = {}
    while True:
        phase = task.phase
        started = time.perf_counter()
        finished = task.step(budget)
        phase_seconds[phase] = phase_seconds.get(phase, 0.0) + (time.perf_counter() - started)
        if finished:
            break
        ticks += 1
        if ticks > 1_000_000:
            raise RuntimeError("Task did not finish")
    task.test_phase_seconds = phase_seconds
    task.finish_props()
    return ticks + 1


def test_csv_and_collection_mode(temp_dir):
    print("[TEST] CSV validation, Collection matching, update, realization, cancellation")
    reset_data()
    scene = bpy.context.scene
    props = scene.csvmi_props
    root = bpy.data.collections.new("Sources")
    child = bpy.data.collections.new("NestedSources")
    scene.collection.children.link(root)
    root.children.link(child)

    source_meshes = {
        "Cube": make_mesh("Mesh_Cube", 0.0),
        "Cube.001": make_mesh("Mesh_Cube_001", 1.0),
        "Cube.002": make_mesh("Mesh_Cube_002", 2.0),
        "Sphere": make_mesh("Mesh_Sphere", 3.0),
    }
    source_objects = {
        name: make_object(name, mesh, root if name != "Sphere" else child)
        for name, mesh in source_meshes.items()
    }

    output = bpy.data.collections.new("CSV_Output")
    output.color_tag = 'COLOR_04'
    output.hide_render = True
    scene.collection.children.link(output)
    dummy = make_object("OldDummy", make_mesh("OldDummyMesh"), output)
    old_child = bpy.data.collections.new("OldChild")
    output.children.link(old_child)
    make_object("OldChildObject", make_mesh("OldChildMesh"), old_child)
    output_pointer = output.as_pointer()

    csv_path = temp_dir / "correctness.csv"
    rows = [
        {"ptnum": "10", "sx": "1", "sy": "2", "sz": "3", "rx": "90", "ry": "0", "rz": "-45", "objname": "Cube.002", "tx": "1.25", "ty": "-2", "tz": "3"},
        {"ptnum": "", "sx": "1", "sy": "1", "sz": "1", "rx": "0", "ry": "0", "rz": "0", "objname": "Cube.100", "tx": "4", "ty": "5", "tz": "6"},
        {"ptnum": "12", "sx": "1", "sy": "1", "sz": "1", "rx": "0", "ry": "0", "rz": "0", "objname": "Missing", "tx": "0", "ty": "0", "tz": "0"},
        {"ptnum": "13", "sx": "-1", "sy": "0", "sz": "2", "rx": "0", "ry": "180", "rz": "0", "objname": "Sphere", "tx": "7", "ty": "8", "tz": "9"},
        {"ptnum": "14", "sx": "1", "sy": "1", "sz": "1", "rx": "0", "ry": "0", "rz": "0", "objname": "", "tx": "0", "ty": "0", "tz": "0"},
        {"ptnum": "15", "sx": "1", "sy": "1", "sz": "1", "rx": "NaN", "ry": "0", "rz": "0", "objname": "Cube", "tx": "0", "ty": "0", "tz": "0"},
    ]
    write_csv(csv_path, rows)

    props.csv_path = str(csv_path)
    props.source_mode = 'COLLECTION'
    props.source_collection = root
    props.ignore_numeric_suffix = True
    props.output_collection_name = "CSV_Output"
    props.use_multi_tick = False

    result = bpy.ops.csvmi.import_csv('EXEC_DEFAULT')
    check(result == {'FINISHED'}, f"CSV import failed: {result}")
    original_cache = csvmi.get_csv_cache(scene)
    check(original_cache.raw_count == 6, "Raw row count mismatch")
    check(len(original_cache.rows) == 4, "Valid row count mismatch")
    check(original_cache.invalid_count == 2, "Invalid row count mismatch")

    bad_path = temp_dir / "missing_columns.csv"
    write_csv(bad_path, [{"objname": "Cube", "tx": "0"}], fieldnames=["objname", "tx"])
    props.csv_path = str(bad_path)
    expect_operator_cancel(lambda: bpy.ops.csvmi.import_csv('EXEC_DEFAULT'), "Invalid CSV should fail")
    check(csvmi.get_csv_cache(scene) is original_cache, "Failed re-import replaced the valid cache")
    props.csv_path = str(csv_path)

    result = bpy.ops.csvmi.update('EXEC_DEFAULT')
    check(result == {'FINISHED'}, f"Update failed: {result}")
    output = bpy.data.collections["CSV_Output"]
    check(output.as_pointer() == output_pointer, "Output Collection datablock was replaced")
    check(output.color_tag == 'COLOR_04' and output.hide_render, "Output Collection settings changed")
    output_layer = csvmi.find_layer_collection(bpy.context.view_layer.layer_collection, output)
    check(output_layer is not None and not output_layer.exclude, "Output View Layer exclusion was not restored")
    check("OldDummy" not in bpy.data.objects and "OldChild" not in bpy.data.collections, "Old output content remains")
    generated = list(output.objects)
    check(len(generated) == 3, f"Expected 3 generated objects, got {len(generated)}")
    check(props.skipped_count == 3, f"Expected 3 skipped rows, got {props.skipped_count}")
    check(props.missing_name_count == 1 and props.missing_row_count == 1, "Missing mesh stats mismatch")
    check(props.collision_group_count == 1, "Suffix collision group count mismatch")

    exact = bpy.data.objects["Cube.003"]
    fallback = bpy.data.objects["Cube.100"]
    sphere = bpy.data.objects["Sphere.001"]
    check(all(not obj.name.startswith("CSV_") for obj in generated), "Generated Object names still use the CSV_ prefix")
    check(exact.data == source_objects["Cube.002"].data, "Exact match did not win")
    check(fallback.data == source_objects["Cube"].data, "Suffix fallback priority mismatch")
    check(tuple(round(v, 5) for v in exact.location) == (1.25, -2.0, 3.0), "Location mismatch")
    check(math.isclose(exact.rotation_euler.x, math.pi / 2, abs_tol=1e-6), "Degree conversion mismatch")
    check(tuple(round(v, 5) for v in sphere.scale) == (-1.0, 0.0, 2.0), "Scale mismatch")
    check(tuple(exact.delta_scale) == (1.0, 1.0, 1.0), "Collection mode received FBX Delta Scale")
    check(tuple(exact.delta_rotation_euler) == (0.0, 0.0, 0.0), "Collection mode received FBX Delta Rotation")
    check(bool(exact["csvmi_linked_mesh"]), "Generated linked flag missing")
    names_by_line = {int(obj["csvmi_csv_line"]): obj.name for obj in generated}

    before_cancel = {obj.as_pointer() for obj in output.objects}
    _, existing_output, resolved, missing_names, missing_rows = csvmi.validate_source_and_output(scene, original_cache)
    cancel_task = csvmi.UpdateTask(scene, original_cache, existing_output, resolved, missing_names, missing_rows)
    cancel_task._create_one(original_cache.rows[0])
    cancel_task.index = 1
    cancel_task.request_cancel()
    drain_task(cancel_task, 0.001)
    check(cancel_task.cancelled, "Update cancellation did not finish as cancelled")
    check({obj.as_pointer() for obj in output.objects} == before_cancel, "Cancelled update changed old output")
    check(not any(c.name.startswith(csvmi.STAGING_NAME) for c in bpy.data.collections), "Staging Collection remains")

    linked_before = {obj.as_pointer(): obj.data.as_pointer() for obj in output.objects}
    realize_cancel = csvmi.RealizeTask(scene, list(output.objects))
    realize_object = realize_cancel.objects[0]
    old_mesh = realize_object.data
    new_mesh = old_mesh.copy()
    realize_object.data = new_mesh
    realize_object["csvmi_linked_mesh"] = False
    realize_cancel.changes.append((realize_object, old_mesh, new_mesh))
    realize_cancel.index = 1
    realize_cancel.request_cancel()
    drain_task(realize_cancel, 0.001)
    check(realize_cancel.cancelled, "Realize cancellation did not roll back")
    check(
        all(obj.data.as_pointer() == linked_before[obj.as_pointer()] for obj in output.objects),
        "Realize rollback did not restore shared meshes",
    )

    check(bpy.ops.csvmi.realize('EXEC_DEFAULT') == {'FINISHED'}, "Realization failed")
    realized_pointers = [obj.data.as_pointer() for obj in output.objects]
    check(len(set(realized_pointers)) == len(realized_pointers), "Realized meshes are not unique")
    check(all(not bool(obj["csvmi_linked_mesh"]) for obj in output.objects), "Realized flags were not updated")

    check(bpy.ops.csvmi.update('EXEC_DEFAULT') == {'FINISHED'}, "Update after realization failed")
    check(all(bool(obj["csvmi_linked_mesh"]) for obj in output.objects), "Update did not restore linked state")
    check(bpy.data.objects["Cube.003"].data == source_objects["Cube.002"].data, "Update did not re-link source mesh")
    check(
        {int(obj["csvmi_csv_line"]): obj.name for obj in output.objects} == names_by_line,
        "Fast re-update changed deterministic Object names",
    )

    output = bpy.data.collections["CSV_Output"]
    before_fast_cancel = {
        obj.as_pointer(): (
            obj.data.as_pointer(),
            tuple(obj.location),
            tuple(obj.rotation_euler),
            tuple(obj.scale),
            tuple(obj.delta_location),
            tuple(obj.delta_rotation_euler),
            tuple(obj.delta_scale),
        )
        for obj in output.objects
    }
    _, existing_output, resolved, missing_names, missing_rows = csvmi.validate_source_and_output(scene, original_cache)
    fast_cancel = csvmi.create_update_task(scene, original_cache, existing_output, resolved, missing_names, missing_rows)
    check(isinstance(fast_cancel, csvmi.InPlaceUpdateTask), "Generated output did not select fast update")
    first_row = original_cache.rows[0]
    first_source = resolved[first_row[csvmi.ROW_NAME]]
    first_object = fast_cancel.existing_by_line.pop(first_row[csvmi.ROW_LINE])
    fast_cancel.snapshots.append(fast_cancel._snapshot(first_object))
    fast_cancel._apply(first_object, first_row, first_source)
    fast_cancel.result_objects.append(first_object)
    fast_cancel.desired_names.append(fast_cancel.name_allocator.reserve(first_row[csvmi.ROW_NAME]))
    fast_cancel.index = 1
    fast_cancel.request_cancel()
    drain_task(fast_cancel, 0.001)
    check(fast_cancel.cancelled, "Fast update cancellation did not roll back")
    after_fast_cancel = {
        obj.as_pointer(): (
            obj.data.as_pointer(),
            tuple(obj.location),
            tuple(obj.rotation_euler),
            tuple(obj.scale),
            tuple(obj.delta_location),
            tuple(obj.delta_rotation_euler),
            tuple(obj.delta_scale),
        )
        for obj in output.objects
    }
    check(after_fast_cancel == before_fast_cancel, "Fast update rollback changed output data")
    check(not output_layer.exclude, "Cancelled update did not restore output visibility")
    print("[PASS] CSV and Collection mode")


def export_selected_fbx(path, objects):
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    result = bpy.ops.export_scene.fbx(
        filepath=str(path),
        check_existing=False,
        use_selection=True,
        object_types={'MESH'},
        use_mesh_modifiers=False,
        bake_anim=False,
        axis_forward='-Z',
        axis_up='Y',
    )
    check(result == {'FINISHED'}, f"FBX fixture export failed: {result}")


def test_fbx_mode(temp_dir):
    print("[TEST] FBX import and safe replacement")
    reset_data()
    scene = bpy.context.scene
    props = scene.csvmi_props
    fixture_collection = bpy.data.collections.new("Fixture")
    scene.collection.children.link(fixture_collection)
    a = make_object("FbxAssetA", make_mesh("FbxMeshA"), fixture_collection)
    b = make_object("FbxAssetB", make_mesh("FbxMeshB", 2.0), fixture_collection)
    first_fbx = temp_dir / "first.fbx"
    export_selected_fbx(first_fbx, [a, b])

    props.source_mode = 'FBX'
    props.fbx_path = str(first_fbx)
    props.fbx_collection_name = "CSVMI_FBX_Source"
    result = bpy.ops.csvmi.import_fbx('EXEC_DEFAULT')
    check(result == {'FINISHED'}, f"FBX import failed: {result}")
    old_collection = props.fbx_managed_collection
    old_pointer = old_collection.as_pointer()
    check(props.fbx_mesh_count == 2, "FBX mesh count mismatch")
    check(bool(old_collection[csvmi.FBX_MANAGED_KEY]), "FBX management marker missing")
    for view_layer in scene.view_layers:
        layer_collection = csvmi.find_layer_collection(view_layer.layer_collection, old_collection)
        check(layer_collection is not None and layer_collection.exclude, "FBX source was not excluded from a View Layer")
    check(not old_collection.hide_viewport, "View Layer exclusion unexpectedly used Collection hiding")

    fallback_collection = bpy.data.collections.new("CSVMI_FBX_Fallback")
    visibility_mode = csvmi.isolate_fbx_source_collection(scene, fallback_collection)
    check(visibility_mode == 'COLLECTION_HIDE', "Unlinked FBX source did not use the visibility fallback")
    check(fallback_collection.hide_viewport and fallback_collection.hide_render, "FBX visibility fallback is incomplete")
    bpy.data.collections.remove(fallback_collection)

    invalid_fbx = temp_dir / "invalid.fbx"
    invalid_fbx.write_text("not an fbx", encoding="utf-8")
    props.fbx_path = str(invalid_fbx)
    expect_operator_cancel(lambda: bpy.ops.csvmi.import_fbx('EXEC_DEFAULT'), "Invalid FBX should fail")
    check(props.fbx_managed_collection.as_pointer() == old_pointer, "Failed FBX import replaced old source")

    c = make_object("FbxAssetC", make_mesh("FbxMeshC", 4.0), fixture_collection)
    second_fbx = temp_dir / "second.fbx"
    export_selected_fbx(second_fbx, [c])
    props.fbx_path = str(second_fbx)
    result = bpy.ops.csvmi.import_fbx('EXEC_DEFAULT')
    check(result == {'FINISHED'}, f"FBX re-import failed: {result}")
    check(props.fbx_managed_collection.as_pointer() != old_pointer, "FBX source was not replaced")
    check(props.fbx_mesh_count == 1, "Re-imported FBX mesh count mismatch")
    check(len(csvmi.collect_collection_objects(props.fbx_managed_collection, mesh_only=True)) == 1, "Managed FBX Collection is incorrect")
    for view_layer in scene.view_layers:
        layer_collection = csvmi.find_layer_collection(view_layer.layer_collection, props.fbx_managed_collection)
        check(layer_collection is not None and layer_collection.exclude, "Re-imported FBX source is visible")

    imported_source = csvmi.collect_collection_objects(props.fbx_managed_collection, mesh_only=True)[0]
    csv_path = temp_dir / "fbx_correction.csv"
    write_csv(csv_path, [{
        "ptnum": "1",
        "sx": "2",
        "sy": "3",
        "sz": "4",
        "rx": "10",
        "ry": "20",
        "rz": "30",
        "objname": imported_source.name,
        "tx": "1",
        "ty": "2",
        "tz": "3",
    }])
    props.csv_path = str(csv_path)
    props.output_collection_name = "FBX_Output"
    props.use_multi_tick = False
    check(bpy.ops.csvmi.import_csv('EXEC_DEFAULT') == {'FINISHED'}, "FBX correction CSV import failed")
    check(bpy.ops.csvmi.update('EXEC_DEFAULT') == {'FINISHED'}, "FBX correction update failed")
    placement = bpy.data.collections["FBX_Output"].objects[0]
    check(placement.data == imported_source.data, "FBX placement did not share the source Mesh")
    check(tuple(round(v, 5) for v in placement.scale) == (2.0, 3.0, 4.0), "FBX correction changed CSV Scale")
    check(
        tuple(round(math.degrees(value), 5) for value in placement.rotation_euler) == (10.0, 20.0, 30.0),
        "FBX local correction changed the CSV Euler values",
    )
    check(
        tuple(round(v, 5) for v in placement.delta_scale) == (0.01, 0.01, 0.01),
        "Default FBX Delta Scale correction is missing",
    )
    check(
        math.isclose(props.fbx_rotation_x, math.pi / 2, abs_tol=1e-6),
        "Default FBX Local X Rotation setting is incorrect",
    )
    csv_rotation = Euler(tuple(math.radians(value) for value in (10.0, 20.0, 30.0)), 'XYZ').to_matrix()
    local_expected = csv_rotation @ Matrix.Rotation(math.pi / 2, 3, 'X')
    world_incorrect = Matrix.Rotation(math.pi / 2, 3, 'X') @ csv_rotation
    actual_rotation = placement.matrix_basis.to_3x3().normalized()
    check(matrix_error(actual_rotation, local_expected) < 1e-5, "FBX correction was not applied around local X")
    check(matrix_error(actual_rotation, world_incorrect) > 0.1, "FBX correction still behaves as a world X rotation")

    props.apply_fbx_correction = False
    check(bpy.ops.csvmi.update('EXEC_DEFAULT') == {'FINISHED'}, "Disabling FBX correction failed")
    placement = bpy.data.collections["FBX_Output"].objects[0]
    check(tuple(placement.delta_scale) == (1.0, 1.0, 1.0), "Disabled FBX correction left Delta Scale behind")
    check(tuple(placement.delta_rotation_euler) == (0.0, 0.0, 0.0), "Disabled FBX correction left Delta Rotation behind")

    props.apply_fbx_correction = True
    props.fbx_unit_scale = 0.02
    props.fbx_rotation_x = math.radians(-90.0)
    check(bpy.ops.csvmi.update('EXEC_DEFAULT') == {'FINISHED'}, "Custom FBX correction update failed")
    placement = bpy.data.collections["FBX_Output"].objects[0]
    check(tuple(round(v, 5) for v in placement.delta_scale) == (0.02, 0.02, 0.02), "Custom FBX Unit Scale failed")
    custom_expected = csv_rotation @ Matrix.Rotation(-math.pi / 2, 3, 'X')
    check(
        matrix_error(placement.matrix_basis.to_3x3().normalized(), custom_expected) < 1e-5,
        "Custom FBX Local X Rotation failed",
    )
    saved_delta_rotation = tuple(placement.delta_rotation_euler)

    fbx_cache = csvmi.get_csv_cache(scene)
    _, existing_output, resolved, missing_names, missing_rows = csvmi.validate_source_and_output(scene, fbx_cache)
    correction_cancel = csvmi.create_update_task(
        scene,
        fbx_cache,
        existing_output,
        resolved,
        missing_names,
        missing_rows,
    )
    row = fbx_cache.rows[0]
    source = resolved[row[csvmi.ROW_NAME]]
    existing = correction_cancel.existing_by_line.pop(row[csvmi.ROW_LINE])
    correction_cancel.snapshots.append(correction_cancel._snapshot(existing))
    props.fbx_unit_scale = 0.03
    props.fbx_rotation_x = math.radians(45.0)
    correction_cancel._apply(existing, row, source)
    correction_cancel.result_objects.append(existing)
    correction_cancel.desired_names.append(correction_cancel.name_allocator.reserve(row[csvmi.ROW_NAME]))
    correction_cancel.index = 1
    correction_cancel.request_cancel()
    drain_task(correction_cancel, 0.001)
    check(tuple(round(v, 5) for v in existing.delta_scale) == (0.02, 0.02, 0.02), "Cancel did not restore FBX Delta Scale")
    check(
        all(math.isclose(actual, expected, abs_tol=1e-6) for actual, expected in zip(existing.delta_rotation_euler, saved_delta_rotation)),
        "Cancel did not restore FBX Delta Rotation",
    )
    check(not props.running and props.active_operation == 'NONE', "FBX import did not release the UI lock")
    print("[PASS] FBX mode")


def make_stress_csv(path, name_count=1232, valid_rows=60568):
    names = [f"Stress_{index:04d}" for index in range(name_count)]
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ptnum", "sx", "sy", "sz", "rx", "ry", "rz", "objname", "tx", "ty", "tz"])
        for index in range(valid_rows):
            writer.writerow([
                index,
                1.0,
                1.0,
                1.0,
                index % 360,
                0.0,
                0.0,
                names[index % name_count],
                index * 0.01,
                index % 97,
                -(index % 31),
            ])
        writer.writerow([valid_rows, 1, 1, 1, 0, 0, 0, "", 0, 0, 0])
    return names


def run_scale_test(temp_dir, valid_rows=60568, name_count=1232, reupdate=True):
    print(f"[STRESS] {valid_rows + 1:,} CSV rows / {name_count:,} source names", flush=True)
    reset_data()
    scene = bpy.context.scene
    props = scene.csvmi_props
    source = bpy.data.collections.new("StressSources")
    scene.collection.children.link(source)
    shared_mesh = make_mesh("StressSharedMesh")
    stress_csv = temp_dir / f"stress_{valid_rows + 1}.csv"
    names = make_stress_csv(stress_csv, name_count=name_count, valid_rows=valid_rows)
    for name in names:
        make_object(name, shared_mesh, source)

    props.csv_path = str(stress_csv)
    if "--stress-fbx" in sys.argv:
        source[csvmi.FBX_MANAGED_KEY] = True
        props.source_mode = 'FBX'
        props.fbx_managed_collection = source
    else:
        props.source_mode = 'COLLECTION'
        props.source_collection = source
    props.ignore_numeric_suffix = False
    props.output_collection_name = "Stress_Output"
    props.use_multi_tick = True

    parse_start = time.perf_counter()
    check(bpy.ops.csvmi.import_csv('EXEC_DEFAULT') == {'FINISHED'}, "Stress CSV import failed")
    parse_seconds = time.perf_counter() - parse_start
    cache = csvmi.get_csv_cache(scene)
    check(cache.raw_count == valid_rows + 1 and len(cache.rows) == valid_rows, "Stress CSV counts mismatch")
    check(len(cache.unique_names) == min(name_count, valid_rows) and cache.invalid_count == 1, "Stress CSV validation mismatch")

    def build_once():
        _, output, resolved, missing_names, missing_rows = csvmi.validate_source_and_output(scene, cache)
        task = csvmi.create_update_task(scene, cache, output, resolved, missing_names, missing_rows)
        ticks = drain_task(task)
        check(not task.cancelled and task.created_count == valid_rows, "Stress task did not create all objects")
        return task, ticks

    first_start = time.perf_counter()
    first_task, first_ticks = build_once()
    first_seconds = time.perf_counter() - first_start
    output = bpy.data.collections["Stress_Output"]
    output_pointer = output.as_pointer()
    check(len(output.objects) == valid_rows, "Stress output object count mismatch")
    check(props.skipped_count == 1, "Stress skipped count mismatch")
    check(all(obj.data == shared_mesh for obj in list(output.objects)[:100]), "Stress meshes are not linked")

    second_task = None
    second_ticks = 0
    second_seconds = 0.0
    if reupdate:
        print("[STRESS] Starting safe re-update", flush=True)
        second_start = time.perf_counter()
        second_task, second_ticks = build_once()
        second_seconds = time.perf_counter() - second_start
        output = bpy.data.collections["Stress_Output"]
        check(output.as_pointer() == output_pointer, "Stress re-update replaced output Collection")
        check(len(output.objects) == valid_rows, "Stress re-update count mismatch")
        check(not any(c.name.startswith(csvmi.STAGING_NAME) for c in bpy.data.collections), "Stress staging Collection remains")

    print(
        "[STRESS RESULT] "
        f"parse={parse_seconds:.2f}s, "
        f"first={first_seconds:.2f}s/{first_ticks}ticks/max={first_task.max_step_seconds * 1000:.1f}ms, "
        + (
            f"reupdate={second_seconds:.2f}s/{second_ticks}ticks/max={second_task.max_step_seconds * 1000:.1f}ms"
            if second_task is not None else "reupdate=skipped"
        ),
        flush=True,
    )
    print(
        "[STRESS PHASES] "
        + ", ".join(f"{phase}={seconds:.2f}s" for phase, seconds in first_task.test_phase_seconds.items()),
        flush=True,
    )
    check(first_task.max_step_seconds < 0.25, "First update exceeded 250ms max tick")
    if second_task is not None:
        check(second_task.max_step_seconds < 0.25, "Re-update exceeded 250ms max tick")
    print("[PASS] Scale test", flush=True)


def option_int(name, default):
    if name not in sys.argv:
        return default
    index = sys.argv.index(name)
    return int(sys.argv[index + 1])


def main():
    csvmi.register()
    try:
        with tempfile.TemporaryDirectory(prefix="csvmi_test_") as temp:
            temp_dir = Path(temp)
            if "--stress-only" not in sys.argv:
                test_csv_and_collection_mode(temp_dir)
                test_fbx_mode(temp_dir)
            if "--stress" in sys.argv:
                run_scale_test(
                    temp_dir,
                    valid_rows=option_int("--stress-rows", 60568),
                    name_count=option_int("--stress-names", 1232),
                    reupdate="--no-reupdate" not in sys.argv,
                )
        print("CSVMI_TESTS_OK")
    finally:
        csvmi.unregister()


if __name__ == "__main__":
    main()
