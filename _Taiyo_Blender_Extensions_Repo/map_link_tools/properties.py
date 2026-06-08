import bpy
from bpy.props import BoolProperty, PointerProperty, StringProperty
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

    use_mesh_instance: BoolProperty(
        name="Use Mesh Instance",
        description="Share the active object's mesh data instead of copying it",
        default=True,
    )
    check_result_message: StringProperty(default="")
