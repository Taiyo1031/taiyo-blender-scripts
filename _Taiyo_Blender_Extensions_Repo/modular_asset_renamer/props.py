import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import PropertyGroup


MODULE_TYPE_ITEMS = (
    ("TEXT", "Text", "Output fixed text"),
    ("CHOICE", "Choice", "Output one value from an editable list"),
    ("DIMENSIONS", "Dimensions", "Output object dimensions"),
    ("INDEX", "Index", "Output a sequential number"),
    ("ORIGINAL_NAME", "Original Name", "Reuse the original object name"),
    ("COLLECTION_NAME", "Collection Name", "Output a collection name"),
)

AXIS_ORDER_ITEMS = tuple(
    (value, value, f"Output dimensions in {value} order")
    for value in ("XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX")
)

UNIT_ITEMS = (
    ("M", "m", "Meters"),
    ("CM", "cm", "Centimeters"),
    ("MM", "mm", "Millimeters"),
)

ROUND_MODE_ITEMS = (
    ("ROUND", "Round", "Round to the nearest value"),
    ("FLOOR", "Floor", "Round down"),
    ("CEIL", "Ceil", "Round up"),
)

SORT_MODE_ITEMS = (
    ("SELECTION", "Selection Order", "Active object first, then selected object order"),
    ("NAME_ASC", "Object Name A-Z", "Sort by object name ascending"),
    ("NAME_DESC", "Object Name Z-A", "Sort by object name descending"),
    ("LOCATION_X", "Location X", "Sort by world X location"),
    ("LOCATION_Y", "Location Y", "Sort by world Y location"),
    ("LOCATION_Z", "Location Z", "Sort by world Z location"),
)

ORIGINAL_MODE_ITEMS = (
    ("FULL", "Full Original Name", "Use the complete original object name"),
    ("STRIP", "Strip Blender Numeric Suffix", "Remove a suffix such as .001"),
    ("SPLIT", "Split by Delimiter", "Use one delimiter-separated part"),
)

COLLECTION_SOURCE_ITEMS = (
    ("FIRST", "First Collection", "Use the first direct collection by name"),
    ("ACTIVE", "Active Collection", "Use the active context collection"),
    ("PARENT", "Parent Collection", "Use the parent of the first direct collection"),
)

_CHOICE_ENUM_CACHE = {}


def choice_enum_items(self, _context):
    if not self.choice_options:
        return [("__NONE__", "No Options", "Add an option first")]
    items = [
        (
            option.option_id,
            option.value or "(empty)",
            option.value or "Empty option",
            option.option_value,
        )
        for option in self.choice_options
    ]
    _CHOICE_ENUM_CACHE[self.as_pointer()] = items
    return items


def preset_enum_items(_self, _context):
    from . import preset_utils

    try:
        presets = preset_utils.load_presets()
    except Exception:
        presets = []
    if not presets:
        return [("__NONE__", "No Presets", "No presets are available")]
    return [
        (preset["name"], preset["name"], f"{len(preset['modules'])} modules")
        for preset in presets
    ]


class MAR_ChoiceOption(PropertyGroup):
    option_id: StringProperty(name="Option ID", default="")
    option_value: IntProperty(name="Option Value", default=1, min=1)
    value: StringProperty(name="Value", default="")


class MAR_Module(PropertyGroup):
    module_id: StringProperty(name="Module ID", default="")
    module_type: EnumProperty(name="Type", items=MODULE_TYPE_ITEMS, default="TEXT")
    enabled: BoolProperty(name="Enabled", default=True)
    display_name: StringProperty(name="Display Name", default="")
    separator_after: StringProperty(name="Separator After", default="_")

    text_value: StringProperty(name="Text", default="")

    choice_label: StringProperty(name="Label", default="Choice")
    choice_options: CollectionProperty(type=MAR_ChoiceOption)
    choice_option_index: IntProperty(name="Option Index", default=0, min=0)
    choice_current: EnumProperty(name="Current", items=choice_enum_items)

    axis_order: EnumProperty(name="Axis Order", items=AXIS_ORDER_ITEMS, default="XYZ")
    dimension_unit: EnumProperty(name="Unit", items=UNIT_ITEMS, default="CM")
    axis_separator: StringProperty(name="Axis Separator", default="x")
    decimal_places: IntProperty(name="Decimal Places", default=0, min=0, max=4)
    round_mode: EnumProperty(name="Round Mode", items=ROUND_MODE_ITEMS, default="ROUND")
    add_unit_suffix: BoolProperty(name="Add Unit Suffix", default=True)
    add_axis_labels: BoolProperty(name="Add Axis Labels", default=False)
    remove_trailing_zeros: BoolProperty(name="Remove Trailing Zeros", default=False)

    start_number: IntProperty(name="Start Number", default=1)
    padding: IntProperty(name="Padding", default=3, min=1, max=12)
    sort_mode: EnumProperty(name="Sort Mode", items=SORT_MODE_ITEMS, default="SELECTION")

    original_mode: EnumProperty(name="Mode", items=ORIGINAL_MODE_ITEMS, default="FULL")
    original_strip_suffix: BoolProperty(
        name="Strip Blender Numeric Suffix",
        default=False,
    )
    original_delimiter: StringProperty(name="Delimiter", default="_")
    original_part_index: IntProperty(name="Part Index (1-based)", default=1, min=1)

    collection_source: EnumProperty(
        name="Collection Source",
        items=COLLECTION_SOURCE_ITEMS,
        default="FIRST",
    )
    collection_strip_suffix: BoolProperty(
        name="Strip Blender Numeric Suffix",
        default=False,
    )


class MAR_PreviewItem(PropertyGroup):
    object_ref: PointerProperty(type=bpy.types.Object)
    old_name: StringProperty(name="Old Name", default="")
    new_name: StringProperty(name="New Name", default="")
    status: StringProperty(name="Status", default="")
    message: StringProperty(name="Message", default="")


class MAR_HistoryItem(PropertyGroup):
    item_type: EnumProperty(
        name="Type",
        items=(
            ("OBJECT", "Object", "Object name history"),
            ("MESH", "Mesh", "Mesh data name history"),
        ),
        default="OBJECT",
    )
    object_ref: PointerProperty(type=bpy.types.Object)
    mesh_ref: PointerProperty(type=bpy.types.Mesh)
    old_name: StringProperty(name="Old Name", default="")
    new_name: StringProperty(name="New Name", default="")


class MAR_Settings(PropertyGroup):
    modules: CollectionProperty(type=MAR_Module)
    module_index: IntProperty(name="Module Index", default=0, min=0)

    preview_items: CollectionProperty(type=MAR_PreviewItem)
    preview_index: IntProperty(name="Preview Index", default=0, min=0)
    history_items: CollectionProperty(type=MAR_HistoryItem)

    selected_preset: EnumProperty(name="Preset", items=preset_enum_items)
    preset_name: StringProperty(name="Preset Name", default="")

    rename_object: BoolProperty(name="Rename Object", default=True)
    rename_mesh_data: BoolProperty(name="Rename Mesh Data", default=True)
    strip_blender_numeric_suffix: BoolProperty(
        name="Strip Blender Numeric Suffix",
        default=True,
    )
    auto_resolve_duplicates: BoolProperty(
        name="Auto Resolve Duplicates",
        default=True,
    )
    error_if_name_exists: BoolProperty(
        name="Error If Name Exists",
        description=(
            "Mark the item as Duplicate instead of automatically resolving "
            "a generated name that already exists"
        ),
        default=False,
    )
    store_original_name: BoolProperty(
        name="Store Original Name as Custom Property",
        default=True,
    )
    rename_only_mesh_objects: BoolProperty(
        name="Rename Only Mesh Objects",
        default=False,
    )
    skip_hidden_objects: BoolProperty(name="Skip Hidden Objects", default=False)
    skip_locked_objects: BoolProperty(name="Skip Locked Objects", default=False)
    replace_spaces: BoolProperty(
        name="Replace Spaces With Underscore",
        default=True,
    )
    remove_invalid_characters: BoolProperty(
        name="Remove Invalid Characters",
        default=True,
    )

    last_target_count: IntProperty(name="Last Target Count", default=0, min=0)
    last_warning: StringProperty(name="Last Warning", default="")
