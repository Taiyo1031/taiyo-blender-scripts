"""Real modal Isolate/restore/Cancel/Undo regression at 60k shared-mesh Objects."""
import bpy,sys,pathlib,time,json,os,traceback,addon_utils
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'_Taiyo_Blender_Extensions_Repo'))
addon_utils.enable('zone_groups',default_set=True)
from zone_groups import runtime as R,operations as O
bpy.context.preferences.view.show_splash=False
bpy.data.batch_remove(ids=list(bpy.data.objects));s=bpy.context.scene
mesh=bpy.data.meshes.new('Shared sample');mesh.from_pydata([(-1,-1,0),(1,-1,0),(0,1,1)],[],[(0,1,2)])
count=int(os.environ.get('ZG_ISOLATE_COUNT','60000'));objects=[]
for i in range(count):
 o=bpy.data.objects.new(f'P{i:05d}',mesh);s.collection.objects.link(o);o.location=(i%300,(i//300)%200,0);objects.append(o)
g=O.new_group(s,'Isolate test')
for o in objects[-100:]:g.manual_members.add().obj=o
objects[-1].hide_viewport=True;objects[1].hide_select=True;objects[2].hide_render=True
bpy.context.view_layer.update();objects[3].hide_set(True)
R.drain(R.evaluation(s));area=next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D')
results=[];stage='start';mark=time.perf_counter();job_start=mark
path=pathlib.Path('/tmp/zone_groups_isolate_large_'+bpy.app.version_string.split()[0]+'.json')
def ctx():return bpy.context.temp_override(area=area,region=next(r for r in area.regions if r.type=='WINDOW'))
def check(name,ok,**extra):
 results.append(dict(test=name,passed=bool(ok),**extra));path.write_text(json.dumps(dict(objects=count,results=results,stats=R.STATS),indent=2));assert ok,name
 print(name,extra,flush=True)
def call(action):
 global job_start
 job_start=time.perf_counter()
 with ctx():getattr(bpy.ops.zg,action)('INVOKE_DEFAULT')
def original():return sum(o.hide_viewport for o in objects)==1 and objects[-1].hide_viewport and objects[3].hide_get() and objects[1].hide_select and objects[2].hide_render

def tick():
 global stage,mark,cancel_start
 try:
  if time.perf_counter()-mark>120:raise TimeoutError(stage)
  if stage=='start' and R.ACTIVE is None:
   with ctx():bpy.ops.ed.undo_push(message='Large Isolate baseline')
   call('isolate');stage='isolated'
  elif stage=='isolated' and R.ACTIVE is None:
   check('Isolate completes',sum(o.hide_viewport for o in objects)==count-99,seconds=time.perf_counter()-job_start)
   call('show_all');stage='restored'
  elif stage=='restored' and R.ACTIVE is None:
   check('Show All restores original monitor/eye/locks',original(),seconds=time.perf_counter()-job_start)
   call('isolate');job=R.ACTIVE;gen=job.generator;writes=R.STATS['writes']
   def hold():
    for value in gen:
     yield value
     if R.STATS['writes']>writes:
      while True:yield
   job.generator=hold();stage='cancel'
  elif stage=='cancel' and objects[0].hide_viewport:
   cancel_start=time.perf_counter();bpy.ops.zg.cancel_job();stage='cancelled'
  elif stage=='cancelled' and R.ACTIVE is None:
   check('Cancel after bulk commit restores all state',original(),seconds=time.perf_counter()-job_start,restore_seconds=time.perf_counter()-cancel_start)
   call('isolate');stage='before_undo'
  elif stage=='before_undo' and R.ACTIVE is None:
   with ctx():bpy.ops.ed.undo()
   # Undo replaces Object wrappers: resolve by name after native Undo.
   stage='undone'
  elif stage=='undone' and R.ACTIVE is None:
   current=bpy.context.scene
   check('Native Undo restores monitor flags',sum(o.hide_viewport for o in current.objects)==1)
   with ctx():bpy.ops.ed.redo()
   stage='redone'
  elif stage=='redone' and R.ACTIVE is None:
   check('Native Redo restores Isolate',sum(o.hide_viewport for o in bpy.context.scene.objects)==count-99)
   print('LARGE ISOLATE PASS',R.STATS,flush=True);bpy.ops.wm.quit_blender();return None
  return .05
 except Exception:
  results.append(dict(stage=stage,error=traceback.format_exc()));path.write_text(json.dumps(dict(objects=count,results=results,stats=R.STATS),indent=2));print(traceback.format_exc(),flush=True);os._exit(1)
bpy.app.timers.register(tick,first_interval=1)
