"""Prepare an unsaved Blender scene for CSV Mesh Instancer v2 UI verification."""

import csv
import sys
import tempfile
import time
from pathlib import Path

import bpy


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "_Taiyo_Blender_Extensions_Repo"))

import csv_mesh_instancer as csvmi  # noqa: E402


def option_int(name, default):
    if name not in sys.argv:
        return default
    return int(sys.argv[sys.argv.index(name) + 1])


def write_fixture(path, row_count, changed=False):
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "ptnum", "Zone", "sx", "sy", "sz", "rx", "ry", "rz",
            "objname", "id", "tx", "ty", "tz", "category", "enabled",
        ])
        for index in range(row_count):
            tx = index % 50
            rz = index % 360
            objname = "UI_Asset"
            category = "Architecture" if index % 2 else "Furniture"
            if changed and index < 30:
                tx += 10
            if changed and 30 <= index < 40:
                objname = "UI_Asset.001"
            if changed and 40 <= index < 50:
                category = "Cleanup"
            writer.writerow([
                index, index % 2, 1, 1, 1, 0, 0, rz, objname, index,
                tx, index // 50, 0, category, index % 3 != 0,
            ])


csvmi.register()
scene = bpy.context.scene

source = bpy.data.collections.new("UI_Test_Source")
source.color_tag = 'COLOR_04'
scene.collection.children.link(source)

mesh_a = bpy.data.meshes.new("UI_Test_Mesh_A")
mesh_a.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
mesh_a.update()
source.objects.link(bpy.data.objects.new("UI_Asset", mesh_a))

mesh_b = bpy.data.meshes.new("UI_Test_Mesh_B")
mesh_b.from_pydata([(0, 0, 0), (0, 1, 0), (0, 0, 1)], [], [(0, 1, 2)])
mesh_b.update()
source.objects.link(bpy.data.objects.new("UI_Asset.001", mesh_b))

csv_path = Path(tempfile.gettempdir()) / "csvmi_v2_ui_test.csv"
ui_row_count = option_int("--ui-rows", 2500)
write_fixture(csv_path, ui_row_count)

props = scene.csvmi_props
props.csv_path = str(csv_path)
props.identity_column = "id"
props.source_mode = 'COLLECTION'
props.source_collection = source
props.ignore_numeric_suffix = True
props.output_collection_name = "CSV_Output_v2"
props.split_by_attribute = True
props.split_attribute = "Zone"
props.use_multi_tick = True
props.status = "Version 2 UI fixture is ready. Click Import CSV."

if "--ui-fbx" in sys.argv:
    props.source_mode = 'FBX'

if "--ui-running" in sys.argv:
    props.running = True
    props.active_operation = 'FBX_IMPORT'
    props.phase = "FBX import"
    props.status = "Importing FBX. Cancellation is applied after Blender finishes this step."


def initial_apply():
    props.use_multi_tick = False
    assert bpy.ops.csvmi.import_csv('EXEC_DEFAULT') == {'FINISHED'}
    for attribute in props.csv_attributes:
        attribute.enabled = attribute.name in {"category", "enabled"}
    assert bpy.ops.csvmi.preview_changes('EXEC_DEFAULT') == {'FINISHED'}
    assert bpy.ops.csvmi.apply_reviewed('EXEC_DEFAULT') == {'FINISHED'}


if "--ui-managed" in sys.argv or "--ui-review" in sys.argv:
    initial_apply()
    secondary = bpy.data.collections.new("CSV_Secondary_Output_v2")
    secondary.color_tag = 'COLOR_05'
    secondary[csvmi.OUTPUT_MANAGED_KEY] = True
    secondary[csvmi.OUTPUT_SCHEMA_KEY] = csvmi.OUTPUT_SCHEMA_VERSION
    secondary.hide_viewport = True
    secondary.hide_render = True
    scene.collection.children.link(secondary)
    csvmi.v2_engine.write_output_state(
        secondary,
        {"schema": 2, "id_column": "id", "records": {}},
    )

if "--ui-review" in sys.argv:
    output = bpy.data.collections["CSV_Output_v2"]
    object_five = next(
        obj for obj in csvmi.collect_collection_objects(output)
        if str(obj.get(csvmi.OBJECT_ID_KEY, "")) == "5"
    )
    object_five.location.x += 3.0
    object_twenty = next(
        obj for obj in csvmi.collect_collection_objects(output)
        if str(obj.get(csvmi.OBJECT_ID_KEY, "")) == "20"
    )
    bpy.data.objects.remove(object_twenty, do_unlink=True)
    write_fixture(csv_path, ui_row_count, changed=True)
    assert bpy.ops.csvmi.import_csv('EXEC_DEFAULT') == {'FINISHED'}
    assert bpy.ops.csvmi.preview_changes('EXEC_DEFAULT') == {'FINISHED'}
    props.show_preview = True
    props.review_search = ""
    props.status = "Change Review fixture: CSV, Blender, conflict, mesh, props, and delete changes."
    props.use_multi_tick = True

if "--ui-auto-update" in sys.argv:
    props.use_multi_tick = True
    assert bpy.ops.csvmi.import_csv('EXEC_DEFAULT') == {'FINISHED'}
    assert bpy.ops.csvmi.preview_changes('EXEC_DEFAULT') == {'FINISHED'}
    ui_update_started = time.perf_counter()
    result = bpy.ops.csvmi.apply_reviewed('EXEC_DEFAULT')
    print(f"CSVMI_UI_APPLY_STARTED rows={ui_row_count} result={result}", flush=True)

    def report_finished_update():
        if props.running:
            return 0.1
        elapsed = time.perf_counter() - ui_update_started
        publish_rate = props.ui_publish_count / max(0.001, props.process_seconds)
        print(
            "CSVMI_UI_APPLY_DONE "
            f"rows={ui_row_count} wall={elapsed:.3f}s process={props.process_seconds:.3f}s "
            f"max_tick={props.max_tick_ms:.1f}ms publishes={props.ui_publish_count} "
            f"publish_rate={publish_rate:.2f}/s progress={props.progress:.3f}",
            flush=True,
        )
        return None

    bpy.app.timers.register(report_finished_update, first_interval=0.1)

if bpy.context.screen is not None:
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces.active.show_region_ui = True

print(f"CSVMI_V2_UI_READY {csv_path} rows={ui_row_count}", flush=True)
