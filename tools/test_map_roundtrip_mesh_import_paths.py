"""Import New Meshes: user-chosen destination and a structure taken from the CSV colname.

blender --background --factory-startup --python-exit-code 1 --python tools/test_map_roundtrip_mesh_import_paths.py
"""
import csv
import importlib
from pathlib import Path
import sys
import tempfile
import bpy
from mathutils import Euler, Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '_Taiyo_Blender_Extensions_Repo'))
mrt = importlib.import_module('map_roundtrip_tools')
from map_roundtrip_tools import mesh_import, placement
from map_roundtrip_tools.zones import ensure_zone
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
    ensure_zone(p, 'Z')
    p.zone_choice = 'Z'
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


def test_destination_outside_library_is_searched(fbx):
    lib, mapc = fixture(fbx)
    outside = bpy.data.collections.new('NewOBJs')  # next to Library, not below it
    bpy.context.scene.collection.children.link(outside)
    p.new_mesh_coll = outside
    write_csv([('NewA', ''), ('NewB', ''), ('Rock', '')])
    run()
    plan = drain(placement.build_plan(p))
    assert not plan.missing_rows and len(plan.rows) == 3, (plan.missing_rows, plan.rows, [i.message for i in plan.issues])
    # The same collection inside Map must never count as Library
    inside = bpy.data.collections.new('InMap')
    mapc.children.link(inside)
    p.new_mesh_coll = inside
    assert 'InMap' not in [c.name for c in placement.walk_library(p)]
    print('PASS meshes imported outside Library are found by the plan; a destination inside Map is ignored')


def test_fbx_object_transform_is_baked_into_the_mesh(fbx):
    """A Y-up/cm FBX (Houdini) arrives as rotation 90 deg / scale 0.01 over raw mesh data; placement only uses the mesh."""
    lib, mapc = fixture(fbx)
    original = mesh_import.fbx_import

    def fake_import(path):
        for name, shift in (('HouA', 0.0), ('HouB', 500.0)):
            m = bpy.data.meshes.new(name)
            m.from_pydata([(shift, 0, 0), (shift + 100, 0, 0), (shift, 0, 300)], [], [(0, 1, 2)])  # 3 m tall after scaling
            ob = bpy.data.objects.new(name, m)
            ob.rotation_euler = Euler((1.5707963, 0, 0))
            ob.scale = (0.01, 0.01, 0.01)
            bpy.context.scene.collection.objects.link(ob)
        return {'FINISHED'}

    mesh_import.fbx_import = fake_import
    p.convert_houdini_fbx = True
    try:
        h = run()
    finally:
        mesh_import.fbx_import = original
    a, b = bpy.data.objects['HouA'], bpy.data.objects['HouB']
    for ob in (a, b):
        assert ob.matrix_basis == Matrix.Identity(4) and tuple(ob.scale) == (1, 1, 1), (ob.name, ob.rotation_euler, ob.scale)
    # raw (0,0,300) -> rotate X 90 deg -> (0,-300,0) -> scale 0.01 -> (0,-3,0)
    assert (a.data.vertices[2].co - Vector((0, -3, 0))).length < 1e-4, a.data.vertices[2].co
    assert (b.data.vertices[0].co - Vector((5, 0, 0))).length < 1e-4, b.data.vertices[0].co
    assert 'baked into 2 meshes' in h.result, h.result
    print('PASS with the checkbox on, the FBX object transform (rotation, scale) is baked into the imported mesh data')


def test_fbx_conversion_is_off_by_default(fbx):
    assert p.bl_rna.properties['convert_houdini_fbx'].default is False
    lib, mapc = fixture(fbx)
    p.convert_houdini_fbx = False
    original = mesh_import.fbx_import

    def fake_import(path):
        m = bpy.data.meshes.new('HouC')
        m.from_pydata([(0, 0, 0), (100, 0, 0), (0, 0, 300)], [], [(0, 1, 2)])
        ob = bpy.data.objects.new('HouC', m)
        ob.rotation_euler = Euler((1.5707963, 0, 0))
        ob.scale = (0.01, 0.01, 0.01)
        bpy.context.scene.collection.objects.link(ob)
        return {'FINISHED'}

    mesh_import.fbx_import = fake_import
    try:
        h = run()
    finally:
        mesh_import.fbx_import = original
    c = bpy.data.objects['HouC']
    assert all(abs(v - 0.01) < 1e-6 for v in c.scale) and abs(c.rotation_euler.x - 1.5707963) < 1e-6, (c.rotation_euler, c.scale)
    assert (c.data.vertices[2].co - Vector((0, 0, 300))).length < 1e-4, c.data.vertices[2].co  # the mesh data is not touched
    assert 'baked' not in h.result, h.result
    print('PASS with the checkbox off (default) the FBX is imported as it is')


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


def test_linear_vertex_colors(fbx):
    operators = {'wm.fbx_import': bpy.ops.wm.fbx_import, 'import_scene.fbx': bpy.ops.import_scene.fbx}
    for name, operator in operators.items():
        options = mesh_import.linear_color_options(operator)
        assert options in ({}, {'import_colors': 'LINEAR'}, {'colors_type': 'LINEAR'}), (name, options)
        try:
            properties = operator.get_rna_type().properties
        except (AttributeError, KeyError, RuntimeError):
            assert options == {}, (name, options)
            continue  # this Blender version may provide only one of the two importers
        supported = [key for key in ('import_colors', 'colors_type')
                     if key in properties and 'LINEAR' in {item.identifier for item in properties[key].enum_items}]
        expected = {supported[0]: 'LINEAR'} if supported else {}
        assert options == expected, (name, options, expected)

    fixture(fbx)  # build_fbx() exported two tiny triangles; it does not create color attributes
    before_meshes = set(bpy.data.meshes)
    assert mesh_import.fbx_import(fbx) == {'FINISHED'}
    imported = set(bpy.data.meshes) - before_meshes
    assert imported and all(len(mesh.vertices) == 3 for mesh in imported), [mesh.name for mesh in imported]
    assert mesh_import.LAST_IMPORTER in operators, mesh_import.LAST_IMPORTER
    expected = mesh_import.linear_color_options(operators[mesh_import.LAST_IMPORTER])
    assert mesh_import.LAST_IMPORT_OPTIONS == expected, (mesh_import.LAST_IMPORTER, mesh_import.LAST_IMPORT_OPTIONS, expected)
    if mesh_import.LAST_IMPORT_OPTIONS:
        assert len(mesh_import.LAST_IMPORT_OPTIONS) == 1
        assert list(mesh_import.LAST_IMPORT_OPTIONS.values()) == ['LINEAR']
    print('PASS runtime importer RNA chooses only a supported LINEAR option and fbx_import records that option')


def build_swap_fbx():
    """Export Rock with four vertices and Fresh, using the same exporter as build_fbx()."""
    bpy.data.batch_remove(ids=list(bpy.data.objects))
    bpy.data.batch_remove(ids=list(bpy.data.collections))
    bpy.data.batch_remove(ids=list(bpy.data.meshes))
    for name, vertices, faces in (
            ('Rock', [(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)], [(0, 1, 2, 3)]),
            ('Fresh', [(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 1, 2)])):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(vertices, [], faces)
        bpy.context.scene.collection.objects.link(bpy.data.objects.new(name, mesh))
    bpy.ops.object.select_all(action='DESELECT')
    for ob in bpy.data.objects:
        ob.select_set(True)
    p.fbx_out_dir = str(TEMP)
    p.fbx_files = 'COMBINED'
    p.zone_name = 'swap_meshes'
    assert bpy.ops.mrt.export_fbx() == {'FINISHED'}
    path = TEMP / 'swap_meshes.fbx'
    assert path.is_file(), path
    return str(path)


def run_swap():
    h = Harness()
    h.swap = True
    drain(mesh_import.MRT_OT_SwapMeshes.work(h, bpy.context))
    return h


def test_swap_meshes(fbx):
    swap_fbx = build_swap_fbx()
    lib, mapc = fixture(swap_fbx)
    entry = p.zones['Z']
    entry.csv_path, entry.fbx_path = '', swap_fbx
    p.mesh_fbx = ''  # the operator must read Z's path, with no legacy fallback available
    p.convert_houdini_fbx = False
    p.if_exists = 'SKIP'  # Swap always replaces same-name meshes, regardless of this setting
    rock = lib.objects['Rock']
    old_mesh = rock.data
    old_name = old_mesh.name
    old_pointer = old_mesh.as_pointer()
    placed = []
    for index in range(2):
        ob = bpy.data.objects.new(f'Rock.{index + 1:03d}', old_mesh)
        ob['ub_zone'] = 'Z'
        mapc.objects.link(ob)
        placed.append(ob)
    bpy.context.view_layer.update()
    assert len(old_mesh.vertices) == 3
    before = {kind: set(getattr(bpy.data, kind)) for kind in ('objects', 'meshes', 'materials', 'collections')}
    coordinates = [tuple(vertex.co) for vertex in old_mesh.vertices]
    old_properties = dict(old_mesh.items())
    imported_count = p.plan_new_meshes_imported

    p.dry_run = True
    h = run_swap()
    assert h.result.startswith('Swap preview: replace 1 meshes, add 1 new,'), h.result
    for kind, items in before.items():
        assert set(getattr(bpy.data, kind)) == items, ('Dry Run left changed data', kind)
    assert bpy.data.meshes.get(old_name) == old_mesh and len(old_mesh.vertices) == 3
    assert rock.data == old_mesh and all(ob.data == old_mesh for ob in placed)
    assert [tuple(vertex.co) for vertex in old_mesh.vertices] == coordinates
    assert dict(old_mesh.items()) == old_properties
    assert bpy.data.objects.get('Fresh') is None
    assert p.plan_new_meshes_imported == imported_count

    p.dry_run = False
    h = run_swap()
    new_mesh = rock.data
    assert new_mesh.as_pointer() != old_pointer, 'Swap must replace the mesh data block'
    assert new_mesh.name == old_name and bpy.data.meshes.get(old_name) == new_mesh
    assert len(new_mesh.vertices) == 4, len(new_mesh.vertices)
    assert all(ob.data == new_mesh and ob.get('ub_zone') == 'Z' for ob in placed)
    assert all(ob in mapc.objects[:] for ob in placed)
    fresh = bpy.data.objects.get('Fresh')
    assert fresh is not None and fresh.type == 'MESH', h.result
    assert any(fresh in collection.objects[:] for collection in placement.walk_collections(lib))
    for mesh in (new_mesh, fresh.data):
        assert mesh.get('mrt_src_fbx') == swap_fbx, (mesh.name, dict(mesh.items()))
        assert mesh.get('mrt_src_zone') == 'Z', (mesh.name, dict(mesh.items()))
    assert p.if_exists == 'SKIP'
    print('PASS Swap previews without changing data, then replaces shared Rock despite SKIP and adds Fresh with source tags')


fbx = build_fbx()
for test in (test_default_destination_and_no_csv, test_user_chosen_destination, test_structure_follows_colname,
             test_existing_structure_is_reused_and_conflicts_warn, test_destination_outside_library_is_searched, test_fbx_object_transform_is_baked_into_the_mesh,
             test_fbx_conversion_is_off_by_default,
             test_cancel_removes_new_collections, test_linear_vertex_colors, test_swap_meshes):
    test(fbx)
mrt.unregister()
print('MRT_MESH_IMPORT_PATHS_PASSED')
