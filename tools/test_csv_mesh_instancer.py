import importlib.util
import math
import os
import sys
import tempfile
import time
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
ADDON_DIR = ROOT / "_Taiyo_Blender_Extensions_Repo" / "csv_mesh_instancer"
REAL_CSV = Path("/Users/taiyoparent/Downloads/StPr_map_PointData (3).csv")


def load_addon():
    spec = importlib.util.spec_from_file_location(
        "csv_mesh_instancer",
        ADDON_DIR / "__init__.py",
        submodule_search_locations=[str(ADDON_DIR)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


csvmi = load_addon()


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def close_enough(left, right, tolerance=1.0e-5):
    return abs(float(left) - float(right)) <= tolerance


def expect_operator_error(callback, text):
    try:
        result = callback()
    except RuntimeError as exc:
        check(text in str(exc), f"Unexpected operator error: {exc}")
        return
    check(result == {'CANCELLED'}, f"Operator unexpectedly returned {result}")


def reset_data():
    csvmi._CSV_CACHE.clear()
    csvmi._ACTIVE_TASKS.clear()
    if bpy.data.objects:
        bpy.data.batch_remove(list(bpy.data.objects))
    for collection in list(bpy.data.collections):
        if collection.name in bpy.data.collections:
            bpy.data.collections.remove(collection)
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0 and mesh.name in bpy.data.meshes:
            bpy.data.meshes.remove(mesh)
    props = bpy.context.scene.csvmi_props
    props.fbx_collection = None
    props.output_collection = None
    props.csv_path = ""
    props.fbx_path = ""
    props.fbx_collection_name = "CSVMI_FBX_Source"
    props.output_collection_name = "CSV_Output"
    props.ignore_numeric_suffix = False
    props.apply_fbx_correction = True
    props.fbx_unit_scale = 0.01
    props.fbx_rotation_x = math.radians(90.0)
    props.use_multi_tick = True
    props.busy = False
    props.can_cancel = False
    props.cancel_requested = False
    props.status = "Ready"


def make_mesh(name, scale=1.0):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(
        [(0.0, 0.0, 0.0), (scale, 0.0, 0.0), (0.0, scale, 0.0)],
        [],
        [(0, 1, 2)],
    )
    mesh.update()
    return mesh


def make_object(name, mesh, collection):
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


def make_source(names, collection_name="CSVMI_FBX_Source"):
    collection = bpy.data.collections.new(collection_name)
    bpy.context.scene.collection.children.link(collection)
    collection[csvmi.FBX_MANAGED_KEY] = True
    objects = {}
    for name in names:
        obj = make_object(name, make_mesh(name), collection)
        obj[csvmi.FBX_CANONICAL_OBJECT_KEY] = name
        obj.data[csvmi.FBX_CANONICAL_MESH_KEY] = name
        objects[name] = obj
    csvmi.hide_source_collection(bpy.context.scene, collection)
    props = bpy.context.scene.csvmi_props
    props.fbx_collection = collection
    props.fbx_mesh_count = len(objects)
    return collection, objects


def write_csv(path, rows, include_extra=True):
    header = "objname,tx,ty,tz,rx,ry,rz,sx,sy,sz"
    if include_extra:
        header += ",id,Zone"
    lines = [header]
    for index, values in enumerate(rows):
        line = ",".join(str(value) for value in values)
        if include_extra:
            line += f",{-1 if index < 2 else index},0"
        lines.append(line)
    path.write_text("\ufeff" + "\n".join(lines) + "\n", encoding="utf-8")


def import_csv(path):
    props = bpy.context.scene.csvmi_props
    props.csv_path = str(path)
    result = bpy.ops.csvmi.import_csv('EXEC_DEFAULT')
    check(result == {'FINISHED'}, f"CSV import failed: {props.status}")
    return csvmi.get_csv_cache(bpy.context.scene)


def write_test_fbx(path):
    bpy.ops.preferences.addon_enable(module="io_scene_fbx")
    collection = bpy.data.collections.new("FBX_Export_Fixture")
    bpy.context.scene.collection.children.link(collection)
    first = make_object("Piece", make_mesh("Piece"), collection)
    legitimate = make_object("Piece.001", make_mesh("Piece.001", 2.0), collection)
    bpy.ops.object.select_all(action='DESELECT')
    first.select_set(True)
    legitimate.select_set(True)
    bpy.context.view_layer.objects.active = first
    result = bpy.ops.export_scene.fbx(
        filepath=str(path),
        use_selection=True,
        object_types={'MESH'},
        use_mesh_modifiers=False,
        bake_anim=False,
        add_leaf_bones=False,
    )
    check(result == {'FINISHED'}, "Synthetic FBX export failed")


def test_csv_import(temp_dir):
    print("[TEST] simple CSV import")
    reset_data()
    valid = temp_dir / "valid.csv"
    write_csv(
        valid,
        [
            ("Piece", 1, 2, 3, 0.1, 0.2, 0.3, 1, 2, 3),
            ("Piece", 4, 5, 6, 0, 0, 0, 1, 1, 1),
        ],
    )
    cache = import_csv(valid)
    check(len(cache.rows) == 2, "CSV row count mismatch")
    check(cache.unique_names == ("Piece",), "CSV name index mismatch")
    check(not hasattr(bpy.context.scene.csvmi_props, "identity_column"), "Stable ID UI still exists")

    invalid = temp_dir / "invalid.csv"
    invalid.write_text(
        "objname,tx,ty,tz,rx,ry,rz,sx,sy,sz\nPiece,nan,0,0,0,0,0,1,1,1\n",
        encoding="utf-8",
    )
    bpy.context.scene.csvmi_props.csv_path = str(invalid)
    expect_operator_error(
        lambda: bpy.ops.csvmi.import_csv('EXEC_DEFAULT'),
        "Invalid CSV data",
    )
    check(csvmi.get_csv_cache(bpy.context.scene) is None, "Invalid CSV left a runtime cache")
    print("[PASS] simple CSV import")


def test_fbx_import_and_placement(temp_dir):
    print("[TEST] FBX import, re-import, and linked placement")
    reset_data()
    fbx_path = temp_dir / "simple_source.fbx"
    write_test_fbx(fbx_path)
    reset_data()
    props = bpy.context.scene.csvmi_props
    props.fbx_path = str(fbx_path)
    props.fbx_collection_name = "CSVMI_FBX_Test"
    check(bpy.ops.csvmi.import_fbx('EXEC_DEFAULT') == {'FINISHED'}, "Initial FBX import failed")
    first_source = props.fbx_collection
    first_objects = {
        csvmi.source_object_name(obj): obj
        for obj in csvmi.collect_collection_objects(first_source, mesh_only=True)
    }
    check(set(first_objects) == {"Piece", "Piece.001"}, "FBX names changed on initial import")
    check(first_source.hide_viewport and first_source.hide_render, "FBX source is visible")

    csv_path = temp_dir / "placement.csv"
    write_csv(
        csv_path,
        [
            ("Piece", 1, 2, 3, 0.1, 0.2, 0.3, 1, 2, 3),
            ("Piece.001", 4, 5, 6, 0, 0, 0, 1, 1, 1),
            ("Missing", 0, 0, 0, 0, 0, 0, 1, 1, 1),
        ],
    )
    import_csv(csv_path)
    props.output_collection_name = "Simple_Output"
    check(bpy.ops.csvmi.place('EXEC_DEFAULT') == {'FINISHED'}, "Initial placement failed")
    output = bpy.data.collections["Simple_Output"]
    check(props.output_collection == output, "Placement did not remember its output Collection")
    placed = list(output.objects)
    check(len(placed) == 2, "Placement count mismatch")
    check(props.missing_count == 1, "Missing source count mismatch")
    check(all(not obj.name.startswith("CSV_") for obj in placed), "CSV_ prefix was added")
    piece = next(obj for obj in placed if obj.data == first_objects["Piece"].data)
    check(tuple(round(value, 6) for value in piece.location) == (1.0, 2.0, 3.0), "Location mismatch")
    check(
        tuple(round(value, 6) for value in piece.rotation_euler)
        == tuple(round(math.radians(value), 6) for value in (0.1, 0.2, 0.3)),
        "CSV degree rotation was not converted to radians",
    )
    check(tuple(round(value, 6) for value in piece.scale) == (1.0, 2.0, 3.0), "Scale mismatch")
    check(all(close_enough(value, 0.01) for value in piece.delta_scale), "FBX unit correction mismatch")
    expected_delta = (
        piece.rotation_euler.to_quaternion()
        @ csvmi.Quaternion((1.0, 0.0, 0.0), props.fbx_rotation_x)
        @ piece.rotation_euler.to_quaternion().conjugated()
    )
    check(piece.delta_rotation_euler.to_quaternion().rotation_difference(expected_delta).angle < 1e-5, "Local X correction mismatch")

    for target, collection in (("FBX", first_source), ("OUTPUT", output)):
        check(
            bpy.ops.csvmi.set_collection_visibility(target=target, visible=True)
            == {'FINISHED'},
            f"{target} Show failed",
        )
        check(csvmi.collection_is_visible(bpy.context.scene, collection), f"{target} stayed hidden")
        check(
            bpy.ops.csvmi.set_collection_visibility(target=target, visible=False)
            == {'FINISHED'},
            f"{target} Hide failed",
        )
        check(not csvmi.collection_is_visible(bpy.context.scene, collection), f"{target} stayed visible")

    old_meshes = {obj.data for obj in placed}
    old_names = {
        obj.as_pointer(): (obj.name, obj.data.name)
        for obj in csvmi.collect_collection_objects(first_source, mesh_only=True)
    }
    invalid_fbx = temp_dir / "invalid.fbx"
    invalid_fbx.write_bytes(b"not an fbx")
    props.fbx_path = str(invalid_fbx)
    expect_operator_error(
        lambda: bpy.ops.csvmi.import_fbx('EXEC_DEFAULT'),
        "FBX import failed",
    )
    check(props.fbx_collection == first_source, "Invalid FBX replaced the source")
    check(
        {
            obj.as_pointer(): (obj.name, obj.data.name)
            for obj in csvmi.collect_collection_objects(first_source, mesh_only=True)
        }
        == old_names,
        "Invalid FBX did not restore names",
    )

    props.fbx_path = str(fbx_path)
    check(bpy.ops.csvmi.import_fbx('EXEC_DEFAULT') == {'FINISHED'}, "FBX re-import failed")
    second_source = props.fbx_collection
    second_objects = {
        csvmi.source_object_name(obj): obj
        for obj in csvmi.collect_collection_objects(second_source, mesh_only=True)
    }
    check(set(second_objects) == {"Piece", "Piece.001"}, "FBX re-import accumulated suffixes")
    check(
        {obj.data.get(csvmi.FBX_CANONICAL_MESH_KEY) for obj in second_objects.values()}
        == {"Piece", "Piece.001"},
        "FBX Mesh canonical names changed",
    )
    check(all("[Previous FBX" in mesh.name for mesh in old_meshes), "Old output Meshes were not staged")

    check(bpy.ops.csvmi.place('EXEC_DEFAULT') == {'FINISHED'}, "Replacement placement failed")
    replaced = list(bpy.data.collections["Simple_Output"].objects)
    new_meshes = {obj.data for obj in second_objects.values()}
    check(all(obj.data in new_meshes for obj in replaced), "Replacement did not use new FBX Meshes")
    check(
        not any(bool(mesh.get(csvmi.FBX_PREVIOUS_MESH_KEY, False)) and mesh.users == 0 for mesh in bpy.data.meshes),
        "Unused Previous FBX Mesh remained",
    )
    print("[PASS] FBX import and placement")


def test_tick_cancel(temp_dir):
    print("[TEST] bounded placement cancellation")
    reset_data()
    _source, _objects = make_source(["Piece"])
    small = temp_dir / "small.csv"
    write_csv(small, [("Piece", 0, 0, 0, 0, 0, 0, 1, 1, 1)])
    import_csv(small)
    props = bpy.context.scene.csvmi_props
    props.output_collection_name = "Cancelled_Output"

    rows = [
        ("Piece", float(index), 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, index + 2)
        for index in range(5000)
    ]
    cache = csvmi.CSVData(str(small), small.stat().st_mtime_ns, small.stat().st_size, rows)
    csvmi._CSV_CACHE[csvmi.scene_key(bpy.context.scene)] = cache
    task = csvmi.PlacementTask(bpy.context.scene, cache, props.fbx_collection, None)
    csvmi.set_running(props, "Placing objects", True)
    started = time.perf_counter()
    check(not task.step(0.004), "Large task unexpectedly finished in one tick")
    first_tick = time.perf_counter() - started
    props.cancel_requested = True
    check(task.step(0.004), "Cancelled task did not finish")
    csvmi.set_idle(props)
    check(task.cancelled, "Task did not record cancellation")
    check("Cancelled_Output" not in bpy.data.collections, "Cancellation created an output")
    check(not any(collection.name.startswith("__CSVMI_BUILD_OUTPUT__") for collection in bpy.data.collections), "Cancellation left staging data")
    check(first_tick < 0.08, f"Placement tick blocked too long: {first_tick:.3f}s")
    print(f"[PASS] bounded cancellation first_tick={first_tick * 1000:.1f}ms")


def test_blender_style_output_names(temp_dir):
    print("[TEST] Blender-style output Object names")
    reset_data()
    make_source(["Piece"])
    csv_path = temp_dir / "names.csv"
    write_csv(
        csv_path,
        [
            ("Piece", 0, 0, 0, 0, 0, 0, 1, 1, 1),
            ("Piece", 1, 0, 0, 0, 0, 0, 1, 1, 1),
        ],
    )
    import_csv(csv_path)
    props = bpy.context.scene.csvmi_props
    props.output_collection_name = "Name_Output"
    check(bpy.ops.csvmi.place('EXEC_DEFAULT') == {'FINISHED'}, "Name placement failed")
    output = bpy.data.collections["Name_Output"]
    check(
        {obj.name for obj in output.objects} == {"Piece.001", "Piece.002"},
        f"Unexpected Blender-style names: {[obj.name for obj in output.objects]}",
    )

    for index, obj in enumerate(output.objects):
        obj.name = f"{index + 2:06d}_Piece"
    check(bpy.ops.csvmi.place('EXEC_DEFAULT') == {'FINISHED'}, "Name migration failed")
    check(
        {obj.name for obj in output.objects} == {"Piece.001", "Piece.002"},
        "Number-prefixed names were not migrated",
    )
    print("[PASS] Blender-style output Object names")


def run_stress(temp_dir):
    stress_csv = REAL_CSV
    source_label = "actual"
    if not stress_csv.is_file():
        stress_csv = temp_dir / "synthetic_60k.csv"
        write_csv(
            stress_csv,
            (
                (
                    f"Piece_{index % 1225:04d}",
                    float(index % 1000),
                    float((index // 1000) % 1000),
                    float(index % 37),
                    float(index % 360),
                    float((index * 2) % 360),
                    float((index * 3) % 360),
                    1.0,
                    1.0,
                    1.0,
                )
                for index in range(60_474)
            ),
        )
        source_label = "synthetic"
    print(f"[STRESS] 60k {source_label} CSV placement and replacement", flush=True)
    reset_data()
    print("[STRESS STAGE] reset", flush=True)
    props = bpy.context.scene.csvmi_props
    props.csv_path = str(stress_csv)
    started = time.perf_counter()
    check(bpy.ops.csvmi.import_csv('EXEC_DEFAULT') == {'FINISHED'}, f"Stress CSV failed: {props.status}")
    import_seconds = time.perf_counter() - started
    cache = csvmi.get_csv_cache(bpy.context.scene)
    stress_rows = int(os.environ.get("CSVMI_STRESS_ROWS", "0"))
    if stress_rows:
        cache = csvmi.CSVData(
            cache.path,
            cache.mtime_ns,
            cache.size,
            cache.rows[:stress_rows],
        )
        csvmi._CSV_CACHE[csvmi.scene_key(bpy.context.scene)] = cache
    print(f"[STRESS STAGE] imported {len(cache.rows):,} rows in {import_seconds:.2f}s", flush=True)
    source, _objects = make_source(cache.unique_names, "Stress_FBX_Source")
    print(f"[STRESS STAGE] built {len(cache.unique_names):,} source Meshes", flush=True)
    props.fbx_collection = source
    props.output_collection_name = "Stress_Output"
    props.use_multi_tick = True
    started = time.perf_counter()
    check(bpy.ops.csvmi.place('EXEC_DEFAULT') == {'FINISHED'}, "Stress placement failed")
    first_seconds = time.perf_counter() - started
    print(f"[STRESS STAGE] placed in {first_seconds:.2f}s", flush=True)
    check(len(bpy.data.collections["Stress_Output"].objects) == len(cache.rows), "Stress count mismatch")
    if os.environ.get("CSVMI_STRESS_SKIP_TOGGLE") != "1":
        output = bpy.data.collections["Stress_Output"]
        toggle_started = time.perf_counter()
        csvmi.set_collection_visibility(bpy.context.scene, output, True)
        csvmi.set_collection_visibility(bpy.context.scene, output, False)
        toggle_seconds = time.perf_counter() - toggle_started
        check(not csvmi.collection_is_visible(bpy.context.scene, output), "Stress output Hide failed")
        print(f"[STRESS STAGE] show/hide in {toggle_seconds:.3f}s", flush=True)
    if os.environ.get("CSVMI_STRESS_FIRST_ONLY") == "1":
        print("[PASS] first-placement stress profile")
        return
    started = time.perf_counter()
    check(bpy.ops.csvmi.place('EXEC_DEFAULT') == {'FINISHED'}, "Stress replacement failed")
    replace_seconds = time.perf_counter() - started
    print(f"[STRESS STAGE] replaced in {replace_seconds:.2f}s", flush=True)
    check(len(bpy.data.collections["Stress_Output"].objects) == len(cache.rows), "Replacement count mismatch")
    print(
        f"[STRESS RESULT] rows={len(cache.rows):,} import={import_seconds:.2f}s "
        f"place={first_seconds:.2f}s replace={replace_seconds:.2f}s",
        flush=True,
    )
    check(import_seconds < 2.0, "CSV import exceeded 2 seconds")
    if not stress_rows:
        check(first_seconds < 15.0, "Initial placement exceeded 15 seconds")
        check(replace_seconds < 18.0, "Replacement exceeded 18 seconds")
    print("[PASS] stress")


def main():
    csvmi.register()
    try:
        props = bpy.context.scene.csvmi_props
        check(props.use_multi_tick, "Split Across Multiple Ticks must default ON")
        check(len(csvmi.CLASSES) == 7, "Unexpected v3 UI/operators remain")
        check(not (ADDON_DIR / "v2_engine.py").exists(), "v2 difference engine still exists")
        with tempfile.TemporaryDirectory(prefix="csvmi_v3_test_") as directory:
            temp_dir = Path(directory)
            if "--stress-only" not in sys.argv:
                test_csv_import(temp_dir)
                test_fbx_import_and_placement(temp_dir)
                test_tick_cancel(temp_dir)
                test_blender_style_output_names(temp_dir)
            if "--stress" in sys.argv:
                run_stress(temp_dir)
        print("CSVMI_V3_TESTS_OK")
    finally:
        csvmi.unregister()


if __name__ == "__main__":
    main()
