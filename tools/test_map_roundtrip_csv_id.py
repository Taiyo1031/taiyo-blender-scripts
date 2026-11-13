"""CSV id handling: ub_csv_id on export, id -1 = new mesh, unknown ids are skipped on import.

blender --background --factory-startup --python-exit-code 1 --python tools/test_map_roundtrip_csv_id.py [-- import|export]  (import/export run only that side; no argument runs everything)
"""
import csv
import importlib
from pathlib import Path
import sys
import tempfile
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '_Taiyo_Blender_Extensions_Repo'))
mrt = importlib.import_module('map_roundtrip_tools')
from map_roundtrip_tools import placement
from map_roundtrip_tools.chunked import Cancelled
from map_roundtrip_tools.zone_csv import MRT_OT_ExportZoneCSV

TEMP = Path(tempfile.mkdtemp(prefix='mrt-csv-id-'))
mrt.register()
p = bpy.context.scene.mrt_props


def drain(generator):
    while True:
        try:
            next(generator)
        except StopIteration as done:
            return done.value


class Harness:
    def __init__(self):
        self._error = ''
        self.result = ''
        self.messages = []

    def progress(self, phase, done, total):
        self.phase = phase

    def report(self, level, text):
        self.messages.append(text)


def row(i, name, x=0.0, col=''):
    return [i, x, 0, 0, 0, 0, 0, 1, 1, 1, name, col]


def write_csv(path, rows):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(placement.CSV_COLUMNS)
        w.writerows(rows)


def fixture(old_ids):
    """Library: Rock/Tree (+ NewRock only as a mesh named in the CSV). Map holds old objects tagged ZONE_A."""
    bpy.data.batch_remove(ids=list(bpy.data.objects))
    bpy.data.batch_remove(ids=list(bpy.data.collections))
    lib = bpy.data.collections.new('Library')
    mapc = bpy.data.collections.new('Map')
    for c in (lib, mapc):
        bpy.context.scene.collection.children.link(c)
    meshes = {}
    for name in ('Rock', 'Tree', 'NewRock'):
        m = bpy.data.meshes.new(name + 'Mesh')
        m.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
        meshes[name] = m
        lib.objects.link(bpy.data.objects.new(name, m))
    olds = []
    for i, csv_id in enumerate(old_ids):
        o = bpy.data.objects.new(f'Rock.{i:03d}', meshes['Rock'])
        o.location = (i, 0, 0)
        o['ub_zone'] = 'ZONE_A'
        if csv_id is not None:
            o['ub_csv_id'] = csv_id
        mapc.objects.link(o)
        olds.append(o)
    p.library_coll, p.map_coll = lib, mapc
    p.placement_csv = str(TEMP / 'ZONE_A.csv')
    p.zone_override = ''
    p.dry_run = True
    p.name_mode = 'numeric_suffix'
    bpy.context.view_layer.update()
    return olds


def plan_for(rows):
    write_csv(p.placement_csv, rows)
    return drain(placement.build_plan(p))


def test_constants():
    from map_roundtrip_tools import constants
    assert constants.CSV_ID_KEY == 'ub_csv_id' and constants.NEW_MESH_ID == -1
    print('PASS constants')


def test_known_unknown_and_new_ids():
    fixture([1, 2, 3])
    plan = plan_for([row(1, 'Rock'), row(3, 'Rock', 3), row(99, 'Rock', 9), row(-1, 'NewRock', 5), row(-1, 'Rock', 6)])
    assert len(plan.rows) == 4, len(plan.rows)
    assert plan.unknown_id_rows == 1 and plan.added == 2
    assert plan.id_check is True
    assert plan.unmatched == set() and plan.missing_rows == 0
    placement.publish_plan(p, plan)
    # ids 1 and 3 update existing objects (1 unchanged, 3 moved), id 2 has no row (retired), the two -1 rows are new
    assert (p.plan_unchanged, p.plan_moved, p.plan_archive, p.plan_create) == (1, 1, 1, 2), (p.plan_unchanged, p.plan_moved, p.plan_archive, p.plan_create)
    assert p.plan_added == 2 and p.plan_unknown_id == 1 and p.plan_id_check
    print('PASS known / unknown / -1 ids')


def test_unknown_id_is_not_reported_as_missing_mesh():
    fixture([1])
    plan = plan_for([row(7, 'NotInLibrary'), row(-1, 'NotInLibrary')])
    assert plan.unknown_id_rows == 1 and plan.rows == []
    assert plan.missing_rows == 1 and plan.unmatched == {'NotInLibrary'} and plan.added == 0
    print('PASS unknown id skipped before mesh lookup; -1 without a Library mesh stays unmatched')


def test_zone_without_ub_csv_id_asks_for_a_new_export():
    fixture([None, None])
    write_csv(p.placement_csv, [row(1, 'Rock')])
    try:
        drain(placement.build_plan(p))
    except ValueError as exc:
        assert 'ub_csv_id' in str(exc) and 'Export Zone CSV' in str(exc), str(exc)
    else:
        raise AssertionError('a zone whose objects have no ub_csv_id must ask for a new export')
    # A zone without any object has nothing to match: every row is new.
    bpy.data.batch_remove(ids=[o for o in bpy.data.objects if o.get('ub_zone')])
    plan = plan_for([row(5, 'Rock'), row(-1, 'NewRock', 2)])
    assert plan.id_check is False and len(plan.rows) == 2 and plan.added == 1 and len(plan.adds) == 2
    print('PASS a zone without ub_csv_id needs a new export; an empty zone takes every row as new')


def test_invalid_ids():
    fixture([1])
    plan = plan_for([row('abc', 'Rock'), row('', 'Rock'), row('1.5', 'Rock'), row('1.0', 'Rock', 1), row('-1.0', 'NewRock', 2)])
    assert plan.invalid == 3, plan.invalid
    assert len(plan.rows) == 2 and plan.added == 1 and plan.unknown_id_rows == 0
    print('PASS non-numeric / non-integer ids are invalid; 1.0 and -1.0 parse')


def test_other_zone_ids_do_not_count():
    olds = fixture([1])
    other = bpy.data.objects.new('Other', olds[0].data)
    other['ub_zone'] = 'ZONE_B'
    other['ub_csv_id'] = 50
    p.map_coll.objects.link(other)
    plan = plan_for([row(50, 'Rock'), row(1, 'Rock')])
    assert plan.unknown_id_rows == 1 and len(plan.rows) == 1
    print('PASS only ids of the target zone count')


def test_replace_uses_only_valid_rows():
    fixture([1, 2])
    write_csv(p.placement_csv, [row(1, 'Rock', 1), row(42, 'Rock', 2), row(-1, 'NewRock', 3)])
    p.dry_run = False
    assert bpy.ops.mrt.replace_zone() == {'FINISHED'}
    created = [o for o in bpy.data.objects if o.get('ub_zone') == 'ZONE_A']
    assert len(created) == 2, len(created)
    assert sorted(round(o.location.x) for o in created) == [1, 3]
    assert 'unknown id 1' in p.status and 'new meshes 1' in p.status, p.status
    print('PASS Replace Zone creates only valid rows;', p.status)


def make_zone_with_objects(count):
    bpy.data.batch_remove(ids=list(bpy.data.objects))
    bpy.data.batch_remove(ids=list(bpy.data.collections))
    mesh = bpy.data.meshes.new('M')
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    objects = []
    for i in range(count):
        o = bpy.data.objects.new(f'Rock.{i:03d}', mesh)
        o.location = (i * 3.0, 0, 0)
        bpy.context.scene.collection.objects.link(o)
        objects.append(o)
    p.zone_scope = 'SCENE'
    p.zone_csv_dir = str(TEMP)
    assert bpy.ops.mrt.new_zone(name='ZONE_A') == {'FINISHED'}
    bpy.context.view_layer.update()
    bpy.ops.object.select_all(action='DESELECT')
    for o in objects:
        o.select_set(True)
    assert bpy.ops.mrt.add_objects_to_zone() == {'FINISHED'}
    bpy.ops.object.select_all(action='DESELECT')
    return objects


def test_export_writes_ub_csv_id():
    objects = make_zone_with_objects(3)
    assert bpy.ops.mrt.export_zone_csv() == {'FINISHED'}
    with open(TEMP / 'ZONE_A.csv') as f:
        rows = list(csv.DictReader(f))
    by_name = {r['objname']: int(r['id']) for r in rows}
    assert len(rows) == 3
    # The tag equals the id written in the CSV for that object (names lose their numeric suffix: use order).
    ids_in_csv = [int(r['id']) for r in rows]
    assert sorted(o['ub_csv_id'] for o in objects) == sorted(ids_in_csv) == [1, 2, 3], by_name
    xs = {round(float(r['tx'])): int(r['id']) for r in rows}
    for o in objects:
        assert o['ub_csv_id'] == xs[round(o.location.x)]
    print('PASS export writes ub_csv_id equal to the CSV id')
    return objects


def test_export_cancel_restores_ub_csv_id():
    objects = make_zone_with_objects(3)
    objects[0]['ub_csv_id'] = 77
    objects[0]['ub_zone'] = 'BEFORE'
    h = Harness()
    g = MRT_OT_ExportZoneCSV.work(h, bpy.context)
    while objects[0].get('ub_zone') == 'BEFORE':
        next(g)
    try:
        g.throw(Cancelled('Injected ESC'))
        drain(g)
    except Cancelled:
        pass
    assert objects[0]['ub_zone'] == 'BEFORE' and objects[0]['ub_csv_id'] == 77
    assert all('ub_csv_id' not in o for o in objects[1:])
    assert not list(TEMP.glob('.mrt-*.csv'))
    print('PASS cancel restores ub_zone and ub_csv_id')


def test_export_then_import_roundtrip():
    objects = make_zone_with_objects(3)
    assert bpy.ops.mrt.export_zone_csv() == {'FINISHED'}
    lib = bpy.data.collections.new('Library')
    mapc = bpy.data.collections.new('Map')
    for c in (lib, mapc):
        bpy.context.scene.collection.children.link(c)
    lib.objects.link(bpy.data.objects.new('Rock', objects[0].data))
    mapc.objects.link(bpy.data.objects.new('Placeholder', objects[0].data))
    p.library_coll, p.map_coll = lib, mapc
    p.placement_csv = str(TEMP / 'ZONE_A.csv')
    with open(p.placement_csv) as f:
        rows = list(csv.reader(f))
    header, body = rows[0], rows[1:]
    body.append(['-1', '10', '0', '0', '0', '0', '0', '1', '1', '1', 'Rock', ''])
    body.append(['999', '11', '0', '0', '0', '0', '0', '1', '1', '1', 'Rock', ''])
    del body[1]  # Houdini deleted one object: its id simply has no row
    with open(p.placement_csv, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(body)
    plan = drain(placement.build_plan(p))
    assert plan.id_check and plan.added == 1 and plan.unknown_id_rows == 1 and len(plan.rows) == 3
    print('PASS export -> Houdini edit -> import plan')


TESTS = (test_constants, test_known_unknown_and_new_ids, test_unknown_id_is_not_reported_as_missing_mesh,
         test_zone_without_ub_csv_id_asks_for_a_new_export, test_invalid_ids, test_other_zone_ids_do_not_count,
         test_replace_uses_only_valid_rows, test_export_writes_ub_csv_id,
         test_export_cancel_restores_ub_csv_id, test_export_then_import_roundtrip)
EXPORT = {'test_export_writes_ub_csv_id', 'test_export_cancel_restores_ub_csv_id'}
BOTH = {'test_export_then_import_roundtrip'}  # needs the import and the export change: only in the default run
# Optional selector after "--": "import" (placement only) or "export" (zone CSV only). Default: all.
mode = sys.argv[sys.argv.index('--') + 1] if '--' in sys.argv[:-1] else 'all'
for test in TESTS:
    name = test.__name__
    if mode != 'all' and (name in BOTH or (mode == 'import') == (name in EXPORT)):
        continue
    test()
mrt.unregister()
print('MRT_CSV_ID_PASSED', mode)
