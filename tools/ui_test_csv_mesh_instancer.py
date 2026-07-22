"""Prepare an unsaved Blender scene for manual CSV Mesh Instancer UI verification."""

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


csvmi.register()
scene = bpy.context.scene

source = bpy.data.collections.new("UI_Test_Source")
source.color_tag = 'COLOR_04'
scene.collection.children.link(source)

mesh_a = bpy.data.meshes.new("UI_Test_Mesh_A")
mesh_a.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
mesh_a.update()
object_a = bpy.data.objects.new("UI_Asset", mesh_a)
source.objects.link(object_a)

mesh_b = bpy.data.meshes.new("UI_Test_Mesh_B")
mesh_b.from_pydata([(0, 0, 0), (0, 1, 0), (0, 0, 1)], [], [(0, 1, 2)])
mesh_b.update()
object_b = bpy.data.objects.new("UI_Asset.001", mesh_b)
source.objects.link(object_b)

csv_path = Path(tempfile.gettempdir()) / "csvmi_ui_test.csv"
ui_row_count = option_int("--ui-rows", 2500)
with open(csv_path, "w", newline="", encoding="utf-8-sig") as handle:
    writer = csv.writer(handle)
    writer.writerow(["ptnum", "sx", "sy", "sz", "rx", "ry", "rz", "objname", "tx", "ty", "tz"])
    for index in range(ui_row_count):
        writer.writerow([index, 1, 1, 1, 0, 0, index % 360, "UI_Asset", index % 50, index // 50, 0])

props = scene.csvmi_props
props.csv_path = str(csv_path)
props.source_mode = 'COLLECTION'
props.source_collection = source
props.ignore_numeric_suffix = True
props.output_collection_name = "CSV_Output"
props.use_multi_tick = True
props.status = "UI test CSV is ready. Click Import CSV."

if "--ui-fbx" in sys.argv:
    props.source_mode = 'FBX'

if "--ui-running" in sys.argv:
    props.running = True
    props.active_operation = 'FBX_IMPORT'
    props.phase = "FBX import"
    props.status = "Importing FBX. Cancellation is applied after Blender finishes this step."

if "--ui-managed" in sys.argv:
    props.use_multi_tick = False
    bpy.ops.csvmi.import_csv('EXEC_DEFAULT')
    bpy.ops.csvmi.update('EXEC_DEFAULT')
    props.use_multi_tick = True
    secondary = bpy.data.collections.new("CSV_Secondary_Output")
    secondary.color_tag = 'COLOR_05'
    secondary[csvmi.OUTPUT_MANAGED_KEY] = True
    secondary.hide_viewport = True
    secondary.hide_render = True
    scene.collection.children.link(secondary)

if "--ui-auto-update" in sys.argv:
    props.use_multi_tick = True
    bpy.ops.csvmi.import_csv('EXEC_DEFAULT')
    ui_update_started = time.perf_counter()
    result = bpy.ops.csvmi.update('EXEC_DEFAULT')
    print(f"CSVMI_UI_UPDATE_STARTED rows={ui_row_count} result={result}", flush=True)

    def report_finished_update():
        if props.running:
            return 0.1
        elapsed = time.perf_counter() - ui_update_started
        publish_rate = props.ui_publish_count / max(0.001, props.process_seconds)
        print(
            "CSVMI_UI_UPDATE_DONE "
            f"rows={ui_row_count} wall={elapsed:.3f}s process={props.process_seconds:.3f}s "
            f"max_tick={props.max_tick_ms:.1f}ms publishes={props.ui_publish_count} "
            f"publish_rate={publish_rate:.2f}/s progress={props.progress:.3f}",
            flush=True,
        )
        return None

    bpy.app.timers.register(report_finished_update, first_interval=0.1)

for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        area.spaces.active.show_region_ui = True

print(f"CSVMI_UI_READY {csv_path} rows={ui_row_count}", flush=True)
