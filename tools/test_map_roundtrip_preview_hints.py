"""Preview wording: new-mesh hint, one warning per duplicate Library name, large-retire warning.

blender --background --factory-startup --python-exit-code 1 --python tools/test_map_roundtrip_preview_hints.py
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
mrt.register()
scene = bpy.context.scene
p = scene.mrt_props
TEMP = Path(tempfile.mkdtemp(prefix='mrt-preview-hints-'))


def drain(g):
    while True:
        try:
            next(g)
        except StopIteration as done:
            return done.value


def fixture(zone_objects=30):
    bpy.data.batch_remove(ids=list(bpy.data.objects))
    bpy.data.batch_remove(ids=list(bpy.data.collections))
    lib = bpy.data.collections.new('Library')
    mapc = bpy.data.collections.new('Map')
    scene.collection.children.link(lib)
    scene.collection.children.link(mapc)
    mesh = bpy.data.meshes.new('M')
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    for name in ('Rock_Def_1', 'Dup_Def_1', 'Dup_Def_1.001', 'Dup_Def_1.002', 'Solo_Def_1', 'Solo_Def_1.001'):
        lib.objects.link(bpy.data.objects.new(name, mesh))
    for i in range(zone_objects):
        ob = bpy.data.objects.new(f'Rock_Def_1.{i:03d}', mesh)
        ob['ub_zone'] = 'Z'
        ob['ub_csv_id'] = i
        mapc.objects.link(ob)
    p.library_coll, p.map_coll, p.new_mesh_coll = lib, mapc, None
    p.zone_override = 'Z'
    p.name_mode = 'numeric_suffix'


def plan_for(rows):
    path = TEMP / 'Z.csv'
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['id', 'tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz', 'objname', 'colname'])
        for csv_id, name in rows:
            w.writerow([csv_id, 0, 0, 0, 0, 0, 0, 1, 1, 1, name, ''])
    p.placement_csv = str(path)
    return drain(placement.build_plan(p))


def kinds(plan, kind):
    return [i for i in plan.issues if i.kind == kind]


def test_new_mesh_hint_survives_similar_names():
    fixture()
    # 'Rock_Def_2' is close to the Library name 'Rock_Def_1'; id -1 means a new mesh that is not in the Library yet.
    plan = plan_for([(-1, 'Rock_Def_2'), (0, 'Rock_Def_2'), (1, 'Rock_Def_1')])
    issues = kinds(plan, 'missing_mesh')
    assert len(issues) == 2, [i.message for i in issues]
    new_row = next(i for i in issues if i.line == 2)
    old_row = next(i for i in issues if i.line == 3)
    assert 'Similar Library names' in new_row.message and 'new mesh (id -1)' in new_row.message and 'Import New Meshes' in new_row.message, new_row.message
    assert 'new mesh' not in old_row.message and 'Similar Library names' in old_row.message, old_row.message
    assert 'left unchanged' in old_row.message
    print('PASS an id -1 row always says it is a new mesh, even when similar names are listed')


def test_new_mesh_rows_are_counted_even_when_the_mesh_is_not_in_the_library():
    fixture()
    # three id -1 rows: one mesh is in the Library, two are not (not imported yet)
    plan = plan_for([(-1, 'Rock_Def_1'), (-1, 'NotYet_A'), (-1, 'NotYet_B'), (0, 'Rock_Def_1')])
    assert plan.new_rows == 3 and plan.added == 1, (plan.new_rows, plan.added)
    placement.publish_plan(p, plan)
    assert p.plan_new_rows == 3 and p.plan_added == 1
    assert 'new meshes 1 of 3 rows with id -1' in placement.plan_summary(plan), placement.plan_summary(plan)
    print('PASS rows with id -1 are counted even when their mesh is not in the Library yet')


def test_new_mesh_hint_without_similar_names():
    fixture()
    plan = plan_for([(-1, 'Zzzzqqqq_Totally_Different')])
    message = kinds(plan, 'missing_mesh')[0].message
    assert 'new mesh (id -1)' in message and 'Import New Meshes' in message, message
    print('PASS an id -1 row without similar names still says it is a new mesh')


def test_duplicate_library_names_are_one_warning_per_name():
    fixture()
    plan = plan_for([(0, 'Rock_Def_1')])
    dups = kinds(plan, 'duplicate_library_name')
    assert len(dups) == 2, [i.message for i in dups]  # Dup_Def_1 (3 objects) and Solo_Def_1 (2 objects)
    dup = next(i for i in dups if 'Dup_Def_1' in i.message and 'Solo' not in i.message)
    for name in ('Dup_Def_1', 'Dup_Def_1.001', 'Dup_Def_1.002'):
        assert name in dup.message, dup.message
    assert dup.severity == 'warning'
    assert plan.duplicates == 3, plan.duplicates  # extra objects: 2 for Dup_Def_1 and 1 for Solo_Def_1
    print('PASS a duplicated Library name gives one warning that lists every object')


def test_large_retire_warning():
    fixture(30)
    plan = plan_for([(0, 'Rock_Def_1'), (1, 'Rock_Def_1')])  # 28 of 30 zone objects have no row
    warnings = kinds(plan, 'many_retired')
    assert len(warnings) == 1, [i.message for i in plan.issues]
    assert warnings[0].severity == 'warning' and '28 of 30' in warnings[0].message and '93%' in warnings[0].message, warnings[0].message
    assert 'CSV' in warnings[0].message and 'Restore Original Map' in warnings[0].message
    fixture(30)
    assert not kinds(plan_for([(i, 'Rock_Def_1') for i in range(29)]), 'many_retired')  # only 1 of 30 retired
    fixture(8)
    assert not kinds(plan_for([(0, 'Rock_Def_1')]), 'many_retired')  # 7 of 8, but too few objects to matter
    fixture(0)
    assert not kinds(plan_for([(-1, 'Rock_Def_1')]), 'many_retired')  # an empty zone retires nothing
    print('PASS retiring most of a zone (at least 10 objects, half or more) is warned about')


for test in (test_new_mesh_hint_survives_similar_names, test_new_mesh_rows_are_counted_even_when_the_mesh_is_not_in_the_library,
             test_new_mesh_hint_without_similar_names,
             test_duplicate_library_names_are_one_warning_per_name, test_large_retire_warning):
    test()
mrt.unregister()
print('MRT_PREVIEW_HINTS_PASSED')
