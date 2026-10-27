"""Mesh Live debounce, invalid-data retention and Cancel in a real UI."""
import bpy,sys,pathlib,time,json,addon_utils,traceback
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'_Taiyo_Blender_Extensions_Repo'))
addon_utils.enable('zone_groups',default_set=True)
from zone_groups import runtime as R,operations as O
bpy.context.preferences.view.show_splash=False
area=next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D')
for o in list(bpy.data.objects):bpy.data.objects.remove(o,do_unlink=True)
s=bpy.context.scene
bpy.ops.mesh.primitive_cube_add();controller=bpy.context.object;controller.name='Controller'
for i in range(1000):
 o=bpy.data.objects.new('Sample',None);s.collection.objects.link(o);o.location=(i%20/5-2,(i//20)%20/5-2,i//400*.2)
g=O.new_group(s,'Live Mesh');g.source='VOLUME';g.update_mode='LIVE';r=R.region(g);r.t_empty=True;v=r.volumes.add();v.kind='MESH';v.controller=controller
bpy.context.view_layer.update();R.invalidate(s)
results=[];stage='ready';start=time.monotonic();mark=start
path=pathlib.Path('/tmp/zone_groups_mesh_live_'+bpy.app.version_string.split()[0]+'.json')
def check(name,test):
 results.append({'test':name,'passed':bool(test)});path.write_text(json.dumps(results,indent=2));assert test,name
def tick():
 global stage,mark,evals,builds,old
 try:
  if time.monotonic()-start>45:raise TimeoutError(stage)
  if stage=='ready' and not g.dirty and R.ACTIVE is None:
   check('Live initial mesh',g.last_evaluated_count>0);old=set(R.get(s).members[g.uid]);evals=R.STATS['evaluations'];builds=R.STATS['mesh_builds'];mark=time.monotonic();stage='drag'
  elif stage=='drag':
   controller.location.x+=.12
   if time.monotonic()-mark>1:
    check('drag debounced',R.STATS['evaluations']==evals);mark=time.monotonic();stage='settled'
  elif stage=='settled' and time.monotonic()-mark>.8 and R.ACTIVE is None and not g.dirty:
   check('Live moved membership',R.get(s).members[g.uid]!=old);check('move reuses mesh cache',R.STATS['mesh_builds']==builds)
   evals=R.STATS['evaluations'];mark=time.monotonic();stage='idle'
  elif stage=='idle' and time.monotonic()-mark>.8:
   check('idle no evaluation',R.STATS['evaluations']==evals)
   with bpy.context.temp_override(area=area,region=next(r for r in area.regions if r.type=='WINDOW')):
    bpy.ops.zg.restriction('INVOKE_DEFAULT',field='render')
   job=R.ACTIVE;original=job.generator
   def hold():
    for value in original:
     yield value
     if job.journal:
      while True:yield
   job.generator=hold();stage='cancel'
  elif stage=='cancel' and R.ACTIVE and R.ACTIVE.journal:
   bpy.ops.zg.cancel_job();stage='cancelled'
  elif stage=='cancelled' and R.ACTIVE is None:
   check('Cancel button restores restriction',all(not o.hide_render for o in s.objects))
   print('MESH LIVE UI PASS',results,flush=True);bpy.ops.wm.quit_blender();return None
  return .08
 except Exception:
  results.append({'error':traceback.format_exc()});path.write_text(json.dumps(results,indent=2));print(traceback.format_exc(),flush=True)
  if R.ACTIVE:R.ACTIVE.abort()
  bpy.ops.wm.quit_blender();return None
bpy.app.timers.register(tick,first_interval=1)
