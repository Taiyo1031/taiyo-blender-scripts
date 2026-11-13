"""Replace Zone as a reversible diff: restore the original map, re-apply the imported one, detailed CSV problems.

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
mrt.register()
p = bpy.context.scene.mrt_props
TEMP = Path(tempfile.mkdtemp(prefix='mrt-restore-'))


class Harness:
    def __init__(self):
        self._error = ''
        self.result = ''
        self.messages = []

    def progress(self, phase, done, total):
        self.phase = phase

    def report(self, level, text):
        self.messages.append(text)


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


def gone(i):
    """A row with use = 0: the object with this id is removed from the map."""
    return [i, 0, 0, 0, 0, 0, 0, 1, 1, 1, 'Rock', '', 0]


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
    p.library_coll, p.map_coll = lib, mapc
    p.zone_override = ''
    p.dry_run = False
    p.name_mode = 'numeric_suffix'
    bpy.context.view_layer.update()
    return mapc, area, olds


def replace():
    assert bpy.ops.mrt.replace_zone() == {'FINISHED'}, p.status


def switch(target):
    assert bpy.ops.mrt.switch_map_state(target=target, zone='ZONE_A') == {'FINISHED'}, p.status


def state():
    return bpy.data.collections['_Replaced_ZONE_A']['ub_state']


def imported_objects(olds):
    return [o for o in bpy.data.objects if o.get('ub_zone') == 'ZONE_A' and o not in olds.values()]


def scenario():
    """id1 unchanged, id2 moved, id3 removed, id4 moved to a new collection, two new objects (one is a repeated id)."""
    mapc, area, olds = fixture()
    write_csv([row(1, 0, 'Area1'), row(2, 100, 'Area1'), gone(3), row(4, 30, 'Area2'), row(-1, 200, 'Area1'), row(1, 300, 'Area1')])
    replace()
    return mapc, area, olds


def test_diff_apply():
    mapc, area, olds = scenario()
    assert tuple(olds[1].location) == (0, 0, 0) and 'ub_run' not in olds[1]  # unchanged: nothing written
    assert tuple(olds[2].location) == (100, 0, 0) and olds[2]['keep_me'] == 'prop2'
    assert olds[3].get('ub_zone') is None and olds[3].users_collection == (bpy.data.collections['_Replaced_ZONE_A'].children['Area1 [ZONE_A]'],)
    area2 = bpy.data.collections['Area2']
    assert olds[4].users_collection == (area2,) and tuple(olds[4].location) == (30, 0, 0)
    fresh = imported_objects(olds)
    assert sorted(round(o.location.x) for o in fresh) == [200, 300]
    assert state() == 'after'
    print('PASS diff: unchanged untouched, moved in place with properties, removed retired, new + repeated id added')


def test_restore_and_reapply():
    mapc, area, olds = scenario()
    fresh = imported_objects(olds)
    switch('BEFORE')
    assert state() == 'before'
    assert [tuple(olds[i].location) for i in (1, 2, 3, 4)] == [(0, 0, 0), (10, 0, 0), (20, 0, 0), (30, 0, 0)]
    assert all(olds[i].users_collection == (area,) and olds[i].get('ub_zone') == 'ZONE_A' for i in (1, 2, 3, 4))
    assert all(olds[i]['keep_me'] == f'prop{i}' and 'ub_archived_from' not in olds[i] for i in (1, 2, 3, 4))
    archive = bpy.data.collections['_Replaced_ZONE_A']
    assert all(o.users_collection[0].name == 'Area1 [ZONE_A]' for o in fresh) and all(o.get('ub_zone') is None for o in fresh)
    # While the original map is shown, importing again is refused.
    try:
        placement_plan = drain(placement.build_plan(p))
    except ValueError as exc:
        assert 'original map' in str(exc), str(exc)
    else:
        raise AssertionError('Replace must be refused while the original map is shown')
    # A manual edit of an imported object survives a round trip.
    switch('AFTER')
    assert state() == 'after'
    assert [tuple(olds[i].location) for i in (1, 2, 4)] == [(0, 0, 0), (100, 0, 0), (30, 0, 0)]
    assert olds[2].users_collection == (area,) and olds[4].users_collection == (bpy.data.collections['Area2'],)
    assert olds[3].users_collection == (archive.children['Area1 [ZONE_A]'],) and olds[3].get('ub_zone') is None
    assert all(o.users_collection == (area,) and o.get('ub_zone') == 'ZONE_A' for o in fresh)
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
    print('PASS restore -> original map exactly, re-apply -> imported map, manual edits kept, Replace refused in between')


def test_second_replace_keeps_the_first_original():
    mapc, area, olds = scenario()
    write_csv([row(1, 0, 'Area1'), row(2, 500, 'Area1'), gone(3), row(4, 30, 'Area2')])  # id2 moves again, id3 stays retired, fresh ids gone
    # the new objects were exported again in a real flow; here they simply have no ids, so they are retired
    replace()
    assert tuple(olds[2].location) == (500, 0, 0)
    switch('BEFORE')
    assert tuple(olds[2].location) == (10, 0, 0), 'the baseline is the map before the FIRST Replace'
    assert olds[3].users_collection == (bpy.data.collections['Area1'],)
    print('PASS a second Replace keeps the first original as the baseline')


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
        w.writerow(['x', 0, 0, 0, 0, 0, 0, 1, 1, 1, 'Rock', ''])        # line 5: id not integer
        w.writerow(['4', 0, 0, 0])                                        # line 6: short row
        w.writerow(row(-1, 0, '', 'Rockk'))                              # line 7: near name
        w.writerow(row(-1, 0, '', 'Marker'))                             # line 8: not a mesh
        w.writerow(row(-1, 0, '', '  '))                                 # line 9: empty objname
        w.writerow(row(77, 0, 'Area1'))                                  # line 10: unknown id
        w.writerow(row(1, 5, 'Area1'))                                   # line 11: repeated id
        w.writerow(row(-1, 0, 'A//B'))                                   # line 12: odd colname
        w.writerow(row(2, 0, 'Area1', 'GoneForever'))                    # line 13: existing object, mesh missing
    p.placement_csv = str(path)
    plan = drain(placement.build_plan(p))
    by_line = {}
    for issue in plan.issues:
        by_line.setdefault(issue.line, []).append(issue)
    text = {line: ' '.join(i.message for i in issues) for line, issues in by_line.items()}
    assert 'tx' in text[3] and "'abc'" in text[3] and by_line[3][0].column == 'tx' and by_line[3][0].value == 'abc', text[3]
    assert 'sz' in text[4] and 'finite' in text[4], text[4]
    assert 'id' in text[5] and 'integer' in text[5], text[5]
    assert '4 columns' in text[6] or 'columns' in text[6], text[6]
    assert 'Rockk' in text[7] and 'Similar' in text[7] and 'Rock' in text[7], text[7]
    assert 'Marker' in text[8] and 'EMPTY' in text[8] and 'not a mesh' in text[8], text[8]
    assert 'objname is empty' in text[9], text[9]
    assert 'id 77' in text[10] and 'not used' in text[10], text[10]
    assert 'id 1' in text[11] and 'line 2' in text[11], text[11]
    assert 'A//B' in text[12], text[12]
    assert 'GoneForever' in text[13] and 'left unchanged' in text[13] and olds[2] in plan.kept_unresolved, text[13]
    errors, warnings = placement_report.counts(plan.issues)
    assert errors >= 8 and warnings >= 3, (errors, warnings)
    lines = placement_report.first_lines(plan.issues, 3)
    assert len(lines) == 3 and all(i.severity == 'error' for i in sorted(plan.issues, key=lambda i: (i.severity != 'error', i.line))[:3])
    p.dry_run = True
    assert bpy.ops.mrt.replace_zone() == {'FINISHED'}
    report = bpy.data.texts[placement_report.REPORT_TEXT].as_string()
    assert 'Line 3' in report and 'Line 13' in report and 'errors' in report
    assert p.plan_errors == errors and p.plan_warnings == warnings
    print('PASS CSV problems name the line, column, value and reason, with hints and a Text report')


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
    print('PASS file-level problems: empty file, missing columns (with the columns found), missing file (with its path)')


def test_selection_and_hide_flags_survive():
    mapc, area, olds = fixture()
    olds[2].select_set(True)
    olds[4].hide_set(True)  # a hidden object cannot stay selected
    flags = {i: (olds[i].select_get(), olds[i].hide_get()) for i in (2, 4)}
    assert flags == {2: (True, False), 4: (False, True)}, flags
    write_csv([row(1, 0, 'Area1'), row(2, 100, 'Area1'), row(4, 30, 'Area2')])
    replace()
    assert {i: (olds[i].select_get(), olds[i].hide_get()) for i in (2, 4)} == flags  # 4 also changed collection
    switch('BEFORE')
    assert {i: (olds[i].select_get(), olds[i].hide_get()) for i in (2, 4)} == flags
    switch('AFTER')
    assert {i: (olds[i].select_get(), olds[i].hide_get()) for i in (2, 4)} == flags
    print('PASS selection and hide flags survive Replace, Restore and Re-apply (link before unlink)')


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
    replace()
    layout = draw_import()
    joined = ' | '.join(layout.texts)
    assert 'Unchanged' in joined and 'Moved' in joined and 'Retire' in joined and 'errors' in joined, joined
    assert any("tx = 'abc'" in t or "'abc'" in t for t in layout.texts), layout.texts
    assert 'MRT Placement Report' in joined
    assert ('mrt.switch_map_state', 'Restore Original Map') in layout.operators, layout.operators
    p.dry_run = False
    write_csv([row(1, 0, 'Area1'), row(2, 100, 'Area1')])
    switch('BEFORE')
    layout = draw_import()
    assert ('mrt.switch_map_state', 'Re-apply Imported Map') in layout.operators, layout.operators
    assert any('ORIGINAL' in t for t in layout.texts), layout.texts
    print('PASS the Import panel shows the plan, the first problems, and the Restore / Re-apply button')


for test in (test_diff_apply, test_restore_and_reapply, test_second_replace_keeps_the_first_original,
             test_switch_rollback, test_selection_and_hide_flags_survive, test_import_panel, test_detailed_problems, test_file_level_errors):
    test()
mrt.unregister()
print('MRT_RESTORE_PASSED')
