"""Preview wording: missing-mesh hint, one warning per duplicate Library name, use column, rows that block the import, fewer-rows warning.

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
from map_roundtrip_tools.zones import ensure_zone
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
    ensure_zone(p, 'Z')
    p.zone_choice = 'Z'
    p.skip_bad_rows = False
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


def kinds(plan, kind):
    return [i for i in plan.issues if i.kind == kind]


def names(objects):
    return sorted(ob.name for ob in objects)


def other_issues(plan):
    """Issues except the Library duplicate-name warnings that this fixture always has."""
    return [i.message for i in plan.issues if i.kind != 'duplicate_library_name']


def test_missing_mesh_hint_lists_similar_names_and_new_meshes():
    fixture()
    # 'Rock_Def_2' is close to the Library name 'Rock_Def_1'; the id column plays no part
    plan = plan_for([(-1, 'Rock_Def_2'), (0, 'Rock_Def_2'), (1, 'Rock_Def_1')])
    issues = kinds(plan, 'missing_mesh')
    assert len(issues) == 2 and plan.missing_rows == 2 and len(plan.rows) == 1, ([i.message for i in issues], plan.missing_rows, len(plan.rows))
    for issue in issues:
        assert 'Similar Library names' in issue.message and 'Import New Meshes' in issue.message and 'cannot be placed' in issue.message, issue.message
        assert 'left unchanged' not in issue.message, issue.message  # nothing is left unchanged any more: the object is archived
    print('PASS a row without a Library mesh says so, lists similar names and points to Import New Meshes')


def test_missing_mesh_hint_without_similar_names():
    fixture()
    plan = plan_for([(-1, 'Zzzzqqqq_Totally_Different')])
    message = kinds(plan, 'missing_mesh')[0].message
    assert 'No similar name in Library' in message and 'Import New Meshes' in message, message
    print('PASS a row without similar names still points to Import New Meshes')


def test_rows_that_cannot_be_placed_block_the_import():
    fixture(5)
    plan = plan_for([(0, 'Rock_Def_1'), (1, 'NotYet_A'), (2, 'Rock_Def_1'), (3, 'Rock_Def_1', 'x')], use_column=True)
    # the last row has a bad use value, the second has no Library mesh
    assert (plan.missing_rows, plan.invalid, len(plan.rows)) == (1, 1, 2), (plan.missing_rows, plan.invalid, len(plan.rows))
    problem = placement.blocking_problem(p, plan)
    assert '1 rows have no Library mesh' in problem and '1 rows cannot be read' in problem and 'Skip rows' in problem, problem
    placement.publish_plan(p, plan)
    assert p.plan_block == problem and p.plan_missing_rows == 1 and p.plan_invalid == 1
    p.skip_bad_rows = True
    assert placement.blocking_problem(p, plan) == ''
    p.skip_bad_rows = False
    print('PASS rows that cannot be placed block the import unless they are skipped on purpose')


def test_a_csv_that_places_nothing_blocks_the_import():
    fixture(5)
    plan = plan_for([(0, 'Rock_Def_1', 0), (1, 'Rock_Def_1', 0)])
    assert plan.rows == [] and plan.unused_rows == 2
    assert 'no row to place' in placement.blocking_problem(p, plan)
    print('PASS a CSV with nothing to place is refused (it would only archive the zone)')


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


def test_every_original_is_archived_and_every_row_is_placed():
    fixture(5)  # ids 0..4
    plan = plan_for([(0, 'Rock_Def_1'), (1, 'Rock_Def_1', 0), (2, 'Rock_Def_1', 1), (3, 'Rock_Def_1', 0)])
    assert len(plan.rows) == 2 and plan.unused_rows == 2, (len(plan.rows), plan.unused_rows)
    assert len(plan.originals) == 5 and plan.previous == [], (len(plan.originals), len(plan.previous))  # the ids do not matter
    assert not other_issues(plan) or {i.kind for i in plan.issues if i.kind != 'duplicate_library_name'} == {'fewer_rows'}, other_issues(plan)
    placement.publish_plan(p, plan)
    assert (p.plan_archive, p.plan_delete, p.plan_create, p.plan_unused_rows, p.plan_block) == (5, 0, 2, 2, ''), \
        (p.plan_archive, p.plan_delete, p.plan_create, p.plan_unused_rows, p.plan_block)
    summary = placement.plan_summary(plan)
    assert 'archive 5 original objects' in summary and 'delete 0 from the earlier import' in summary and 'place 2 (use 0 rows 2)' in summary, summary
    print('PASS the plan archives every original object and places every row with use = 1')


def test_use_zero_rows_place_nothing_and_say_nothing():
    fixture(3)
    plan = plan_for([(99, 'NoSuchMesh', 0), (-1, 'NoSuchMesh', 0), (0, 'Rock_Def_1', 1)])
    assert plan.unused_rows == 2 and len(plan.rows) == 1 and plan.missing_rows == 0
    assert not [i for i in plan.issues if i.kind not in ('duplicate_library_name', 'fewer_rows')], other_issues(plan)
    print('PASS a use = 0 row with a missing mesh is ignored without a warning')


def test_bad_use_value_and_empty_use():
    fixture(3)
    plan = plan_for([(0, 'Rock_Def_1', 'x'), (1, 'Rock_Def_1', 2), (2, 'Rock_Def_1', '')])
    bad = kinds(plan, 'bad_use')
    assert len(bad) == 2 and plan.invalid == 2, [i.message for i in plan.issues]
    assert 'must be 0' in bad[0].message and bad[0].line == 2 and bad[0].column == 'use' and bad[0].value == 'x', bad[0]
    assert len(plan.rows) == 1 and plan.unused_rows == 0  # an empty use cell means 1
    print('PASS use accepts only 0 or 1 (empty = 1); other values are invalid rows')


def test_same_id_twice_is_two_rows_now():
    fixture(3)
    plan = plan_for([(1, 'Rock_Def_1', 0), (1, 'Rock_Def_1', 1), (1, 'Rock_Def_1', 1)])
    assert len(plan.rows) == 2 and plan.unused_rows == 1, (len(plan.rows), plan.unused_rows)
    assert not [i for i in plan.issues if i.kind in ('use_conflict', 'duplicate_id', 'unknown_id')], [i.message for i in plan.issues]
    print('PASS the id column is not checked: repeated ids are separate rows, no id warnings exist')


def test_without_a_use_column_every_row_is_placed():
    fixture(30)
    plan = plan_for([(0, 'Rock_Def_1'), (1, 'Rock_Def_1')], use_column=False)
    assert len(plan.rows) == 2 and plan.unused_rows == 0 and len(plan.originals) == 30
    print('PASS a CSV without a use column places every row')


def test_fewer_rows_warning():
    fixture(30)
    plan = plan_for([(i, 'Rock_Def_1') for i in range(10)])
    warning = kinds(plan, 'fewer_rows')
    assert len(warning) == 1 and warning[0].severity == 'warning' and 'whole zone' in warning[0].message, [i.message for i in plan.issues]
    assert '10 objects, but Z has 30' in warning[0].message, warning[0].message
    plan = plan_for([(i, 'Rock_Def_1') for i in range(15)])  # half of the zone is still fine
    assert not kinds(plan, 'fewer_rows')
    plan = plan_for([(i, 'Rock_Def_1') for i in range(30)])
    assert not kinds(plan, 'fewer_rows')
    print('PASS a CSV that places fewer than half of the zone\'s objects gets a warning')


def test_no_zone_selected_is_refused():
    fixture()
    p.zone_choice = 'ALL'
    try:
        plan_for([(0, 'Rock_Def_1')])
    except ValueError as exc:
        assert 'Choose the zone' in str(exc), exc
    else:
        raise AssertionError('All Zones cannot be imported')
    p.zone_choice = 'Z'
    print('PASS All Zones cannot be imported')


for test in (test_missing_mesh_hint_lists_similar_names_and_new_meshes, test_missing_mesh_hint_without_similar_names,
             test_rows_that_cannot_be_placed_block_the_import, test_a_csv_that_places_nothing_blocks_the_import,
             test_duplicate_library_names_are_one_warning_per_name, test_every_original_is_archived_and_every_row_is_placed,
             test_use_zero_rows_place_nothing_and_say_nothing, test_bad_use_value_and_empty_use,
             test_same_id_twice_is_two_rows_now, test_without_a_use_column_every_row_is_placed,
             test_fewer_rows_warning, test_no_zone_selected_is_refused):
    test()
mrt.unregister()
print('MRT_PREVIEW_HINTS_PASSED')
