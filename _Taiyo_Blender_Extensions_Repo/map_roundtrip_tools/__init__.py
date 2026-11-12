bl_info = {
    'name': 'Map Roundtrip Tools', 'author': 'Taiyo', 'version': (0, 5, 1),
    'blender': (4, 5, 0), 'location': 'View3D > Sidebar > Map Roundtrip',
    'description': 'Roundtrip linked map placements and library FBX meshes through Houdini',
    'category': 'Import-Export',
}
import bpy
from .zones import (MRT_LegacyZoneEntry, MRT_LegacyUBTProps, migrate_legacy_zone_registry, MRT_ZoneEntry, MRT_OT_NewZone, MRT_OT_RegisterZoneEmpties,
                    MRT_OT_ZoneEmptyAction, MRT_OT_AddZoneEmpty, MRT_OT_SelectInZone,
                    MRT_OT_SelectZoneEmpties, register_zone_properties, unregister_zone_properties)
from .zone_csv import MRT_OT_ExportZoneCSV
from .zone_add_objects import MRT_OT_AddObjectsToZone
from .props import MRT_Props
from .presets import MRT_OT_SavePreset, MRT_OT_DeletePreset
from .placement import MRT_OT_ReplaceZone
from .mesh_import import MRT_OT_ImportMeshes
from .fbx_export import MRT_OT_ExportFBX, MRT_OT_ExportFBXNative
from .ui import MRT_PT_Export, MRT_PT_Import
from .ui_zones import (MRT_PT_Zones, MRT_PT_ZoneRange, MRT_PT_ZoneEmpties, MRT_PT_ZoneCheck,
                       MRT_PT_ZoneCSV, MRT_PT_ZoneAdvanced)

# Panels are listed in registration order: Zones (with its sub-panels) must come first.
classes = (MRT_LegacyZoneEntry, MRT_LegacyUBTProps, MRT_ZoneEntry, MRT_Props, MRT_OT_NewZone, MRT_OT_RegisterZoneEmpties,
           MRT_OT_ZoneEmptyAction, MRT_OT_AddZoneEmpty, MRT_OT_SelectInZone, MRT_OT_SelectZoneEmpties,
           MRT_OT_ExportZoneCSV, MRT_OT_AddObjectsToZone, MRT_OT_SavePreset, MRT_OT_DeletePreset, MRT_OT_ReplaceZone,
           MRT_OT_ImportMeshes, MRT_OT_ExportFBX, MRT_OT_ExportFBXNative,
           MRT_PT_Zones, MRT_PT_ZoneRange, MRT_PT_ZoneEmpties, MRT_PT_ZoneCheck, MRT_PT_ZoneCSV, MRT_PT_ZoneAdvanced,
           MRT_PT_Export, MRT_PT_Import)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.mrt_props = bpy.props.PointerProperty(type=MRT_Props)
    register_zone_properties()
    bpy.app.handlers.load_post.append(migrate_legacy_zone_registry)
    bpy.app.timers.register(migrate_legacy_zone_registry, first_interval=0.0)


def unregister():
    from . import chunked, zones
    if chunked._RUNNING is not None or zones._RUNNING:
        raise RuntimeError('Finish or cancel Map Roundtrip before disabling the extension.')
    if bpy.app.timers.is_registered(migrate_legacy_zone_registry):
        bpy.app.timers.unregister(migrate_legacy_zone_registry)
    bpy.app.handlers.load_post.remove(migrate_legacy_zone_registry)
    unregister_zone_properties()
    del bpy.types.Scene.mrt_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
