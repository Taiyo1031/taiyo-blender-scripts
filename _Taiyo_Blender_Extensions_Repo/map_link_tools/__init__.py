bl_info = {
    "name": "Map Link Tools",
    "author": "Generated for production map workflow",
    "version": (0, 2, 1),
    "blender": (4, 5, 0),
    "location": "View3D > Sidebar > Map Link Tools",
    "description": "Minimal map layout tools for renaming, checking mesh links, and replacing objects.",
    "category": "Object",
}

DOCUMENTATION_URL = "https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/_Taiyo_Blender_Extensions_Repo/map_link_tools/README.md"

import bpy
from bpy.props import PointerProperty

from . import properties
from .operators import check_ops, helper_ops, rename_ops, replace_ops
from .ui import panels


classes = (
    properties.MapLinkToolsSettings,
    rename_ops.MAPLINK_OT_remove_suffix_selected,
    rename_ops.MAPLINK_OT_object_name_to_mesh_name,
    rename_ops.MAPLINK_OT_mesh_name_to_object_name,
    check_ops.MAPLINK_OT_check_collection_mesh_links,
    check_ops.MAPLINK_OT_select_unlinked_in_collection,
    replace_ops.MAPLINK_OT_set_replace_collection_from_active_layer,
    replace_ops.MAPLINK_OT_replace_selected_with_active_object,
    replace_ops.MAPLINK_OT_replace_selected_with_collection_instance,
    replace_ops.MAPLINK_OT_replace_collection_instances_with_matching_mesh,
    helper_ops.MAPLINK_OT_unhide_helper_collection,
    helper_ops.MAPLINK_OT_make_helper_collection_selectable,
    panels.VIEW3D_PT_map_link_tools,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.maplink_settings = PointerProperty(type=properties.MapLinkToolsSettings)


def unregister():
    if hasattr(bpy.types.Scene, "maplink_settings"):
        delattr(bpy.types.Scene, "maplink_settings")
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
