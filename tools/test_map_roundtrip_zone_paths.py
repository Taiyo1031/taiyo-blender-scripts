"""Zone-local CSV / FBX paths, legacy path migration and .blend persistence.

blender --background --factory-startup --python-exit-code 1 --python tools/test_map_roundtrip_zone_paths.py
"""
import csv
import importlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '_Taiyo_Blender_Extensions_Repo'))
mrt = importlib.import_module('map_roundtrip_tools')
from map_roundtrip_tools import placement, ui_common
from map_roundtrip_tools.zones import ensure_zone
mrt.register()
scene = bpy.context.scene
p = scene.mrt_props
TEMP = Path(tempfile.mkdtemp(prefix='mrt-zone-paths-'))


def fixture():
    global scene, p
    scene = bpy.context.scene
    p = scene.mrt_props
    bpy.data.batch_remove(ids=list(bpy.data.objects))
    bpy.data.batch_remove(ids=list(bpy.data.collections))
    bpy.data.batch_remove(ids=list(bpy.data.meshes))
    p.zones.clear()
    p.placement_csv = p.mesh_fbx = ''
    p.running = False
    lib = bpy.data.collections.new('Library')
    scene.collection.children.link(lib)
    mesh = bpy.data.meshes.new('RockMesh')
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    lib.objects.link(bpy.data.objects.new('Rock', mesh))
    mapc = bpy.data.collections.new('Map')
    scene.collection.children.link(mapc)
    p.library_coll, p.map_coll, p.new_mesh_coll, p.archive_coll = lib, mapc, None, None
    p.name_mode = 'numeric_suffix'
    p.skip_bad_rows = False
    for zone in ('A', 'B'):
        ensure_zone(p, zone)
    p.zone_choice = 'A'
    bpy.context.view_layer.update()


def row(x):
    return [-1, x, 0, 0, 0, 0, 0, 1, 1, 1, 'Rock', '', 1]


def write_csv(rows, name):
    path = TEMP / name
    with open(path, 'w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow([*placement.CSV_COLUMNS, 'use'])
        writer.writerows(rows)
    return str(path)


def drain(generator):
    while True:
        try:
            next(generator)
        except StopIteration as done:
            return done.value


def test_zone_paths_are_independent_and_empty_fields_fall_back():
    fixture()
    p.placement_csv, p.mesh_fbx = 'Legacy.csv', 'Legacy.fbx'
    for zone in ('A', 'B'):
        entry = p.zones[zone]
        entry.csv_path, entry.fbx_path = zone + '.csv', zone + '.fbx'
    for zone in ('A', 'B', 'A'):
        p.zone_choice = zone
        chosen = p.zone_choice
        assert placement.zone_path(p, chosen, 'csv_path') == zone + '.csv'
        assert placement.zone_path(p, chosen, 'fbx_path') == zone + '.fbx'
    p.zones['A'].csv_path = ''
    assert placement.zone_path(p, 'A', 'csv_path') == 'Legacy.csv'
    assert placement.zone_path(p, 'A', 'fbx_path') == 'A.fbx'
    p.zones['A'].fbx_path = ''
    assert placement.zone_path(p, 'A', 'fbx_path') == 'Legacy.fbx'
    assert placement.zone_path(p, 'B', 'csv_path') == 'B.csv'
    assert placement.zone_path(p, 'B', 'fbx_path') == 'B.fbx'
    print('PASS switching zones uses their own paths; empty fields fall back independently')


def test_build_plan_reads_the_selected_zones_csv():
    fixture()
    p.zones['A'].csv_path = write_csv([row(10)], 'A.csv')
    p.zones['B'].csv_path = write_csv([row(20), row(21)], 'B.csv')
    assert p.placement_csv == ''
    for zone, expected_xs in (('A', [10]), ('B', [20, 21]), ('A', [10])):
        p.zone_choice = zone
        plan = drain(placement.build_plan(p))
        assert plan.zone == zone, plan.zone
        assert len(plan.rows) == len(expected_xs), (zone, plan.rows)
        assert [r[2][0] for r in plan.rows] == expected_xs, plan.rows
        assert not plan.missing_rows and not plan.invalid, plan.issues
    assert p.placement_csv == '', 'planning must not copy a zone path into the legacy field'
    print('PASS build_plan reads the selected zone CSV (one row in A, two rows in B)')


def test_rename_keeps_the_zones_paths():
    fixture()
    for zone in ('A', 'B'):
        p.zones[zone].csv_path, p.zones[zone].fbx_path = zone + '.csv', zone + '.fbx'
    assert bpy.ops.mrt.rename_zone(old_name='A', new_name='Renamed') == {'FINISHED'}
    assert p.zones.get('A') is None
    assert p.zone_choice == 'Renamed'
    assert (p.zones['Renamed'].csv_path, p.zones['Renamed'].fbx_path) == ('A.csv', 'A.fbx')
    assert (p.zones['B'].csv_path, p.zones['B'].fbx_path) == ('B.csv', 'B.fbx')
    assert placement.zone_path(p, 'Renamed', 'csv_path') == 'A.csv'
    assert placement.zone_path(p, 'Renamed', 'fbx_path') == 'A.fbx'
    print('PASS renaming preserves both paths and leaves the other zone alone')


def test_prepare_paths_migrates_legacy_paths_once():
    fixture()
    p.placement_csv, p.mesh_fbx = 'X.csv', 'Y.fbx'
    assert (p.zones['A'].csv_path, p.zones['A'].fbx_path) == ('', '')
    assert ui_common.prepare_paths(scene.name, 'A') is None
    assert (p.zones['A'].csv_path, p.zones['A'].fbx_path) == ('X.csv', 'Y.fbx')
    assert (p.placement_csv, p.mesh_fbx) == ('', '')
    before = [(z.name, z.csv_path, z.fbx_path) for z in p.zones]
    assert ui_common.prepare_paths(scene.name, 'A') is None
    assert [(z.name, z.csv_path, z.fbx_path) for z in p.zones] == before
    assert (p.placement_csv, p.mesh_fbx) == ('', '')
    assert (p.zones['B'].csv_path, p.zones['B'].fbx_path) == ('', '')
    print('PASS prepare_paths moves legacy paths into the shown zone once and clears the old fields')


def test_paths_entry_defers_creating_a_missing_entry():
    fixture()
    p.placement_csv, p.mesh_fbx = 'X.csv', 'Y.fbx'
    before = [(z.name, z.csv_path, z.fbx_path) for z in p.zones]
    assert ui_common.paths_entry(p, 'Missing') is None
    assert [(z.name, z.csv_path, z.fbx_path) for z in p.zones] == before
    assert p.zones.get('Missing') is None
    assert (p.placement_csv, p.mesh_fbx) == ('X.csv', 'Y.fbx')
    print('PASS paths_entry returns None for a missing entry without writing during the call')


def test_all_zones_and_no_selection_cannot_build_a_plan():
    fixture()
    p.placement_csv = write_csv([row(1)], 'fallback.csv')
    p.mesh_fbx = 'Fallback.fbx'
    assert placement.zone_path(p, '', 'csv_path') == p.placement_csv
    assert placement.zone_path(p, '', 'fbx_path') == 'Fallback.fbx'
    p.zone_choice = 'ALL'
    assert placement.effective_zone(p) == ''
    # '' is not an assignable RNA enum item; a minimal props stand-in covers the no-selection branch.
    none_selected = SimpleNamespace(library_coll=p.library_coll, map_coll=p.map_coll, zone_choice='')
    for props in (p, none_selected):
        try:
            drain(placement.build_plan(props))
        except ValueError as error:
            assert 'Choose the zone' in str(error), str(error)
        else:
            raise AssertionError('All Zones / no selection must refuse to build a plan')
    print('PASS All Zones and no selection use the fallback lookup but refuse to build a plan')


def test_zone_paths_survive_save_and_reopen():
    global scene, p
    fixture()
    expected = {zone: (str(TEMP / (zone + '.csv')), str(TEMP / (zone + '.fbx'))) for zone in ('A', 'B')}
    for zone, (csv_path, fbx_path) in expected.items():
        p.zones[zone].csv_path, p.zones[zone].fbx_path = csv_path, fbx_path
    p.zone_choice = 'B'
    path = str(TEMP / 'zone_paths.blend')
    assert bpy.ops.wm.save_as_mainfile(filepath=path) == {'FINISHED'}
    p.zones.clear()  # reloading must restore the saved values, not keep the current in-memory registry
    assert bpy.ops.wm.open_mainfile(filepath=path) == {'FINISHED'}
    scene = bpy.context.scene
    p = scene.mrt_props  # all pre-open RNA references are stale; the add-on remains registered
    assert {z.name: (z.csv_path, z.fbx_path) for z in p.zones} == expected
    assert p.zone_choice == 'B'
    assert (p.placement_csv, p.mesh_fbx) == ('', '')
    for zone, (csv_path, fbx_path) in expected.items():
        assert placement.zone_path(p, zone, 'csv_path') == csv_path
        assert placement.zone_path(p, zone, 'fbx_path') == fbx_path
    print('PASS both zones retain their CSV and FBX paths after saving and reopening the blend')


for test in (test_zone_paths_are_independent_and_empty_fields_fall_back, test_build_plan_reads_the_selected_zones_csv,
             test_rename_keeps_the_zones_paths, test_prepare_paths_migrates_legacy_paths_once,
             test_all_zones_and_no_selection_cannot_build_a_plan, test_zone_paths_survive_save_and_reopen,
             test_paths_entry_defers_creating_a_missing_entry):  # last: its timer must not affect save / reopen
    test()
mrt.unregister()
print('MRT_ZONE_PATHS_PASSED')
