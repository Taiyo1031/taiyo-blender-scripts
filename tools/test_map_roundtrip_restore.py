"""Import as a whole-zone replacement (0.10.0): restore the original map, re-apply the imported one, detailed CSV problems.

blender --background --factory-startup --python-exit-code 1 --python tools/test_map_roundtrip_restore.py
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
from map_roundtrip_tools.chunked import Cancelled
from map_roundtrip_tools.zones import ensure_zone
mrt.register()
p = bpy.context.scene.mrt_props
TEMP = Path(tempfile.mkdtemp(prefix='mrt-restore-'))


def drain(g):
    while True:
        try:
            next(g)
        except StopIteration as done:
            return done.value


def make(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(c)
    return c


def write_csv(rows):
    path = TEMP / 'ZONE_A.csv'
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow([*placement.CSV_COLUMNS, 'use'])
        w.writerows(rows)
    p.placement_csv = str(path)


def row(i, x, col='', name='Rock'):
    return [i, x, 0, 0, 0, 0, 0, 1, 1, 1, name, col]


def fixture():
    bpy.data.batch_remove(ids=list(bpy.data.objects))
    bpy.data.batch_remove(ids=list(bpy.data.collections))
    bpy.data.batch_remove(ids=list(bpy.data.meshes))
    for text in list(bpy.data.texts):
        bpy.data.texts.remove(text)
    m = bpy.data.meshes.new('RockMesh')
    m.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    lib = make('Library')
    lib.objects.link(bpy.data.objects.new('Rock', m))
    mapc = make('Map')
    area = make('Area1', mapc)
    olds = {}
    for csv_id in (1, 2, 3, 4):
        o = bpy.data.objects.new(f'Rock.{csv_id:03d}', m)
        o.location = ((csv_id - 1) * 10, 0, 0)
        o['ub_zone'] = 'ZONE_A'
        o['ub_csv_id'] = csv_id
        o['keep_me'] = f'prop{csv_id}'
        area.objects.link(o)
        olds[csv_id] = o
    p.library_coll, p.map_coll, p.new_mesh_coll, p.archive_coll = lib, mapc, None, None
    ensure_zone(p, 'ZONE_A')
    p.zone_choice = 'ZONE_A'
    p.dry_run = False
    p.skip_bad_rows = False
    p.name_mode = 'numeric_suffix'
    bpy.context.view_layer.update()
    return mapc, area, olds


def do_import():
    assert bpy.ops.mrt.replace_zone() == {'FINISHED'}, p.status


def switch(target):
    assert bpy.ops.mrt.switch_map_state(target=target, zone='ZONE_A') == {'FINISHED'}, p.status


def state():
    return bpy.data.collections['_Replaced_ZONE_A']['ub_state']


def imported_objects(olds):
    return [o for o in bpy.data.objects if o.get('ub_zone') == 'ZONE_A' and o not in olds.values()]


def scenario():
    """Four original objects; the CSV places four rows (none of the ids matters): two in Area1, one in a new Area2."""
    mapc, area, olds = fixture()
    write_csv([row(1, 0, 'Area1'), row(2, 100, 'Area1'), row(4, 30, 'Area2'), row(-1, 200, 'Area1')])
    do_import()
    return mapc, area, olds


def test_import_applies():
    mapc, area, olds = scenario()
    archive = bpy.data.collections['_Replaced_ZONE_A']
    assert all(olds[i].get('ub_zone') is None and olds[i].get('ub_archived_from') == 'ZONE_A' for i in (1, 2, 3, 4)), 'every original is archived'
    assert all(olds[i]['keep_me'] == f'prop{i}' and tuple(olds[i].location) == ((i - 1) * 10, 0, 0) for i in (1, 2, 3, 4)), 'originals are untouched'
    assert all(olds[i].users_collection == (archive.children['Area1 [ZONE_A]'],) for i in (1, 2, 3, 4)), [o.users_collection for o in olds.values()]
    fresh = imported_objects(olds)
    assert sorted(round(o.location.x) for o in fresh) == [0, 30, 100, 200], [o.location.x for o in fresh]
    area2 = bpy.data.collections['Area2']
    assert area2 in mapc.children[:] and [round(o.location.x) for o in area2.objects] == [30]
    assert all('keep_me' not in o for o in fresh), 'imported objects are new objects'
    assert state() == 'after'
    print('PASS import: all originals archived untouched, every CSV row placed (the ids play no part), Area2 created')


def test_restore_and_reapply():
    mapc, area, olds = scenario()
    fresh = imported_objects(olds)
    switch('BEFORE')
    assert state() == 'before'
    assert [tuple(olds[i].location) for i in (1, 2, 3, 4)] == [(0, 0, 0), (10, 0, 0), (20, 0, 0), (30, 0, 0)]
    assert all(olds[i].users_collection == (area,) and olds[i].get('ub_zone') == 'ZONE_A' for i in (1, 2, 3, 4))
    assert all(olds[i]['keep_me'] == f'prop{i}' and 'ub_archived_from' not in olds[i] for i in (1, 2, 3, 4))
    assert all(o.users_collection[0].name in ('Area1 [ZONE_A]', 'Area2 [ZONE_A]') for o in fresh), [o.users_collection for o in fresh]
    assert all(o.get('ub_zone') is None for o in fresh)
    # While the original map is shown the plan counts the stashed import as the earlier import: it is deleted, not kept.
    plan = drain(placement.build_plan(p))
    assert (len(plan.originals), len(plan.previous), len(plan.rows)) == (4, 4, 4), (len(plan.originals), len(plan.previous), len(plan.rows))
    switch('AFTER')
    assert state() == 'after'
    assert all(olds[i].users_collection[0].name == 'Area1 [ZONE_A]' and olds[i].get('ub_zone') is None for i in (1, 2, 3, 4))
    assert all(o.get('ub_zone') == 'ZONE_A' and o.users_collection[0].name in ('Area1', 'Area2') for o in fresh)
    # A manual edit of an imported object survives a round trip.
    edited = next(o for o in fresh if round(o.location.x) == 200)
    edited.location.x = 250
    edited['mine'] = 1
    switch('BEFORE')
    switch('AFTER')
    assert round(edited.location.x) == 250 and edited['mine'] == 1
    # Switching to the state that is already shown is an error, not a no-op.
    try:
        switch('AFTER')
    except RuntimeError as exc:
        assert 'already shows' in str(exc), str(exc)
    else:
        raise AssertionError('switching to the shown state must report it')
    print('PASS restore -> original map exactly, re-apply -> imported map, manual edits kept')


def test_second_import_keeps_the_first_original():
    mapc, area, olds = scenario()
    write_csv([row(1, 500, 'Area1'), row(2, 600, 'Area1')])
    do_import()
    assert sorted(round(o.location.x) for o in imported_objects(olds)) == [500, 600]
    assert all(olds[i].get('ub_archived_from') == 'ZONE_A' for i in (1, 2, 3, 4)), 'the archive is not touched'
    switch('BEFORE')
    assert [tuple(olds[i].location) for i in (1, 2, 3, 4)] == [(0, 0, 0), (10, 0, 0), (20, 0, 0), (30, 0, 0)], 'the baseline is the map before the first import'
    assert olds[3].users_collection == (area,)
    switch('AFTER')
    assert sorted(round(o.location.x) for o in imported_objects(olds)) == [500, 600]
    print('PASS a second import replaces the first import and keeps the first original as the baseline')


def test_switch_rollback():
    mapc, area, olds = scenario()
    before = {o: (tuple(o.location), tuple(c.name for c in o.users_collection), o.get('ub_zone')) for o in bpy.data.objects}
    colls_before = set(bpy.data.collections)
    op = mrt.restore.MRT_OT_SwitchMapState
    stub = type('S', (), {'target': 'BEFORE', 'zone': 'ZONE_A', '_error': '', 'result': '', 'progress': lambda self, *a: setattr(self, 'phase', a[0]), 'report': lambda *a: None})()
    g = op.work(stub, bpy.context)
    while getattr(stub, 'phase', '') != 'Switching map state':
        next(g)
    try:
        g.throw(Cancelled('Injected ESC'))
        drain(g)
    except Cancelled:
        pass
    after = {o: (tuple(o.location), tuple(c.name for c in o.users_collection), o.get('ub_zone')) for o in bpy.data.objects}
    assert after == before and state() == 'after' and set(bpy.data.collections) == colls_before
    print('PASS ESC while switching restores everything')


def test_flags_survive_a_failed_import():
    mapc, area, olds = fixture()
    olds[2].select_set(True)
    olds[4].hide_set(True)  # a hidden object cannot stay selected
    flags = {i: (olds[i].select_get(), olds[i].hide_get()) for i in (2, 4)}
    assert flags == {2: (True, False), 4: (False, True)}, flags
    write_csv([row(1, 0, 'Area1'), row(2, 100, 'Area1'), row(4, 30, 'Area2')])
    real = placement.apply_absent
    calls = []

    def boom(*args, **kwargs):
        calls.append(1)
        if len(calls) == 3:
            raise RuntimeError('boom')
        return real(*args, **kwargs)
    placement.apply_absent = boom
    try:
        try:
            bpy.ops.mrt.replace_zone()
        except RuntimeError:
            pass
    finally:
        placement.apply_absent = real
    assert len(calls) == 3
    assert all(o.get('ub_zone') == 'ZONE_A' and o.users_collection[0].name == 'Area1' for o in olds.values()), 'rolled back'
    assert {i: (olds[i].select_get(), olds[i].hide_get()) for i in (2, 4)} == flags, 'selection and hide flags survive the rollback'
    print('PASS selection and hide flags survive a failed import (link before unlink, flags restored)')


class Layout:
    """Accepts any layout call and remembers the texts and operators; row(), box() return the same recorder."""
    def __init__(self):
        self.texts, self.operators = [], []

    def __getattr__(self, name):
        def call(*args, **kwargs):
            if 'text' in kwargs:
                self.texts.append(kwargs['text'])
            if name == 'operator':
                self.operators.append((args[0], kwargs.get('text')))
            return self
        return call


def draw_import():
    layout = Layout()
    mrt.ui.MRT_PT_Import.draw(type('Fake', (), {'layout': layout})(), bpy.context)
    return layout


def test_import_panel():
    mapc, area, olds = scenario()
    p.dry_run = True
    write_csv([row(1, 0, 'Area1'), ['2', 'abc', 0, 0, 0, 0, 0, 1, 1, 1, 'Rock', ''], row(2, 100, 'Area1')])
    do_import()
    layout = draw_import()
    joined = ' | '.join(layout.texts)
    assert 'Archive' in joined and 'Delete' in joined and 'Place 2 CSV rows' in joined and 'errors' in joined, joined
    assert any("'abc'" in t for t in layout.texts), layout.texts
    assert 'MRT Placement Report' in joined and 'Zone: ZONE_A' in joined and 'the imported CSV is shown' in joined, joined
    assert ('mrt.switch_map_state', 'Restore Original Map') in layout.operators, layout.operators
    assert ('mrt.replace_zone', 'Preview Import') in layout.operators, layout.operators
    p.dry_run = False
    write_csv([row(1, 0, 'Area1'), row(2, 100, 'Area1')])
    switch('BEFORE')
    layout = draw_import()
    assert ('mrt.switch_map_state', 'Re-apply Imported Map') in layout.operators, layout.operators
    assert any('ORIGINAL' in t for t in layout.texts), layout.texts
    assert ('mrt.replace_zone', 'Import Zone') in layout.operators, layout.operators
    print('PASS the Import panel shows the zone, the plan, the first problems, and the Restore / Re-apply button')


def test_detailed_problems():
    mapc, area, olds = fixture()
    # The library also holds a non-mesh and a near name, to make the hints visible.
    bpy.data.collections['Library'].objects.link(bpy.data.objects.new('Marker', None))
    bpy.data.collections['Library'].objects.link(bpy.data.objects.new('Rocks', bpy.data.meshes['RockMesh']))
    path = TEMP / 'ZONE_A.csv'
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(placement.CSV_COLUMNS)
        w.writerow(row(1, 0, 'Area1'))                       # line 2: fine
        w.writerow(['2', 'abc', 0, 0, 0, 0, 0, 1, 1, 1, 'Rock', ''])   # line 3: bad number in tx
        w.writerow(['3', 0, 0, 0, 0, 0, 0, 1, 1, 'nan', 'Rock', ''])    # line 4: not finite in sz
        w.writerow(['x', 0, 0, 0, 0, 0, 0, 1, 1, 1, 'Rock', ''])        # line 5: the id is not read any more: a fine row
        w.writerow(['4', 0, 0, 0])                                        # line 6: short row
        w.writerow(row(-1, 0, '', 'Rockk'))                              # line 7: near name
        w.writerow(row(-1, 0, '', 'Marker'))                             # line 8: not a mesh
        w.writerow(row(-1, 0, '', '  '))                                 # line 9: empty objname
        w.writerow(row(77, 0, 'Area1'))                                  # line 10: an id the export never had: a fine row
        w.writerow(row(1, 5, 'Area1'))                                   # line 11: a repeated id: a fine row
        w.writerow(row(-1, 0, 'A//B'))                                   # line 12: odd colname
        w.writerow(row(2, 0, 'Area1', 'GoneForever'))                    # line 13: mesh missing
    p.placement_csv = str(path)
    plan = drain(placement.build_plan(p))
    by_line = {}
    for issue in plan.issues:
        by_line.setdefault(issue.line, []).append(issue)
    text = {line: ' '.join(i.message for i in issues) for line, issues in by_line.items()}
    assert 'tx' in text[3] and "'abc'" in text[3] and by_line[3][0].column == 'tx' and by_line[3][0].value == 'abc', text[3]
    assert 'sz' in text[4] and 'finite' in text[4], text[4]
    assert 'columns' in text[6], text[6]
    assert 'Rockk' in text[7] and 'Similar' in text[7] and 'Rock' in text[7] and 'Import New Meshes' in text[7], text[7]
    assert 'Marker' in text[8] and 'EMPTY' in text[8] and 'not a mesh' in text[8], text[8]
    assert 'objname is empty' in text[9], text[9]
    assert 'A//B' in text[12], text[12]
    assert 'GoneForever' in text[13] and 'cannot be placed' in text[13], text[13]
    assert not {5, 10, 11} & by_line.keys(), 'ids are not checked any more: rows 5, 10 and 11 are placed'
    assert len(plan.rows) == 5 and plan.invalid == 4 and plan.missing_rows == 3, (len(plan.rows), plan.invalid, plan.missing_rows)
    errors, warnings = placement_report.counts(plan.issues)
    assert errors == 7 and warnings >= 1, (errors, warnings)
    lines = placement_report.first_lines(plan.issues, 3)
    assert len(lines) == 3 and all(i.severity == 'error' for i in sorted(plan.issues, key=lambda i: (i.severity != 'error', i.line))[:3])
    p.dry_run = True
    assert bpy.ops.mrt.replace_zone() == {'FINISHED'}
    report = bpy.data.texts[placement_report.REPORT_TEXT].as_string()
    assert 'Line 3' in report and 'Line 13' in report and 'errors' in report
    assert p.plan_errors == errors and p.plan_warnings == warnings
    assert p.plan_block and (p.plan_create, p.plan_invalid, p.plan_missing_rows) == (5, 4, 3), (p.plan_block, p.plan_create)
    print('PASS CSV problems name the line, column, value and reason, with hints and a Text report; ids are no longer checked')


def test_file_level_errors():
    mapc, area, olds = fixture()
    path = TEMP / 'broken.csv'
    path.write_text('')
    p.placement_csv = str(path)
    for text, expected in (('', 'empty'), ('id,tx\n', 'Missing CSV columns')):
        path.write_text(text)
        try:
            drain(placement.build_plan(p))
        except ValueError as exc:
            assert expected in str(exc), str(exc)
        else:
            raise AssertionError(expected)
    p.placement_csv = str(TEMP / 'nope.csv')
    try:
        drain(placement.build_plan(p))
    except ValueError as exc:
        assert 'nope.csv' in str(exc), str(exc)
    p.placement_csv = str(path)
    path.write_text(','.join(placement.CSV_COLUMNS) + '\n')
    p.zone_choice = 'ALL'
    try:
        drain(placement.build_plan(p))
    except ValueError as exc:
        assert 'Choose the zone' in str(exc), str(exc)
    else:
        raise AssertionError('All Zones cannot be imported')
    p.zone_choice = 'ZONE_A'
    print('PASS file-level problems: empty file, missing columns (with the columns found), missing file (with its path), no zone chosen')


for test in (test_import_applies, test_restore_and_reapply, test_second_import_keeps_the_first_original,
             test_switch_rollback, test_flags_survive_a_failed_import, test_import_panel, test_detailed_problems, test_file_level_errors):
    test()
mrt.unregister()
print('MRT_RESTORE_PASSED')
