"""60k-object timing for Add Selected Objects, Select Meshes In Zone and Export Zone CSV.

blender --background --factory-startup --python-exit-code 1 --python tools/benchmark_map_roundtrip_add_objects.py
"""
import csv
import importlib
import json
from pathlib import Path
import sys
import tempfile
import time
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '_Taiyo_Blender_Extensions_Repo'))
mrt = importlib.import_module('map_roundtrip_tools')
from map_roundtrip_tools.zones import zone_empties, zone_name
mrt.register()
scene = bpy.context.scene
bpy.data.batch_remove(ids=list(bpy.data.objects))  # drop the default cube (it shares an origin with grid object 0)
p = scene.mrt_props
COLUMNS = ROWS = 245  # 60,025 objects on a 2 m grid
mesh = bpy.data.meshes.new('M')
collection = scene.collection
t = time.perf_counter()
objects = []
for i in range(COLUMNS * ROWS):
    ob = bpy.data.objects.new('Obj', mesh)
    ob.location = ((i % COLUMNS) * 2.0, (i // COLUMNS) * 2.0, 0.0)
    collection.objects.link(ob)
    objects.append(ob)
bpy.context.view_layer.update()
build_seconds = time.perf_counter() - t
half = COLUMNS // 2
chosen = [ob for i, ob in enumerate(objects) if i % COLUMNS < half]
bpy.ops.object.select_all(action='DESELECT')
for ob in chosen:
    ob.select_set(True)
p.zone_scope = 'SCENE'
assert bpy.ops.mrt.new_zone(name='ZONE_BIG') == {'FINISHED'}
p.merge_distance = 5.0
result = {'blender': bpy.app.version_string, 'objects': len(objects), 'selected': len(chosen), 'scene_build_seconds': round(build_seconds, 2)}


def timed(label, operator):
    t = time.perf_counter()
    assert operator() == {'FINISHED'}, p.status
    result[label + '_seconds'] = round(time.perf_counter() - t, 2)
    result[label + '_max_tick_seconds'] = round(p.max_tick, 3)
    result[label + '_status'] = p.status


timed('add_selected_objects', bpy.ops.mrt.add_objects_to_zone)
t = time.perf_counter()
bpy.context.view_layer.update()
result['depsgraph_update_after_add_seconds'] = round(time.perf_counter() - t, 2)
result['empties'] = sum(1 for e in zone_empties(scene, p.zone_prefix) if zone_name(e) == 'ZONE_BIG')
# Selection-independent check: the zone must contain exactly the chosen objects.
bpy.ops.object.select_all(action='DESELECT')
t = time.perf_counter()
assert bpy.ops.mrt.select_in_zone() == {'FINISHED'}
result['select_in_zone_seconds'] = round(time.perf_counter() - t, 2)
inside = {ob for ob in bpy.context.selected_objects}
result['zone_equals_selection'] = inside == set(chosen)
result['zone_missing'] = len(set(chosen) - inside)
result['zone_extra'] = len(inside - set(chosen))
assert result['zone_equals_selection'], (len(inside), len(chosen))
out = Path(tempfile.mkdtemp(prefix='mrt-bench-csv-'))
p.zone_csv_dir = str(out)
bpy.ops.object.select_all(action='DESELECT')
timed('export_zone_csv', bpy.ops.mrt.export_zone_csv)
with open(out / 'ZONE_BIG.csv', newline='') as stream:
    result['csv_rows'] = sum(1 for _ in csv.DictReader(stream))
assert result['csv_rows'] == len(chosen)
path = Path(tempfile.gettempdir()) / ('mrt_add_objects_benchmark_' + bpy.app.version_string.split()[0] + '.json')
path.write_text(json.dumps(result, indent=2))
print('ADD_OBJECTS_BENCHMARK', json.dumps(result, indent=2), flush=True)
mrt.unregister()
