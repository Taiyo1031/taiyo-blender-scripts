"""Union/subtraction, add button, persistence and 100k point benchmark."""
import importlib
import json
from pathlib import Path
import sys
import tempfile
import time
import bpy
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'_Taiyo_Blender_Extensions_Repo'))
ubt=importlib.import_module('unreal_bridge_tools')
from unreal_bridge_tools.zones import collect_zone_boxes,inside_mask,points_of
ubt.register()
bpy.data.batch_remove(ids=list(bpy.data.objects))
bpy.data.batch_remove(ids=list(bpy.data.collections))
scene=bpy.context.scene
p=scene.ubt_props
scene.cursor.location=(3,4,5)
assert bpy.ops.ubt.add_zone_empty(zone_name='ZONE_A')=={'FINISHED'}
a=bpy.context.view_layer.objects.active
assert a.empty_display_type=='CUBE' and a.ubt_zone_operation=='ADD'
assert tuple(a.location)==(3,4,5) and a['zone']=='ZONE_A' and p.zone_choice=='ZONE_A'
assert bpy.ops.ubt.add_zone_empty()=={'FINISHED'}
b=bpy.context.view_layer.objects.active
assert b!=a and b['zone']=='ZONE_A'
a.location=(0,0,0);a.empty_display_size=2
b.location=(5,0,0);b.empty_display_size=1
b.rotation_euler=(0,0,.5);b.scale=(1,2,1)
assert bpy.ops.ubt.add_zone_empty()=={'FINISHED'}
cut=bpy.context.view_layer.objects.active
cut.location=(0,0,0);cut.empty_display_size=.75;cut.ubt_zone_operation='SUBTRACT'
# Another zone can still claim origins removed from A.
assert bpy.ops.ubt.add_zone_empty(zone_name='ZONE_B')=={'FINISHED'}
other=bpy.context.view_layer.objects.active
other.location=(0,0,0);other.empty_display_size=1
# Legacy .001 objects have no operation property and remain additive.
legacy=bpy.data.objects.new('ZONE_LEGACY.001',None)
legacy.empty_display_type='CUBE';scene.collection.objects.link(legacy)
legacy.location=(50,0,0)
# A zone with only negative boxes is empty.
assert bpy.ops.ubt.add_zone_empty(zone_name='ZONE_NEG')=={'FINISHED'}
negative=bpy.context.view_layer.objects.active;negative.ubt_zone_operation='SUBTRACT'
negative.location=(0,0,0)
bpy.context.view_layer.update()
zones=collect_zone_boxes(scene,'ZONE_')
pts=np.array([[0,0,0,1],[1.5,0,0,1],[5,0,0,1],[30,0,0,1],[.75,0,0,1]],dtype=float)
assert inside_mask(pts,zones['ZONE_A']).tolist()==[False,True,True,False,False]
assert inside_mask(pts,zones['ZONE_B']).tolist()==[True,False,False,False,True]
assert not inside_mask(pts,zones['ZONE_NEG']).any()
assert len(zones['ZONE_LEGACY'])==1
# Duplicated cut boxes still subtract, including after rotation/scale.
cut.rotation_euler=(0,0,.6);cut.scale=(2,1,1)
bpy.context.view_layer.update()
zones=collect_zone_boxes(scene,'ZONE_')
assert not inside_mask(np.array([[0,0,0,1.]]),zones['ZONE_A'])[0]
mesh=bpy.data.meshes.new('Mesh');objects=[]
for xyz in ((0,0,0),(1.9,0,0),(5,0,0),(30,0,0)):
 o=bpy.data.objects.new('Candidate',mesh);scene.collection.objects.link(o);o.location=xyz;objects.append(o)
bpy.context.view_layer.update()
p.scope='all';p.zone_choice='ZONE_A'
assert bpy.ops.ubt.select_in_zone()=={'FINISHED'}
assert set(bpy.context.selected_objects)==set(objects[1:3])
p.zone_choice='ALL'
assert bpy.ops.ubt.select_in_zone()=={'FINISHED'}
assert set(bpy.context.selected_objects)==set(objects[:3])
assert 'ZONE_A 2' in p.zone_result and 'ZONE_B 1' in p.zone_result
# Undoable data operation settings persist through a .blend save/load.
cut_name=cut.name
path=Path(tempfile.mkdtemp(prefix='ubt-zones-'))/'zones.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(path))
bpy.ops.wm.open_mainfile(filepath=str(path))
assert bpy.context.scene.objects[cut_name].ubt_zone_operation=='SUBTRACT'
assert bpy.context.scene.objects[cut_name]['zone']=='ZONE_A'
zones=collect_zone_boxes(bpy.context.scene,'ZONE_')
pts=np.ones((100000,4));pts[:,:3]=np.random.default_rng(5).uniform(-6,6,(100000,3))
t=time.perf_counter();inside_mask(pts,zones['ZONE_A']);seconds=time.perf_counter()-t
result={'blender':bpy.app.version_string,'numpy_100k_union_subtract_seconds':seconds,'passed':True}
Path('/tmp/ubt_zone_boolean_'+bpy.app.version_string.split()[0]+'.json').write_text(json.dumps(result,indent=2))
print('ZONE_BOOLEAN_TESTS_PASSED',result,flush=True)
ubt.unregister()
