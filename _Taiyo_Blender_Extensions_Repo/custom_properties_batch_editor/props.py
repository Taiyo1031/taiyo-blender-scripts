import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import AddonPreferences, PropertyGroup


ADDON_ID = __package__

TARGET_TYPE_ITEMS = (
    ("OBJECT", "Object", "Edit custom properties on objects"),
    ("MESH", "Mesh Data", "Edit custom properties on mesh data-blocks"),
    ("MATERIAL", "Material", "Edit custom properties on materials in material slots"),
)

SCOPE_ITEMS = (
    ("SELECTED", "Selected Objects", "Use selected objects"),
    ("ACTIVE", "Active Object", "Use only the active object"),
    ("SCENE", "All Scene Objects", "Use all objects in the current scene"),
)

PROPERTY_TYPE_ITEMS = (
    ("STRING", "String", "Text value"),
    ("INT", "Int", "Integer value"),
    ("FLOAT", "Float", "Floating-point value"),
    ("BOOL", "Bool", "Boolean value"),
)

OPERATION_MODE_ITEMS = (
    ("UPSERT", "Add or Overwrite", "Add missing properties and overwrite existing values"),
    ("ADD_ONLY", "Add Only", "Add the property only when it does not exist"),
    ("EDIT_ONLY", "Edit Existing Only", "Change only targets that already have the property"),
)

MATCH_MODE_ITEMS = (
    ("EXISTS", "Exists", "Match targets that contain the property"),
    ("EQUALS", "Equals", "Match targets whose value equals the search value"),
    ("CONTAINS", "Contains", "Match string values containing the search text"),
    ("NOT_EXISTS", "Not Exists", "Match targets that do not contain the property"),
)

DELETE_MODE_ITEMS = (
    ("EXISTS", "Delete If Exists", "Delete the property whenever it exists"),
    ("VALUE", "Delete If Value Matches", "Delete only when the value matches"),
)

PROPERTY_LIST_MODE_ITEMS = (
    ("ACTIVE_ONLY", "Active Only", "Show properties from the active object's current target"),
    ("SELECTED_SUMMARY", "Selected Summary", "Summarize properties across selected objects"),
    ("TARGET_DATA", "Target Data", "Summarize properties across the current target scope"),
)


def preset_enum_items(_self, _context):
    from . import preset_utils

    try:
        presets = preset_utils.load_presets()
    except Exception:
        presets = []
    if not presets:
        return [("__NONE__", "No Presets", "No presets are available")]
    return [
        (preset["name"], preset["name"], f"{len(preset['properties'])} properties")
        for preset in presets
    ]


class CPBE_PresetPropertyItem(PropertyGroup):
    property_name: StringProperty(name="Property Name", default="")
    property_type: EnumProperty(name="Type", items=PROPERTY_TYPE_ITEMS, default="STRING")
    string_value: StringProperty(name="String Value", default="")
    int_value: IntProperty(name="Int Value", default=0)
    float_value: FloatProperty(name="Float Value", default=0.0)
    bool_value: BoolProperty(name="Bool Value", default=False)


class CPBE_PropertySummaryItem(PropertyGroup):
    property_name: StringProperty(name="Property Name", default="")
    value_type: StringProperty(name="Type", default="")
    value_preview: StringProperty(name="Value", default="")
    target_count: IntProperty(name="Count", default=0, min=0)
    mixed: BoolProperty(name="Mixed", default=False)


class CPBE_Settings(PropertyGroup):
    target_type: EnumProperty(name="Target Type", items=TARGET_TYPE_ITEMS, default="OBJECT")
    scope: EnumProperty(name="Scope", items=SCOPE_ITEMS, default="SELECTED")
    include_hidden: BoolProperty(name="Include Hidden", default=False)
    include_disabled_viewport: BoolProperty(
        name="Include Disabled Viewport",
        default=False,
    )
    unique_data_only: BoolProperty(
        name="Unique Data Only",
        description="Process shared mesh data only once",
        default=True,
    )

    property_name: StringProperty(name="Property Name", default="")
    property_type: EnumProperty(name="Property Type", items=PROPERTY_TYPE_ITEMS, default="STRING")
    string_value: StringProperty(name="Value", default="")
    int_value: IntProperty(name="Value", default=0)
    float_value: FloatProperty(name="Value", default=0.0)
    bool_value: BoolProperty(name="Value", default=False)
    operation_mode: EnumProperty(name="Operation Mode", items=OPERATION_MODE_ITEMS, default="UPSERT")

    search_property_name: StringProperty(name="Property Name", default="")
    search_match_mode: EnumProperty(name="Match Mode", items=MATCH_MODE_ITEMS, default="EXISTS")
    search_property_type: EnumProperty(name="Value Type", items=PROPERTY_TYPE_ITEMS, default="STRING")
    search_string_value: StringProperty(name="Value", default="")
    search_int_value: IntProperty(name="Value", default=0)
    search_float_value: FloatProperty(name="Value", default=0.0)
    search_bool_value: BoolProperty(name="Value", default=False)
    case_sensitive: BoolProperty(name="Case Sensitive", default=False)

    delete_property_name: StringProperty(name="Property Name", default="")
    delete_mode: EnumProperty(name="Delete Mode", items=DELETE_MODE_ITEMS, default="EXISTS")
    delete_property_type: EnumProperty(name="Value Type", items=PROPERTY_TYPE_ITEMS, default="STRING")
    delete_string_value: StringProperty(name="Value", default="")
    delete_int_value: IntProperty(name="Value", default=0)
    delete_float_value: FloatProperty(name="Value", default=0.0)
    delete_bool_value: BoolProperty(name="Value", default=False)
    confirm_delete: BoolProperty(name="Confirm Delete", default=False)

    property_list_mode: EnumProperty(
        name="List Mode",
        items=PROPERTY_LIST_MODE_ITEMS,
        default="ACTIVE_ONLY",
    )
    property_summaries: CollectionProperty(type=CPBE_PropertySummaryItem)
    property_summary_index: IntProperty(default=0)

    preset_name: StringProperty(name="Preset Name", default="")
    selected_preset: EnumProperty(name="Preset", items=preset_enum_items)
    preset_properties: CollectionProperty(type=CPBE_PresetPropertyItem)
    preset_property_index: IntProperty(default=0)

    result_target_type: StringProperty(default="-")
    result_scanned: IntProperty(default=0, min=0)
    result_changed: IntProperty(default=0, min=0)
    result_skipped: IntProperty(default=0, min=0)
    result_failed: IntProperty(default=0, min=0)
    log_text: StringProperty(default="No operation has run yet.")


class CPBE_AddonPreferences(AddonPreferences):
    bl_idname = ADDON_ID

    def draw(self, _context):
        layout = self.layout
        layout.label(text="Documentation")
        op = layout.operator("wm.url_open", text="Open User Guide on GitHub", icon="URL")
        from . import DOCUMENTATION_URL

        op.url = DOCUMENTATION_URL
