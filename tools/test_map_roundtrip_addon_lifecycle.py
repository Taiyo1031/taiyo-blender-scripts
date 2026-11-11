import bpy,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'_Taiyo_Blender_Extensions_Repo'))
import map_roundtrip_tools as m
import unreal_bridge_tools as u
for register,unregister in [((m,u),(m,u)),((m,u),(u,m)),((u,m),(m,u)),((u,m),(u,m))]:
 for a in register:a.register()
 assert set(u.UBT_Props.bl_rna.properties['scope'].enum_items.keys())=={'direct','recursive','all'}
 assert 'tag_zone' not in u.UBT_Props.bl_rna.properties
 assert not hasattr(bpy.types,'UBT_OT_SelectInZone')
 bpy.ops.mrt.new_zone(name='ZONE_LIFECYCLE')
 bpy.ops.mrt.add_zone_empty()
 for a in unregister:a.unregister()
print('MRT_UBT_LIFECYCLE_PASSED',bpy.app.version_string)
