"""Helper debug tools: zone Library selection, missing names, state counts and reports.

blender --background --factory-startup --python-exit-code 1 --python tools/test_map_roundtrip_debug_tools.py
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
from map_roundtrip_tools import helper, placement, placement_report
from map_roundtrip_tools.zones import ensure_zone
mrt.register()
scene = bpy.context.scene
p = scene.mrt_props
TEMP_DIR = tempfile.TemporaryDirectory(prefix='mrt-debug-')
TEMP = Path(TEMP_DIR.name)
REPORT = 'MRT Debug Report'


def drain(g):
    while True:
        try:
            next(g)
        except StopIteration as done:
            return done.value


def coll(name, parent):
    c = bpy.data.collections.new(name)
    parent.children.link(c)
    return c


def mesh(name):
    m = bpy.data.meshes.new(name)
    m.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    return m


def obj(name, data, collection, zone=None):
    ob = bpy.data.objects.new(name, data)
    collection.objects.link(ob)
    if zone:
        ob['ub_zone'] = zone
    return ob


def write_csv(names, name='Z1.csv'):
    path = TEMP / name
    with open(path, 'w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(placement.CSV_COLUMNS)
        for i, name in enumerate(names):
            writer.writerow([i, 0, 0, 0, 0, 0, 0, 1, 1, 1, name, ''])
    p.zones['Z1'].csv_path = str(path)
    return path


bpy.data.batch_remove(ids=list(bpy.data.objects))
lib = coll('Library', scene.collection)
mapc = coll('Map', scene.collection)
area = coll('Area', mapc)
archive = coll('_Replaced_Z1', scene.collection)
rock, tree, unused_mesh = mesh('Rock'), mesh('Tree'), mesh('Unused')
lib_rock = obj('Rock', rock, lib)
lib_tree = obj('Tree', tree, lib)
lib_unused = obj('Unused', unused_mesh, lib)
rocks = [obj(f'Rock.{i + 1:03d}', rock, area if i == 2 else mapc, 'Z1')
         for i in range(3)]
rocks[0]['ub_csv_id'] = 1
rocks[1]['ub_csv_id'] = 1
obj('Tree.001', tree, area, 'Z1')
obj('Tree.002', tree, mapc, 'Z2')
obj('Tree.003', tree, area, 'Z2')
alien = obj('Alien', mesh('Alien'), mapc, 'Z1')
outside = obj('Outside', tree, scene.collection, 'Z1')
archived = obj('Archived', unused_mesh, archive)
archived['ub_archived_from'] = 'Z1'
imported = obj('Rock.004', rock, mapc, 'Z1')
imported['ub_run'] = json.dumps({'zone': 'Z1', 'before': None})
p.library_coll, p.map_coll = lib, mapc
p.new_mesh_coll = None
ensure_zone(p, 'Z1')
ensure_zone(p, 'Z2')
p.zone_choice = 'Z1'
p.name_mode = 'numeric_suffix'
bpy.context.view_layer.update()


def select(objs):
    bpy.ops.object.select_all(action='DESELECT')
    for ob in objs:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def selected():
    return {o.name for o in bpy.context.view_layer.objects if o.select_get()}


class Reports:
    """Check execute()'s cancellation result without bpy.ops raising on ERROR reports."""
    def __init__(self):
        self.messages = []

    def report(self, levels, message):
        self.messages.append((levels, message))


def assert_cancelled(operator_type, message):
    reports = Reports()
    assert operator_type.execute(reports, bpy.context) == {'CANCELLED'}
    assert any('ERROR' in levels and message in text
               for levels, text in reports.messages), reports.messages


def test_scan_and_cached_unused():
    usage = drain(helper.scan_usage(p))
    helper.USAGE = usage
    assert helper.usage_is_valid(usage)
    # Z1: 3 Rock + 1 Tree + 1 imported Rock; Alien has no Library mesh.
    # Outside and Archived are outside Map and contribute no uses.
    assert usage.zone_counts == {'Z1': 5, 'Z2': 2}, usage.zone_counts
    assert usage.library_set == {lib_rock, lib_tree, lib_unused}, usage.library_set
    unused = helper.unused(usage)
    assert [ob.name for ob in unused] == ['Unused'], unused
    assert helper.unused(usage) is unused, 'unused() must reuse its cached list'
    print('PASS scan zone counts / Library set / cached unused (archive excluded)')


def test_zone_library_objects():
    usage = helper.USAGE
    assert [ob.name for ob in helper.zone_library_objects(usage, 'Z1')] == ['Rock', 'Tree']
    assert [ob.name for ob in helper.zone_library_objects(usage, 'Z2')] == ['Tree']
    assert helper.zone_library_objects(usage, 'Unknown') == []
    print('PASS zone Library objects')


def test_select_zone_library():
    p.zone_choice = 'Z1'
    select([alien, outside])
    assert bpy.ops.mrt.helper_select_zone_library() == {'FINISHED'}
    assert selected() == {'Rock', 'Tree'}, selected()
    usage = helper.USAGE
    try:
        p.zone_choice = 'ALL'
        assert_cancelled(helper.MRT_OT_HelperSelectZoneLibrary, 'Choose one zone')
        p.zone_choice = 'Z1'
        helper.USAGE = None
        assert_cancelled(helper.MRT_OT_HelperSelectZoneLibrary, 'Run Scan Usage first.')
    finally:
        p.zone_choice = 'Z1'
        helper.USAGE = usage
    print('PASS select zone Library / All Zones and no-scan cancellation')


def test_names_not_in_library():
    assert list(placement.CSV_COLUMNS) == [
        'id', 'tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz', 'objname', 'colname']
    path = write_csv(['Rock', 'Rock.001', 'Ghost', 'Tree'])
    missing = helper.names_not_in_library(p, helper.USAGE, 'Z1')
    assert missing['objects'] == ['Alien'], missing
    assert missing['csv'] == ['Ghost'], missing  # Rock.001 normalizes to Rock.
    assert bpy.ops.mrt.helper_missing_names() == {'FINISHED'}
    lines = bpy.data.texts[REPORT].as_string().splitlines()
    assert '# Zone: Z1' in lines and '# Names not in Library' in lines, lines
    start = lines.index('# Names not in Library')
    assert lines[start + 1:] == ['Objects (1):', 'Alien', 'CSV (1):', 'Ghost'], lines
    try:
        p.zones['Z1'].csv_path = str(TEMP / 'Missing.csv')
        missing = helper.names_not_in_library(p, helper.USAGE, 'Z1')
        assert missing == {'objects': ['Alien'], 'csv': []}, missing
    finally:
        p.zones['Z1'].csv_path = str(path)
    print('PASS missing Map / normalized CSV names / unreadable CSV / missing-names operator')


def test_zone_state_counts():
    # Link one Rock into two Map collections: it must still count once.
    area.objects.link(rocks[0])
    try:
        counts = helper.zone_state_counts(p)
    finally:
        area.objects.unlink(rocks[0])
    z1 = counts['Z1']
    assert z1['original'] == 6, z1  # 3 Rock + 1 Tree + Alien + Outside (also an original).
    assert z1['imported'] == 1, z1  # Rock.004 has ub_run.before == null for Z1.
    assert z1['archived'] == 1, z1  # Archived has ub_archived_from == Z1, no ub_zone.
    assert z1['outside'] == 1, z1  # Outside only; Archived is excluded from outside.
    assert z1['duplicate_ids'] == 1, z1  # One repeated id value (1), held by two Rocks.
    z2 = counts['Z2']
    assert z2['original'] == 2, z2  # The two Tree instances in Map.
    assert z2 == dict(original=2, imported=0, archived=0, outside=0, duplicate_ids=0), z2
    print('PASS original / imported / archived / outside / duplicate ids (one count per object)')


def test_write_text_and_reports():
    text = placement_report.write_text(REPORT, ['old content', 'must disappear'])
    rewritten = placement_report.write_text(REPORT, ['replacement'])
    assert rewritten == text, 'write_text() must reuse the existing Text datablock'
    assert rewritten.as_string() == 'replacement\n', rewritten.as_string()
    assert bpy.ops.mrt.helper_zone_state() == {'FINISHED'}
    text = bpy.data.texts[REPORT]
    state = text.as_string()
    assert 'Z1' in state and '# Zone state' in state, state
    assert 'replacement' not in state, state
    assert bpy.ops.mrt.helper_debug_report() == {'FINISHED'}
    report = bpy.data.texts[REPORT].as_string()
    assert 'Z1' in report, report
    assert report.splitlines().count('# Zone state') == 1, report
    assert report.splitlines().count('# Unused Library objects') == 1, report
    assert report.split('# Unused Library objects\n', 1)[1] == 'Unused\n', report
    text.write('sentinel: must be cleared\n')
    assert bpy.ops.mrt.helper_debug_report() == {'FINISHED'}
    assert bpy.data.texts[REPORT] == text
    assert text.as_string() == report, text.as_string()
    print('PASS write_text / zone state / repeatable debug report replaces Text contents')


def test_stale_usage():
    # usage_is_valid() probes only the first sorted Library object: delete Rock.
    usage = helper.USAGE
    assert usage.library_objects[0] == lib_rock
    bpy.data.objects.remove(lib_rock, do_unlink=True)
    assert helper.USAGE is usage
    assert helper.usage_is_valid(helper.USAGE) is False
    assert_cancelled(helper.MRT_OT_HelperSelectZoneLibrary, 'Scan Usage again.')
    print('PASS deleted Library object invalidates scan and cancels selection safely')


try:
    for test in (test_scan_and_cached_unused, test_zone_library_objects, test_select_zone_library,
                 test_names_not_in_library, test_zone_state_counts, test_write_text_and_reports,
                 test_stale_usage):
        test()
finally:
    helper.USAGE = None
    mrt.unregister()
    TEMP_DIR.cleanup()
print('MRT_DEBUG_TOOLS_PASSED')
