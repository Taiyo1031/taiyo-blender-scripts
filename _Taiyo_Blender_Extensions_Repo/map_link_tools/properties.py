import bpy
from bpy.props import BoolProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import PropertyGroup


class MapLinkToolsSettings(PropertyGroup):
    show_rename: BoolProperty(
        name="Rename",
        default=True,
    )
    show_check: BoolProperty(
        name="Check",
        default=True,
    )
    show_replace: BoolProperty(
        name="Replace",
        default=True,
    )
    show_helper: BoolProperty(
        name="Helper",
        default=True,
    )

    collection_a: PointerProperty(
        name="Collection A",
        type=bpy.types.Collection,
    )
    collection_b: PointerProperty(
        name="Collection B",
        type=bpy.types.Collection,
    )
    replace_collection: PointerProperty(
        name="Instance Collection",
        type=bpy.types.Collection,
    )
    matching_mesh_collection: PointerProperty(
        name="Matching Mesh Collection",
        type=bpy.types.Collection,
    )
    helper_collection: PointerProperty(
        name="Helper Collection",
        type=bpy.types.Collection,
    )

    use_mesh_instance: BoolProperty(
        name="Use Mesh Instance",
        description="Share the active object's mesh data instead of copying it",
        default=True,
    )
    helper_make_selectable: BoolProperty(
        name="Make Selectable Too",
        description="Also make the collection tree and objects selectable when unhiding",
        default=True,
    )
    rename_unselected_conflicts: BoolProperty(
        name="Rename Unselected Conflicts",
        description=(
            "When removing .001, rename an unselected object that already uses the target name "
            "to the selected object's old name instead of skipping"
        ),
        default=False,
    )
    check_result_message: StringProperty(default="")
    helper_result_message: StringProperty(default="")

    is_running: BoolProperty(default=False)
    cancel_requested: BoolProperty(default=False)
    operation_name: StringProperty(default="")
    operation_message: StringProperty(default="")
    processed_count: IntProperty(default=0, min=0)
    total_count: IntProperty(default=0, min=0)
    progress_percent: FloatProperty(default=0.0, min=0.0, max=100.0)
