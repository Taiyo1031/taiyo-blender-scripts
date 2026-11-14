"""Zone CSV exports the zone's meshes, independent of the selection."""
import csv
import importlib
from pathlib import Path
import sys
import tempfile
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '_Taiyo_Blender_Extensions_Repo'))
mrt = importlib.import_module('map_roundtrip_tools')
mrt.register()
bpy.data.batch_remove(ids=list(bpy.data.objects))
bpy.data.batch_remove(ids=list(bpy.data.collections))
scene = bpy.context.scene
p = scene.mrt_props
p.zone_scope = 'SCENE'
out = Path(tempfile.mkdtemp(prefix='mrt-csv-'))
p.zone_csv_dir = str(out)


def cancelled(operator):
    """bpy.ops reports an operator error either as {'CANCELLED'} or as RuntimeError."""
    try:
        return operator() == {'CANCELLED'}
    except RuntimeError:
        return True


def zone_box(name, x, size=1.0):
    assert bpy.ops.mrt.add_zone_empty(zone_name=name) == {'FINISHED'}
    e = bpy.context.view_layer.objects.active
    e.location = (x, 0, 0)
    e.empty_display_size = size
    return e


zone_box('ZONE_A', 0)
zone_box('ZONE_B', 10)
overlap_a = zone_box('ZONE_A', 20)
overlap_b = zone_box('ZONE_B', 20)
mesh = bpy.data.meshes.new('M')


def mk(name, x):
    ob = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(ob)
    ob.location = (x, 0, 0)
    return ob


a1, a2 = mk('A1', .2), mk('A2.001', -.4)
b1 = mk('B1', 10.3)
out_of_zone = mk('Far', 100)
both = mk('Both', 20)
a2.hide_set(True)  # hidden objects are still exported
bpy.context.view_layer.update()


def rows(name):
    with open(out / (name + '.csv'), newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


# The selection must not matter: select only the far-away mesh.
bpy.ops.object.select_all(action='DESELECT')
out_of_zone.select_set(True)
p.zone_choice = 'ZONE_A'
assert bpy.ops.mrt.export_zone_csv() == {'FINISHED'}, p.status
names = sorted(r['objname'] for r in rows('ZONE_A'))
assert names == ['A1', 'A2', 'Both'], names  # numeric suffix normalized
assert a1['ub_zone'] == 'ZONE_A' and a2['ub_zone'] == 'ZONE_A' and both['ub_zone'] == 'ZONE_A'
assert 'ub_zone' not in out_of_zone and 'ub_zone' not in b1
assert list(rows('ZONE_A')[0]) == list(mrt.constants.CSV_COLUMNS)
assert 'left to' not in p.status  # no mesh of ZONE_A is owned by another zone

# ALL: one file per zone; a mesh in both zones goes to the first zone only.
for ob in (a1, a2, both):
    del ob['ub_zone']
p.zone_choice = 'ALL'
assert bpy.ops.mrt.export_zone_csv() == {'FINISHED'}, p.status
assert sorted(r['objname'] for r in rows('ZONE_A')) == ['A1', 'A2', 'Both']
assert sorted(r['objname'] for r in rows('ZONE_B')) == ['B1']
assert b1['ub_zone'] == 'ZONE_B' and both['ub_zone'] == 'ZONE_A'
assert 'ub_zone' not in out_of_zone

# One zone: the same ownership as All Zones. `Both` is inside ZONE_A and ZONE_B; ZONE_A (first by name) owns it.
for ob in (a1, a2, both, b1):
    if 'ub_zone' in ob:
        del ob['ub_zone']
p.zone_choice = 'ZONE_B'
assert bpy.ops.mrt.export_zone_csv() == {'FINISHED'}, p.status
assert sorted(r['objname'] for r in rows('ZONE_B')) == ['B1'], [r['objname'] for r in rows('ZONE_B')]
assert 'left to that zone' in p.status and '1 meshes' in p.status, p.status
assert b1['ub_zone'] == 'ZONE_B' and 'ub_zone' not in both
p.zone_choice = 'ZONE_A'
assert bpy.ops.mrt.export_zone_csv() == {'FINISHED'}, p.status
assert sorted(r['objname'] for r in rows('ZONE_A')) == ['A1', 'A2', 'Both']
assert both['ub_zone'] == 'ZONE_A'
# Exporting ZONE_B again never takes `Both` away from ZONE_A.
p.zone_choice = 'ZONE_B'
assert bpy.ops.mrt.export_zone_csv() == {'FINISHED'}, p.status
assert both['ub_zone'] == 'ZONE_A' and sorted(r['objname'] for r in rows('ZONE_B')) == ['B1']

# Failure keeps existing files and restores tags.
sentinel = (out / 'ZONE_A.csv').read_text()
for ob in (a1, a2, both, b1):
    del ob['ub_zone']
real_replace = mrt.zone_csv.os.replace


def boom(*args, **kwargs):
    raise OSError('simulated failure')


mrt.zone_csv.os.replace = boom
try:
    p.zone_choice = 'ZONE_A'
    assert cancelled(bpy.ops.mrt.export_zone_csv)
finally:
    mrt.zone_csv.os.replace = real_replace
assert (out / 'ZONE_A.csv').read_text() == sentinel
assert not any('ub_zone' in ob for ob in (a1, a2, both, b1, out_of_zone))
assert not list(out.glob('.mrt-*'))

# An empty zone is an error, not an empty file.
zone_box('ZONE_EMPTY', 500)
p.zone_choice = 'ZONE_EMPTY'
assert cancelled(bpy.ops.mrt.export_zone_csv)
assert not (out / 'ZONE_EMPTY.csv').exists()
assert not list(out.glob('.mrt-*'))
print('ZONE_CSV_TESTS_PASSED', flush=True)
mrt.unregister()
