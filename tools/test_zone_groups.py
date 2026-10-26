"""Blender integration checks. Run with --factory-startup --python-exit-code 1."""
import sys, pathlib, json, traceback, time
import bpy
from mathutils import Matrix
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'_Taiyo_Blender_Extensions_Repo'))
import zone_groups as Z
from zone_groups import runtime as R, operations as O, geometry as G
import numpy as np
Z.register()
RESULTS={}
def check(name,fn):
    try: fn(); RESULTS[name]='PASS'; print(name,'PASS')
    except Exception:
        RESULTS[name]='FAIL'; traceback.print_exc()
def op(name,**kw):
    result=getattr(bpy.ops.zg,name)(**kw)
    assert result=={'FINISHED'},(name,result)
def reset():
    R.MUTATING+=1
    try:
        for o in list(bpy.data.objects): bpy.data.objects.remove(o,do_unlink=True)
        bpy.context.scene.zg.groups.clear()
        bpy.context.scene.zg.isolate_uid=''; bpy.context.scene.zg.color_enabled=False
        R.CACHE.clear()
    finally: R.MUTATING-=1
    return bpy.context.scene

def obj(name,xyz=(0,0,0),mesh=True):
    if mesh:
        data=bpy.data.meshes.new(name)
        data.from_pydata([tuple(v) for v in G.SIGNS],[],[])
    else: data=None
    o=bpy.data.objects.new(name,data); bpy.context.scene.collection.objects.link(o); o.location=xyz
    bpy.context.view_layer.update(); return o

def select(*objects):
    for o in bpy.context.selected_objects: o.select_set(False)
    for o in objects: o.select_set(True)
    bpy.context.view_layer.objects.active=objects[0] if objects else None

def group(name='Group',volume=False):
    op('group_new'); g=R.active(bpy.context.scene); g.name=name
    if volume: op('membership_mode',value='VOLUME')
    return g

def evaluate():
    bpy.context.view_layer.update(); R.invalidate(bpy.context.scene); op('evaluate')
def members(g): return R.get(bpy.context.scene).members[g.uid]
def volume(g,shape='CUBE',size=1,operation='ADD',location=(0,0,0)):
    op('volume_add',shape=shape); r=R.region(g); v=r.volumes[-1]; v.operation=operation
    v.controller.empty_display_size=size; v.controller.location=location
    return v.controller

def manual():
    s=reset(); a=obj('A'); b=obj('B'); c=obj('C'); n=len(bpy.data.collections)
    x=group('X'); assert len(bpy.data.collections)==n
    select(a,b); op('add_selected'); op('add_selected'); assert members(x)=={a,b}
    xuid=x.uid; y=group('Y'); select(a,c); op('add_selected'); yuid=y.uid
    s.zg.active_index=0; select(a); op('remove_selected'); assert members(x)=={b} and members(y)=={a,c}
    select(a); op('add_selected'); op('select_members',mode='SET'); assert set(bpy.context.selected_objects)=={a,b}
    select(c); op('select_members',mode='EXTEND'); assert set(bpy.context.selected_objects)=={a,b,c}
    op('select_members',mode='DESELECT'); assert set(bpy.context.selected_objects)=={c}
    select(a); op('select_groups_of_selection'); assert set(bpy.context.selected_objects)=={a,b,c}
    x.name='Renamed'; op('group_move',direction='DOWN'); assert R.active(s).uid==xuid
    select(); assert bpy.ops.zg.add_selected()=={'CANCELLED'}
    assert bpy.ops.zg.remove_selected()=={'CANCELLED'}
    op('select_groups_of_selection')
    count=len(bpy.data.objects); op('group_duplicate'); assert len(bpy.data.objects)==count
    dup=R.active(s); assert members(dup)=={a,b}
    op('group_merge',source_uid=yuid); assert members(R.active(s))=={a,b,c}
    op('group_remove'); assert a.name in bpy.data.objects
    assert len(bpy.data.collections)==n
    select(); op('select_members'); assert {a,b}==set(bpy.context.selected_objects)
    for t in ['T01','T02','T03','T04','T05','T06','T07','T18','T20','T24','T34','T35']: RESULTS[t]='PASS'
check('Manual',manual)

def spatial():
    s=reset(); a=obj('Inside',(.2,0,0)); b=obj('Outside',(4,0,0)); edge=obj('Boundary',(1,0,0))
    g=group('Zone',True); box=volume(g); evaluate(); assert members(g)=={a,edge}
    RESULTS['T08']='PASS'
    box.empty_display_type='SPHERE'; box.scale=(2,1,1); edge.location=(2,0,0)
    evaluate(); assert members(g)=={a,edge}; RESULTS['T09']='PASS'
    parent=obj('Parent',(2,0,0),False); box.parent=parent; box.rotation_euler.z=.4
    evaluate(); assert a not in members(g); RESULTS['T10']='PASS'
    box.parent=None; box.rotation_euler=(0,0,0); box.scale=(1,1,1); box.location=(0,0,0)
    edge.location=(1,0,0); box.empty_display_type='CUBE'; box.empty_display_size=2
    volume(g,size=.3,operation='EXCLUDE'); volume(g,size=1)
    evaluate(); assert a not in members(g) and edge in members(g)
    r=R.region(g); r.volumes.move(0,2); evaluate(); assert a not in members(g) and edge in members(g); RESULTS['T11']='PASS'
    for ref in list(r.volumes): pass
    r.volumes.clear(); volume(g,size=.1); a.location=(0,0,0)
    for mode,expected in [('ORIGIN',True),('BOUNDS_CENTER',True),('FULLY_INSIDE',False),('ANY_OVERLAP',True)]:
        r.eval_mode=mode; evaluate(); assert (a in members(g))==expected,(mode,members(g))
    r.volumes[0].controller.empty_display_type='SPHERE'; evaluate(); assert a in members(g)
    RESULTS['T12']='PASS'
    r.t_mesh=False; r.t_empty=True; evaluate(); assert a not in members(g)
    assert not any(v.controller in members(g) for v in r.volumes); RESULTS['T13']='PASS'
    select(a,b); op('fit_to_selection'); fitted=r.volumes[-1].controller
    assert fitted.scale.x>=3; RESULTS['T14']='PASS'
    bad=volume(g); bad.scale=(0,0,0); evaluate(); assert 'Zero scale' in R.get(s).warning
    bad.scale=(1,1,1); bad.empty_display_type='PLAIN_AXES'; evaluate(); assert 'Unsupported' in R.get(s).warning
    bpy.data.objects.remove(bad,do_unlink=True); evaluate(); assert 'Missing' in R.get(s).warning; RESULTS['T15']='PASS'
    g.update_mode='MANUAL'; R.invalidate(s); assert bpy.ops.zg.select_members()=={'CANCELLED'}
    op('evaluate'); g.update_mode='DIRTY'; op('select_members'); assert not g.dirty; RESULTS['T16']='PASS'
check('Spatial',spatial)

def merge():
    s=reset(); a=obj('A'); b=obj('B',(3,0,0))
    x=group('X',True); box=volume(x,size=5); volume(x,size=1,operation='EXCLUDE'); evaluate(); assert a not in members(x)
    uid=x.uid; y=group('Y',True); volume(y,size=1); evaluate(); assert a in members(y)
    wanted=members(x)|members(y); source=y.uid; s.zg.active_index=0
    op('group_merge',source_uid=source); x=R.active(s); assert x.uid==uid and members(x)==wanted and len(x.regions)==2
    RESULTS['T21']='PASS'
    x.regions[1].eval_mode='ANY_OVERLAP'; evaluate()
    op('group_duplicate'); dup=R.active(s)
    assert dup.regions[0].volumes[0].controller!=box
    before=dup.regions[0].volumes[0].controller.matrix_world.copy(); box.location.x=20
    bpy.context.view_layer.update(); assert dup.regions[0].volumes[0].controller.matrix_world==before; RESULTS['T19']='PASS'
    expected=members(x)|members(dup); source=dup.uid; s.zg.active_index=0
    evaluate(); expected=members(x)|members(dup); op('group_merge',source_uid=source); assert members(R.active(s))==expected
    R.active(s).regions[-1].volumes[0].controller.location.x=50; evaluate(); RESULTS['T22']='PASS'
    voluid=R.active(s).uid; group('Manual'); assert bpy.ops.zg.group_merge(source_uid=voluid)=={'CANCELLED'}; RESULTS['T23']='PASS'
check('Merge',merge)

def styles():
    s=reset(); a=obj('A'); b=obj('B'); c=obj('Unrelated'); a.color=(.1,.2,.3,1); original=tuple(a.color)
    x=group('X'); select(a,b); op('add_selected'); x.color=(1,0,0,1)
    y=group('Y'); select(a); op('add_selected'); y.color=(0,1,0,1)
    s.zg.active_index=0; op('restriction',field='show'); assert a.hide_viewport
    s.zg.active_index=1; op('restriction',field='show'); s.zg.active_index=0; op('restriction',field='show'); assert a.hide_viewport
    s.zg.active_index=1; op('restriction',field='show'); assert not a.hide_viewport; RESULTS['T25']='PASS'
    a.hide_viewport=True; op('restriction',field='show'); op('show_all'); assert a.hide_viewport
    a.hide_viewport=False; RESULTS['T26']='PASS'
    for field,attr in [('selectable','hide_select'),('render','hide_render')]:
        op('restriction',field=field); assert getattr(a,attr); op('restriction',field=field); assert not getattr(a,attr)
    RESULTS['T27']='PASS'
    op('isolate'); assert c.hide_viewport and b.hide_viewport and not a.hide_viewport
    op('isolate'); assert not c.hide_viewport and not b.hide_viewport
    op('isolate'); op('show_all'); assert not c.hide_viewport; RESULTS['T28']='PASS'
    op('color_toggle'); assert tuple(a.color)==(1,0,0,1)
    op('group_move',direction='UP'); assert tuple(a.color)==(0,1,0,1)
    s.zg.color_rule='OVERLAP'; op('evaluate'); assert tuple(a.color)==(1,0,1,1)
    op('color_toggle'); assert np.allclose(a.color,original)
    other=bpy.data.scenes.new('Other'); other.collection.objects.link(a)
    op('color_toggle'); assert a.zg_baseline.mask>0
    other.zg.color_enabled=True; gg=O.new_group(other); gg.manual_members.add().obj=a; gg.color=(0,0,1,1)
    R.drain(R.evaluation(other)); R.drain(R.apply_style(other)); assert tuple(a.color)==(1,0,1,1)
    assert 'Shared Object' in R.get(other).warning; bpy.data.scenes.remove(other)
    RESULTS['Color']='PASS'; RESULTS['SharedScene']='PASS'
    tx=O.Transaction(s); tx.saved=O.dump(s.zg); R.ACTIVE=tx
    x.show=False; tx.generator=R.apply_style(s,tx.journal)
    next(tx.generator); tx.abort(); assert not a.hide_viewport and not b.hide_viewport
    RESULTS['Cancel']='PASS'
check('Styles',styles)

def lifecycle():
    s=bpy.context.scene
    vg=group('Persistent Volume',True); volume(vg,size=2)
    O.copy_region(vg.regions[0],vg.regions.add())
    vg.regions[1].eval_mode='ANY_OVERLAP'; vg.regions[1].t_light=False
    evaluate()
    expected_controllers=[v.controller.name for g in s.zg.groups for r in g.regions for v in r.volumes if v.controller]
    path='/tmp/zone_groups_save_test.blend'
    bpy.ops.wm.save_as_mainfile(filepath=path)
    expected=[g.uid for g in s.zg.groups]; bpy.ops.wm.open_mainfile(filepath=path)
    s=bpy.context.scene; assert [g.uid for g in s.zg.groups]==expected
    assert [v.controller.name for g in s.zg.groups for r in g.regions for v in r.volumes if v.controller]==expected_controllers
    assert s.zg.groups[-1].regions[1].eval_mode=='ANY_OVERLAP'
    assert not s.zg.groups[-1].regions[1].t_light
    op('evaluate'); RESULTS['T30']='PASS'
    Z.unregister(); Z.register(); Z.register()
    assert bpy.app.handlers.depsgraph_update_post.count(R.depsgraph_update)==1
    RESULTS['T31']='PASS'
check('Lifecycle',lifecycle)
def geometry_edges():
    cube=G.SIGNS.copy()
    for shape in ['CUBE','SPHERE']:
        f=G.box_overlap if shape=='CUBE' else G.sphere_overlap
        assert f(cube*10,1)
        assert f(cube+np.array([2,0,0]),1)
        assert not f(cube+np.array([2.00001,0,0]),1)
        flat=cube.copy(); flat[:,2]=0
        assert f(flat,1)
        shear=np.eye(4); shear[0,1]=1.5
        assert f(G.transform(cube,shear),1)
    assert G.inside(np.array([[1,0,0]]),'SPHERE',1)[0]
check('GeometryEdges',geometry_edges)
ui_source=(pathlib.Path(Z.__file__).parent/'ui.py').read_text()
assert not any(word in ui_source for word in ('[MOCK]', 'Export', 'CSV', 'Both'))
RESULTS['T33']='PASS'
for t in ['T17','T29','T32']: RESULTS.setdefault(t,'NOT RUN')
path=pathlib.Path('/tmp/zone_groups_test_results.json'); path.write_text(json.dumps(RESULTS,indent=2))
print('ZONE_GROUPS_RESULTS',json.dumps(RESULTS))
if 'FAIL' in RESULTS.values(): raise RuntimeError('Zone Groups tests failed')
