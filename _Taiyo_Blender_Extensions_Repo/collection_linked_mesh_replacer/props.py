import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)


class CLMR_PreviewItem(bpy.types.PropertyGroup):
    target_name: StringProperty(default="")
    match_name: StringProperty(default="")
    source_mesh: StringProperty(default="")
    confidence: StringProperty(default="")
    candidate_count: IntProperty(default=0, min=0)


class CLMR_Settings(bpy.types.PropertyGroup):
    source_collection: PointerProperty(
        name="Source Collection",
        description="Collection containing the canonical mesh objects",
        type=bpy.types.Collection,
    )
    match_method: EnumProperty(
        name="Match Method",
        items=[
            (
                "SHAPE_HASH",
                "Mesh Shape Hash",
                "Match topology and normalized local mesh geometry",
            ),
        ],
        default="SHAPE_HASH",
    )
    verify_match: BoolProperty(
        name="Verify Match Before Replace",
        description="Recalculate both meshes immediately before replacement",
        default=True,
    )
    recursive_search: BoolProperty(
        name="Search Source Collection Recursively",
        description="Include objects in child collections",
        default=True,
    )
    keep_transform: BoolProperty(
        name="Keep Transform",
        description="Copy the target object's world transform",
        default=True,
    )
    adjust_bbox_center: BoolProperty(
        name="Adjust by Bounding Box Center",
        description="Offset the new object so its world bounding box center matches the target",
        default=True,
    )
    original_mode: EnumProperty(
        name="Original Object Mode",
        items=[
            (
                "BACKUP",
                "Move to Backup Collection",
                "Move and hide the original object in a backup collection",
            ),
            (
                "DELETE",
                "Delete Original",
                "Permanently remove the original object",
            ),
            (
                "HIDE",
                "Hide Original",
                "Keep the original in place but hide it in viewport and render",
            ),
            (
                "KEEP",
                "Keep Original",
                "Keep the original object unchanged",
            ),
        ],
        default="BACKUP",
    )
    backup_collection_name: StringProperty(
        name="Backup Collection",
        default="_MeshReplace_Backup",
    )
    multiple_matches: EnumProperty(
        name="Multiple Matches",
        items=[
            (
                "FIRST",
                "Use First Match",
                "Use the first source object sorted by name",
            ),
        ],
        default="FIRST",
    )
    ignore_source_objects: BoolProperty(
        name="Ignore Source Collection Objects",
        description="Do not replace objects contained in the source collection",
        default=True,
    )
    select_new_objects: BoolProperty(
        name="Select New Object After Replace",
        default=True,
    )
    rename_to_source: BoolProperty(
        name="Rename New Object to Source Name",
        default=False,
    )

    result_selected: StringProperty(default="")
    result_match: StringProperty(default="")
    result_source_mesh: StringProperty(default="")
    result_confidence: StringProperty(default="Not Searched")
    result_candidates: IntProperty(default=0, min=0)

    preview_items: CollectionProperty(type=CLMR_PreviewItem)
    preview_index: IntProperty(default=0, min=0)
    preview_matched: IntProperty(default=0, min=0)
    preview_not_found: IntProperty(default=0, min=0)
    preview_skipped: IntProperty(default=0, min=0)

    batch_replaced: IntProperty(default=0, min=0)
    batch_not_found: IntProperty(default=0, min=0)
    batch_failed: IntProperty(default=0, min=0)
    batch_skipped: IntProperty(default=0, min=0)
