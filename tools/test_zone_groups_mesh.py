"""1.1 regression: mesh solid membership, cache invalidation and new operations."""
import bpy,sys,pathlib,json
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'_Taiyo_Blender_Extensions_Repo'))
import zone_groups as Z
from zone_groups import runtime as R,mesh_volume as M
Z.register()
for o in list(bpy.data.objects):bpy.data.objects.remove(o,do_unlink=True)
s=bpy.context.scene

def drain_result(gen):
    while True:
        try:next(gen)
        except StopIteration as e:return e.value

def solid(o):return drain_result(M.build(o.data,R.STATS))
def select(*objects):
    for o in bpy.context.selected_objects:o.select_set(False)
    for o in objects:o.select_set(True)
    bpy.context.view_layer.objects.active=objects[0] if objects else None

def point(name,xyz):
    o=bpy.data.objects.new(name,None);s.collection.objects.link(o);o.location=xyz;return o

def evaluate():
    bpy.context.view_layer.update();R.invalidate(s);assert bpy.ops.zg.evaluate()=={'FINISHED'}

bpy.ops.mesh.primitive_cube_add();cube=bpy.context.object
c=solid(cube);assert c.contains([(0,0,0),(1,0,0),(1.1,0,0)]).tolist()==[True,True,False]
bpy.ops.mesh.primitive_torus_add(major_segments=24,minor_segments=8,major_radius=2,minor_radius=.5)
torus=bpy.context.object;c=solid(torus)
assert c.contains([(0,0,0),(2,0,0),(3,0,0)]).tolist()==[False,True,False]
# Concave L-shaped prism (closed, no through hole).
outline=[(0,0),(2,0),(2,1),(1,1),(1,2),(0,2)];n=len(outline)
vertices=[(x,y,z) for z in (-1,1) for x,y in outline]
faces=[tuple(reversed(range(n))),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
mesh=bpy.data.meshes.new('Concave');mesh.from_pydata(vertices,[],faces);mesh.update()
l=bpy.data.objects.new('L Volume',mesh);s.collection.objects.link(l)
c=solid(l);assert c.contains([(.5,1.5,0),(1.5,.5,0),(1.5,1.5,0)]).tolist()==[True,True,False]
p=point('Inside',(.5,.5,0));q=point('Notch',(1.5,1.5,0))
select(p,q);assert bpy.ops.zg.group_from_selection()=={'FINISHED'};assert len(s.zg.groups[0].manual_members)==2
assert bpy.ops.zg.group_new()=={'FINISHED'};assert bpy.ops.zg.membership_mode(value='VOLUME')=={'FINISHED'}
g=R.active(s);uid=g.uid;r=R.region(g);r.t_empty=True;r.t_mesh=False
assert bpy.ops.zg.volume_mesh(mesh_name=l.name)=={'FINISHED'}
assert R.get(s).members[uid]=={p}
assert r.volumes[0].kind=='MESH'
assert bpy.ops.zg.volume_select(index=0)=={'FINISHED'};assert bpy.context.active_object==l
builds=R.STATS['mesh_builds'];l.location.x=5;evaluate();assert not R.get(s).members[uid];assert R.STATS['mesh_builds']==builds
l.location.x=0;evaluate();assert R.get(s).members[uid]=={p}
l.scale=(-2,1,1);p.location.x=-1;evaluate();assert p in R.get(s).members[uid]
l.scale=(1,1,1);p.location.x=.5;evaluate()
# Mesh cache changes when raw geometry changes, including shared data.
for v in l.data.vertices:v.co.x+=10
l.data.update();bpy.context.view_layer.update();evaluate();assert p not in R.get(s).members[uid]
for v in l.data.vertices:v.co.x-=10
l.data.update();bpy.context.view_layer.update();evaluate();assert p in R.get(s).members[uid]
# Bounds-center, shear and raw-mesh modifier policy.
r.eval_mode='BOUNDS_CENTER';evaluate();assert p in R.get(s).members[uid]
from mathutils import Matrix
l.matrix_world=Matrix(((1,.4,0,0),(0,1,0,0),(0,0,1,0),(0,0,0,1)))
evaluate();assert p in R.get(s).members[uid]
l.matrix_world=Matrix.Identity(4)
mod=l.modifiers.new('Ignored','SOLIDIFY');mod.thickness=100
evaluate();assert q not in R.get(s).members[uid];l.modifiers.remove(mod)
r.eval_mode='ORIGIN'
# Mixed Empty exclusion retains the mesh solid as its ADD operand.
assert bpy.ops.zg.volume_add(shape='SPHERE')=={'FINISHED'}
r=R.region(R.active(s));v=r.volumes[-1];v.operation='EXCLUDE';v.controller.location=p.location;v.controller.empty_display_size=.1
evaluate();assert p not in R.get(s).members[uid]
assert bpy.ops.zg.volume_remove()=={'FINISHED'};evaluate();assert p in R.get(s).members[uid]
# Independent controller/data duplicate.
assert bpy.ops.zg.group_duplicate()=={'FINISHED'}
dup=R.region(R.active(s)).volumes[0].controller;assert dup!=l and dup.data!=l.data
# Isolate switches rows, does not simply disable existing isolate.
a=s.zg.groups[0].uid;b=s.zg.groups[1].uid
assert bpy.ops.zg.row_isolate(uid=a)=={'FINISHED'};assert s.zg.isolate_uid==a
assert bpy.ops.zg.row_isolate(uid=b)=={'FINISHED'};assert s.zg.isolate_uid==b
assert bpy.ops.zg.row_isolate(uid=b)=={'FINISHED'};assert not s.zg.isolate_uid
# Save/reload retains typed Mesh references and rebuilds runtime sets.
filepath='/tmp/zone_groups_mesh_roundtrip.blend'
bpy.ops.wm.save_as_mainfile(filepath=filepath);bpy.ops.wm.open_mainfile(filepath=filepath)
s=bpy.context.scene;l=bpy.data.objects['L Volume'];p=bpy.data.objects['Inside'];q=bpy.data.objects['Notch'];cube=bpy.data.objects['Cube']
evaluate();assert p in R.get(s).members[uid]
# Invalid open mesh must fail validation and retain committed result.
s.zg.active_index=1;old=set(R.get(s).members[uid])
import bmesh
bm=bmesh.new();bm.from_mesh(l.data);bm.faces.ensure_lookup_table();bmesh.ops.delete(bm,geom=[bm.faces[0]],context='FACES');bm.to_mesh(l.data);bm.free();l.data.update();bpy.context.view_layer.update();R.invalidate(s)
assert bpy.ops.zg.evaluate()=={'CANCELLED'};assert R.get(s).members[uid]==old
# Rejection of unsupported modes is explicit.
r=R.region(R.active(s));r.eval_mode='ANY_OVERLAP';count=len(r.volumes)
assert bpy.ops.zg.volume_mesh(mesh_name=cube.name)=={'CANCELLED'};assert len(r.volumes)==count
for cls in Z.CLASSES:
    if issubclass(cls,bpy.types.Operator):assert getattr(cls,'bl_description',''),cls.__name__
print('MESH_REGRESSION_PASS',bpy.app.version_string,R.STATS)
Z.unregister()
