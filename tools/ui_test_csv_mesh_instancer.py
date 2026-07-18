"""Prepare an unsaved Blender scene for manual CSV Mesh Instancer UI verification."""

import csv
import sys
import tempfile
from pathlib import Path

import bpy


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "_Taiyo_Blender_Extensions_Repo"))

import csv_mesh_instancer as csvmi  # noqa: E402


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
with open(csv_path, "w", newline="", encoding="utf-8-sig") as handle:
    writer = csv.writer(handle)
    writer.writerow(["ptnum", "sx", "sy", "sz", "rx", "ry", "rz", "objname", "tx", "ty", "tz"])
    for index in range(2500):
        writer.writerow([index, 1, 1, 1, 0, 0, index % 360, "UI_Asset", index % 50, index // 50, 0])

props = scene.csvmi_props
props.csv_path = str(csv_path)
props.source_mode = 'COLLECTION'
props.source_collection = source
props.ignore_numeric_suffix = True
props.output_collection_name = "CSV_Output"
props.use_multi_tick = True
props.status = "UI test CSV is ready. Click Import CSV."

if "--ui-running" in sys.argv:
    props.running = True
    props.active_operation = 'FBX_IMPORT'
    props.phase = "FBX import"
    props.status = "Importing FBX. Cancellation is applied after Blender finishes this step."

for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        area.spaces.active.show_region_ui = True

print(f"CSVMI_UI_READY {csv_path}", flush=True)
