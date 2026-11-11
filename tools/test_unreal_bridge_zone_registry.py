"""Explicit zone/Empty registration and Japanese tooltips."""
import sys,tempfile
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'_Taiyo_Blender_Extensions_Repo'))
import unreal_bridge_tools as ubt
import map_roundtrip_tools as mrt
from unreal_bridge_tools.zones import zone_empties,zone_items
ubt.register();mrt.register()
bpy.data.batch_remove(ids=list(bpy.data.objects))
s=bpy.context.scene;p=s.ubt_props
assert bpy.ops.ubt.new_zone(name='ZONE_Z')=={'FINISHED'}
assert p.zone_choice=='ZONE_Z' and 'ZONE_Z' in p.zones
assert 'ZONE_Z' in [i[0] for i in zone_items(p,bpy.context)]
# An unrelated legacy zone sorting before Z can disappear during reassignment.
a=bpy.data.objects.new('ZONE_A',None);a.empty_display_type='CUBE';s.collection.objects.link(a)
b=bpy.data.objects.new('Artist Box',None);b.empty_display_type='PLAIN_AXES';s.collection.objects.link(b)
b.location=(2,3,4);b.rotation_euler=(.1,.2,.3);b.scale=(2,3,4)
saved=(tuple(b.location),tuple(b.rotation_euler),tuple(b.scale))
p.zone_choice='ZONE_Z'
a.select_set(True);b.select_set(True)
assert bpy.ops.ubt.register_zone_empties()=={'FINISHED'}
assert a['zone']==b['zone']=='ZONE_Z' and p.zone_choice=='ZONE_Z'
assert b.name=='Artist Box' and b.empty_display_type=='CUBE'
assert saved==(tuple(b.location),tuple(b.rotation_euler),tuple(b.scale))
assert set(zone_empties(s,'ZONE_'))=={a,b}
assert bpy.ops.ubt.zone_empty_action(object_name=b.name,action='SELECT')=={'FINISHED'}
assert set(bpy.context.selected_objects)=={b}
assert bpy.ops.ubt.zone_empty_action(object_name=a.name,action='UNREGISTER')=={'FINISHED'}
assert a.name in s.objects and a not in set(zone_empties(s,'ZONE_'))
assert p.zone_choice=='ZONE_Z'
# UI registration can re-enable the same object without renaming it.
bpy.ops.object.select_all(action='DESELECT');a.select_set(True)
assert bpy.ops.ubt.register_zone_empties()=={'FINISHED'}
assert a in set(zone_empties(s,'ZONE_'))
assert bpy.ops.ubt.new_zone(name='ZONE_EMPTY')=={'FINISHED'}
mesh=bpy.data.meshes.new('Candidate');ob=bpy.data.objects.new('Candidate',mesh);s.collection.objects.link(ob)
bpy.context.view_layer.update();bpy.ops.object.select_all(action='DESELECT');ob.select_set(True)
p.scope='all'
try:bpy.ops.ubt.select_in_zone()
except RuntimeError:pass
else:raise AssertionError('Empty zone must fail before changing selection')
assert ob.select_get()
path=Path(tempfile.mkdtemp(prefix='zone-registry-'))/'registry.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(path));bpy.ops.wm.open_mainfile(filepath=str(path))
p=bpy.context.scene.ubt_props
assert 'ZONE_EMPTY' in p.zones and 'ZONE_Z' in p.zones
assert bpy.context.scene.objects['Artist Box']['zone']=='ZONE_Z'
for attr in ('exchange_dir','zone_name','library_coll','map_coll','placement_csv','mesh_fbx','zone_override','dry_run'):
 assert mrt.MRT_Props.bl_rna.properties[attr].description,attr
assert '参考' in mrt.MRT_Props.bl_rna.properties['exchange_dir'].description
assert '自動' in ubt.UBT_Props.bl_rna.properties['zone_prefix'].description
print('ZONE_REGISTRY_AND_TOOLTIPS_PASSED',bpy.app.version_string,flush=True)
mrt.unregister();ubt.unregister()
