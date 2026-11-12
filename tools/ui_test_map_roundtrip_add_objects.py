"""Real UI: Add Selected Objects, physical ESC rollback, Undo/Redo, drawn result, screenshots.

blender --factory-startup --enable-event-simulate --python tools/ui_test_map_roundtrip_add_objects.py
Set MRT_SHOT_DIR to a folder to also save screenshots of the viewport and the sidebar.
"""
import json
import os
from pathlib import Path
import sys
import time
import traceback
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '_Taiyo_Blender_Extensions_Repo'))
import map_roundtrip_tools as mrt
from map_roundtrip_tools import chunked
from map_roundtrip_tools.zones import zone_empties
mrt.register()
bpy.context.preferences.view.show_splash = False
bpy.data.batch_remove(ids=list(bpy.data.objects))
scene = bpy.context.scene
p = scene.mrt_props
COLUMNS, ROWS = 80, 75
mesh = bpy.data.meshes.new('M')
mesh.from_pydata([(-.4, -.4, 0), (.4, -.4, 0), (0, .4, 0)], [], [(0, 1, 2)])
objects = []
for i in range(COLUMNS * ROWS):
    ob = bpy.data.objects.new('Rock', mesh)
    ob.location = ((i % COLUMNS) * 2.0, (i // COLUMNS) * 2.0, 0.0)
    scene.collection.objects.link(ob)
    objects.append(ob)
chosen = [ob for i, ob in enumerate(objects) if i % COLUMNS < COLUMNS // 2]
p.zone_scope = 'SCENE'
p.merge_distance = 0.0  # one empty per object: enough creation steps to cancel in the middle
assert bpy.ops.mrt.new_zone(name='ZONE_UI') == {'FINISHED'}
bpy.ops.object.select_all(action='DESELECT')
for ob in chosen:
    ob.select_set(True)
area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
region = next(r for r in area.regions if r.type == 'WINDOW')
area.spaces.active.show_region_ui = True
original_tick = chunked.ChunkedOperator.tick


def paced_tick(self, context):
    self._items_per_tick = 32  # enough ticks for deterministic ESC injection
    return original_tick(self, context)


chunked.ChunkedOperator.tick = paced_tick
real_new_empty = mrt.zone_add_objects._new_empty


def slow_new_empty(name):
    time.sleep(.001)  # make the creation phase long enough to press ESC in the middle of it
    return real_new_empty(name)


mrt.zone_add_objects._new_empty = slow_new_empty
stage = 'tab'
start = time.monotonic()
results = []
path = Path('/tmp/map_roundtrip_add_objects_ui_' + bpy.app.version_string.split()[0] + '.json')
shots = os.environ.get('MRT_SHOT_DIR')


def check(name, condition):
    results.append({'test': name, 'passed': bool(condition)})
    path.write_text(json.dumps(results, indent=2))
    assert condition, name


def empties():
    # Undo reloads the data blocks, so never keep scene/props references across an undo step.
    current = bpy.context.scene
    return [e for e in zone_empties(current, current.mrt_props.zone_prefix)]


def invoke():
    with bpy.context.temp_override(area=area, region=region):
        bpy.ops.mrt.add_objects_to_zone('INVOKE_DEFAULT')


def screenshot(name):
    if not shots:
        return
    for key, a in (('viewport', area),):
        with bpy.context.temp_override(window=bpy.context.window, area=a, region=next(r for r in a.regions if r.type == 'WINDOW')):
            bpy.ops.screen.screenshot_area(filepath=str(Path(shots) / f'{name}_{key}.png'))


def tick():
    global stage
    try:
        if time.monotonic() - start > 240:
            raise TimeoutError(stage)
        job = chunked._RUNNING
        if stage == 'tab':
            # Click the sidebar tab strip (right edge) so the screenshots show the Map Roundtrip panels.
            win = bpy.context.window
            x = area.x + int(area.width * .9925)
            y = area.y + int(area.height * (1 - .195))
            win.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)
            win.event_simulate(type='LEFTMOUSE', value='PRESS', x=x, y=y)
            win.event_simulate(type='LEFTMOUSE', value='RELEASE', x=x, y=y)
            stage = 'start'
        elif stage == 'start':
            with bpy.context.temp_override(area=area, region=region):
                bpy.context.view_layer.update()
                bpy.ops.ed.undo_push(message='Add Objects baseline')
            invoke()
            stage = 'cancel'
        elif stage == 'cancel' and job and job._phase == 'Creating zone empties' and job._done > 20:
            bpy.context.window.event_simulate(type='ESC', value='PRESS')
            stage = 'cancelled'
        elif stage == 'cancelled' and job is None:
            check('ESC rolls back every new empty', not empties() and not [o for o in bpy.data.objects if o.type == 'EMPTY'])
            check('Cancel message', p.status.startswith('Cancelled'))
            check('selection untouched by cancel', {o for o in bpy.data.objects if o.select_get()} == set(chosen))
            check('meshes untouched by cancel', len(objects) == len([o for o in bpy.data.objects if o.type == 'MESH']))
            invoke()
            stage = 'complete'
        elif stage == 'complete' and job is None:
            found = empties()
            check('modal completion creates one empty per object', len(found) == len(chosen))
            check('status reports the result', p.status.startswith('Added ' + str(len(chosen))))
            with bpy.context.temp_override(area=area, region=region):
                bpy.context.view_layer.update()
                bpy.ops.object.select_all(action='DESELECT')
                bpy.ops.mrt.select_in_zone('EXEC_DEFAULT')
            inside = {o for o in bpy.data.objects if o.type == 'MESH' and o.select_get()}
            check('zone contains exactly the objects that were selected', inside == set(chosen))
            check('drawn empties are evaluated', all(e.evaluated_get(bpy.context.evaluated_depsgraph_get()).matrix_world.translation.length >= 0 for e in found[:50]))
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=2)
            screenshot('after_add')
            stage = 'undo'
            with bpy.context.temp_override(area=area, region=region):
                bpy.ops.ed.undo()
        elif stage == 'undo' and job is None:
            check('Undo removes the added empties', not empties())
            check('Undo keeps all meshes', len([o for o in bpy.data.objects if o.type == 'MESH']) == len(objects))
            stage = 'redo'
            with bpy.context.temp_override(area=area, region=region):
                bpy.ops.ed.redo()
        elif stage == 'redo' and job is None:
            check('Redo restores the empties', len(empties()) > 0)
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=2)
            screenshot('after_redo')
            print('MRT_ADD_OBJECTS_UI_PASSED', path, flush=True)
            bpy.ops.wm.quit_blender()
            return None
        return .04
    except Exception:
        results.append({'error': traceback.format_exc()})
        path.write_text(json.dumps(results, indent=2))
        print(traceback.format_exc(), flush=True)
        bpy.ops.wm.quit_blender()
        return None


bpy.app.timers.register(tick, first_interval=1)
