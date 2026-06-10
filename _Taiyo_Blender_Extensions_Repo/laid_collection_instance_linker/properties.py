import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)


NAME_SOURCE_ITEMS = (
    (
        "OBJECT_THEN_MESH",
        "Object Name, then Mesh Data",
        "Try the object name first, then the mesh data name when no target is found",
    ),
    (
        "OBJECT_ONLY",
        "Object Name Only",
        "Match target collections using only object names",
    ),
    (
        "MESH_ONLY",
        "Mesh Data Name Only",
        "Match target collections using only mesh data names",
    ),
)


class LCIL_PreviewItem(bpy.types.PropertyGroup):
    status: StringProperty(default="")
    object_name: StringProperty(default="")
    match_key: StringProperty(default="")
    source_name_field: StringProperty(default="")
    target_collection: StringProperty(default="")
    target_path: StringProperty(default="")
    color_tag: StringProperty(default="NONE")
    detail: StringProperty(default="")


class LCIL_Settings(bpy.types.PropertyGroup):
    laid_map_collection: PointerProperty(
        name="Laid_MAP Collection",
        description="Source map collection whose objects provide transforms",
        type=bpy.types.Collection,
    )
    individual_root: PointerProperty(
        name="Laid_Individual Root",
        description="Root containing target collections with direct mesh objects",
        type=bpy.types.Collection,
    )
    output_collection_name: StringProperty(
        name="Output Collection",
        description="Collection receiving generated instances",
        default="Generated_SIM_Map",
    )
    name_source: EnumProperty(
        name="Name Source",
        items=NAME_SOURCE_ITEMS,
        default="OBJECT_THEN_MESH",
    )
    ignore_numeric_suffix: BoolProperty(
        name="Ignore .001 / .1234",
        description="Ignore a trailing dot followed only by digits",
        default=True,
    )
    only_mesh_objects: BoolProperty(
        name="Only Mesh Objects",
        description="Process only mesh objects under Laid_MAP",
        default=True,
    )
    group_by_target: BoolProperty(
        name="Group by Target Collection",
        description="Create one output child collection per target collection",
        default=True,
    )
    instance_prefix: StringProperty(
        name="Instance Prefix",
        description="Prefix for generated collection instance object names",
        default="INST_",
    )
    show_issues_only: BoolProperty(
        name="Show Issues Only",
        description="Show only missing and duplicate preview results",
        default=True,
    )
    preview_items: CollectionProperty(type=LCIL_PreviewItem)
    preview_index: IntProperty(default=0, min=0)
    preview_linked: IntProperty(default=0, min=0)
    preview_missing: IntProperty(default=0, min=0)
    preview_duplicate: IntProperty(default=0, min=0)
    preview_skipped: IntProperty(default=0, min=0)
