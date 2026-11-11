"""Real UI Add Empty invoke/Undo/Redo smoke test."""
from pathlib import Path
import json,sys,time,traceback
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'_Taiyo_Blender_Extensions_Repo'))
import unreal_bridge_tools as ubt
ubt.register()
bpy.context.preferences.view.show_splash=False
bpy.data.batch_remove(ids=list(bpy.data.objects))
a=bpy.data.objects.new('ZONE_A',None);a.empty_display_type='CUBE'
bpy.context.scene.collection.objects.link(a)
bpy.context.scene.ubt_props.zone_choice='ZONE_A'
area=next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D')
region=next(r for r in area.regions if r.type=='WINDOW')
area.spaces.active.show_region_ui=True
ui=next(r for r in area.regions if r.type=='UI')
stage='start';start=time.monotonic();results=[]
path=Path('/tmp/ubt_zone_ui_'+bpy.app.version_string.split()[0]+'.json')
def check(name,ok):
 results.append({'test':name,'passed':bool(ok)});path.write_text(json.dumps(results,indent=2));assert ok,name
def tick():
 global stage
 try:
  if time.monotonic()-start>25:raise TimeoutError(stage)
  with bpy.context.temp_override(area=area,region=region):
   if stage=='start':
    bpy.context.view_layer.update()
    bpy.ops.ed.undo_push(message='Zone baseline')
    bpy.ops.ubt.add_zone_empty('INVOKE_DEFAULT',True);stage='added'
   elif stage=='added':
    check('Add Empty invoke',len(bpy.context.scene.objects)==2)
    check('Automatic membership',bpy.context.view_layer.objects.active.get('zone')=='ZONE_A')
    bpy.ops.ed.undo();stage='undone'
   elif stage=='undone':
    check('Undo Add Empty',len(bpy.context.scene.objects)==1)
    bpy.ops.ed.redo();stage='redone'
   elif stage=='redone':
    check('Redo Add Empty',len(bpy.context.scene.objects)==2)
    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP',iterations=1)
    print('ZONE_UI_PASSED',path,flush=True);bpy.ops.wm.quit_blender();return None
  return .5
 except Exception:
  results.append({'error':traceback.format_exc()});path.write_text(json.dumps(results,indent=2))
  print(traceback.format_exc(),flush=True);bpy.ops.wm.quit_blender();return None
bpy.app.timers.register(tick,first_interval=1)
