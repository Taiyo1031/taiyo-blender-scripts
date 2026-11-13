"""colname as a collection path: export writes it, Replace Zone restores the hierarchy.

blender --background --factory-startup --python-exit-code 1 --python tools/test_map_roundtrip_colname_path.py
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

TEMP = Path(tempfile.mkdtemp(prefix='mrt-colname-'))
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


def clear():
    bpy.data.batch_remove(ids=list(bpy.data.objects))
    bpy.data.batch_remove(ids=list(bpy.data.collections))
    p.library_coll = None
    p.map_coll = None


def make(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(c)
    return c


def mesh_object(name, collection, x, mesh):
    o = bpy.data.objects.new(name, mesh)
    o.location = (x, 0, 0)
    collection.objects.link(o)
    return o


def new_mesh():
    m = bpy.data.meshes.new('M')
    m.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    return m


def write_csv(path, rows):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(placement.CSV_COLUMNS)
        w.writerows(rows)


def row(i, x, col, name='Rock'):
    return [i, x, 0, 0, 0, 0, 0, 1, 1, 1, name, col]


def export_colnames(set_map):
    """Scene with objects in assorted collections; returns {x: colname} read back from the exported CSV."""
    clear()
    mesh = new_mesh()
    mapc = make('Map')
    area = make('Area1', mapc)
    rocks = make('Rocks', area)
    other = make('Other')
    deep = make('Deep', other)
    odd = make('Odd/Name', mapc)
    spots = [(mapc, 0), (area, 3), (rocks, 6), (deep, 9), (bpy.context.scene.collection, 12), (odd, 15)]
    objects = [mesh_object(f'Rock.{i:03d}', c, x, mesh) for i, (c, x) in enumerate(spots)]
    p.map_coll = mapc if set_map else None
    p.zone_scope = 'SCENE'
    p.zone_csv_dir = str(TEMP)
    assert bpy.ops.mrt.new_zone(name='ZONE_A') == {'FINISHED'}
    bpy.context.view_layer.update()
    bpy.ops.object.select_all(action='DESELECT')
    for o in objects:
        o.select_set(True)
    assert bpy.ops.mrt.add_objects_to_zone() == {'FINISHED'}
    bpy.ops.object.select_all(action='DESELECT')
    assert bpy.ops.mrt.export_zone_csv() == {'FINISHED'}
    with open(TEMP / 'ZONE_A.csv') as f:
        return {round(float(r['tx'])): r['colname'] for r in csv.DictReader(f)}


def test_export_path_relative_to_map():
    got = export_colnames(True)
    assert got == {0: '', 3: 'Area1', 6: 'Area1/Rocks', 9: 'Other/Deep', 12: '', 15: 'Odd/Name'}, got
    print('PASS export: path relative to Map; outside Map from the scene root; "/" in a name falls back to the name')


def test_export_path_without_map():
    got = export_colnames(False)
    assert got == {0: 'Map', 3: 'Map/Area1', 6: 'Map/Area1/Rocks', 9: 'Other/Deep', 12: '', 15: 'Odd/Name'}, got
    print('PASS export: no Map collection set -> path from the scene root')


def import_fixture():
    clear()
    mesh = new_mesh()
    lib = make('Library')
    lib.objects.link(bpy.data.objects.new('Rock', mesh))
    mapc = make('Map')
    area = make('Area1', mapc)
    rocks = make('Rocks', area)
    legacy = make('Legacy', mapc)
    outside = make('Outside')
    p.library_coll, p.map_coll = lib, mapc
    p.placement_csv = str(TEMP / 'ZONE_A.csv')
    p.zone_override = 'ZONE_X'
    p.dry_run = True
    p.name_mode = 'numeric_suffix'
    bpy.context.view_layer.update()
    return mapc, area, rocks, legacy, outside


def test_resolution():
    mapc, area, rocks, legacy, outside = import_fixture()
    cols = ['', 'Area1/Rocks', 'Area1/Trees', 'New1/New2', 'Legacy', 'Fresh', 'Rocks', 'A//B', 'Map/Area1/Rocks']
    write_csv(p.placement_csv, [row(i, i, c) for i, c in enumerate(cols)])
    plan = drain(placement.build_plan(p))
    assert len(plan.rows) == len(cols)
    assert {'/'.join(path) for path in plan.new_collections} == {'Area1/Trees', 'New1', 'New1/New2', 'Fresh', 'A//B'}, plan.new_collections
    assert plan.collections['Area1/Rocks'] == rocks and plan.collections['Rocks'] == rocks
    assert plan.collections['Legacy'] == legacy and plan.collections['Map/Area1/Rocks'] == rocks
    placement.publish_plan(p, plan)
    assert p.plan_collections == 5
    print('PASS resolution: existing path / new path with intermediates / legacy name / literal "//" name')


def test_replace_builds_hierarchy():
    mapc, area, rocks, legacy, outside = import_fixture()
    cols = ['', 'Area1/Rocks', 'Area1/Trees', 'New1/New2', 'Legacy', 'Fresh']
    write_csv(p.placement_csv, [row(i, i, c) for i, c in enumerate(cols)])
    p.dry_run = False
    before = set(bpy.data.collections)
    assert bpy.ops.mrt.replace_zone() == {'FINISHED'}
    trees, new1, new2, fresh = (bpy.data.collections[n] for n in ('Trees', 'New1', 'New2', 'Fresh'))
    assert trees in area.children[:] and new1 in mapc.children[:] and new2 in new1.children[:] and fresh in mapc.children[:]
    assert {c.name for c in set(bpy.data.collections) - before} == {'Trees', 'New1', 'New2', 'Fresh', '_Replaced_ZONE_X'}
    where = {round(o.location.x): o.users_collection[0] for o in bpy.data.objects if o.get('ub_zone') == 'ZONE_X'}
    assert where == {0: mapc, 1: rocks, 2: trees, 3: new2, 4: legacy, 5: fresh}, where
    print('PASS Replace Zone creates the nested collections and places each object in its collection')


def test_name_conflict_is_reported():
    mapc, area, rocks, legacy, outside = import_fixture()
    write_csv(p.placement_csv, [row(0, 0, 'Area1/Outside')])
    plan = drain(placement.build_plan(p))
    assert plan.name_conflicts == {'Area1/Outside'}, plan.name_conflicts
    p.dry_run = False
    h = Harness()
    drain(placement.MRT_OT_ReplaceZone.work(h, bpy.context))
    created = bpy.data.collections.get('Outside.001')
    assert created is not None and created in area.children[:] and outside.children[:] == []
    assert any('Outside' in m for m in h.messages), h.messages
    print('PASS a collection name already used elsewhere is reported, not hidden')


def test_rollback_removes_new_collections():
    for exception in (Cancelled('Injected ESC'), RuntimeError('Injected failure')):
        mapc, area, rocks, legacy, outside = import_fixture()
        write_csv(p.placement_csv, [row(0, 0, 'New1/New2'), row(1, 1, 'Area1/Trees')])
        p.dry_run = False
        before = set(bpy.data.objects), set(bpy.data.collections)
        h = Harness()
        g = placement.MRT_OT_ReplaceZone.work(h, bpy.context)
        while getattr(h, 'phase', '') != 'Creating linked instances':
            next(g)
        try:
            g.throw(exception)
            drain(g)
        except (Cancelled, RuntimeError):
            pass
        assert before == (set(bpy.data.objects), set(bpy.data.collections))
        assert area.children[:] == [rocks] and mapc.children[:] == [area, legacy]
    print('PASS ESC / exception remove the new nested collections and leave the old tree intact')


def test_export_then_restore_hierarchy():
    export_colnames(True)
    mapc = bpy.data.collections['Map']
    olds = [o for o in bpy.data.objects if o.get('ub_zone') == 'ZONE_A']
    lib = make('Library')
    lib.objects.link(bpy.data.objects.new('Rock', olds[0].data))
    for name in ('Rocks', 'Area1'):
        bpy.data.collections.remove(bpy.data.collections[name])  # the nested tree is gone
    p.library_coll, p.map_coll = lib, mapc
    p.placement_csv = str(TEMP / 'ZONE_A.csv')
    p.zone_override = ''
    p.dry_run = False
    assert bpy.ops.mrt.replace_zone() == {'FINISHED'}
    new = [o for o in bpy.data.objects if o.get('ub_zone') == 'ZONE_A']
    assert len(new) == 6
    area = bpy.data.collections['Area1']
    rocks = bpy.data.collections['Rocks']
    assert area in mapc.children[:] and rocks in area.children[:]
    where = {round(o.location.x): o.users_collection[0].name for o in new}
    # The same objects were relinked (nothing was recreated); the ones outside Map did not move at all.
    assert set(new) == set(olds)
    assert where[3] == 'Area1' and where[6] == 'Rocks' and where[0] == 'Map' and where[15] == 'Odd/Name' and where[9] == 'Deep', where
    assert where[12] == 'Scene Collection', where
    assert 'Other.001' not in bpy.data.collections, [c.name for c in bpy.data.collections]
    print('PASS export -> restore: the Map hierarchy comes back by relinking the same objects')


def test_houdini_edits_moved_removed_and_added():
    """What comes back from Houdini: moved row = moved in place, missing row = retired, id -1 = added mesh."""
    mapc, area, rocks, legacy, outside = import_fixture()
    from_houdini = make('FromHoudini', bpy.data.collections['Library'])
    new_rock_mesh = new_mesh()
    from_houdini.objects.link(bpy.data.objects.new('NewRock', new_rock_mesh))
    olds = []
    for i, csv_id in enumerate((1, 2)):  # exported ids 1 and 2
        o = bpy.data.objects.new(f'Rock.{i:03d}', bpy.data.objects['Rock'].data)
        o.location = (i * 10, 0, 0)
        o['ub_zone'] = 'ZONE_X'
        o['ub_csv_id'] = csv_id
        o['keep_me'] = 'custom property'
        area.objects.link(o)
        olds.append(o)
    # Houdini: id 1 moved to x=100, id 2 deleted (no row), a new mesh added (-1) under a new path, id 99 is unknown.
    write_csv(p.placement_csv, [row(1, 100, 'Area1'), row(-1, 200, 'Area2/NewRocks', 'NewRock'), row(99, 300, 'Area1')])
    p.dry_run = False
    assert bpy.ops.mrt.replace_zone() == {'FINISHED'}
    assert tuple(olds[0].location) == (100, 0, 0) and olds[0]['keep_me'] == 'custom property'  # moved in place, properties kept
    assert olds[0].users_collection == (area,) and olds[0].get('ub_zone') == 'ZONE_X'
    new = [o for o in bpy.data.objects if o.get('ub_zone') == 'ZONE_X' and o not in olds]
    assert len(new) == 1 and round(new[0].location.x) == 200 and new[0].data == new_rock_mesh  # id 99 was not used
    area2, new_rocks = bpy.data.collections['Area2'], bpy.data.collections['NewRocks']
    assert area2 in mapc.children[:] and new_rocks in area2.children[:] and new[0].users_collection == (new_rocks,)
    archive = bpy.context.scene.collection.children['_Replaced_ZONE_X']
    retired = archive.children['Area1 [ZONE_X]']  # same hierarchy as the original, as a mirror
    assert olds[1].users_collection == (retired,) and 'ub_zone' not in olds[1] and olds[1]['keep_me'] == 'custom property'
    assert 'moved 1' in p.status and 'retired 1' in p.status and 'added 1' in p.status and 'unknown id 1' in p.status, p.status
    print('PASS Houdini edits: moved in place, removed -> retired with hierarchy, id -1 + colname path -> nested collection')


for test in (test_export_path_relative_to_map, test_export_path_without_map, test_resolution,
             test_replace_builds_hierarchy, test_name_conflict_is_reported,
             test_rollback_removes_new_collections, test_export_then_restore_hierarchy,
             test_houdini_edits_moved_removed_and_added):
    test()
mrt.unregister()
print('MRT_COLNAME_PATH_PASSED')
