"""Blender integration and FBX content checks. Run with --python-exit-code 1."""
import csv
import importlib
import json
import math
from pathlib import Path
import sys
import tempfile
import bpy
from mathutils import Matrix

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '_Taiyo_Blender_Extensions_Repo'))
mrt = importlib.import_module('map_roundtrip_tools')
ubt = importlib.import_module('unreal_bridge_tools')
from map_roundtrip_tools import placement, mesh_import, fbx_export, presets
from map_roundtrip_tools.chunked import Cancelled

TEMP = Path(tempfile.mkdtemp(prefix='mrt-tests-'))


def drain(generator):
    while True:
        try:
            next(generator)
        except StopIteration as done:
            return done.value


class Harness:
    def __init__(self):
        self._error = ''
        self.result = ''
        self.messages = []
    def progress(self, phase, done, total):
        self.phase = phase
    def report(self, level, text):
        self.messages.append(text)


def reset():
    bpy.data.batch_remove(ids=list(bpy.data.objects))
    bpy.data.batch_remove(ids=list(bpy.data.collections))
    bpy.context.scene.mrt_props.library_coll = None
    bpy.context.scene.mrt_props.map_coll = None


def collection(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(c)
    return c


def obj(name, c, mesh=None):
    o = bpy.data.objects.new(name, mesh)
    c.objects.link(o)
    return o


def fixture():
    reset()
    lib, mapc = collection('Library'), collection('Map')
    mesh = bpy.data.meshes.new('RockMesh')
    mesh.from_pydata([(0,0,0), (1,0,0), (0,1,0)], [], [(0,1,2)])
    source = obj('Rock', lib, mesh)
    old = obj('Rock.001', mapc, mesh)
    old.location = (3,4,5)
    old.rotation_euler = (.1,.2,.3)
    old.scale = (1,2,3)
    old['ub_zone'] = 'ZONE_A'
    old['ub_archived_from'] = 'earlier'
    p = bpy.context.scene.mrt_props
    p.library_coll, p.map_coll = lib, mapc
    p.placement_csv = str(TEMP / 'ZONE_A.csv')
    p.zone_override = ''
    p.old_mode = 'ARCHIVE'
    p.dry_run = True
    p.if_exists = 'SKIP'
    p.name_mode = 'numeric_suffix'
    write_csv(p.placement_csv)
    bpy.context.view_layer.update()
    return p, lib, mapc, source, old


def write_csv(path, rows=None, header=None):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(header or mrt.placement.CSV_COLUMNS)
        w.writerows(rows if rows is not None else [[1,3,4,5,math.degrees(.1),math.degrees(.2),math.degrees(.3),1,2,3,'Rock','Rocks']])


def expect_error(call, text):
    try:
        call()
    except (ValueError, RuntimeError) as exc:
        assert text in str(exc), str(exc)
    else:
        raise AssertionError('Expected error: ' + text)


def test_placement():
    p, lib, mapc, source, old = fixture()
    before = set(bpy.data.objects), set(bpy.data.collections)
    assert bpy.ops.mrt.replace_zone() == {'FINISHED'}
    assert p.plan_archive == p.plan_create == 1
    assert before == (set(bpy.data.objects), set(bpy.data.collections))
    p.dry_run = False
    assert bpy.ops.mrt.replace_zone() == {'FINISHED'}
    new = [o for o in bpy.data.objects if o.get('ub_zone') == 'ZONE_A']
    assert len(new) == 1 and new[0].data == source.data
    assert new[0].parent is None and new[0].rotation_mode == 'XYZ'
    assert (new[0].location - old.location).length < 1e-5
    assert (new[0].rotation_euler.to_matrix() - old.rotation_euler.to_matrix()).to_quaternion().angle < 1e-4
    assert tuple(new[0].scale) == tuple(old.scale)
    archive = bpy.context.scene.collection.children['_Replaced_ZONE_A']
    assert old.name in archive.objects and 'ub_zone' not in old and old['ub_archived_from'] == 'ZONE_A'
    assert placement.find_layer(bpy.context.view_layer.layer_collection, archive).exclude
    assert bpy.ops.mrt.replace_zone() == {'FINISHED'}
    assert sum(o.get('ub_zone') == 'ZONE_A' for o in bpy.data.objects) == 1
    assert len(archive.objects) == 2
    p.old_mode = 'DELETE'
    assert bpy.ops.mrt.replace_zone() == {'FINISHED'}
    assert sum(o.get('ub_zone') == 'ZONE_A' for o in bpy.data.objects) == 1
    print('PASS placement preview/archive/repeat/delete/shared mesh/transforms')


def test_plan_errors():
    p, *_ = fixture()
    rows = [[1,0,0,0,0,0,0,1,1,1,'Missing',''], [2,'bad',0,0,0,0,0,1,1,1,'Rock',''], [3,'nan',0,0,0,0,0,1,1,1,'Rock','']]
    write_csv(p.placement_csv, rows)
    plan = drain(placement.build_plan(p))
    assert plan.invalid == 2 and plan.missing_rows == 1 and plan.unmatched == {'Missing'}
    write_csv(p.placement_csv, [[i,0,0,0,0,0,0,1,1,1,f'Missing{i}',''] for i in range(7)])
    many = drain(placement.build_plan(p))
    placement.publish_plan(p, many)
    assert p.plan_missing == 7 and 'Missing4' in p.plan_names and 'Missing5' not in p.plan_names and 'and 2 more' in p.plan_names
    duplicate_mesh = bpy.data.meshes.new('ExactDuplicateMesh')
    duplicate = obj('Rock.999', p.library_coll, duplicate_mesh)
    write_csv(p.placement_csv, [[1,0,0,0,0,0,0,1,1,1,'Rock.999',''],[2,0,0,0,0,0,0,1,1,1,'Rock.123','']])
    named = drain(placement.build_plan(p))
    assert named.rows[0][0] == duplicate_mesh and named.rows[1][0] != duplicate_mesh and named.duplicates == 1
    write_csv(p.placement_csv, [], ['id'])
    expect_error(lambda: drain(placement.build_plan(p)), 'Missing CSV columns')
    print('PASS invalid/nonfinite/unresolved/missing columns')


def test_rollback():
    for phase in ('Creating linked instances', 'Archiving', 'tags'):
        p, lib, mapc, source, old = fixture()
        p.dry_run = False
        old.select_set(True)
        old.hide_set(True)
        original_state = old.hide_get(), old.select_get()
        before = set(bpy.data.objects), set(bpy.data.collections)
        h = Harness()
        g = placement.MRT_OT_ReplaceZone.work(h, bpy.context)
        while True:
            next(g)
            if (phase == 'tags' and 'ub_zone' not in old) or (phase != 'tags' and getattr(h, 'phase', '') == phase):
                break
        try:
            g.throw(Cancelled('Injected ESC'))
            drain(g)
        except Cancelled:
            pass
        assert before == (set(bpy.data.objects), set(bpy.data.collections)), phase
        assert old.name in mapc.objects and old['ub_zone'] == 'ZONE_A'
        assert old['ub_archived_from'] == 'earlier'
        assert (old.hide_get(), old.select_get()) == original_state, phase
        # Re-run with an ordinary exception, not only ESC.
        h = Harness()
        g = placement.MRT_OT_ReplaceZone.work(h, bpy.context)
        while getattr(h, 'phase', '') != 'Creating linked instances':
            next(g)
        try:
            g.throw(RuntimeError('Injected failure'))
            drain(g)
        except RuntimeError:
            pass
        assert before == (set(bpy.data.objects), set(bpy.data.collections))
    print('PASS rollback during creation/archive/tag changes and exception')


def test_ubt():
    p, lib, mapc, source, old = fixture()
    u = bpy.context.scene.ubt_props
    u.filters.clear()
    u.scope = 'selected'
    u.collection = None
    u.name_mode = 'numeric_suffix'
    u.tag_zone = True
    u.export_path = str(TEMP / 'ZONE_A.csv')
    bpy.ops.object.select_all(action='DESELECT')
    old.select_set(True)
    assert bpy.ops.ubt.export_csv() == {'FINISHED'}
    assert old['ub_zone'] == 'ZONE_A'
    with open(u.export_path) as f:
        rows = list(csv.reader(f))
    assert tuple(rows[0]) == placement.CSV_COLUMNS and len(rows) == 2
    assert rows[1][-2] == 'Rock'
    bpy.ops.object.select_all(action='DESELECT')
    u.export_path = str(TEMP / 'empty.csv')
    expect_error(lambda: bpy.ops.ubt.export_csv(), 'No objects selected.')
    assert not Path(u.export_path).exists()
    # Exercise cancellation and write failure using the real UBT lifecycle harness.
    h = Harness()
    for name in dir(ubt.UBT_OT_ExportCSV):
        if name.startswith('_') and callable(getattr(ubt.UBT_OT_ExportCSV, name)) and not name.startswith('__'):
            setattr(Harness, name, getattr(ubt.UBT_OT_ExportCSV, name))
    h._timer = h._file = h._writer = None
    old.select_set(True)
    u.export_path = str(TEMP / 'ZONE_CANCEL.csv')
    old['ub_zone'] = 'BEFORE'
    assert h._initialize(bpy.context) is None
    h._process_one(bpy.context)
    h._finish(bpy.context, cancelled=True)
    assert old['ub_zone'] == 'BEFORE'
    h._timer = h._file = h._writer = None
    assert h._initialize(bpy.context) is None
    h._process_one(bpy.context)
    assert h._try_restart_to_temp(bpy.context, OSError('injected'))
    assert h._tag_targets == []
    h._finish(bpy.context, error_message='injected')
    assert old['ub_zone'] == 'BEFORE'
    # Rotated/scaled cube; numeric-suffix alias shares the zone.
    e = obj('ZONE_A', bpy.context.scene.collection)
    e.empty_display_type = 'CUBE'
    e.empty_display_size = 1
    e.location = old.location
    e.rotation_euler = (0,0,.7)
    e.scale = (2,3,4)
    e2 = obj('ZONE_A.001', bpy.context.scene.collection)
    e2.empty_display_type = 'CUBE'
    e2.empty_display_size = 1
    e2.location = (100,100,100)
    e3 = obj('ZONE_B', bpy.context.scene.collection)
    e3.empty_display_type = 'CUBE'
    e3.location = old.location
    e3.empty_display_size = 2
    u.scope = 'recursive'
    u.collection = mapc
    u.zone_choice = 'ALL'
    bpy.context.view_layer.update()
    assert bpy.ops.ubt.select_in_zone() == {'FINISHED'}
    assert set(bpy.context.selected_objects) == {old}
    assert 'ZONE_A 1' in u.zone_result and 'ZONE_B 0' in u.zone_result
    hidden = obj('HiddenRock', mapc, source.data)
    hidden.location = old.location
    bpy.context.view_layer.update()
    hidden.hide_set(True)
    assert bpy.ops.ubt.select_in_zone() == {'FINISHED'}
    assert set(bpy.context.selected_objects) == {old}
    bpy.data.batch_remove(ids=[e,e2,e3])
    expect_error(lambda: bpy.ops.ubt.select_in_zone(), 'No zone empties found')
    print('PASS UBT selected/empty/cancel/retry/rotated-scaled-overlap/hidden/empty zones')


def test_fbx():
    p, lib, mapc, source, old = fixture()
    bpy.ops.object.select_all(action='DESELECT')
    source.select_set(True)
    old.select_set(True)
    bpy.context.view_layer.objects.active = old
    selected = set(bpy.context.selected_objects)
    p.fbx_out_dir = str(TEMP / 'fbx')
    p.fbx_files = 'PER_OBJECT'
    assert p.fbx_vertex_colors == 'LINEAR'
    # Include a color attribute in exported data.
    colors = source.data.color_attributes.new(name='Color', type='FLOAT_COLOR', domain='CORNER')
    for c in colors.data:
        c.color = (.1,.3,.7,1)
    assert bpy.ops.mrt.export_fbx() == {'FINISHED'}
    assert set(bpy.context.selected_objects) == selected and bpy.context.view_layer.objects.active == old
    files = sorted(Path(p.fbx_out_dir).glob('*.fbx'))
    assert len(files) == 2
    before = set(bpy.data.objects)
    mesh_import.fbx_import(str(files[0]))
    fresh = set(bpy.data.objects) - before
    imported_meshes = [o for o in fresh if o.type == 'MESH']
    assert len(imported_meshes) == 1, 'temp_override exported extra objects'
    assert imported_meshes[0].data.color_attributes, 'Vertex colors missing'
    bpy.data.batch_remove(ids=fresh)
    # Imported name Rock should resolve to existing Library object despite .001 collision.
    p.mesh_fbx = str(Path(p.fbx_out_dir) / 'Rock.fbx')
    p.if_exists = 'SKIP'
    before = set(bpy.data.objects)
    assert bpy.ops.mrt.import_meshes() == {'FINISHED'}
    assert before == set(bpy.data.objects)
    shared = old.data
    p.if_exists = 'UPDATE'
    assert bpy.ops.mrt.import_meshes() == {'FINISHED'}
    assert old.data == source.data and source.data != shared
    assert before == set(bpy.data.objects)
    # A genuinely new mesh, with same-base material reuse.
    mat = bpy.data.materials.new('Stone')
    source.data.materials.append(mat)
    source.name = 'NewRock'
    bpy.ops.object.select_all(action='DESELECT')
    source.select_set(True)
    p.fbx_files = 'COMBINED'
    p.zone_name = 'new mesh'
    assert bpy.ops.mrt.export_fbx() == {'FINISHED'}
    source.name = 'Rock'
    p.mesh_fbx = str(Path(p.fbx_out_dir) / 'new_mesh.fbx')
    p.if_exists = 'SKIP'
    assert bpy.ops.mrt.import_meshes() == {'FINISHED'}
    target = lib.children['FromHoudini']
    assert len(target.objects) == 1 and target.objects[0].data.materials[0] == mat
    assert not any(m.name.startswith('Stone.') for m in bpy.data.materials)
    # Twelve per-object outputs, sanitization and existing-path collision.
    bpy.ops.object.select_all(action='DESELECT')
    for i in range(12):
        o = obj(f'Asset.{i}', mapc, source.data)
        o.select_set(True)
    p.fbx_files = 'PER_OBJECT'
    p.fbx_out_dir = str(TEMP / 'twelve')
    assert bpy.ops.mrt.export_fbx() == {'FINISHED'}
    assert len(list(Path(p.fbx_out_dir).glob('*.fbx'))) == 12
    assert all('.' not in f.stem for f in Path(p.fbx_out_dir).glob('*.fbx'))
    assert bpy.ops.mrt.export_fbx() == {'FINISHED'}
    assert len(list(Path(p.fbx_out_dir).glob('*.fbx'))) == 24
    print('PASS FBX override content/per-object/combined/selection/linear-color payload/SKIP/UPDATE/materials')
    print('FBX_IMPORTER', mesh_import.LAST_IMPORTER)



def test_import_rollback_and_fallback():
    from types import SimpleNamespace
    original_bpy = mesh_import.bpy
    called = []
    def absent(**kwargs):
        raise AttributeError('no new importer')
    def legacy(**kwargs):
        called.append(kwargs['filepath'])
        return {'FINISHED'}
    try:
        mesh_import.bpy = SimpleNamespace(data=original_bpy.data, ops=SimpleNamespace(wm=SimpleNamespace(fbx_import=absent), import_scene=SimpleNamespace(fbx=legacy)))
        mesh_import.fbx_import('fallback.fbx')
        assert called == ['fallback.fbx'] and mesh_import.LAST_IMPORTER == 'import_scene.fbx'
    finally:
        mesh_import.bpy = original_bpy
    p, lib, mapc, source, old = fixture()
    bpy.ops.object.select_all(action='DESELECT')
    source.select_set(True)
    p.fbx_out_dir = str(TEMP / 'rollback-fbx')
    p.fbx_files = 'PER_OBJECT'
    bpy.ops.mrt.export_fbx()
    p.mesh_fbx = str(TEMP / 'rollback-fbx/Rock.fbx')
    p.if_exists = 'UPDATE'
    original_mesh = old.data
    before = mesh_import.data_snapshot()
    h = Harness()
    g = mesh_import.MRT_OT_ImportMeshes.work(h, bpy.context)
    while old.data == original_mesh:
        next(g)
    try:
        g.throw(Cancelled('Injected import ESC'))
        drain(g)
    except Cancelled:
        pass
    assert old.data == source.data == original_mesh
    assert mesh_import.data_snapshot() == before
    source.name = 'DifferentLibraryAsset'
    p.if_exists = 'SKIP'
    before = mesh_import.data_snapshot()
    h = Harness()
    g = mesh_import.MRT_OT_ImportMeshes.work(h, bpy.context)
    while p.library_coll.children.get('FromHoudini') is None:
        next(g)
    try:
        g.throw(Cancelled('Injected new target ESC'))
        drain(g)
    except Cancelled:
        pass
    assert mesh_import.data_snapshot() == before
    print('PASS FBX fallback / UPDATE rollback / new collection rollback')


def test_presets():
    presets.PATH_OVERRIDE = str(TEMP / 'presets.json')
    p = bpy.context.scene.mrt_props
    presets.save({'Test': {'fbx_vertex_colors':'garbage', 'fbx_scale':2.0, 'fbx_tangent':'bad'}})
    p.fbx_preset = 'Test'
    assert p.fbx_vertex_colors == 'LINEAR' and p.fbx_scale == 2 and not p.fbx_tangent
    assert bpy.ops.mrt.delete_preset() == {'FINISHED'}
    assert p.fbx_preset == 'Unreal SM (Default)'
    assert bpy.ops.mrt.save_preset(preset_name='Saved') == {'FINISHED'}
    assert set(presets.load()['Saved']) == set(mrt.presets.FBX_DEFAULTS)
    print('PASS presets/defaults/validation/save/delete')


mrt.register()
ubt.register()
try:
    test_placement()
    test_plan_errors()
    test_rollback()
    test_ubt()
    test_fbx()
    test_import_rollback_and_fallback()
    test_presets()
    print('MAP_ROUNDTRIP_INTEGRATION_PASSED', TEMP)
finally:
    ubt.unregister()
    mrt.unregister()
