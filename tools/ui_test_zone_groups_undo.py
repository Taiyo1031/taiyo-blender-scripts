"""Undo/redo round trips for all structural operation families in a real UI."""
import bpy, sys, pathlib, json, time, traceback, addon_utils
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'_Taiyo_Blender_Extensions_Repo'))
addon_utils.enable('zone_groups',default_set=True)
from zone_groups import runtime as R, operations as O
bpy.context.preferences.view.show_splash=False
area=next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D')
s=bpy.context.scene; g=O.new_group(s,'Base')
results=[]; stage='next'; index=0; started=time.monotonic(); before=None; after=None
ACTIONS=['add_selected','remove_selected','add_selected','group_duplicate','group_merge','color_toggle','isolate','show_all','group_new','membership_mode','volume_add','fit_to_selection','group_duplicate','group_merge','group_remove']
def ctx(): return bpy.context.temp_override(area=area,region=next(r for r in area.regions if r.type=='WINDOW'))
def canonical(pg):
    d=O.dump(pg)
    def clean(value):
        if isinstance(value,dict): return {k:clean(v) for k,v in value.items() if k not in {'dirty','last_evaluated_count'}}
        if isinstance(value,list): return [clean(v) for v in value]
        if isinstance(value,bpy.types.ID): return value.name
        return value
    return clean(d)
def snap():
    return (canonical(bpy.context.scene.zg),sorted((o.name,tuple(o.location),tuple(o.scale),o.hide_viewport,o.hide_select,o.hide_render,tuple(o.color)) for o in bpy.context.scene.objects))
def record(name,ok):
    results.append({'test':name,'passed':bool(ok)})
    pathlib.Path('/tmp/zone_groups_undo_results.json').write_text(json.dumps(results,indent=2))
    if not ok: raise AssertionError(name)
def tick():
    global stage,index,before,after
    try:
        if time.monotonic()-started>120: raise TimeoutError(stage)
        if stage=='next':
            if index==len(ACTIONS):
                print('ZONE GROUPS ALL UNDO PASS',flush=True); bpy.ops.wm.quit_blender(); return None
            action=ACTIONS[index]; kw={}
            if action=='membership_mode': kw={'value':'VOLUME'}
            if action=='group_merge':
                active=R.active(bpy.context.scene)
                kw={'source_uid':next(g.uid for g in bpy.context.scene.zg.groups if g.uid!=active.uid and g.source==active.source)}
            before=snap()
            with ctx():
                bpy.ops.ed.undo_push(message='Before '+action)
                result=getattr(bpy.ops.zg,action)('EXEC_DEFAULT',**kw)
            record(action+' starts',result=={'RUNNING_MODAL'})
            stage='done'
        elif stage=='done' and R.ACTIVE is None:
            after=snap()
            with ctx(): bpy.ops.ed.undo()
            stage='undo'
        elif stage=='undo':
            record(ACTIONS[index]+' Undo',snap()==before)
            with ctx(): bpy.ops.ed.redo()
            stage='redo'
        elif stage=='redo' and R.ACTIVE is None:
            record(ACTIONS[index]+' Redo',snap()==after)
            index+=1; stage='next'
        return .06
    except Exception:
        results.append({'stage':stage,'action':ACTIONS[index],'error':traceback.format_exc()})
        pathlib.Path('/tmp/zone_groups_undo_results.json').write_text(json.dumps(results,indent=2))
        print(traceback.format_exc(),flush=True)
        if R.ACTIVE: R.ACTIVE.abort()
        bpy.ops.wm.quit_blender(); return None
bpy.app.timers.register(tick,first_interval=1)
