bl_info = {
    "name": "Custom Properties Batch Editor",
    "author": "Taiyo",
    "version": (1, 0, 0),
    "blender": (4, 4, 0),
    "location": "View3D > Sidebar (N) > Custom Props",
    "description": "Batch edit and search custom properties on objects, meshes, and materials.",
    "category": "Object",
}

import bpy
from bpy.props import PointerProperty

from . import operators, props, ui


DOCUMENTATION_URL = (
    "https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/"
    "_Taiyo_Blender_Extensions_Repo/custom_properties_batch_editor/README.md"
)


classes = (
    props.CPBE_PresetPropertyItem,
    props.CPBE_PropertySummaryItem,
    props.CPBE_Settings,
    props.CPBE_AddonPreferences,
    operators.CPBE_OT_apply_property,
    operators.CPBE_OT_search_property,
    operators.CPBE_OT_delete_property,
    operators.CPBE_OT_refresh_property_list,
    operators.CPBE_OT_copy_log,
    operators.CPBE_OT_add_preset_item,
    operators.CPBE_OT_remove_preset_item,
    operators.CPBE_OT_clear_preset_items,
    operators.CPBE_OT_load_preset_to_editor,
    operators.CPBE_OT_save_preset,
    operators.CPBE_OT_apply_preset,
    operators.CPBE_OT_delete_preset,
    operators.CPBE_OT_import_presets,
    operators.CPBE_OT_export_presets,
    ui.CPBE_UL_property_summary,
    ui.CPBE_UL_preset_properties,
    ui.CPBE_PT_main,
    ui.CPBE_PT_target,
    ui.CPBE_PT_add_edit,
    ui.CPBE_PT_search,
    ui.CPBE_PT_delete,
    ui.CPBE_PT_property_list,
    ui.CPBE_PT_presets,
    ui.CPBE_PT_log,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.cpbe_settings = PointerProperty(type=props.CPBE_Settings)


def unregister():
    if hasattr(bpy.types.Scene, "cpbe_settings"):
        del bpy.types.Scene.cpbe_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
