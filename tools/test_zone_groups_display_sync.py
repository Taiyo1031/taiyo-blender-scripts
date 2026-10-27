"""Verify viewport evaluated IDs, not just original Object values after bulk writes."""
import bpy,sys,pathlib,json
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'_Taiyo_Blender_Extensions_Repo'))
import zone_groups as Z
from zone_groups import runtime as R,operations as O
Z.register();bpy.data.batch_remove(ids=list(bpy.data.objects));s=bpy.context.scene
mesh=bpy.data.meshes.new('Shared');mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)])
objects=[]
for i in range(200):
 obj=bpy.data.objects.new(str(i),mesh);s.collection.objects.link(obj);objects.append(obj)
g=O.new_group(s);g.color=(1,0,0,1)
for obj in objects:g.manual_members.add().obj=obj
bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get();results=[]
def styled():
 R.MUTATING+=1
 try:R.drain(R.evaluation(s));R.drain(R.apply_style(s))
 finally:R.MUTATING-=1
 bpy.context.view_layer.update()
def colors(expected):
 assert all(tuple(o.color)==expected and tuple(o.evaluated_get(dg).color)==expected for o in objects)
R.MUTATING+=1;s.zg.color_enabled=True;R.MUTATING-=1
styled();colors((1,0,0,1));results.append('Bulk enable: original and evaluated color')
g.color=(0,1,0,1);styled();colors((0,1,0,1));results.append('Bulk color edit reaches evaluated Objects')
s.zg.color_enabled=False;styled();colors((1,1,1,1));results.append('Disable restores evaluated original colors')
tx=O.Transaction(s)
def work():
 s.zg.color_enabled=True
 yield from R.apply_style(s,tx.journal)
tx.generator=tx.prepare(work())
R.MUTATING+=1
try:R.drain(tx.generator)
finally:R.MUTATING-=1
bpy.context.view_layer.update();colors((0,1,0,1));tx.abort();bpy.context.view_layer.update();colors((1,1,1,1));results.append('Cancel after bulk color commit restores evaluated colors')
g=s.zg.groups[0];g.show=False;styled()
assert all(o.evaluated_get(dg).hide_viewport for o in objects)
assert all(not o.visible_get() for o in objects);results.append('Bulk viewport restriction reaches evaluated visibility')
g.show=True;styled();assert all(o.visible_get() for o in objects);results.append('Bulk visibility restore')
g.render=False;styled();assert all(o.evaluated_get(dg).hide_render for o in objects);results.append('Bulk render restriction reaches evaluated IDs')
g.render=True;styled();assert all(not o.evaluated_get(dg).hide_render for o in objects)
path=pathlib.Path('/tmp/zone_groups_display_sync_'+bpy.app.version_string.split()[0]+'.json');path.write_text(json.dumps(dict(blender=bpy.app.version_string,passed=results),indent=2))
print('DISPLAY_SYNC_PASS',bpy.app.version_string,results,flush=True)
Z.unregister()
