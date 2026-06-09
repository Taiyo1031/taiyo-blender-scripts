bl_info = {
    "name": "Modular Asset Renamer",
    "author": "Taiyo",
    "version": (1, 0, 6),
    "blender": (4, 5, 0),
    "location": "View3D > Sidebar (N) > Rename Tools",
    "description": "Build names from reusable modules and rename selected assets",
    "category": "Object",
}

import bpy
from bpy.props import PointerProperty

from . import operators, preset_utils, props, ui


DOCUMENTATION_URL = (
    "https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/"
    "_Taiyo_Blender_Extensions_Repo/modular_asset_renamer/README.md"
)


class MAR_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__ or __name__

    def draw(self, _context):
        layout = self.layout
        layout.label(text="Documentation")
        operator = layout.operator(
            "wm.url_open",
            text="Open Japanese User Guide on GitHub",
            icon="URL",
        )
        operator.url = DOCUMENTATION_URL


classes = (
    MAR_AddonPreferences,
    props.MAR_ChoiceOption,
    props.MAR_Module,
    props.MAR_PreviewItem,
    props.MAR_HistoryItem,
    props.MAR_Settings,
    operators.MAR_OT_add_module,
    operators.MAR_OT_remove_module,
    operators.MAR_OT_move_module,
    operators.MAR_OT_duplicate_module,
    operators.MAR_OT_toggle_module,
    operators.MAR_OT_set_separator,
    operators.MAR_OT_add_choice_option,
    operators.MAR_OT_remove_choice_option,
    operators.MAR_OT_move_choice_option,
    operators.MAR_OT_repair_choice_modules,
    operators.MAR_OT_preview,
    operators.MAR_OT_apply,
    operators.MAR_OT_revert,
    operators.MAR_OT_clear_preview,
    operators.MAR_OT_copy_preview_name,
    operators.MAR_OT_copy_all_preview_names,
    operators.MAR_OT_select_preview_name_matches,
    operators.MAR_OT_clear_history,
    operators.MAR_OT_load_preset,
    operators.MAR_OT_save_preset,
    operators.MAR_OT_save_preset_as,
    operators.MAR_OT_delete_preset,
    operators.MAR_OT_import_presets,
    operators.MAR_OT_export_presets,
    ui.MAR_UL_modules,
    ui.MAR_UL_choice_options,
    ui.MAR_UL_preview,
    ui.MAR_PT_main,
)


def _repair_existing_choice_modules():
    for scene in bpy.data.scenes:
        settings = getattr(scene, "mar_settings", None)
        if settings is not None:
            preset_utils.repair_settings(settings)
    return None


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.mar_settings = PointerProperty(type=props.MAR_Settings)
    if not bpy.app.timers.is_registered(_repair_existing_choice_modules):
        bpy.app.timers.register(_repair_existing_choice_modules, first_interval=0.1)


def unregister():
    if bpy.app.timers.is_registered(_repair_existing_choice_modules):
        bpy.app.timers.unregister(_repair_existing_choice_modules)
    if hasattr(bpy.types.Scene, "mar_settings"):
        del bpy.types.Scene.mar_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
