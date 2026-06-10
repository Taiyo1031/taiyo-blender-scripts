bl_info = {
    "name": "CW_Laid Collection Instance Linker",
    "author": "Taiyo",
    "version": (1, 0, 1),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar (N) > Laid Linker",
    "description": "Match laid map objects to collections and generate collection instances",
    "category": "Object",
}

import bpy
from bpy.props import PointerProperty

from . import operators, properties, ui


DOCUMENTATION_URL = (
    "https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/"
    "_Taiyo_Blender_Extensions_Repo/laid_collection_instance_linker/README.md"
)


class LCIL_AddonPreferences(bpy.types.AddonPreferences):
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
    LCIL_AddonPreferences,
    properties.LCIL_PreviewItem,
    properties.LCIL_Settings,
    operators.LCIL_OT_preview_link,
    operators.LCIL_OT_select_object,
    operators.LCIL_OT_select_issue_objects,
    operators.LCIL_OT_generate_instances,
    operators.LCIL_OT_realize_instances,
    operators.LCIL_OT_delete_generated_empties,
    ui.LCIL_UL_preview_results,
    ui.LCIL_PT_main,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.lcil_settings = PointerProperty(type=properties.LCIL_Settings)


def unregister():
    if hasattr(bpy.types.Scene, "lcil_settings"):
        del bpy.types.Scene.lcil_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
