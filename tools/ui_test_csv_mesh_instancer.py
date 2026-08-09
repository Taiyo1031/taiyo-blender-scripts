import importlib.util
import sys
import tempfile
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
ADDON_DIR = ROOT / "_Taiyo_Blender_Extensions_Repo" / "csv_mesh_instancer"


spec = importlib.util.spec_from_file_location(
    "csv_mesh_instancer",
    ADDON_DIR / "__init__.py",
    submodule_search_locations=[str(ADDON_DIR)],
)
csvmi = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = csvmi
spec.loader.exec_module(csvmi)
csvmi.register()


scene = bpy.context.scene
props = scene.csvmi_props
mesh = bpy.data.meshes.new("Piece")
mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
source = bpy.data.collections.new("CSVMI_FBX_UI_Source")
scene.collection.children.link(source)
source[csvmi.FBX_MANAGED_KEY] = True
obj = bpy.data.objects.new("Piece", mesh)
obj[csvmi.FBX_CANONICAL_OBJECT_KEY] = "Piece"
mesh[csvmi.FBX_CANONICAL_MESH_KEY] = "Piece"
source.objects.link(obj)
props.fbx_collection = source
props.fbx_collection_name = source.name
props.fbx_mesh_count = 1
csvmi.hide_source_collection(scene, source)


csv_path = Path(tempfile.gettempdir()) / "csvmi_v3_ui.csv"
csv_path.write_text(
    "objname,tx,ty,tz,rx,ry,rz,sx,sy,sz\n"
    "Piece,0,0,0,0,0,0,1,1,1\n",
    encoding="utf-8",
)
props.csv_path = str(csv_path)
assert bpy.ops.csvmi.import_csv('EXEC_DEFAULT') == {'FINISHED'}
props.fbx_path = str(Path(tempfile.gettempdir()) / "source.fbx")
props.output_collection_name = "CSV_UI_Output"
props.status = "Simple v3 UI with fast FBX and CSV Output visibility."


if "--ui-place" in sys.argv:
    props.use_multi_tick = False
    assert bpy.ops.csvmi.place('EXEC_DEFAULT') == {'FINISHED'}
    props.use_multi_tick = True


for window in bpy.context.window_manager.windows:
    for area in window.screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces.active.show_region_ui = True
            area.tag_redraw()


print("CSVMI_V3_UI_READY", flush=True)
