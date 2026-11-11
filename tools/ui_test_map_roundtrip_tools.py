"""Real modal UI regression, including physical ESC events and archive rollback.
Run Blender with --enable-event-simulate --python this_file.
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
    mapc.objects.link(ob)
    old.append(ob)
scene.collection.children.link(lib)
scene.collection.children.link(mapc)
p = scene.mrt_props
p.library_coll, p.map_coll = lib,mapc
p.dry_run = False
p.old_mode = 'ARCHIVE'
temp = Path(tempfile.mkdtemp(prefix='mrt-ui-'))
p.placement_csv = str(temp/'ZONE_UI.csv')
with open(p.placement_csv,'w',newline='') as f:
    writer = csv.writer(f)
    writer.writerow(mrt.placement.CSV_COLUMNS)
    writer.writerows((i,i%50,i//50,0,0,0,0,1,1,1,'Rock','') for i in range(count))
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


def tick():
    global stage
    try:
        if time.monotonic()-start>120:
            raise TimeoutError(stage)
        job = chunked._RUNNING
        if stage == 'start':
            invoke()
            stage = 'cancel_creation'
        elif stage == 'cancel_creation' and job and job._phase == 'Creating linked instances' and job._done > 100:
            bpy.context.window.event_simulate(type='ESC',value='PRESS')
            stage = 'creation_cancelled'
        elif stage == 'creation_cancelled' and job is None:
            check('ESC creation rollback',len(bpy.data.objects) == count+1 and all(o.get('ub_zone')=='ZONE_UI' for o in old))
            check('rollback message','Rolled back' in p.status)
            invoke()
            stage = 'cancel_archive'
        elif stage == 'cancel_archive' and job and job._phase == 'Archiving' and job._done > 100:
            bpy.context.window.event_simulate(type='ESC',value='PRESS')
            stage = 'archive_cancelled'
        elif stage == 'archive_cancelled' and job is None:
            check('ESC archive rollback',len(bpy.data.objects)==count+1 and len(mapc.objects)==count)
            check('old tags restored',all(o.get('ub_zone')=='ZONE_UI' for o in old))
            invoke()
            stage = 'complete'
        elif stage == 'complete' and job is None:
            check('modal completion',len(mapc.objects)==count and all(o.get('ub_zone')=='ZONE_UI' for o in mapc.objects))
            check('modal archive',all('ub_zone' not in o and o.get('ub_archived_from')=='ZONE_UI' for o in old))
            check('modal mesh sharing',all(o.data==mesh for o in mapc.objects))
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
