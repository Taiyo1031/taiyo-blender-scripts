import bpy,sys,pathlib,time,json,resource
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'_Taiyo_Blender_Extensions_Repo'))
import zone_groups as Z
from zone_groups import runtime as R,mesh_volume as M
Z.register();s=bpy.context.scene
rows=[];samples=[];controller=None
bpy.data.batch_remove(ids=list(bpy.data.objects))
for count in (1000,10000,50000):
 for segments in (0,16,64):
  R.MUTATING+=1
  s.zg.groups.clear();R.CACHE.clear()
  if controller is not None:bpy.data.objects.remove(controller,do_unlink=True)
  for i in range(len(samples),count):
   o=bpy.data.objects.new('P',None);s.collection.objects.link(o);samples.append(o);o.location=((i%100)/10-5,((i//100)%10)-4.5,(i//10000)*.2)
  if segments:
   bpy.ops.mesh.primitive_torus_add(major_segments=segments,minor_segments=8,major_radius=2,minor_radius=.6)
   controller=bpy.context.object
  else:
   controller=bpy.data.objects.new('Box',None);s.collection.objects.link(controller);controller.empty_display_type='CUBE';controller.empty_display_size=2
  bpy.context.view_layer.update();R.MUTATING-=1
  bpy.ops.zg.group_new();bpy.ops.zg.membership_mode(value='VOLUME');g=R.active(s);r=R.region(g);r.t_empty=True;r.t_mesh=False
  v=r.volumes.add();v.kind='MESH' if segments else 'EMPTY';v.controller=controller
  bpy.context.view_layer.update()
  R.STATS.update(slice_max_ms=0.,handler_max_ms=0.,mesh_builds=0,mesh_build_ms=0.,mesh_native_max_ms=0.)
  R.invalidate(s);start=time.perf_counter();gen=R.evaluation(s)
  while not R.tick_job(gen):pass
  elapsed=(time.perf_counter()-start)*1000
  build_count=R.STATS['mesh_builds'];controller.location.x+=.2;bpy.context.view_layer.update();R.invalidate(s);start=time.perf_counter();gen=R.evaluation(s)
  while not R.tick_job(gen):pass
  move=(time.perf_counter()-start)*1000
  assert R.STATS['mesh_builds']==build_count
  row=dict(objects=count,triangles=len(controller.data.polygons)*2 if segments else 0,evaluate_ms=elapsed,move_ms=move,members=g.last_evaluated_count,rss_mb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024**2,**R.STATS)
  rows.append(row);print(row,flush=True)
  pathlib.Path('/tmp/zone_groups_mesh_benchmark_'+bpy.app.version_string.split()[0]+'.json').write_text(json.dumps(rows,indent=2))
pathlib.Path('/tmp/zone_groups_mesh_benchmark_'+bpy.app.version_string.split()[0]+'.json').write_text(json.dumps(rows,indent=2))
Z.unregister()
