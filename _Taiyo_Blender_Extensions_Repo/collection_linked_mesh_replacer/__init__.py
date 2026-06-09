bl_info = {
    "name": "Collection Linked Mesh Replacer",
    "author": "Taiyo",
    "version": (1, 0, 8),
    "blender": (4, 5, 0),
    "location": "View3D > Sidebar (N) > Mesh Replace",
    "description": "Replace mesh objects with linked copies matched from a source collection",
    "category": "Object",
}

import bpy
from bpy.props import PointerProperty

from . import cache, operators, props, ui


DOCUMENTATION_URL = (
    "https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/"
    "_Taiyo_Blender_Extensions_Repo/collection_linked_mesh_replacer/README.md"
)


class CLMR_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__ or __name__

    def draw(self, context):
        layout = self.layout
        layout.label(text="Documentation")
        operator = layout.operator(
            "wm.url_open",
            text="Open User Guide on GitHub",
            icon="URL",
        )
        operator.url = DOCUMENTATION_URL


classes = (
    CLMR_AddonPreferences,
    props.CLMR_PreviewItem,
    props.CLMR_Settings,
    operators.CLMR_OT_build_cache,
    operators.CLMR_OT_clear_cache,
    operators.CLMR_OT_find_match,
    operators.CLMR_OT_thorough_find_match,
    operators.CLMR_OT_thorough_replace_active,
    operators.CLMR_OT_replace_active_manual,
    operators.CLMR_OT_find_selected,
    operators.CLMR_OT_replace_all_selected,
    ui.CLMR_UL_preview_results,
    ui.CLMR_PT_source,
    ui.CLMR_PT_actions,
    ui.CLMR_PT_match_result,
    ui.CLMR_PT_fallback,
    ui.CLMR_PT_cache,
    ui.CLMR_PT_settings,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.clmr_settings = PointerProperty(type=props.CLMR_Settings)


def unregister():
    cache.clear_cache()
    if hasattr(bpy.types.Scene, "clmr_settings"):
        del bpy.types.Scene.clmr_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
