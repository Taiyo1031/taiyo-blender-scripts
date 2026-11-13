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


def plan_for(rows, use_column=True):
    """rows are (id, objname) or (id, objname, use); `use` is written as given."""
    path = TEMP / 'Z.csv'
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['id', 'tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz', 'objname', 'colname', *(['use'] if use_column else [])])
        for csv_id, name, *use in rows:
            w.writerow([csv_id, 0, 0, 0, 0, 0, 0, 1, 1, 1, name, '', *use])
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


def names(objects):
    return sorted(ob.name for ob in objects)


def other_issues(plan):
    """Issues except the Library duplicate-name warnings that this fixture always has."""
    return [i.message for i in plan.issues if i.kind != 'duplicate_library_name']


def test_use_zero_retires_only_marked_objects():
    fixture(5)  # ids 0..4
    plan = plan_for([(0, 'Rock_Def_1'), (1, 'Rock_Def_1', 0), (2, 'Rock_Def_1', 1), (3, 'Rock_Def_1', 0)])  # id 4 has no row
    assert len(plan.rows) == 2 and plan.unused_rows == 2, (len(plan.rows), plan.unused_rows)
    assert names(plan.retired) == ['Rock_Def_1.001', 'Rock_Def_1.003'], names(plan.retired)
    assert names(plan.not_in_csv) == ['Rock_Def_1.004'], names(plan.not_in_csv)
    assert 'Rock_Def_1.004' in names(plan.unchanged), names(plan.unchanged)
    assert not kinds(plan, 'many_retired') and not other_issues(plan), other_issues(plan)
    placement.publish_plan(p, plan)
    assert (p.plan_archive, p.plan_not_in_csv, p.plan_unused_rows, p.plan_unchanged) == (2, 1, 2, 3), \
        (p.plan_archive, p.plan_not_in_csv, p.plan_unused_rows, p.plan_unchanged)
    summary = placement.plan_summary(plan)
    assert 'retired 2 (use 0 rows 2)' in summary and 'not in CSV 1' in summary, summary
    print('PASS use = 0 retires only the marked objects; objects without a row stay as they are')


def test_use_zero_rows_place_nothing_and_say_nothing():
    fixture(3)
    plan = plan_for([(99, 'NoSuchMesh', 0), (-1, 'NoSuchMesh', 0), (0, 'Rock_Def_1', 1)])
    assert plan.unused_rows == 2 and len(plan.rows) == 1 and plan.new_rows == 0 and plan.unknown_id_rows == 0
    assert plan.missing_rows == 0 and not other_issues(plan), other_issues(plan)
    assert plan.retired == [] and len(plan.not_in_csv) == 2
    print('PASS a use = 0 row with an unknown id or a missing mesh is ignored without a warning')


def test_bad_use_value_and_empty_use():
    fixture(3)
    plan = plan_for([(0, 'Rock_Def_1', 'x'), (1, 'Rock_Def_1', 2), (2, 'Rock_Def_1', '')])
    bad = kinds(plan, 'bad_use')
    assert len(bad) == 2 and plan.invalid == 2, [i.message for i in plan.issues]
    assert 'must be 0' in bad[0].message and bad[0].line == 2 and bad[0].column == 'use' and bad[0].value == 'x', bad[0]
    assert len(plan.rows) == 1 and plan.unused_rows == 0  # an empty use cell means 1
    print('PASS use accepts only 0 or 1 (empty = 1); other values are invalid rows')


def test_use_zero_loses_to_a_use_one_row_of_the_same_id():
    fixture(3)
    plan = plan_for([(1, 'Rock_Def_1', 0), (1, 'Rock_Def_1', 1)])
    assert plan.retired == [] and len(kinds(plan, 'use_conflict')) == 1, [i.message for i in plan.issues]
    print('PASS the same id with use = 0 and use = 1: the object is kept and a warning says so')


def test_without_a_use_column_nothing_is_retired():
    fixture(30)
    plan = plan_for([(0, 'Rock_Def_1'), (1, 'Rock_Def_1')], use_column=False)
    assert plan.retired == [] and len(plan.not_in_csv) == 28 and plan.unused_rows == 0
    assert not kinds(plan, 'many_retired')
    print('PASS a CSV without a use column keeps every object that has no row (no mass retire)')


for test in (test_new_mesh_hint_survives_similar_names, test_new_mesh_rows_are_counted_even_when_the_mesh_is_not_in_the_library,
             test_new_mesh_hint_without_similar_names,
             test_duplicate_library_names_are_one_warning_per_name, test_use_zero_retires_only_marked_objects,
             test_use_zero_rows_place_nothing_and_say_nothing, test_bad_use_value_and_empty_use,
             test_use_zero_loses_to_a_use_one_row_of_the_same_id, test_without_a_use_column_nothing_is_retired):
    test()
mrt.unregister()
print('MRT_PREVIEW_HINTS_PASSED')
