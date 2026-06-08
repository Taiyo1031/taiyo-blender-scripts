import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty
from bpy.types import PropertyGroup


SCAN_MODE_ITEMS = (
    ("USES", "Uses", "Show references used by the target"),
    ("USED_BY", "Used By", "Show data that references the target"),
    ("BOTH", "Both", "Show both incoming and outgoing references"),
)


class BRG_Settings(PropertyGroup):
    target_type: StringProperty(name="Target Type", default="")
    target_name: StringProperty(name="Target Name", default="")
    target_id: StringProperty(name="Target ID", default="")

    scan_mode: EnumProperty(
        name="Scan Mode",
        items=SCAN_MODE_ITEMS,
        default="BOTH",
    )
    depth: IntProperty(
        name="Depth",
        description="How many reference levels to expand",
        default=3,
        min=1,
        max=5,
    )

    include_objects: BoolProperty(name="Object", default=True)
    include_meshes: BoolProperty(name="Mesh", default=True)
    include_collections: BoolProperty(name="Collection", default=True)
    include_armatures: BoolProperty(name="Armature", default=True)
    include_bones: BoolProperty(name="Bone", default=True)
    include_constraints: BoolProperty(name="Constraint", default=True)
    include_geonodes: BoolProperty(name="Geometry Nodes", default=True)
    include_node_groups: BoolProperty(name="Node Group", default=True)
    include_materials: BoolProperty(name="Material", default=False)
    include_images: BoolProperty(name="Image", default=False)

    output_folder: StringProperty(
        name="Output Folder",
        description="Folder where graph_data.js is written",
        default="//blend_reference_graph/",
        subtype="DIR_PATH",
    )
    viewer_file: StringProperty(name="Viewer File", default="viewer.html")
    status_message: StringProperty(default="No graph data generated yet.")
    last_update: StringProperty(name="Last Update", default="-")
    node_count: IntProperty(name="Nodes", default=0, min=0)
    edge_count: IntProperty(name="Edges", default=0, min=0)


def filters_from_settings(settings):
    return {
        "OBJECT": settings.include_objects,
        "MESH": settings.include_meshes,
        "COLLECTION": settings.include_collections,
        "ARMATURE": settings.include_armatures,
        "BONE": settings.include_bones,
        "CONSTRAINT": settings.include_constraints,
        "MODIFIER": settings.include_geonodes,
        "GEONODES": settings.include_geonodes,
        "NODEGROUP": settings.include_node_groups,
        "MATERIAL": settings.include_materials,
        "IMAGE": settings.include_images,
        "WARNING": True,
    }
