"""Legacy UBT data survives without registering UBT; batch selection is separate."""
import bpy,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'_Taiyo_Blender_Extensions_Repo'))
class LegacyZone(bpy.types.PropertyGroup):
 name:bpy.props.StringProperty()
class LegacySettings(bpy.types.PropertyGroup):
 zones:bpy.props.CollectionProperty(type=LegacyZone)
bpy.utils.register_class(LegacyZone);bpy.utils.register_class(LegacySettings)
bpy.types.Scene.ubt_props=bpy.props.PointerProperty(type=LegacySettings)
s=bpy.context.scene;s.ubt_props.zones.add().name='ZONE_EMPTY_OLD'
del bpy.types.Scene.ubt_props
bpy.utils.unregister_class(LegacySettings);bpy.utils.unregister_class(LegacyZone)
bpy.data.batch_remove(ids=list(bpy.data.objects))
legacy=[]
for name,zone,operation,enabled in [('ZONE_OLD','ZONE_OLD',0,True),('ZONE_OLD.001','ZONE_OLD',1,True),('ZONE_DISABLED','ZONE_OLD',0,False),('ZONE_B','ZONE_B',0,True)]:
 e=bpy.data.objects.new(name,None);e.empty_display_type='CUBE';e['zone']=zone;e['ubt_zone_operation']=operation;e['ubt_zone_enabled']=enabled;s.collection.objects.link(e);legacy.append(e)
import map_roundtrip_tools as mrt
from map_roundtrip_tools.zones import zone_items,collect_zone_boxes
mrt.register();p=s.mrt_props
assert 'ZONE_EMPTY_OLD' in {e[0] for e in zone_items(p,bpy.context)}
assert legacy[1].mrt_zone_operation=='SUBTRACT' and not legacy[2].mrt_zone_enabled
p.zone_choice='ZONE_OLD';bpy.context.view_layer.update()
assert bpy.ops.mrt.select_zone_empties()=={'FINISHED'}
assert set(bpy.context.selected_objects)==set(legacy[:2])
p.zone_choice='ALL';assert bpy.ops.mrt.select_zone_empties()=={'FINISHED'}
assert set(bpy.context.selected_objects)=={legacy[0],legacy[1],legacy[3]}
boxes=collect_zone_boxes(s,'ZONE_')['ZONE_OLD'];assert len(boxes)==len(boxes.subtract)==1
assert not hasattr(bpy.types,'UBT_OT_SelectInZone')
print('LEGACY_ZONE_MIGRATION_AND_BATCH_SELECTION_PASSED',bpy.app.version_string)
mrt.unregister()
