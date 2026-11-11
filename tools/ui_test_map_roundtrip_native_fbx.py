"""Open Blender's actual FBX file browser, inspect settings, then cancel."""
import sys,time,json,tempfile,traceback
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'_Taiyo_Blender_Extensions_Repo'))
import map_roundtrip_tools as mrt
mrt.register();bpy.context.preferences.view.show_splash=False
bpy.ops.object.select_all(action='DESELECT')
mesh=bpy.data.meshes.new('Native');mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)])
ob=bpy.data.objects.new('Native',mesh);bpy.context.scene.collection.objects.link(ob)
ob.select_set(True);bpy.context.view_layer.objects.active=ob
p=bpy.context.scene.mrt_props;p.zone_name='Native UI test';p.fbx_out_dir=tempfile.mkdtemp(prefix='native-fbx-')
expected=Path(p.fbx_out_dir)/'Native_UI_test.fbx'
area=next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D')
region=next(r for r in area.regions if r.type=='WINDOW')
results=[];stage='start';start=time.monotonic()
path=Path('/tmp/native_fbx_ui_'+bpy.app.version_string.split()[0]+'.json')
def check(name,value):
 results.append({'test':name,'passed':bool(value)});path.write_text(json.dumps(results,indent=2));assert value,name
def tick():
 global stage
 try:
  if time.monotonic()-start>30:raise TimeoutError(stage)
  if stage=='start':
   with bpy.context.temp_override(area=area,region=region):bpy.ops.mrt.export_fbx_native('INVOKE_DEFAULT')
   stage='open'
  elif stage=='open':
   matches=[(w,a) for w in bpy.context.window_manager.windows for a in w.screen.areas if a.type=='FILE_BROWSER' and a.spaces.active.active_operator]
   if not matches:return .2
   w,a=matches[0];op=a.spaces.active.active_operator
   check('Native Blender FBX operator',op.bl_rna.identifier=='EXPORT_SCENE_OT_fbx')
   check('Selected Meshes',op.use_selection and set(op.object_types)=={'MESH'})
   check('Linear colors',op.colors_type=='LINEAR')
   check('Blender preset support','PRESET' in op.bl_options)
   check('No file before export',not expected.exists())
   with bpy.context.temp_override(window=w,area=a,region=next(r for r in a.regions if r.type=='WINDOW')):bpy.ops.file.cancel()
   stage='cancelled'
  elif stage=='cancelled':
   check('Cancel leaves no file',not expected.exists())
   print('NATIVE_FBX_UI_PASSED',path,flush=True);bpy.ops.wm.quit_blender();return None
  return .3
 except Exception:
  results.append({'error':traceback.format_exc()});path.write_text(json.dumps(results,indent=2));print(traceback.format_exc(),flush=True);bpy.ops.wm.quit_blender();return None
bpy.app.timers.register(tick,first_interval=1)
