"""Archive To: where `_Replaced_<Zone>` is created, and what is refused.

blender --background --factory-startup --python-exit-code 1 --python tools/test_map_roundtrip_archive_dest.py
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
TEMP = Path(tempfile.mkdtemp(prefix='mrt-archive-dest-'))


def make(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or scene.collection).children.link(c)
    return c


def fixture():
    bpy.data.batch_remove(ids=list(bpy.data.objects))
    bpy.data.batch_remove(ids=list(bpy.data.collections))
    m = bpy.data.meshes.get('RockMesh') or bpy.data.meshes.new('RockMesh')
    if not m.vertices:
        m.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    lib = make('Library')
    lib.objects.link(bpy.data.objects.new('Rock', m))
    mapc = make('Map')
    for csv_id in (1, 2, 3):
        o = bpy.data.objects.new(f'Rock.{csv_id:03d}', m)
        o['ub_zone'] = 'ZONE_A'
        o['ub_csv_id'] = csv_id
        mapc.objects.link(o)
    path = TEMP / 'ZONE_A.csv'
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(placement.CSV_COLUMNS)
        w.writerow([1, 0, 0, 0, 0, 0, 0, 1, 1, 1, 'Rock', ''])  # ids 2 and 3 have no row: they are retired
    p.library_coll, p.map_coll, p.new_mesh_coll, p.archive_coll = lib, mapc, None, None
    p.placement_csv = str(path)
    p.zone_override = ''
    p.dry_run = False
    p.name_mode = 'numeric_suffix'
    bpy.context.view_layer.update()
    return lib, mapc


def replace():
    try:
        return bpy.ops.mrt.replace_zone()
    except RuntimeError:
        return {'CANCELLED'}


def test_default_is_the_scene_root():
    fixture()
    assert replace() == {'FINISHED'}, p.status
    archive = bpy.data.collections['_Replaced_ZONE_A']
    assert archive in scene.collection.children[:]
    print('PASS without Archive To the archive is a child of the scene root')


def test_archive_goes_to_the_chosen_collection():
    fixture()
    backup = make('Backups')
    inner = make('Inner', backup)
    p.archive_coll = inner
    assert replace() == {'FINISHED'}, p.status
    archive = bpy.data.collections['_Replaced_ZONE_A']
    assert archive in inner.children[:] and archive not in scene.collection.children[:]
    home = bpy.data.objects['Rock.002'].users_collection[0]
    assert home == archive or home in archive.children_recursive, home.name
    layer = placement.find_layer(bpy.context.view_layer.layer_collection, archive)
    assert layer is not None and layer.exclude, 'the archive stays excluded from the view layer'
    # Restore / Re-apply still find it by name
    assert bpy.ops.mrt.switch_map_state(target='BEFORE', zone='ZONE_A') == {'FINISHED'}, p.status
    assert bpy.data.objects['Rock.002'].get('ub_zone') == 'ZONE_A'
    assert bpy.ops.mrt.switch_map_state(target='AFTER', zone='ZONE_A') == {'FINISHED'}, p.status
    assert bpy.data.objects['Rock.002'].get('ub_zone') is None
    # A second Replace keeps using the archive where it is, even if Archive To changed
    p.archive_coll = None
    assert replace() == {'FINISHED'}, p.status
    assert archive in inner.children[:] and len([c for c in bpy.data.collections if c.name.startswith('_Replaced_ZONE_A')]) == 1
    print('PASS the archive is made in Archive To, stays excluded, and Restore / Re-apply still work')


def test_refused_destinations_change_nothing():
    for kind in ('map', 'inside_map', 'library', 'inside_library', 'not_in_scene'):
        lib, mapc = fixture()  # collections are made again each time, so choose the bad one after the fixture
        bad = {'map': mapc, 'inside_map': make('InMap', mapc), 'library': lib, 'inside_library': make('InLib', lib),
               'not_in_scene': bpy.data.collections.new('NotInScene')}[kind]
        p.archive_coll = bad
        assert replace() == {'CANCELLED'}, kind
        assert 'Archive To' in p.status, p.status
        assert bpy.data.collections.get('_Replaced_ZONE_A') is None
        assert all(o.get('ub_zone') == 'ZONE_A' for o in bpy.data.objects if o.name.startswith('Rock.')), kind
    print('PASS Archive To inside Map / Library or outside the scene is refused before anything changes')


for test in (test_default_is_the_scene_root, test_archive_goes_to_the_chosen_collection,
             test_refused_destinations_change_nothing):
    test()
mrt.unregister()
print('MRT_ARCHIVE_DEST_PASSED')
