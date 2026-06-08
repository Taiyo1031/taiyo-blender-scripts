import bpy
from bpy.props import EnumProperty, IntProperty, StringProperty
from bpy.types import AddonPreferences, PropertyGroup


ADDON_ID = __package__


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

    status_message: StringProperty(default="No graph data generated yet.")
    last_update: StringProperty(name="Last Update", default="-")
    node_count: IntProperty(name="Nodes", default=0, min=0)
    edge_count: IntProperty(name="Edges", default=0, min=0)
    resolved_output_path: StringProperty(name="Resolved Output Path", default="-")


class BRG_AddonPreferences(AddonPreferences):
    bl_idname = ADDON_ID

    output_mode: EnumProperty(
        name="Output Location",
        description="Choose where temporary viewer files are written",
        items=(
            ("TEMP", "System Temp", "Use a process-specific folder in the operating system temp directory"),
            ("CUSTOM", "Custom Folder", "Use a persistent custom output folder"),
        ),
        default="TEMP",
    )
    custom_output_folder: StringProperty(
        name="Custom Folder",
        description="Folder where graph_data.js and viewer files are written",
        default="",
        subtype="DIR_PATH",
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "output_mode")
        if self.output_mode == "CUSTOM":
            layout.prop(self, "custom_output_folder")
        layout.label(text="Viewer files are replaced each time graph data is updated.", icon="INFO")
