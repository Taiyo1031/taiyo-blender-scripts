"""Import replaces the zone as a whole (0.10.0): the zone's original objects go to the archive, an earlier import is deleted,
every CSV row is placed. The CSV does not have to match the export.

blender --background --factory-startup --python-exit-code 1 --python tools/test_map_roundtrip_full_import.py
"""
import csv
import importlib
import json
from pathlib import Path
import sys
import tempfile
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '_Taiyo_Blender_Extensions_Repo'))
mrt = importlib.import_module('map_roundtrip_tools')
from map_roundtrip_tools import placement, placement_report, ui_common
from map_roundtrip_tools.zones import ensure_zone
mrt.register()
scene = bpy.context.scene
p = scene.mrt_props
TEMP = Path(tempfile.mkdtemp(prefix='mrt-full-'))


def make(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or scene.collection).children.link(c)
    return c


def row(x, name='NewRock', col='', use=1, i=-1):
    return [i, x, 0, 0, 0, 0, 0, 1, 1, 1, name, col, use]


def write_csv(rows, name='Return.csv'):
    path = TEMP / name
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow([*placement.CSV_COLUMNS, 'use'])
        w.writerows(rows)
    p.placement_csv = str(path)


def fixture(zone='Z'):
    bpy.data.batch_remove(ids=list(bpy.data.objects))
    bpy.data.batch_remove(ids=list(bpy.data.collections))
    for k in list(bpy.data.collections):
        bpy.data.collections.remove(k)
    meshes = {}
    for name in ('Rock', 'NewRock'):
        m = bpy.data.meshes.new(name + 'Mesh')
        m.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
        meshes[name] = m
    lib = make('Library')
    for name, m in meshes.items():
        lib.objects.link(bpy.data.objects.new(name, m))
    mapc = make('Map')
    sub = make('A', mapc)
    olds = []
    for i in range(3):
        o = bpy.data.objects.new(f'Rock.{i + 1:03d}', meshes['Rock'])
        o['ub_zone'] = zone
        o['ub_csv_id'] = i + 1
        o.location.x = 100 + i
        (sub if i == 2 else mapc).objects.link(o)
        olds.append(o)
    p.library_coll, p.map_coll, p.new_mesh_coll, p.archive_coll = lib, mapc, None, None
    ensure_zone(p, zone)
    p.zone_choice = zone
    p.name_mode = 'numeric_suffix'
    p.skip_bad_rows = False
    bpy.context.view_layer.update()
    return mapc, olds


def run(dry):
    p.dry_run = dry
    try:
        return bpy.ops.mrt.replace_zone()
    except RuntimeError:  # a cancelled operator raises with its message; p.status keeps the text
        return {'CANCELLED'}


def ok(dry):
    assert run(dry) == {'FINISHED'}, p.status


def zone_objects(zone='Z'):
    return [o for o in bpy.data.objects if o.get('ub_zone') == zone]


def archived(zone='Z'):
    return [o for o in bpy.data.objects if o.get('ub_archived_from') == zone]


def xs(objects):
    return sorted(round(o.location.x) for o in objects)


def in_map(mapc, ob):
    return any(ob in c.objects[:] for c in placement.walk_collections(mapc))


def test_first_import_archives_the_originals_and_places_every_row():
    mapc, olds = fixture()
    write_csv([row(10), row(11), row(12, 'Rock', 'A/B'), row(13, use=0)])  # none of the CSV rows has an id that matches the export
    ok(True)
    assert (p.plan_archive, p.plan_delete, p.plan_create, p.plan_unused_rows) == (3, 0, 3, 1), (p.plan_archive, p.plan_delete, p.plan_create, p.plan_unused_rows)
    assert not p.plan_block, p.plan_block
    ok(False)
    assert xs(zone_objects()) == [10, 11, 12], xs(zone_objects())
    assert sorted(o.name for o in archived()) == ['Rock.001', 'Rock.002', 'Rock.003'], [o.name for o in archived()]
    assert all(not in_map(mapc, o) and 'ub_zone' not in o for o in olds)
    assert placement.map_state('Z') == 'after'
    b = bpy.data.collections['B']
    assert any(o.location.x == 12 for o in b.objects) and b.name == 'B' and b in bpy.data.collections['A'].children[:]
    run_specs = {o.name: json.loads(o['ub_run']) for o in zone_objects()}
    assert all(s['before'] is None for s in run_specs.values())
    print('PASS the first import archives all originals and places every row (the CSV need not match the export)')


def test_second_import_deletes_the_earlier_import_and_keeps_the_archive():
    mapc, olds = fixture()
    write_csv([row(10), row(11), row(12)])
    ok(False)
    first = {o.name for o in zone_objects()}
    n_objects = len(bpy.data.objects)
    write_csv([row(20), row(21), row(22), row(23)])
    ok(True)
    assert (p.plan_archive, p.plan_delete, p.plan_create) == (0, 3, 4), (p.plan_archive, p.plan_delete, p.plan_create)
    ok(False)
    assert xs(zone_objects()) == [20, 21, 22, 23], xs(zone_objects())
    assert len(bpy.data.objects) == n_objects + 1, (len(bpy.data.objects), n_objects)  # 3 deleted, 4 made
    assert sorted(o.name for o in archived()) == ['Rock.001', 'Rock.002', 'Rock.003'], 'the archive is not touched'
    assert first <= {o.name for o in zone_objects()}, (first, {o.name for o in zone_objects()})  # no suffix drift: NewRock, NewRock.001, ...
    print('PASS a second import deletes the earlier import, leaves the archive alone and keeps the names')


def test_restore_import_again_and_reapply():
    mapc, olds = fixture()
    write_csv([row(10), row(11)])
    ok(False)
    assert bpy.ops.mrt.switch_map_state(target='BEFORE', zone='Z') == {'FINISHED'}, p.status
    assert xs(zone_objects()) == [100, 101, 102] and all(in_map(mapc, o) for o in olds), xs(zone_objects())
    assert placement.map_state('Z') == 'before'
    write_csv([row(30), row(31), row(32)])
    ok(True)  # importing while the original map is shown is allowed
    assert (p.plan_archive, p.plan_delete, p.plan_create) == (3, 2, 3), (p.plan_archive, p.plan_delete, p.plan_create)
    ok(False)
    assert xs(zone_objects()) == [30, 31, 32] and placement.map_state('Z') == 'after', xs(zone_objects())
    assert sorted(o.name for o in archived()) == ['Rock.001', 'Rock.002', 'Rock.003']
    assert bpy.ops.mrt.switch_map_state(target='BEFORE', zone='Z') == {'FINISHED'}, p.status
    assert xs(zone_objects()) == [100, 101, 102], xs(zone_objects())
    assert olds[2].users_collection == (bpy.data.collections['A'],), olds[2].users_collection
    assert bpy.ops.mrt.switch_map_state(target='AFTER', zone='Z') == {'FINISHED'}, p.status
    assert xs(zone_objects()) == [30, 31, 32], xs(zone_objects())
    print('PASS Restore Original Map, import again from the original map, Re-apply')


def test_a_row_without_a_library_mesh_blocks_the_import():
    mapc, olds = fixture()
    write_csv([row(10), row(11, 'NoSuchMesh'), row(12)])
    ok(True)
    assert p.plan_block and (p.plan_missing_rows, p.plan_create) == (1, 2), (p.plan_block, p.plan_missing_rows, p.plan_create)
    before = len(bpy.data.objects)
    assert run(False) != {'FINISHED'}
    assert len(bpy.data.objects) == before and xs(zone_objects()) == [100, 101, 102] and not archived()
    p.skip_bad_rows = True
    ok(True)
    assert not p.plan_block
    ok(False)
    assert xs(zone_objects()) == [10, 12] and len(archived()) == 3
    print('PASS rows that cannot be placed block the import unless they are skipped on purpose')


def test_empty_csv_and_all_zones_do_nothing():
    mapc, olds = fixture()
    write_csv([row(10, use=0)])
    ok(True)
    assert p.plan_block and p.plan_create == 0, p.plan_block
    assert run(False) != {'FINISHED'} and xs(zone_objects()) == [100, 101, 102]
    write_csv([row(10)])
    p.zone_choice = 'ALL'
    assert run(True) != {'FINISHED'}, 'All Zones cannot be imported'
    assert 'Choose the zone' in p.status, p.status
    p.zone_choice = 'Z'
    print('PASS a CSV that places nothing and All Zones never change the map')


def test_objects_of_a_0_6_to_0_9_replace_count_as_the_earlier_import():
    mapc, olds = fixture()
    legacy = bpy.data.objects.new('Legacy', olds[0].data)
    legacy['ub_zone'] = 'Z'
    legacy['ub_run'] = json.dumps({'zone': 'Z', 'before': None})
    mapc.objects.link(legacy)
    write_csv([row(10)])
    ok(True)
    assert (p.plan_archive, p.plan_delete) == (3, 1), (p.plan_archive, p.plan_delete)
    ok(False)
    assert 'Legacy' not in bpy.data.objects and xs(zone_objects()) == [10]
    print('PASS an object an older Replace created is deleted as part of the earlier import')


def test_failure_rolls_everything_back():
    mapc, olds = fixture()
    write_csv([row(10), row(11)])
    n_before = len(bpy.data.objects)
    real = placement.apply_absent
    calls = []

    def boom(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError('boom')
        return real(*args, **kwargs)
    placement.apply_absent = boom
    try:
        assert run(False) != {'FINISHED'}
    finally:
        placement.apply_absent = real
    assert xs(zone_objects()) == [100, 101, 102] and not archived(), xs(zone_objects())
    assert all(in_map(mapc, o) for o in olds) and len(bpy.data.objects) == n_before, (len(bpy.data.objects), n_before)
    assert bpy.data.collections.get('_Replaced_Z') is None or not bpy.data.collections['_Replaced_Z'].objects
    print('PASS a failure in the middle puts every original back and removes the new objects')


def test_two_zones_do_not_touch_each_other():
    mapc, olds = fixture('Z')
    other = bpy.data.objects.new('Other', olds[0].data)
    other['ub_zone'] = 'Y'
    mapc.objects.link(other)
    write_csv([row(10)])
    ok(False)
    assert other.get('ub_zone') == 'Y' and in_map(mapc, other)
    print('PASS an object of another zone is left alone')


def test_banner_and_collection_icons():
    mapc, olds = fixture()
    assert ui_common.shown_zone(p) == 'Z'
    p.zone_choice = 'Z'
    ui_common.invalidate_choice()
    mapc.color_tag = 'COLOR_04'
    assert ui_common.collection_icon(mapc) == 'COLLECTION_COLOR_04' and ui_common.collection_icon(None) == 'OUTLINER_COLLECTION'
    icons = bpy.types.UILayout.bl_rna.functions['prop'].parameters['icon'].enum_items.keys()
    assert all(f'COLLECTION_COLOR_0{n}' in icons for n in range(1, 9)), 'icon names'
    print('PASS the panel header knows the zone; collection fields use the collection color icons')


for test in (test_first_import_archives_the_originals_and_places_every_row, test_second_import_deletes_the_earlier_import_and_keeps_the_archive,
             test_restore_import_again_and_reapply, test_a_row_without_a_library_mesh_blocks_the_import, test_empty_csv_and_all_zones_do_nothing,
             test_objects_of_a_0_6_to_0_9_replace_count_as_the_earlier_import, test_failure_rolls_everything_back,
             test_two_zones_do_not_touch_each_other, test_banner_and_collection_icons):
    test()
mrt.unregister()
print('MRT_FULL_IMPORT_PASSED')
