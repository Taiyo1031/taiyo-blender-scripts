"""Import New Meshes: user-chosen destination and a structure taken from the CSV colname.

blender --background --factory-startup --python-exit-code 1 --python tools/test_map_roundtrip_mesh_import_paths.py
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
from map_roundtrip_tools import mesh_import
from map_roundtrip_tools.chunked import Cancelled
mrt.register()
p = bpy.context.scene.mrt_props
TEMP = Path(tempfile.mkdtemp(prefix='mrt-mesh-paths-'))


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


def build_fbx():
    """Write one FBX that holds NewA and NewB (new meshes) and return its path."""
    bpy.data.batch_remove(ids=list(bpy.data.objects))
    bpy.data.batch_remove(ids=list(bpy.data.collections))
    for name in ('NewA', 'NewB'):
        m = bpy.data.meshes.new(name)
        m.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
        bpy.context.scene.collection.objects.link(bpy.data.objects.new(name, m))
    bpy.ops.object.select_all(action='DESELECT')
    for ob in bpy.data.objects:
        ob.select_set(True)
    p.fbx_out_dir = str(TEMP)
    p.fbx_files = 'COMBINED'
    p.zone_name = 'new_meshes'
    assert bpy.ops.mrt.export_fbx() == {'FINISHED'}
    return str(TEMP / 'new_meshes.fbx')


def fixture(fbx):
    bpy.data.batch_remove(ids=list(bpy.data.objects))
    bpy.data.batch_remove(ids=list(bpy.data.collections))
    bpy.data.batch_remove(ids=list(bpy.data.meshes))
    lib = bpy.data.collections.new('Library')
    bpy.context.scene.collection.children.link(lib)
    m = bpy.data.meshes.new('Rock')
    m.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    lib.objects.link(bpy.data.objects.new('Rock', m))
    mapc = bpy.data.collections.new('Map')
    bpy.context.scene.collection.children.link(mapc)
    p.library_coll, p.map_coll = lib, mapc
    p.mesh_fbx = fbx
    p.new_mesh_coll = None
    p.placement_csv = ''
    p.if_exists = 'SKIP'
    p.name_mode = 'numeric_suffix'
    return lib, mapc


def write_csv(rows):
    path = TEMP / 'return.csv'
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['id', 'tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz', 'objname', 'colname'])
        for i, (name, col) in enumerate(rows):
            w.writerow([-1, i, 0, 0, 0, 0, 0, 1, 1, 1, name, col])
    p.placement_csv = str(path)


def run():
    h = Harness()
    drain(mesh_import.MRT_OT_ImportMeshes.work(h, bpy.context))
    return h


def where(name):
    return bpy.data.objects[name].users_collection[0]


def test_default_destination_and_no_csv(fbx):
    lib, mapc = fixture(fbx)
    run()
    root = lib.children['FromHoudini']
    assert where('NewA') == root and where('NewB') == root
    print('PASS no CSV: both meshes go straight under Library/FromHoudini')


def test_user_chosen_destination(fbx):
    lib, mapc = fixture(fbx)
    mine = bpy.data.collections.new('MyNew')
    lib.children.link(mine)
    p.new_mesh_coll = mine
    run()
    assert where('NewA') == mine and where('NewB') == mine and 'FromHoudini' not in lib.children
    print('PASS the destination collection chosen by the user is used')


def test_structure_follows_colname(fbx):
    lib, mapc = fixture(fbx)
    write_csv([('NewA', 'Area2/NewRocks'), ('NewA', 'Area2/NewRocks'), ('NewB', '')])
    run()
    root = lib.children['FromHoudini']
    a = where('NewA')
    assert a.name == 'NewRocks [FromHoudini]' and a.get('ub_mirror_of') == 'NewRocks'
    area2 = next(c for c in root.children if c.get('ub_mirror_of') == 'Area2')
    assert a in area2.children[:] and area2.name == 'Area2 [FromHoudini]'
    assert where('NewB') == root  # empty colname -> straight under the destination
    print('PASS the colname hierarchy is rebuilt (as mirrors) under the destination')


def test_existing_structure_is_reused_and_conflicts_warn(fbx):
    lib, mapc = fixture(fbx)
    write_csv([('NewA', 'Area2/NewRocks'), ('NewA', 'Area3'), ('NewA', 'Area2/NewRocks'), ('NewB', 'Area2/NewRocks')])
    h = run()
    root = lib.children['FromHoudini']
    a, b = where('NewA'), where('NewB')
    assert a == b and a.get('ub_mirror_of') == 'NewRocks'  # NewA: Area2/NewRocks is the most common
    assert any('NewA' in m and ('Area3' in m or 'several' in m) for m in h.messages), h.messages
    count = len(bpy.data.collections)
    # running the import again reuses the collections it made
    for ob in (bpy.data.objects['NewA'], bpy.data.objects['NewB']):
        bpy.data.objects.remove(ob)
    run()
    assert len(bpy.data.collections) == count, 'mirror collections must be reused, not duplicated'
    print('PASS the most common colname wins, several colnames warn, mirrors are reused')


def test_cancel_removes_new_collections(fbx):
    lib, mapc = fixture(fbx)
    write_csv([('NewA', 'Area2/NewRocks'), ('NewB', 'Area9/Deep/Er')])
    before_collections = set(bpy.data.collections)
    before_objects = set(bpy.data.objects)
    h = Harness()
    g = mesh_import.MRT_OT_ImportMeshes.work(h, bpy.context)
    while not any(c.get('ub_mirror_of') for c in bpy.data.collections):
        next(g)
    try:
        g.throw(Cancelled('Injected ESC'))
        drain(g)
    except Cancelled:
        pass
    assert set(bpy.data.collections) == before_collections and set(bpy.data.objects) == before_objects
    print('PASS ESC removes the collections made for the structure')


fbx = build_fbx()
for test in (test_default_destination_and_no_csv, test_user_chosen_destination, test_structure_follows_colname,
             test_existing_structure_is_reused_and_conflicts_warn, test_cancel_removes_new_collections):
    test(fbx)
mrt.unregister()
print('MRT_MESH_IMPORT_PATHS_PASSED')
