"""Add Selected Objects: merge nearby origins, never capture unselected meshes."""
import importlib
from pathlib import Path
import sys
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '_Taiyo_Blender_Extensions_Repo'))
mrt = importlib.import_module('map_roundtrip_tools')
from map_roundtrip_tools.zones import zone_empties, zone_name
mrt.register()
scene = bpy.context.scene
p = scene.mrt_props
mesh = bpy.data.meshes.new('M')
Operator = mrt.zone_add_objects.MRT_OT_AddObjectsToZone


def cancelled(operator):
    """bpy.ops reports an operator error either as {'CANCELLED'} or as RuntimeError."""
    try:
        return operator() == {'CANCELLED'}
    except RuntimeError:
        return True
assert 'UNDO' in Operator.bl_options


def reset():
    bpy.data.batch_remove(ids=list(bpy.data.objects))
    p.zones.clear()
    p.zone_scope = 'SCENE'
    p.zone_choice = 'ALL'


def mk(name, xyz):
    ob = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(ob)
    ob.location = xyz
    return ob


def select(objs):
    bpy.ops.object.select_all(action='DESELECT')
    for ob in objs:
        ob.select_set(True)


def new_zone(name):
    assert bpy.ops.mrt.new_zone(name=name) == {'FINISHED'}
    assert p.zone_choice == name


def empties(zone='ZONE_A'):
    return [e for e in zone_empties(scene, p.zone_prefix) if zone_name(e) == zone]


def meshes_in_zone():
    bpy.ops.object.select_all(action='DESELECT')
    assert bpy.ops.mrt.select_in_zone() == {'FINISHED'}
    return set(bpy.context.selected_objects)


# --- All Zones cannot be the target.
reset()
assert not bpy.ops.mrt.add_objects_to_zone.poll()

# --- one cluster, no contamination: a single empty that covers everything.
reset()
new_zone('ZONE_A')
chosen = [mk(f'S{i}', (i, 0, 0)) for i in range(5)]
select(chosen)
p.merge_distance = 10.0
assert bpy.ops.mrt.add_objects_to_zone() == {'FINISHED'}, p.status
bpy.context.view_layer.update()
found = empties()
assert len(found) == 1, len(found)
e = found[0]
assert e.empty_display_type == 'CUBE' and e.mrt_zone_operation == 'ADD' and e['zone'] == 'ZONE_A'
assert abs(e.location.x - 2) < 1e-3 and min(e.scale) >= 1e-3
assert meshes_in_zone() == set(chosen)
assert set(o for o in bpy.context.scene.objects if o.select_get()) == set(chosen)

# --- unselected mesh in between forces a split; zone still equals the selection.
reset()
new_zone('ZONE_A')
chosen = [mk(f'S{i}', (i, 0, 0)) for i in range(5)]
intruder = mk('Intruder', (2, 0, .0005))
select(chosen)
assert bpy.ops.mrt.add_objects_to_zone() == {'FINISHED'}, p.status
bpy.context.view_layer.update()
assert len(empties()) >= 2
assert meshes_in_zone() == set(chosen)
assert intruder not in meshes_in_zone()

# --- far from the origin, box edges must survive Blender's float32 matrix inverse.
for offset in (490.0, 5000.0, 50000.0):
    reset()
    new_zone('ZONE_A')
    chosen = [mk(f'F{i}_{j}', (offset + 2 * i, offset / 2 + 2 * j, 0)) for i in range(4) for j in range(4)]
    neighbour = mk('Neighbour', (offset + 2 * 4, offset / 2, 0))
    select(chosen)
    p.merge_distance = 20.0
    assert bpy.ops.mrt.add_objects_to_zone() == {'FINISHED'}, p.status
    bpy.context.view_layer.update()
    assert meshes_in_zone() == set(chosen), (offset, len(meshes_in_zone()))
    assert neighbour not in meshes_in_zone()

# --- merge_distance 0: one empty per object.
reset()
new_zone('ZONE_A')
chosen = [mk(f'S{i}', (i * .1, 0, 0)) for i in range(4)]
select(chosen)
p.merge_distance = 0.0
assert bpy.ops.mrt.add_objects_to_zone() == {'FINISHED'}
assert len(empties()) == 4

# --- running again adds nothing (already inside).
before = len(empties())
select(chosen)
assert bpy.ops.mrt.add_objects_to_zone() == {'FINISHED'}
assert len(empties()) == before
assert 'Nothing to add: 4' in p.status, p.status

# --- same origin as an unselected object cannot be separated: no empty, warning count.
reset()
new_zone('ZONE_A')
twin_a = mk('Chosen', (5, 5, 5))
mk('Twin', (5, 5, 5))
free = mk('Free', (50, 0, 0))
select([twin_a, free])
p.merge_distance = 0.0
assert bpy.ops.mrt.add_objects_to_zone() == {'FINISHED'}
assert len(empties()) == 1 and 'unseparable 1' in p.status, p.status
assert meshes_in_zone() == {free}

# --- non-mesh selection is ignored; nothing selected is an error.
reset()
new_zone('ZONE_A')
lone = bpy.data.objects.new('NotMesh', None)
scene.collection.objects.link(lone)
ok = mk('Ok', (0, 0, 0))
select([lone, ok])
assert bpy.ops.mrt.add_objects_to_zone() == {'FINISHED'}
assert 'ignored non-mesh 1' in p.status
select([lone])
assert cancelled(bpy.ops.mrt.add_objects_to_zone)

# --- an existing Subtract box that covers a new object is reported, not hidden.
reset()
new_zone('ZONE_A')
assert bpy.ops.mrt.add_zone_empty(zone_name='ZONE_A') == {'FINISHED'}
cut = bpy.context.view_layer.objects.active
cut.location = (10, 0, 0)
cut.empty_display_size = 1
cut.mrt_zone_operation = 'SUBTRACT'
bpy.context.view_layer.update()
inside_cut = mk('InsideCut', (10, 0, 0))
open_area = mk('OpenArea', (20, 0, 0))
select([inside_cut, open_area])
p.merge_distance = 0.0
assert bpy.ops.mrt.add_objects_to_zone() == {'FINISHED'}, p.status
assert 'removed by Subtract 1' in p.status, p.status
assert len(empties()) == 3  # the cut itself + two new boxes

# --- failure rolls back every created empty.
reset()
new_zone('ZONE_A')
chosen = [mk(f'S{i}', (i * 5, 0, 0)) for i in range(6)]
select(chosen)
p.merge_distance = 0.0
real = mrt.zone_add_objects._new_empty
calls = []


def failing(name):
    calls.append(name)
    if len(calls) == 4:
        raise RuntimeError('simulated failure')
    return real(name)


mrt.zone_add_objects._new_empty = failing
try:
    assert cancelled(bpy.ops.mrt.add_objects_to_zone)
finally:
    mrt.zone_add_objects._new_empty = real
assert not empties()
assert not [o for o in bpy.data.objects if o.type == 'EMPTY']
print('ADD_OBJECTS_TO_ZONE_TESTS_PASSED', flush=True)
mrt.unregister()
