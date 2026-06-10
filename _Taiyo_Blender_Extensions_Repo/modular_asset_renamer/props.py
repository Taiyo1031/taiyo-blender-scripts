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

DIMENSION_AXIS_ITEMS = (
    ("X", "X", "Output the X dimension"),
    ("Y", "Y", "Output the Y dimension"),
    ("Z", "Z", "Output the Z dimension"),
    (
        "LARGEST",
        "Largest",
        "Output the largest dimension; ties prefer X, then Y, then Z",
    ),
)

UNIT_ITEMS = (
    ("M", "m", "Meters"),
    ("CM", "cm", "Centimeters"),
    ("MM", "mm", "Millimeters"),
)

ROUND_MODE_ITEMS = (
    ("ROUND", "Round", "Round half up at the selected decimal place"),
    ("FLOOR", "Floor", "Round down at the selected decimal place"),
    ("CEIL", "Ceil", "Round up at the selected decimal place"),
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
_CHOICE_ENUM_RETIRED_ITEMS = []
_EMPTY_CHOICE_ENUM_ITEMS = [("__NONE__", "No Options", "Add an option first")]
_PRESET_ENUM_CACHE = None
_PRESET_ENUM_RETIRED_ITEMS = []
_EMPTY_PRESET_ENUM_ITEMS = [
    ("__NONE__", "No Presets", "No presets are available")
]


def choice_enum_items(self, _context):
    if not self.choice_options:
        return _EMPTY_CHOICE_ENUM_ITEMS

    signature = tuple(
        (option.option_id, option.option_value, option.value)
        for option in self.choice_options
    )
    cache_key = self.module_id or f"pointer:{self.as_pointer()}"
    cached = _CHOICE_ENUM_CACHE.get(cache_key)
    if cached is not None and cached["signature"] == signature:
        return cached["items"]

    items = [
        (
            option_id,
            value or "(empty)",
            value or "Empty option",
        )
        for option_id, option_value, value in signature
    ]
    if cached is not None:
        _CHOICE_ENUM_RETIRED_ITEMS.append(cached["items"])
    _CHOICE_ENUM_CACHE[cache_key] = {
        "signature": signature,
        "items": items,
    }
    return items


def preset_enum_items(_self, _context):
    global _PRESET_ENUM_CACHE

    from . import preset_utils

    try:
        presets = preset_utils.load_presets()
    except Exception:
        presets = []
    if not presets:
        return _EMPTY_PRESET_ENUM_ITEMS

    signature = tuple(
        (preset["name"], len(preset["modules"]))
        for preset in presets
    )
    if (
        _PRESET_ENUM_CACHE is not None
        and _PRESET_ENUM_CACHE["signature"] == signature
    ):
        return _PRESET_ENUM_CACHE["items"]

    items = [
        (preset["name"], preset["name"], f"{len(preset['modules'])} modules")
        for preset in presets
    ]
    if _PRESET_ENUM_CACHE is not None:
        _PRESET_ENUM_RETIRED_ITEMS.append(_PRESET_ENUM_CACHE["items"])
    _PRESET_ENUM_CACHE = {
        "signature": signature,
        "items": items,
    }
    return items


def selected_preset_updated(self, _context):
    from . import preset_utils

    try:
        selected = self.selected_preset
    except Exception:
        return
    if not selected or selected == "__NONE__":
        self.preset_name = ""
        return

    try:
        preset = preset_utils.find_preset(
            preset_utils.load_presets(),
            selected,
        )
        if preset is None:
            self.last_warning = f"Preset not found: {selected}"
            return
        preset_utils.load_preset_into_settings(self, preset)
    except Exception as exc:
        self.last_warning = f"Preset load failed: {exc}"
        return

    self.preset_name = selected
    self.last_warning = ""


class MAR_ChoiceOption(PropertyGroup):
    option_id: StringProperty(name="Option ID", default="")
    option_value: IntProperty(name="Option Value", default=1, min=1)
    value: StringProperty(name="Value", default="")


class MAR_DimensionPart(PropertyGroup):
    axis: EnumProperty(
        name="Dimension",
        items=DIMENSION_AXIS_ITEMS,
        default="X",
    )
    separator_after: StringProperty(name="Separator After", default="")


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
    dimension_parts: CollectionProperty(type=MAR_DimensionPart)
    dimension_part_index: IntProperty(name="Dimension Part Index", default=0, min=0)
    dimension_parts_migrated: BoolProperty(
        name="Dimension Parts Migrated",
        default=False,
        options={"HIDDEN"},
    )
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

    selected_preset: EnumProperty(
        name="Preset",
        items=preset_enum_items,
        update=selected_preset_updated,
    )
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
