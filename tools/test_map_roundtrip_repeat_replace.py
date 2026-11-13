"""Replace Zone repeated with the same CSV: id -1 rows must not create their objects again, and a collection
created with a suffix (UNI.001, because UNI is used elsewhere) must still match the colname UNI.

blender --background --factory-startup --python-exit-code 1 --python tools/test_map_roundtrip_repeat_replace.py
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
from map_roundtrip_tools import placement, placement_report
mrt.register()
scene = bpy.context.scene
p = scene.mrt_props
TEMP = Path(tempfile.mkdtemp(prefix='mrt-repeat-'))


def make(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or scene.collection).children.link(c)
    return c


def row(i, x, name='NewRock', col='', use=1):
    return [i, x, 0, 0, 0, 0, 0, 1, 1, 1, name, col, use]


def write_csv(rows):
    path = TEMP / 'Z.csv'
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow([*placement.CSV_COLUMNS, 'use'])
        w.writerows(rows)
    p.placement_csv = str(path)


def fixture():
    bpy.data.batch_remove(ids=list(bpy.data.objects))
    bpy.data.batch_remove(ids=list(bpy.data.collections))
    meshes = {}
    for name in ('Rock', 'NewRock'):
        m = bpy.data.meshes.new(name + 'Mesh')
        m.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
        meshes[name] = m
    lib = make('Library')
    for name, m in meshes.items():
        lib.objects.link(bpy.data.objects.new(name, m))
    mapc = make('Map')
    olds = {}
    for csv_id in (1, 2):
        o = bpy.data.objects.new(f'Rock.{csv_id:03d}', meshes['Rock'])
        o['ub_zone'] = 'Z'
        o['ub_csv_id'] = csv_id
        mapc.objects.link(o)
        olds[csv_id] = o
    p.library_coll, p.map_coll, p.new_mesh_coll, p.archive_coll = lib, mapc, None, None
    p.zone_override = 'Z'
    p.name_mode = 'numeric_suffix'
    bpy.context.view_layer.update()
    return mapc, olds


def run(dry):
    p.dry_run = dry
    assert bpy.ops.mrt.replace_zone() == {'FINISHED'}, p.status


def zone_objects():
    return [o for o in bpy.data.objects if o.get('ub_zone') == 'Z']


def xs(objects):
    return sorted(round(o.location.x) for o in objects)


def test_repeat_replace_does_not_duplicate_new_objects():
    mapc, olds = fixture()
    write_csv([row(1, 0, 'Rock'), row(2, 0, 'Rock'), row(-1, 10), row(-1, 20), row(-1, 30)])
    run(False)
    assert len(zone_objects()) == 5, len(zone_objects())
    run(True)  # the same CSV again
    assert (p.plan_create, p.plan_moved, p.plan_archive, p.plan_unchanged) == (0, 0, 0, 5), \
        (p.plan_create, p.plan_moved, p.plan_archive, p.plan_unchanged)
    run(False)
    assert len(zone_objects()) == 5 and xs(zone_objects()) == [0, 0, 10, 20, 30], xs(zone_objects())
    # Houdini changed one of the new objects and dropped another one.
    write_csv([row(1, 0, 'Rock'), row(2, 0, 'Rock'), row(-1, 10), row(-1, 25)])
    run(True)
    assert (p.plan_create, p.plan_moved, p.plan_archive) == (0, 1, 0), (p.plan_create, p.plan_moved, p.plan_archive)
    assert 'unmatched_added' in {i.kind for i in placement_report.LAST_ISSUES}, [i.kind for i in placement_report.LAST_ISSUES]
    run(False)
    assert len(zone_objects()) == 5 and xs(zone_objects()) == [0, 0, 10, 25, 30], xs(zone_objects())
    print('PASS repeating Replace with the same CSV does not add the id -1 objects again; changed ones are updated')


def test_repeat_replace_then_restore_and_reapply():
    mapc, olds = fixture()
    write_csv([row(1, 0, 'Rock'), row(2, 0, 'Rock'), row(-1, 10), row(-1, 20)])
    run(False)
    write_csv([row(1, 0, 'Rock'), row(2, 0, 'Rock'), row(-1, 11), row(-1, 20)])
    run(False)
    assert xs(zone_objects()) == [0, 0, 11, 20], xs(zone_objects())
    assert bpy.ops.mrt.switch_map_state(target='BEFORE', zone='Z') == {'FINISHED'}, p.status
    assert xs(zone_objects()) == [0, 0], xs(zone_objects())
    assert bpy.ops.mrt.switch_map_state(target='AFTER', zone='Z') == {'FINISHED'}, p.status
    assert xs(zone_objects()) == [0, 0, 11, 20], xs(zone_objects())
    print('PASS repeat Replace, Restore Original Map and Re-apply keep the same objects')


def test_suffixed_collection_matches_its_colname():
    mapc, olds = fixture()
    make('UNI')  # the name is used outside the Map, so the new collection becomes UNI.001
    write_csv([row(1, 0, 'Rock', 'UNI'), row(2, 0, 'Rock')])
    run(False)
    created = bpy.data.collections.get('UNI.001')
    assert created is not None and created in mapc.children[:] and olds[1].users_collection == (created,)
    run(True)
    assert p.plan_moved == 0 and p.plan_collections == 0 and p.plan_unchanged == 2, \
        (p.plan_moved, p.plan_collections, p.plan_unchanged)
    parents, roots = placement.build_parent_index(mapc)
    assert placement.collection_colname(created, mapc, parents, roots) == 'UNI'
    run(False)
    assert 'UNI.002' not in bpy.data.collections and olds[1].users_collection == (created,)
    print('PASS a collection created as UNI.001 for the colname UNI is found again (not moved, not created again)')


def test_renamed_suffixed_collection_uses_its_real_name():
    mapc, olds = fixture()
    make('UNI')
    write_csv([row(1, 0, 'Rock', 'UNI'), row(2, 0, 'Rock')])
    run(False)
    created = bpy.data.collections['UNI.001']
    created.name = 'Trees'
    parents, roots = placement.build_parent_index(mapc)
    assert placement.collection_colname(created, mapc, parents, roots) == 'Trees'
    print('PASS a renamed collection is named by its new name, not by the old tag')


def test_same_rotation_with_opposite_quaternion_is_not_a_move():
    """The quaternion of an Euler rotation can be q or -q (the same rotation): neither counts as moved."""
    mapc, olds = fixture()
    ob = olds[1]
    for euler in ((-3.56379, -0.15201, -0.25699), (-3.0177, -3.46077, -0.79062), (0.08108, -3.52688, -0.95882), (3.1, 0.2, -3.0)):
        ob.rotation_mode = 'XYZ'
        ob.rotation_euler = euler
        bpy.context.view_layer.update()
        assert not placement._transform_differs(ob, tuple(ob.location), euler, (1, 1, 1)), euler
        assert placement._transform_differs(ob, tuple(ob.location), (euler[0] + 0.01, euler[1], euler[2]), (1, 1, 1)), euler
    print('PASS a rotation written back from the CSV is never reported as moved (q and -q are the same rotation)')


def test_new_objects_are_found_again_after_restore_and_reapply():
    """Restore / Re-apply store an 'after' state in ub_run; the objects made by Replace must still be matched to id -1 rows."""
    mapc, olds = fixture()
    write_csv([row(1, 0, 'Rock'), row(2, 0, 'Rock'), row(-1, 10), row(-1, 20)])
    run(False)
    assert bpy.ops.mrt.switch_map_state(target='BEFORE', zone='Z') == {'FINISHED'}, p.status
    assert bpy.ops.mrt.switch_map_state(target='AFTER', zone='Z') == {'FINISHED'}, p.status
    run(True)
    assert (p.plan_create, p.plan_moved, p.plan_unchanged) == (0, 0, 4), (p.plan_create, p.plan_moved, p.plan_unchanged)
    run(False)
    assert xs(zone_objects()) == [0, 0, 10, 20], xs(zone_objects())
    print('PASS objects made by Replace are found again after Restore Original Map and Re-apply (no duplicates)')


def test_retired_object_comes_back_when_the_csv_uses_it_again():
    """An earlier Replace retired id 2 (use 0). A newer CSV says use 1: the object returns to the Map and takes the row."""
    mapc, olds = fixture()
    write_csv([row(1, 0, 'Rock'), row(2, 0, 'Rock', use=0)])
    run(False)
    assert olds[2].get('ub_zone') is None and olds[2].get('ub_archived_from') == 'Z' and olds[2] not in mapc.objects[:]
    run(True)  # the same CSV: nothing to do, the retired object is not "unknown"
    assert (p.plan_moved, p.plan_archive, p.plan_unknown_id, p.plan_resurrected) == (0, 0, 0, 0), \
        (p.plan_moved, p.plan_archive, p.plan_unknown_id, p.plan_resurrected)
    write_csv([row(1, 0, 'Rock'), row(2, 7, 'Rock')])
    run(True)
    assert (p.plan_moved, p.plan_resurrected, p.plan_unknown_id, p.plan_archive) == (1, 1, 0, 0), \
        (p.plan_moved, p.plan_resurrected, p.plan_unknown_id, p.plan_archive)
    run(False)
    ob = olds[2]
    assert ob.get('ub_zone') == 'Z' and 'ub_archived_from' not in ob, dict(ob.items())
    assert ob.users_collection == (mapc,) and round(ob.location.x) == 7, (ob.users_collection, ob.location.x)
    assert 'after' not in placement.read_run(ob) and placement.read_run(ob)['before']['colls'] == [mapc.name], placement.read_run(ob)
    run(True)  # a second Preview with the same CSV: everything is in place
    assert (p.plan_moved, p.plan_create, p.plan_resurrected, p.plan_unchanged) == (0, 0, 0, 2), \
        (p.plan_moved, p.plan_create, p.plan_resurrected, p.plan_unchanged)
    # the original map still comes back, and the imported map again
    assert bpy.ops.mrt.switch_map_state(target='BEFORE', zone='Z') == {'FINISHED'}, p.status
    assert xs(zone_objects()) == [0, 0] and olds[2].users_collection == (mapc,), xs(zone_objects())
    assert bpy.ops.mrt.switch_map_state(target='AFTER', zone='Z') == {'FINISHED'}, p.status
    assert xs(zone_objects()) == [0, 7] and olds[2].get('ub_zone') == 'Z', xs(zone_objects())
    print('PASS a retired object comes back when a newer CSV has a use = 1 row for it; Restore/Re-apply keep working')


def test_retired_object_stays_retired_without_a_library_mesh():
    mapc, olds = fixture()
    write_csv([row(1, 0, 'Rock'), row(2, 0, 'Rock', use=0)])
    run(False)
    write_csv([row(1, 0, 'Rock'), row(2, 7, 'NoSuchMesh')])
    run(True)
    assert (p.plan_moved, p.plan_resurrected) == (0, 0), (p.plan_moved, p.plan_resurrected)
    run(False)
    assert olds[2].get('ub_zone') is None and olds[2].get('ub_archived_from') == 'Z'
    print('PASS a retired object whose row has no Library mesh stays retired')


for test in (test_same_rotation_with_opposite_quaternion_is_not_a_move, test_repeat_replace_does_not_duplicate_new_objects, test_repeat_replace_then_restore_and_reapply,
             test_new_objects_are_found_again_after_restore_and_reapply, test_retired_object_comes_back_when_the_csv_uses_it_again,
             test_retired_object_stays_retired_without_a_library_mesh,
             test_suffixed_collection_matches_its_colname, test_renamed_suffixed_collection_uses_its_real_name):
    test()
mrt.unregister()
print('MRT_REPEAT_REPLACE_PASSED')
