"""Separate factory-startup UI process: actual modal/Undo/Live/draw checks."""
import bpy, sys, pathlib, time, json, traceback, addon_utils
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'_Taiyo_Blender_Extensions_Repo'))
addon_utils.enable('zone_groups', default_set=True)
from zone_groups import runtime as R, operations as O
bpy.context.preferences.view.show_splash=False
area=next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D')
area.spaces.active.show_region_ui=True
results=[]; stage='start'; started=time.monotonic(); mark=started; evals=0
for o in list(bpy.data.objects): bpy.data.objects.remove(o,do_unlink=True)
s=bpy.context.scene
for i in range(10000):
    o=bpy.data.objects.new(f'ZG_{i:04d}',None); s.collection.objects.link(o); o.location=(i%50,i//50,0)
    o.select_set(True)
g=O.new_group(s,'Manual')
for o in s.objects: g.manual_members.add().obj=o
R.drain(R.evaluation(s)); bpy.context.view_layer.update()
def ctx(): return bpy.context.temp_override(area=area,region=next(r for r in area.regions if r.type=='WINDOW'))
def record(name,ok):
    results.append({'test':name,'passed':bool(ok)})
    pathlib.Path('/tmp/zone_groups_ui_results.json').write_text(json.dumps(results,indent=2))
    if not ok: raise AssertionError(name)
def call(name,**kw):
    with ctx(): return getattr(bpy.ops.zg,name)('INVOKE_DEFAULT',**kw)
def tick():
    global stage,mark,evals
    try:
        if time.monotonic()-started>100: raise TimeoutError(stage)
        s=bpy.context.scene
        if stage=='start':
            with ctx(): bpy.ops.ed.undo_push(message='Zone Groups fixture')
            record('modal started',call('restriction',field='render')=={'RUNNING_MODAL'})
            stage='applied'
        elif stage=='applied' and R.ACTIVE is None:
            record('restriction applied',all(o.hide_render for o in s.objects))
            with ctx(): bpy.ops.ed.undo()
            stage='undone'
        elif stage=='undone':
            record('native Undo restores restrictions',not any(o.hide_render for o in s.objects))
            with ctx(): bpy.ops.ed.redo()
            stage='redone'
        elif stage=='redone' and R.ACTIVE is None:
            record('native Redo restores restrictions',all(o.hide_render for o in s.objects))
            call('restriction',field='render')
            # Hold the first partially written batch so even fast machines have
            # a deterministic cancellation window before the next timer tick.
            job=R.ACTIVE; original=job.generator
            def cancel_window():
                for value in original:
                    yield value
                    if job.journal:
                        while True: yield
            job.generator=cancel_window(); stage='cancel'
        elif stage=='cancel' and R.ACTIVE and R.ACTIVE.journal:
            R.ACTIVE.cancel_requested=True; stage='cancelled'
        elif stage=='cancelled' and R.ACTIVE is None:
            record('modal Cancel restores restrictions',all(o.hide_render for o in s.objects))
            call('group_duplicate'); stage='duplicated'
        elif stage=='duplicated' and R.ACTIVE is None:
            record('duplicate completes',len(s.zg.groups)==2)
            with ctx(): bpy.ops.ed.undo()
            stage='dup_undo'
        elif stage=='dup_undo':
            record('native Undo restores group definitions',len(s.zg.groups)==1)
            with ctx(): bpy.ops.ed.redo()
            stage='dup_redo'
        elif stage=='dup_redo' and R.ACTIVE is None:
            record('native Redo restores group definitions',len(s.zg.groups)==2)
            R.MUTATING+=1
            for i in range(len(s.objects),10000):
                o=bpy.data.objects.new(f'ZG_{i:04d}',None); s.collection.objects.link(o); o.location=(i%100,i//100,0)
            g=O.new_group(s,'Live'); g.source='VOLUME'; g.update_mode='LIVE'
            r=R.region(g); r.t_empty=True
            o=bpy.data.objects.new('Controller',None); s.collection.objects.link(o); o.empty_display_type='CUBE'; o.empty_display_size=2
            r.volumes.add().controller=o
            for i in range(1,4):
                extra=bpy.data.objects.new('Controller'+str(i),None); s.collection.objects.link(extra)
                extra.empty_display_type='CUBE'; extra.empty_display_size=2; extra.location.x=i*10
                r.volumes.add().controller=extra
            R.MUTATING-=1; R.invalidate(s); stage='live'; mark=time.monotonic()
        elif stage=='live' and R.ACTIVE is None and not R.active(s).dirty:
            record('Live evaluates without panel action',R.active(s).last_evaluated_count>0)
            evals=R.STATS['evaluations']; stage='drag'; mark=time.monotonic()
        elif stage=='drag':
            bpy.data.objects['Controller'].location.x+=.1
            if time.monotonic()-mark>.6:
                record('Live debounces continuous drag',R.STATS['evaluations']==evals)
                stage='settle'; mark=time.monotonic()
        elif stage=='settle' and R.ACTIVE is None and not R.active(s).dirty:
            record('Live settles once',R.STATS['evaluations']==evals+1)
            bpy.data.objects['ZG_0000'].location.x=100000
            stage='object_moved'
        elif stage=='object_moved' and R.ACTIVE is None and not R.active(s).dirty:
            record('Live detects member Object movement',bpy.data.objects['ZG_0000'] not in R.get(s).members[R.active(s).uid])
            evals=R.STATS['evaluations']; mark=time.monotonic(); stage='draw'
            for r in area.regions:
                if r.type=='UI': r.active_panel_category='Groups'
        elif stage=='draw' and time.monotonic()-mark>1:
            record('Panel redraw does not evaluate',R.STATS['evaluations']==evals)
            with ctx(): bpy.ops.screen.screenshot(filepath='/tmp/zone_groups_ui.png')
            pathlib.Path('/tmp/zone_groups_live_stats.json').write_text(json.dumps(R.STATS,indent=2)); print('ZONE GROUPS UI PASS',R.STATS,flush=True); bpy.ops.wm.quit_blender(); return None
        return .04
    except Exception:
        results.append({'stage':stage,'error':traceback.format_exc()})
        pathlib.Path('/tmp/zone_groups_ui_results.json').write_text(json.dumps(results,indent=2))
        print(traceback.format_exc(),flush=True)
        if R.ACTIVE: R.ACTIVE.abort()
        bpy.ops.wm.quit_blender(); return None
bpy.app.timers.register(tick,first_interval=1)
