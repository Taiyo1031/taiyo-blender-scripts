"""60k-object timing for the whole-zone Import (archive all originals, place every row), importing again, Restore Original Map and Re-apply.

blender --background --factory-startup --python-exit-code 1 --python tools/benchmark_map_roundtrip_diff.py [-- SIDE]

SIDE is the side of the object grid (default 245: 60,025 objects; the whole-zone import needs tens of minutes for that, mostly
to delete the 60k objects of the first import when importing again). Use e.g. `-- 45` (2,025 objects) for a quick check.
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
from map_roundtrip_tools import placement, restore
mrt.register()
scene = bpy.context.scene
bpy.data.batch_remove(ids=list(bpy.data.objects))
p = scene.mrt_props
COLUMNS = ROWS = int(sys.argv[sys.argv.index('--') + 1]) if '--' in sys.argv else 245
mesh = bpy.data.meshes.new('M')
lib = bpy.data.collections.new('Library')
scene.collection.children.link(lib)
lib.objects.link(bpy.data.objects.new('Obj', mesh))
mapc = bpy.data.collections.new('Map')
scene.collection.children.link(mapc)
objects = []
for i in range(COLUMNS * ROWS):
    ob = bpy.data.objects.new('Obj', mesh)
    ob.location = ((i % COLUMNS) * 2.0, (i // COLUMNS) * 2.0, 0.0)
    mapc.objects.link(ob)
    objects.append(ob)
bpy.context.view_layer.update()
p.library_coll, p.map_coll = lib, mapc
p.zone_scope = 'MAP'
assert bpy.ops.mrt.new_zone(name='ZONE_BIG') == {'FINISHED'}
p.merge_distance = 5.0
bpy.ops.object.select_all(action='DESELECT')
for ob in objects:
    ob.select_set(True)
assert bpy.ops.mrt.add_objects_to_zone() == {'FINISHED'}, p.status
out = Path(tempfile.mkdtemp(prefix='mrt-bench-diff-'))
p.zone_csv_dir = str(out)
assert bpy.ops.mrt.export_zone_csv() == {'FINISHED'}, p.status
rows = list(csv.reader(open(out / 'ZONE_BIG.csv', newline='')))
header, body = rows[0], rows[1:]
edited, kept, moved, removed = [], 0, 0, 0
for i, r in enumerate(body):
    if i % 6 == 0:
        removed += 1  # deleted in Houdini: the row stays, with use = 0
        edited.append([*r[:12], '0'])
        continue
    if i % 3 == 1:
        r[1] = str(float(r[1]) + 0.5)  # moved in Houdini
        if i % 2 == 0:
            r[11] = 'Area2'  # and half of them to another collection
        moved += 1
    else:
        kept += 1
    edited.append(r)
added = 10000 if COLUMNS == 245 else COLUMNS * ROWS // 6
for i in range(added):
    edited.append(['-1', str(i * 0.1), '500', '0', '0', '0', '0', '1', '1', '1', 'Obj', '', '1'])
with open(out / 'return.csv', 'w', newline='') as stream:
    w = csv.writer(stream)
    w.writerow([*header[:12], 'use'])
    w.writerows(edited)
p.placement_csv = str(out / 'return.csv')
assert p.zone_choice == 'ZONE_BIG', p.zone_choice  # new_zone selected it
result = {'blender': bpy.app.version_string, 'objects': len(objects), 'expected': {'archive': len(objects), 'place': kept + moved + added, 'rows_with_use_0': removed}}


class H:
    _error = ''
    _past_cancel = placement.MRT_OT_ReplaceZone._past_cancel

    def __init__(self):
        self.phase = 'Plan'

    def report(self, *args):
        pass

    def progress(self, phase, done, total):
        self.phase = phase


def timed(label, work):
    h = H()
    g = work(h)
    phases, longest, begin_all = {}, 0.0, time.perf_counter()
    while True:
        begin = time.perf_counter()
        phase = h.phase
        try:
            next(g)
        except StopIteration:
            elapsed = time.perf_counter() - begin  # the last step: final sync and clean-up
            phases['Last step'] = phases.get('Last step', 0) + elapsed
            longest = max(longest, elapsed)
            break
        elapsed = time.perf_counter() - begin
        phases[phase] = phases.get(phase, 0) + elapsed
        longest = max(longest, elapsed)
    result[label] = {'seconds': round(time.perf_counter() - begin_all, 2), 'max_step_seconds': round(longest, 3), 'phases': {k: round(v, 2) for k, v in phases.items()}, 'result': h.result}


p.dry_run = True
timed('preview', lambda h: placement.MRT_OT_ReplaceZone.work(h, bpy.context))
p.dry_run = False
timed('import', lambda h: placement.MRT_OT_ReplaceZone.work(h, bpy.context))
assert result['expected']['place'] == sum(1 for o in bpy.data.objects if o.get('ub_zone') == 'ZONE_BIG'), 'every row is placed'
timed('import_again', lambda h: placement.MRT_OT_ReplaceZone.work(h, bpy.context))  # deletes the first import, places the rows again
assert result['expected']['place'] == sum(1 for o in bpy.data.objects if o.get('ub_zone') == 'ZONE_BIG')


def with_target(h, target):
    h.target, h.zone = target, 'ZONE_BIG'
    return h


timed('restore_original', lambda h: restore.MRT_OT_SwitchMapState.work(with_target(h, 'BEFORE'), bpy.context))
timed('reapply_imported', lambda h: restore.MRT_OT_SwitchMapState.work(with_target(h, 'AFTER'), bpy.context))
path = Path(tempfile.gettempdir()) / 'mrt_diff_benchmark_4.5.9.json'
path.write_text(json.dumps(result, indent=2))
print('DIFF_BENCHMARK', json.dumps(result, indent=2), flush=True)
mrt.unregister()
