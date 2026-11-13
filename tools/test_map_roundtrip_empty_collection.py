"""Add Selected Objects puts each new Empty in the collection of the objects it was made from.

blender --background --factory-startup --python-exit-code 1 --python tools/test_map_roundtrip_empty_collection.py
"""
import importlib
from pathlib import Path
import sys
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '_Taiyo_Blender_Extensions_Repo'))
mrt = importlib.import_module('map_roundtrip_tools')
from map_roundtrip_tools.chunked import Cancelled
from map_roundtrip_tools.zones import zone_empties, zone_name
mrt.register()
scene = bpy.context.scene
p = scene.mrt_props
mesh = bpy.data.meshes.new('M')
Operator = mrt.zone_add_objects.MRT_OT_AddObjectsToZone


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
    p.zones.clear()
    p.zone_scope = 'SCENE'
    p.zone_choice = 'ALL'
    p.merge_distance = 5.0
    assert bpy.ops.mrt.new_zone(name='ZONE_A') == {'FINISHED'}


def coll(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or scene.collection).children.link(c)
    return c


def mk(name, x, *collections):
    ob = bpy.data.objects.new(name, mesh)
    ob.location = (x, 0, 0)
    for c in collections:
        c.objects.link(ob)
    return ob


def run(objs):
    bpy.context.view_layer.update()
    bpy.ops.object.select_all(action='DESELECT')
    for ob in objs:
        ob.select_set(True)
    assert bpy.ops.mrt.add_objects_to_zone() == {'FINISHED'}, p.status


def empties():
    return {round(e.location.x): e for e in zone_empties(scene, p.zone_prefix) if zone_name(e) == 'ZONE_A'}


def test_each_empty_goes_to_its_collection():
    reset()
    a, b = coll('A'), coll('B')
    child = coll('Child', b)
    objs = [mk('a0', 0, a), mk('a1', 1, a), mk('b0', 50, b), mk('c0', 100, child), mk('r0', 150, scene.collection)]
    run(objs)
    found = empties()
    assert len(found) == 4, found.keys()  # a0 and a1 merge into one empty
    assert [e for e in found.values() if round(e.location.x) in (0, 1)][0].users_collection == (a,)
    assert found[50].users_collection == (b,) and found[100].users_collection == (child,)
    assert found[150].users_collection == (scene.collection,)
    print('PASS each empty is linked to the collection of its objects (nested and scene root too)')


def test_majority_and_report():
    reset()
    a, b = coll('A'), coll('B')
    run([mk('x0', 200, a), mk('x1', 201, b), mk('x2', 202, b)])
    found = empties()
    assert len(found) == 1
    assert next(iter(found.values())).users_collection == (b,)  # two of three objects are in B
    assert 'mixed-collection empties 1' in p.status, p.status
    print('PASS a merged empty goes to the majority collection and the mix is reported')


def test_tie_goes_to_the_first_collection_in_the_scene():
    reset()
    a, b = coll('A'), coll('B')
    run([mk('t0', 300, b), mk('t1', 301, a)])
    assert next(iter(empties().values())).users_collection == (a,)  # A comes first in the scene
    print('PASS a tie goes to the collection that comes first in the scene')


def test_object_in_two_collections_and_unlinked_collection():
    reset()
    a, b = coll('A'), coll('B')
    run([mk('m0', 400, b, a)])
    assert next(iter(empties().values())).users_collection == (a,)  # first in the scene, not link order
    reset()
    hidden = bpy.data.collections.new('NotInScene')  # never linked to the scene
    ob = mk('u0', 500, hidden, scene.collection)
    run([ob])
    assert next(iter(empties().values())).users_collection == (scene.collection,)
    print('PASS an object in two collections uses the first one in the scene; collections outside the scene are ignored')


def test_cancel_removes_empties_from_their_collections():
    reset()
    a, b = coll('A'), coll('B')
    objs = [mk(f'o{i}', 700 + i * 20, a if i % 2 else b) for i in range(300)]
    p.merge_distance = 0.0
    bpy.context.view_layer.update()
    bpy.ops.object.select_all(action='DESELECT')
    for ob in objs:
        ob.select_set(True)
    before = len(bpy.data.objects)
    h = Harness()
    g = Operator.work(h, bpy.context)
    while getattr(h, 'phase', '') != 'Creating zone empties':
        next(g)
    next(g)  # one more step: the empties of the first batch exist now
    assert len(bpy.data.objects) > before
    try:
        g.throw(Cancelled('Injected ESC'))
        while True:
            next(g)
    except (Cancelled, StopIteration):
        pass
    assert len(bpy.data.objects) == before and not empties()
    assert all(o.type == 'MESH' for c in (a, b) for o in c.objects), 'no empty may stay linked to a collection'
    print('PASS ESC removes the new empties from every collection')


for test in (test_each_empty_goes_to_its_collection, test_majority_and_report,
             test_tie_goes_to_the_first_collection_in_the_scene,
             test_object_in_two_collections_and_unlinked_collection,
             test_cancel_removes_empties_from_their_collections):
    test()
mrt.unregister()
print('MRT_EMPTY_COLLECTION_PASSED')
