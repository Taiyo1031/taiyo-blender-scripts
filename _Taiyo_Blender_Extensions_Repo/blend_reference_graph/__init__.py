bl_info = {
    "name": "Blend Reference Graph",
    "author": "Taiyo",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Blend Ref Graph",
    "description": "Visualize Blender object, mesh, collection, constraint, and Geometry Nodes references.",
    "category": "Object",
}

import bpy
from bpy.props import PointerProperty

from . import operators, panels, properties


classes = (
    properties.BRG_Settings,
    operators.BRG_OT_use_selected,
    operators.BRG_OT_update_graph_data,
    operators.BRG_OT_open_viewer,
    operators.BRG_OT_update_and_open_viewer,
    panels.VIEW3D_PT_blend_reference_graph,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.brg_settings = PointerProperty(type=properties.BRG_Settings)


def unregister():
    if hasattr(bpy.types.Scene, "brg_settings"):
        delattr(bpy.types.Scene, "brg_settings")
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
