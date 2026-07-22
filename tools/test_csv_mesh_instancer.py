"""Blender 4.5 regression and scale tests for CSV Mesh Instancer v2.

Run:
  blender --background --factory-startup --python tools/test_csv_mesh_instancer.py
  blender --background --factory-startup --python tools/test_csv_mesh_instancer.py -- --stress
"""

import csv
import math
import os
import sys
import tempfile
import time
from pathlib import Path

import bpy


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "_Taiyo_Blender_Extensions_Repo"))

import csv_mesh_instancer as csvmi  # noqa: E402


FIELDS = [
    "ptnum", "Zone", "sx", "sy", "sz", "rx", "ry", "rz",
    "objname", "id", "tx", "ty", "tz", "weight", "label",
]


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def expect_error(call, contains):
    try:
        call()
    except (ValueError, RuntimeError) as exc:
        check(contains in str(exc), f"Expected {contains!r}, got {exc!r}")
        return
    raise AssertionError(f"Expected error containing {contains!r}")


def reset_data():
    scene = bpy.context.scene
    csvmi.clear_csv_cache(scene)
    csvmi.clear_preview_cache(scene)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    for text in list(bpy.data.texts):
        bpy.data.texts.remove(text)
    props = scene.csvmi_props
    props.source_collection = None
    props.fbx_managed_collection = None
    props.attribute_filters.clear()
    props.csv_attributes.clear()
    props.identity_column = "id"
    props.output_collection_name = "CSV_Output"
    props.split_by_attribute = True
    props.split_attribute = "Zone"
    props.use_multi_tick = False


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


def row(identity, objname="AssetA", zone="0", tx=0.0, rz=0.0, weight="1.5", label="A"):
    return {
        "ptnum": str(identity), "Zone": str(zone), "sx": "1", "sy": "1", "sz": "1",
        "rx": "0", "ry": "0", "rz": str(rz), "objname": objname, "id": str(identity),
        "tx": str(tx), "ty": "0", "tz": "0", "weight": str(weight), "label": label,
    }


def write_csv(path, rows, fields=FIELDS):
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def import_preview_apply(scene, csv_path):
    props = scene.csvmi_props
    props.csv_path = str(csv_path)
    check(bpy.ops.csvmi.import_csv('EXEC_DEFAULT') == {'FINISHED'}, "CSV import failed")
    for attribute in props.csv_attributes:
        attribute.enabled = True
    check(bpy.ops.csvmi.preview_changes('EXEC_DEFAULT') == {'FINISHED'}, "Preview failed")
    check(bpy.ops.csvmi.apply_reviewed('EXEC_DEFAULT') == {'FINISHED'}, "Apply failed")


def preview_by_id(scene):
    preview = csvmi.get_preview_cache(scene)
    check(preview is not None, "Preview cache is missing")
    return {change["identity"]: change for change in preview.changes}


def managed_object(output, identity):
    for obj in csvmi.collect_collection_objects(output):
        if str(obj.get(csvmi.OBJECT_ID_KEY, "")) == str(identity):
            return obj
    return None


def test_identity_validation(temp_dir):
    print("[TEST] strict persistent identity validation")
    duplicate = temp_dir / "duplicate.csv"
    write_csv(duplicate, [row("-1"), row("-1", tx=2)])
    expect_error(lambda: csvmi.load_csv_data(str(duplicate), "id"), "duplicate values")

    missing = temp_dir / "missing_id.csv"
    bad = row("1")
    bad["id"] = ""
    write_csv(missing, [bad])
    expect_error(lambda: csvmi.load_csv_data(str(missing), "id"), "Identity is empty")

    valid = temp_dir / "negative_ids.csv"
    write_csv(valid, [row("-11"), row("-12", zone=1)])
    cache = csvmi.load_csv_data(str(valid), "id")
    check(set(cache.rows_by_id) == {"-11", "-12"}, "Unique negative IDs were rejected")
    check("ptnum" not in cache.extra_columns, "ptnum leaked into extra attributes")

    actual = Path("/Users/taiyoparent/Downloads/StPr_map_PointData (3).csv")
    if actual.exists():
        expect_error(lambda: csvmi.load_csv_data(str(actual), "id"), "duplicate values")
    print("[PASS] identity validation")


def test_v2_workflow(temp_dir):
    print("[TEST] v2 preview, three-way merge, filters, tombstones, and state")
    reset_data()
    scene = bpy.context.scene
    props = scene.csvmi_props
    source = bpy.data.collections.new("Sources")
    scene.collection.children.link(source)
    mesh_a = make_mesh("MeshA")
    mesh_b = make_mesh("MeshB", 2.0)
    source_a = make_object("AssetA", mesh_a, source)
    source_b = make_object("AssetB", mesh_b, source)
    props.source_mode = 'COLLECTION'
    props.source_collection = source

    csv_path = temp_dir / "workflow.csv"
    rows = [row("100", "AssetA", 0, tx=1, weight="1.25", label="first"), row("200", "AssetA", 1, tx=2, weight="2", label="second")]
    write_csv(csv_path, rows)
    import_preview_apply(scene, csv_path)

    output = bpy.data.collections["CSV_Output"]
    check(int(output[csvmi.OUTPUT_SCHEMA_KEY]) == 2, "v2 output schema marker missing")
    state = csvmi.v2_engine.read_output_state(output, "id")
    check(set(state["records"]) == {"100", "200"}, "Persistent ID registry mismatch")
    check(output.hide_viewport and output.hide_render, "Completed output was not hidden")
    zone_values = {child.get(csvmi.ZONE_VALUE_KEY) for child in output.children if child.get(csvmi.ZONE_COLLECTION_KEY)}
    check(zone_values == {"0", "1"}, "Zone child Collections were not created")

    object_100 = managed_object(output, "100")
    object_200 = managed_object(output, "200")
    check(object_100.data == source_a.data and object_200.data == source_a.data, "Initial linked Mesh mismatch")
    check(object_100["id"] == "100" and "ptnum" not in object_100, "Visible ID or ptnum policy mismatch")
    check(math.isclose(object_100["weight"], 1.25), "Typed float Custom Property mismatch")
    check(object_100["label"] == "first", "String Custom Property mismatch")

    check(bpy.ops.csvmi.preview_changes('EXEC_DEFAULT') == {'FINISHED'}, "No-change Preview failed")
    check(len(csvmi.get_preview_cache(scene).changes) == 0, "Unchanged IDs appeared in Change Review")

    object_100.location.x = 10.0
    rows[0]["tx"] = "5"
    rows[0]["weight"] = "9.5"
    rows[1]["tx"] = "8"
    rows[1]["objname"] = "AssetB"
    write_csv(csv_path, rows)
    props.csv_path = str(csv_path)
    check(bpy.ops.csvmi.import_csv('EXEC_DEFAULT') == {'FINISHED'}, "Changed CSV import failed")
    check(bpy.ops.csvmi.preview_changes('EXEC_DEFAULT') == {'FINISHED'}, "Changed Preview failed")
    changes = preview_by_id(scene)
    check(changes["100"]["transform_kind"] == "CONFLICT", "Transform conflict was not detected")
    check(changes["100"]["transform_decision"] == "KEEP", "Conflict did not default to Keep Blender")
    check(changes["200"]["transform_decision"] == "APPLY", "CSV-only Transform did not default to Apply")
    check(changes["200"]["mesh_decision"] == "RELINK", "Unedited Mesh did not default to Relink")
    check(bpy.ops.csvmi.apply_reviewed('EXEC_DEFAULT') == {'FINISHED'}, "Reviewed update failed")
    check(math.isclose(object_100.location.x, 10.0), "Blender Transform conflict was overwritten")
    check(math.isclose(object_200.location.x, 8.0), "CSV-only Transform was not applied")
    check(object_200.data == source_b.data, "CSV Mesh relink was not applied")

    check(bpy.ops.csvmi.preview_changes('EXEC_DEFAULT') == {'FINISHED'}, "Override Preview failed")
    check("100" not in preview_by_id(scene), "Resolved Transform override was repeatedly reported")

    object_100.data = object_100.data.copy()
    object_100["csvmi_linked_mesh"] = False
    rows[0]["objname"] = "AssetB"
    write_csv(csv_path, rows)
    check(bpy.ops.csvmi.import_csv('EXEC_DEFAULT') == {'FINISHED'}, "Mesh CSV import failed")
    check(bpy.ops.csvmi.preview_changes('EXEC_DEFAULT') == {'FINISHED'}, "Mesh Preview failed")
    mesh_change = preview_by_id(scene)["100"]
    check(mesh_change["mesh_kind"] == "CONFLICT" and mesh_change["mesh_decision"] == "KEEP", "Edited Mesh was not protected")
    edited_mesh = object_100.data
    check(bpy.ops.csvmi.apply_reviewed('EXEC_DEFAULT') == {'FINISHED'}, "Mesh protection Apply failed")
    check(object_100.data == edited_mesh, "Edited Mesh was overwritten")

    rule = props.attribute_filters.add()
    rule.attribute = "Zone"
    csvmi.sync_filter_rule_values(rule, csvmi.get_csv_cache(scene))
    for value in rule.values:
        value.selected = value.value == "1"
    rows[0]["tx"] = "50"
    rows[1]["tx"] = "80"
    write_csv(csv_path, rows)
    check(bpy.ops.csvmi.import_csv('EXEC_DEFAULT') == {'FINISHED'}, "Filter CSV import failed")
    check(bpy.ops.csvmi.preview_changes('EXEC_DEFAULT') == {'FINISHED'}, "Filter Preview failed")
    changes = preview_by_id(scene)
    check(changes["100"]["status"] == "FILTERED_OUT", "Zone 0 was not filtered out")
    check(changes["200"]["status"] != "FILTERED_OUT", "Zone 1 was unexpectedly filtered")
    check(bpy.ops.csvmi.apply_reviewed('EXEC_DEFAULT') == {'FINISHED'}, "Filtered Apply failed")
    check(not math.isclose(object_100.location.x, 50.0), "Filtered Zone 0 changed")
    check(math.isclose(object_200.location.x, 80.0), "Selected Zone 1 did not update")

    props.attribute_filters.clear()
    bpy.data.objects.remove(object_200, do_unlink=True)
    check(bpy.ops.csvmi.preview_changes('EXEC_DEFAULT') == {'FINISHED'}, "Delete Preview failed")
    deleted_change = preview_by_id(scene)["200"]
    check(deleted_change["status"] == "BLENDER_DELETED", "Blender standard Delete was not detected")
    check(bpy.ops.csvmi.apply_reviewed('EXEC_DEFAULT') == {'FINISHED'}, "Tombstone Apply failed")
    tombstone = managed_object(output, "200")
    check(tombstone is not None and tombstone.type == 'EMPTY', "Hidden Empty tombstone was not created")
    deleted_collection = next(child for child in output.children if child.get(csvmi.DELETED_COLLECTION_KEY))
    check(deleted_collection.hide_viewport and deleted_collection.hide_render, "Deleted Collection is visible")

    check(bpy.ops.csvmi.preview_changes('EXEC_DEFAULT') == {'FINISHED'}, "Restore Preview failed")
    restore_change = preview_by_id(scene)["200"]
    restore_change["object_decision"] = "RESTORE"
    check(bpy.ops.csvmi.apply_reviewed('EXEC_DEFAULT') == {'FINISHED'}, "Restore Apply failed")
    restored = managed_object(output, "200")
    check(restored.type == 'MESH' and restored.data == source_b.data, "Tombstone Restore failed")

    rows = [rows[0]]
    write_csv(csv_path, rows)
    check(bpy.ops.csvmi.import_csv('EXEC_DEFAULT') == {'FINISHED'}, "CSV deletion import failed")
    check(bpy.ops.csvmi.preview_changes('EXEC_DEFAULT') == {'FINISHED'}, "CSV deletion Preview failed")
    check(preview_by_id(scene)["200"]["status"] == "CSV_DELETED", "CSV deletion was not detected")
    check(bpy.ops.csvmi.apply_reviewed('EXEC_DEFAULT') == {'FINISHED'}, "CSV deletion Apply failed")
    csv_deleted_object = managed_object(output, "200")
    check(
        csv_deleted_object.type == 'EMPTY',
        f"CSV-deleted ID was not tombstoned: type={csv_deleted_object.type}, "
        f"data={getattr(csv_deleted_object.data, 'name', None)}, "
        f"collections={[collection.name for collection in csv_deleted_object.users_collection]}",
    )

    rows.append(row("200", "AssetB", 1, tx=80, weight="2", label="second"))
    write_csv(csv_path, rows)
    check(bpy.ops.csvmi.import_csv('EXEC_DEFAULT') == {'FINISHED'}, "Reappearing ID import failed")
    check(bpy.ops.csvmi.preview_changes('EXEC_DEFAULT') == {'FINISHED'}, "Reappearing ID Preview failed")
    check(preview_by_id(scene)["200"]["object_decision"] == "KEEP_DELETED", "Deleted ID was automatically restored")

    props.review_search = "200"
    csvmi.refresh_review_page(scene)
    check(all(item.identity == "200" for item in props.review_rows), "Change Review search failed")
    check(len(props.review_rows) <= csvmi.REVIEW_PAGE_SIZE, "Change Review pagination failed")

    state_before = csvmi.v2_engine.read_output_state(output, "id")
    text = bpy.data.texts[output[csvmi.OUTPUT_STATE_TEXT_KEY]]
    encoded = text.as_string()
    text.clear()
    text.write("corrupted")
    expect_error(lambda: csvmi.v2_engine.read_output_state(output, "id"), "corrupted")
    text.clear()
    text.write(encoded)
    check(csvmi.v2_engine.read_output_state(output, "id") == state_before, "State restoration fixture failed")

    legacy = bpy.data.collections.new("Legacy_Output")
    legacy[csvmi.OUTPUT_MANAGED_KEY] = True
    scene.collection.children.link(legacy)
    expect_error(lambda: csvmi.v2_engine.read_output_state(legacy, "id"), "not created")
    print("[PASS] v2 workflow")


def test_v2_ticks_and_cancel(temp_dir):
    print("[TEST] v2 bounded ticks and cancellation rollback")
    reset_data()
    scene = bpy.context.scene
    props = scene.csvmi_props
    source = bpy.data.collections.new("TickSources")
    scene.collection.children.link(source)
    make_object("TickAsset", make_mesh("TickMesh"), source)
    props.source_mode = 'COLLECTION'
    props.source_collection = source
    props.output_collection_name = "Tick_Output"
    props.split_by_attribute = False
    rows = [row(str(index), "TickAsset", 0, tx=index) for index in range(1000)]
    csv_path = temp_dir / "ticks.csv"
    write_csv(csv_path, rows)
    import_preview_apply(scene, csv_path)
    output = bpy.data.collections["Tick_Output"]
    state_before = csvmi.v2_engine.read_output_state(output, "id")
    location_before = managed_object(output, "0").location.x

    for record in rows:
        record["tx"] = str(float(record["tx"]) + 100.0)
    write_csv(csv_path, rows)
    check(bpy.ops.csvmi.import_csv('EXEC_DEFAULT') == {'FINISHED'}, "Tick import failed")
    check(bpy.ops.csvmi.preview_changes('EXEC_DEFAULT') == {'FINISHED'}, "Tick Preview failed")
    preview = csvmi.get_preview_cache(scene)
    cancel_task = csvmi.V2ApplyTask(scene, preview)
    cancel_task.step(0.001)
    cancel_task.request_cancel()
    while not cancel_task.step(0.001):
        pass
    cancel_task.finish_props()
    check(cancel_task.cancelled, "Cancellation did not finish as cancelled")
    check(csvmi.v2_engine.read_output_state(output, "id") == state_before, "Cancel changed the ID registry")
    check(math.isclose(managed_object(output, "0").location.x, location_before), "Cancel did not restore Transform")

    apply_task = csvmi.V2ApplyTask(scene, preview)
    while not apply_task.step(0.012):
        pass
    apply_task.finish_props()
    check(not apply_task.cancelled, "Ticked Apply was cancelled unexpectedly")
    check(apply_task.max_step_seconds < 0.060, f"Tick exceeded 60ms: {apply_task.max_step_seconds:.3f}s")
    check(math.isclose(managed_object(output, "0").location.x, 100.0), "Ticked Apply did not update Transform")
    check(props.use_multi_tick is False, "Test fixture unexpectedly changed the setting")
    print(f"[PASS] bounded ticks max={apply_task.max_step_seconds * 1000.0:.1f}ms")


def test_managed_output_cleanup(temp_dir):
    print("[TEST] v2 managed output clear and delete")
    reset_data()
    scene = bpy.context.scene
    props = scene.csvmi_props
    source = bpy.data.collections.new("CleanupSources")
    scene.collection.children.link(source)
    make_object("CleanupAsset", make_mesh("CleanupMesh"), source)
    props.source_collection = source
    props.output_collection_name = "Cleanup_Output"
    csv_path = temp_dir / "cleanup.csv"
    write_csv(csv_path, [row(str(index), "CleanupAsset", index % 2) for index in range(25)])
    import_preview_apply(scene, csv_path)
    output = bpy.data.collections["Cleanup_Output"]
    state_text_name = output[csvmi.OUTPUT_STATE_TEXT_KEY]
    check(
        bpy.ops.csvmi.clear_output('EXEC_DEFAULT', collection_name=output.name) == {'FINISHED'},
        "Managed Clear failed",
    )
    check(output.name in bpy.data.collections, "Clear removed the root Collection")
    check(len(csvmi.collect_collection_objects(output)) == 0 and len(output.children) == 0, "Clear left contents")
    check(csvmi.v2_engine.read_output_state(output, "id")["records"] == {}, "Clear did not reset state")
    check(state_text_name not in bpy.data.texts, "Clear left the previous state Text")

    check(bpy.ops.csvmi.preview_changes('EXEC_DEFAULT') == {'FINISHED'}, "Preview after Clear failed")
    check(bpy.ops.csvmi.apply_reviewed('EXEC_DEFAULT') == {'FINISHED'}, "Recreate after Clear failed")
    output = bpy.data.collections["Cleanup_Output"]
    state_text_name = output[csvmi.OUTPUT_STATE_TEXT_KEY]
    check(
        bpy.ops.csvmi.delete_output('EXEC_DEFAULT', collection_name=output.name) == {'FINISHED'},
        "Managed Delete failed",
    )
    check("Cleanup_Output" not in bpy.data.collections, "Delete left the root Collection")
    check(state_text_name not in bpy.data.texts, "Delete left the state Text")

    regular = bpy.data.collections.new("Regular")
    scene.collection.children.link(regular)
    expect_error(
        lambda: bpy.ops.csvmi.delete_output('EXEC_DEFAULT', collection_name=regular.name),
        "not managed",
    )
    print("[PASS] managed output cleanup")


def make_unique_actual_copy(source_path, destination, limit=0):
    with open(source_path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        if limit:
            rows = rows[:limit]
        fields = reader.fieldnames
    seen = set()
    replacement = -9_000_000
    for record in rows:
        identity = record["id"].strip()
        if identity in seen:
            while str(replacement) in seen:
                replacement -= 1
            record["id"] = str(replacement)
            identity = record["id"]
            replacement -= 1
        seen.add(identity)
    write_csv(destination, rows, fields)


def run_stress(temp_dir):
    source_csv = Path("/Users/taiyoparent/Downloads/StPr_map_PointData (3).csv")
    if not source_csv.exists():
        print("[SKIP] actual 60k CSV is unavailable")
        return
    print("[STRESS] corrected temporary copy of the 60,474-row actual CSV", flush=True)
    reset_data()
    scene = bpy.context.scene
    props = scene.csvmi_props
    corrected = temp_dir / "actual_unique_ids.csv"
    stress_limit = int(os.environ.get("CSVMI_STRESS_LIMIT", "0") or 0)
    for argument in sys.argv:
        if argument.startswith("--stress-limit="):
            stress_limit = int(argument.split("=", 1)[1])
    if "--profile" in sys.argv:
        os.environ["CSVMI_PROFILE"] = "1"
    make_unique_actual_copy(source_csv, corrected, stress_limit)
    parse_start = time.perf_counter()
    cache = csvmi.load_csv_data(str(corrected), "id")
    parse_seconds = time.perf_counter() - parse_start
    expected_count = stress_limit or 60474
    check(len(cache.rows) == expected_count, "Actual CSV corrected copy row count mismatch")
    print(f"[STRESS STAGE] parsed {len(cache.rows):,} rows in {parse_seconds:.2f}s", flush=True)

    source = bpy.data.collections.new("StressSources")
    scene.collection.children.link(source)
    shared_mesh = make_mesh("StressShared")
    for name in sorted(cache.unique_names):
        make_object(name, shared_mesh, source)
    print(f"[STRESS STAGE] created {len(cache.unique_names):,} source Objects", flush=True)
    props.source_mode = 'COLLECTION'
    props.source_collection = source
    props.csv_path = str(corrected)
    props.output_collection_name = "Stress_Output"
    props.split_by_attribute = True
    props.split_attribute = "Zone"
    props.use_multi_tick = False
    import_start = time.perf_counter()
    check(bpy.ops.csvmi.import_csv('EXEC_DEFAULT') == {'FINISHED'}, "Stress import failed")
    import_seconds = time.perf_counter() - import_start
    print(f"[STRESS STAGE] imported in {import_seconds:.2f}s", flush=True)
    preview_start = time.perf_counter()
    check(bpy.ops.csvmi.preview_changes('EXEC_DEFAULT') == {'FINISHED'}, "Stress Preview failed")
    preview_seconds = time.perf_counter() - preview_start
    print(f"[STRESS STAGE] previewed in {preview_seconds:.2f}s", flush=True)
    check(len(csvmi.get_preview_cache(scene).changes) == expected_count, "Stress Preview change count mismatch")
    apply_start = time.perf_counter()
    if "--ticks" in sys.argv:
        tick_task = csvmi.V2ApplyTask(scene, csvmi.get_preview_cache(scene))
        while not tick_task.step(csvmi.LARGE_TASK_TIME_BUDGET_SECONDS):
            tick_task.publish_progress()
        tick_task.finish_props()
        # The adaptive loop targets 12ms. Blender occasionally spends about
        # 100ms in one indivisible bpy.data.objects.new() ID-table resize; that
        # single API call cannot be split further, so guard against real freezes.
        check(
            tick_task.max_step_seconds < 0.200,
            f"60k tick exceeded 200ms: {tick_task.max_step_seconds:.3f}s in {tick_task.max_step_phase}; "
            f"max item {tick_task.max_item_seconds:.3f}s",
        )
    else:
        check(bpy.ops.csvmi.apply_reviewed('EXEC_DEFAULT') == {'FINISHED'}, "Stress Apply failed")
    apply_seconds = time.perf_counter() - apply_start
    print(f"[STRESS STAGE] applied in {apply_seconds:.2f}s", flush=True)
    output = bpy.data.collections["Stress_Output"]
    if "--lookup-profile" in sys.argv:
        state = csvmi.v2_engine.read_output_state(output, "id")
        lookup_start = time.perf_counter()
        lookup_objects = [
            bpy.data.objects.get(record.get("object_name", ""))
            for record in state["records"].values()
        ]
        lookup_seconds = time.perf_counter() - lookup_start
        global_start = time.perf_counter()
        global_objects = [obj for obj in bpy.data.objects if csvmi.OBJECT_ID_KEY in obj]
        global_seconds = time.perf_counter() - global_start
        collection_start = time.perf_counter()
        collection_objects = csvmi.collect_collection_objects(output)
        collection_seconds = time.perf_counter() - collection_start
        print(
            f"[LOOKUP PROFILE] names={lookup_seconds:.3f}s/{len(lookup_objects):,} "
            f"global={global_seconds:.3f}s/{len(global_objects):,} "
            f"collection={collection_seconds:.3f}s/{len(collection_objects):,}",
            flush=True,
        )
    check(len(csvmi.collect_collection_objects(output, mesh_only=True)) == expected_count, "Stress output count mismatch")
    no_change_start = time.perf_counter()
    check(bpy.ops.csvmi.preview_changes('EXEC_DEFAULT') == {'FINISHED'}, "Stress no-change Preview failed")
    no_change_seconds = time.perf_counter() - no_change_start
    check(len(csvmi.get_preview_cache(scene).changes) == 0, "Stress no-change table is not empty")
    print(
        "[STRESS RESULT] "
        f"parse={parse_seconds:.2f}s import={import_seconds:.2f}s preview={preview_seconds:.2f}s "
        f"apply={apply_seconds:.2f}s no_change={no_change_seconds:.2f}s max_tick={props.max_tick_ms:.1f}ms",
        flush=True,
    )
    if not stress_limit:
        check(import_seconds < 2.0, "CSV validation exceeded 2 seconds")
        check(preview_seconds < 3.0, "Initial Preview exceeded 3 seconds")
        check(apply_seconds < 15.0, "Initial Apply exceeded 15 seconds")
        check(no_change_seconds < 2.0, "No-change Preview exceeded 2 seconds")
    print("[PASS] stress")


def main():
    csvmi.register()
    try:
        check(bpy.context.scene.csvmi_props.use_multi_tick, "Split Across Multiple Ticks must default ON")
        with tempfile.TemporaryDirectory(prefix="csvmi_v2_test_") as directory:
            temp_dir = Path(directory)
            test_identity_validation(temp_dir)
            test_v2_workflow(temp_dir)
            test_v2_ticks_and_cancel(temp_dir)
            test_managed_output_cleanup(temp_dir)
            if "--stress" in sys.argv:
                run_stress(temp_dir)
        print("CSVMI_V2_TESTS_OK")
    finally:
        csvmi.unregister()


if __name__ == "__main__":
    main()
