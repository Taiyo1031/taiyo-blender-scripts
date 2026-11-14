"""Real modal UI regression: physical ESC events, rollback, Import Zone (whole-zone replacement), Restore Original Map, Re-apply
and importing again. Run Blender with --enable-event-simulate --python this_file.
"""
import csv
import json
from pathlib import Path
import sys
import tempfile
import time
import traceback
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '_Taiyo_Blender_Extensions_Repo'))
import map_roundtrip_tools as mrt
from map_roundtrip_tools import chunked
from map_roundtrip_tools.zones import ensure_zone
mrt.register()
bpy.context.preferences.view.show_splash = False
bpy.data.batch_remove(ids=list(bpy.data.objects))
bpy.data.batch_remove(ids=list(bpy.data.collections))
scene = bpy.context.scene
lib, mapc = bpy.data.collections.new('UI Library'), bpy.data.collections.new('UI Map')
mesh = bpy.data.meshes.new('Cube')
mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)])
source = bpy.data.objects.new('Rock',mesh)
lib.objects.link(source)
count = 2000
old = []
for i in range(count):
    ob = bpy.data.objects.new('Rock',mesh)
    ob.location = (i%50,i//50,0)
    ob['ub_zone'] = 'ZONE_UI'
    ob['ub_csv_id'] = i + 1
    mapc.objects.link(ob)
    old.append(ob)
scene.collection.children.link(lib)
scene.collection.children.link(mapc)
p = scene.mrt_props
p.library_coll, p.map_coll = lib,mapc
ensure_zone(p, 'ZONE_UI')
p.zone_choice = 'ZONE_UI'
p.dry_run = False
temp = Path(tempfile.mkdtemp(prefix='mrt-ui-'))
p.placement_csv = str(temp/'Return.csv')
placed = count - count // 4 + count // 4  # every 4th row has use = 0 (not placed); count // 4 more rows have id -1
with open(p.placement_csv,'w',newline='') as f:
    writer = csv.writer(f)
    writer.writerow([*mrt.placement.CSV_COLUMNS, 'use'])
    # the ids play no part; even rows are shifted by 0.5
    writer.writerows((i + 1, i % 50 + (0.5 if (i + 1) % 2 == 0 else 0), i // 50, 0, 0, 0, 0, 1, 1, 1, 'Rock', '', 0 if (i + 1) % 4 == 0 else 1) for i in range(count))
    writer.writerows((-1, i % 50, 100 + i // 50, 0, 0, 0, 0, 1, 1, 1, 'Rock', '') for i in range(count // 4))
area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
region = next(r for r in area.regions if r.type == 'WINDOW')
# Keep enough ticks for deterministic ESC injection without replacing production work.
original_tick = chunked.ChunkedOperator.tick

def paced_tick(self,context):
    self._items_per_tick = 64
    return original_tick(self,context)
chunked.ChunkedOperator.tick = paced_tick
stage = 'start'
start = time.monotonic()
results = []
path = Path('/tmp/map_roundtrip_ui_'+bpy.app.version_string.split()[0]+'.json')

def check(name, condition):
    results.append({'test':name,'passed':bool(condition)})
    path.write_text(json.dumps(results,indent=2))
    assert condition,name


def invoke():
    with bpy.context.temp_override(area=area,region=region):
        bpy.ops.mrt.replace_zone('INVOKE_DEFAULT')


def imported():
    return [o for o in bpy.data.objects if o.get('ub_zone') == 'ZONE_UI' and o not in old]


def originals_in_place(untouched=True):
    """All originals are in the Map at their positions (untouched: no ub_run yet, i.e. no import has changed them)."""
    return all(o.get('ub_zone') == 'ZONE_UI' and 'ub_archived_from' not in o and (not untouched or 'ub_run' not in o) for o in old) \
        and len(mapc.objects) == count and all(abs(o.location.x-(i%50))<1e-6 for i,o in enumerate(old))


def tick():
    global stage
    try:
        if time.monotonic()-start>240:
            raise TimeoutError(stage)
        job = chunked._RUNNING
        if stage == 'start':
            invoke()
            stage = 'cancel_creation'
        elif stage == 'cancel_creation' and job and job._phase == 'Placing CSV rows' and job._done > 100:
            bpy.context.window.event_simulate(type='ESC',value='PRESS')
            stage = 'creation_cancelled'
        elif stage == 'creation_cancelled' and job is None:
            check('ESC placing rollback',len(bpy.data.objects) == count+1 and originals_in_place())
            check('rollback message','Rolled back' in p.status)
            invoke()
            stage = 'cancel_archive'
        elif stage == 'cancel_archive' and job and job._phase == 'Archiving original objects' and job._done > 100:
            bpy.context.window.event_simulate(type='ESC',value='PRESS')
            stage = 'archive_cancelled'
        elif stage == 'archive_cancelled' and job is None:
            check('ESC archive rollback',len(bpy.data.objects)==count+1 and originals_in_place())
            check('no archive left','_Replaced_ZONE_UI' not in bpy.data.collections)
            invoke()
            stage = 'complete'
        elif stage == 'complete' and job is None:
            archived = [o for o in old if 'ub_zone' not in o]
            check('every original archived',len(archived)==count and all(o.get('ub_archived_from')=='ZONE_UI' for o in archived))
            check('originals untouched',all(abs(o.location.x-(i%50))<1e-6 for i,o in enumerate(old)))
            check('every row placed',len(imported())==placed and len(mapc.objects)==placed)
            check('mesh sharing',all(o.data==mesh for o in mapc.objects))
            check('state after',bpy.data.collections['_Replaced_ZONE_UI']['ub_state']=='after')
            with bpy.context.temp_override(area=area,region=region):
                bpy.ops.mrt.switch_map_state('INVOKE_DEFAULT',target='BEFORE',zone='ZONE_UI')
            stage = 'restored'
        elif stage == 'restored' and job is None:
            check('original map back',originals_in_place(untouched=False))
            check('imported objects stashed',len(imported())==0 and all('ub_zone' not in o for o in bpy.data.objects if 'ub_run' in o and o not in old))
            check('state before',bpy.data.collections['_Replaced_ZONE_UI']['ub_state']=='before')
            with bpy.context.temp_override(area=area,region=region):
                bpy.ops.mrt.switch_map_state('INVOKE_DEFAULT',target='AFTER',zone='ZONE_UI')
            stage = 'reapplied'
        elif stage == 'reapplied' and job is None:
            check('imported map back',len(imported())==placed and len([o for o in old if 'ub_zone' not in o])==count)
            invoke()  # import again: the earlier import is deleted, the archive stays
            stage = 'again'
        elif stage == 'again' and job is None:
            check('second import replaces the first',len(imported())==placed and len(bpy.data.objects)==count+1+placed)
            check('archive kept',len([o for o in old if o.get('ub_archived_from')=='ZONE_UI'])==count)
            print('MRT_UI_PASSED',path,flush=True)
            bpy.ops.wm.quit_blender()
            return None
        return .04
    except Exception:
        results.append({'error':traceback.format_exc()})
        path.write_text(json.dumps(results,indent=2))
        print(traceback.format_exc(),flush=True)
        bpy.ops.wm.quit_blender()
        return None
bpy.app.timers.register(tick,first_interval=1)
