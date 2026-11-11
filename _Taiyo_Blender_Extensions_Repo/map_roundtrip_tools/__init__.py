bl_info = {
    'name': 'Map Roundtrip Tools', 'author': 'Taiyo', 'version': (0, 1, 0),
    'blender': (4, 5, 0), 'location': 'View3D > Sidebar > Map Roundtrip',
    'description': 'Roundtrip linked map placements and library FBX meshes through Houdini',
    'category': 'Import-Export',
}
import bpy
from .props import MRT_Props
from .presets import MRT_OT_SavePreset, MRT_OT_DeletePreset
from .placement import MRT_OT_ReplaceZone
from .mesh_import import MRT_OT_ImportMeshes
from .fbx_export import MRT_OT_ExportFBX
from .ui import MRT_PT_Export, MRT_PT_Import

classes = (MRT_Props, MRT_OT_SavePreset, MRT_OT_DeletePreset, MRT_OT_ReplaceZone,
           MRT_OT_ImportMeshes, MRT_OT_ExportFBX, MRT_PT_Export, MRT_PT_Import)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.mrt_props = bpy.props.PointerProperty(type=MRT_Props)


def unregister():
    from . import chunked
    if chunked._RUNNING is not None:
        raise RuntimeError('Finish or cancel Map Roundtrip before disabling the extension.')
    del bpy.types.Scene.mrt_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
