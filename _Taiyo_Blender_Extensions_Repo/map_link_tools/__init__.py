bl_info = {
    "name": "Map Link Tools",
    "author": "Generated for production map workflow",
    "version": (0, 1, 0),
    "blender": (4, 5, 0),
    "location": "View3D > Sidebar > Map Link Tools",
    "description": "Utilities for renaming, organizing, and managing linked map objects, mesh users, and collection instances.",
    "category": "Object",
}

DOCUMENTATION_URL = "https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/_Taiyo_Blender_Extensions_Repo/map_link_tools/README.md"

import re
import time

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import AddonPreferences, Operator, Panel, PropertyGroup, UIList


LOG_PREFIX = "[Map Link Tools]"
MAX_SECONDS_PER_TICK = 0.012
TIMER_INTERVAL = 0.02
PREVIEW_LIST_LIMIT = 50
BLENDER_SUFFIX_RE = re.compile(r"\.(\d{3})$")


TARGET_ITEMS = (
    ("OBJECT", "Object Names", "Rename object data-block names"),
    ("MESH", "Mesh Data Names", "Rename mesh data-block names"),
    ("BOTH", "Object + Mesh Data Names", "Rename both object and mesh data names"),
)

DUPLICATE_ITEMS = (
    ("AUTO_UNIQUE", "Auto Unique with _01", "Generate custom underscore numeric suffixes"),
    ("BLENDER", "Use Blender Default .001", "Let names use Blender-style numeric suffixes"),
    ("SKIP", "Skip Duplicates", "Skip items whose target name is already used"),
    ("CUSTOM", "Add Custom Suffix", "Append a custom suffix before making the name unique"),
)

RENAME_MODE_ITEMS = (
    ("PATTERN", "Pattern Rename", "Rename with prefix, base name, index, and suffix"),
    ("FIND_REPLACE", "Find and Replace", "Replace text in selected names"),
    ("ADD_PREFIX_SUFFIX", "Add Prefix / Suffix", "Add text before and after selected names"),
    ("REMOVE_PREFIX_SUFFIX", "Remove Prefix / Suffix", "Remove matching text from selected names"),
    ("ACTIVE_OBJECT", "Rename by Active Object", "Use the active object name as the base"),
)

SYNC_DIRECTION_ITEMS = (
    ("OBJECT_TO_MESH", "Object Name -> Mesh Data Name", "Copy object names to mesh data names"),
    ("MESH_TO_OBJECT", "Mesh Data Name -> Object Name", "Copy mesh data names to object names"),
    ("COMPARE", "Compare Only", "Only report object and mesh name mismatches"),
)

SHARED_MESH_ITEMS = (
    ("SKIP", "Skip Shared Mesh Data", "Do not rename mesh data used by multiple objects"),
    ("RENAME_WARN", "Rename Shared Mesh Data with Warning", "Rename shared mesh data and report warnings"),
    ("MAKE_SINGLE", "Make Single User Before Rename", "Copy shared mesh data before renaming"),
)

PREVIEW_STATUS_ITEMS = (
    ("CHANGE", "Change", "This item will be changed"),
    ("SKIP", "Skip", "This item will be skipped"),
    ("WARNING", "Warning", "This item will be changed with a warning"),
    ("ERROR", "Error", "This item cannot be processed"),
    ("INFO", "Info", "Information only"),
)

PREVIEW_ACTION_ITEMS = (
    ("NONE", "None", "No action"),
    ("RENAME_OBJECT", "Rename Object", "Rename an object"),
    ("RENAME_MESH", "Rename Mesh Data", "Rename mesh data"),
    ("SINGLE_USER", "Make Single User", "Copy mesh data for one object"),
    ("SINGLE_USER_RENAME", "Make Single User and Rename", "Copy mesh data then rename it"),
)

DATA_BLOCK_ITEMS = (
    ("OBJECT", "Object", "Object data-block"),
    ("MESH", "Mesh Data", "Mesh data-block"),
    ("COLLECTION_INSTANCE", "Collection Instance", "Collection instance empty"),
    ("ACTION", "Action", "Operation action"),
    ("INFO", "Info", "Information item"),
)

PROGRESS_STATUS_ITEMS = (
    ("IDLE", "Idle", "No operation is running"),
    ("RUNNING", "Running", "Operation is running"),
    ("COMPLETED", "Completed", "Operation completed"),
    ("CANCELED", "Canceled", "Operation canceled"),
    ("ERROR", "Error", "Operation failed"),
)

COLLECTION_SOURCE_ITEMS = (
    ("FIRST", "First Collection", "Use the first direct collection membership"),
    ("ACTIVE", "Active Collection", "Use the active layer collection name"),
)


# -----------------------------------------------------------------------------
# Naming helpers
# -----------------------------------------------------------------------------

def has_blender_numeric_suffix(name):
    return bool(BLENDER_SUFFIX_RE.search(name or ""))


def split_blender_numeric_suffix(name):
    match = BLENDER_SUFFIX_RE.search(name or "")
    if not match:
        return name or "", None
    return name[:match.start()], int(match.group(1))


def remove_blender_numeric_suffix(name):
    base, number = split_blender_numeric_suffix(name)
    return base if number is not None else (name or "")


def convert_blender_suffix_to_index(name, digits=2, separator="_"):
    base, number = split_blender_numeric_suffix(name)
    if number is None:
        return name or ""
    digits = max(1, int(digits))
    return f"{base}{separator}{number:0{digits}d}"


def clean_name(name):
    raw = (name or "").strip()
    base, number = split_blender_numeric_suffix(raw)
    suffix = f".{number:03d}" if number is not None else ""
    text = re.sub(r"\s+", "_", base)
    text = text.replace(".", "_")
    text = re.sub(r"_+", "_", text)
    text = text.strip("_")
    return (text or "Object") + suffix


def make_unique_name(base_name, existing_names, digits=2, separator="_"):
    base_name = (base_name or "Object").strip() or "Object"
    digits = max(1, int(digits))
    if base_name not in existing_names:
        return base_name
    index = 1
    while True:
        candidate = f"{base_name}{separator}{index:0{digits}d}"
        if candidate not in existing_names:
            return candidate
        index += 1


def make_blender_unique_name(base_name, existing_names):
    base_name = (base_name or "Object").strip() or "Object"
    if base_name not in existing_names:
        return base_name
    index = 1
    while True:
        candidate = f"{base_name}.{index:03d}"
        if candidate not in existing_names:
            return candidate
        index += 1


def format_index(index, digits):
    return f"{index:0{max(1, int(digits))}d}"


def format_pattern(pattern, obj, collection_name, index, digits):
    object_name = obj.name if obj else "Object"
    return pattern.format(
        ObjectName=object_name,
        CollectionName=collection_name or "Collection",
        Index=format_index(index, digits),
    )


class NameAllocator:
    def __init__(self, existing_names, settings):
        self.used = set(existing_names)
        self.settings = settings

    def reserve(self, desired_name, current_name):
        desired_name = (desired_name or "Object").strip() or "Object"
        current_name = current_name or ""
        self.used.discard(current_name)
        handling = self.settings.duplicate_handling

        if desired_name == current_name:
            self.used.add(current_name)
            return current_name, "SKIP", "Already matches target name."

        if handling == "SKIP" and desired_name in self.used:
            self.used.add(current_name)
            return desired_name, "SKIP", "Target name already exists."

        if handling == "BLENDER":
            result = make_blender_unique_name(desired_name, self.used)
        elif handling == "CUSTOM" and desired_name in self.used:
            custom = self.settings.custom_duplicate_suffix or "_copy"
            result = make_unique_name(
                desired_name + custom,
                self.used,
                self.settings.digits,
                self.settings.separator or "_",
            )
        else:
            result = make_unique_name(
                desired_name,
                self.used,
                self.settings.digits,
                self.settings.separator or "_",
            )

        self.used.add(result)
        if result == current_name:
            return result, "SKIP", "Already matches target name."
        return result, "CHANGE", ""


# -----------------------------------------------------------------------------
# Blender data helpers
# -----------------------------------------------------------------------------

def log(settings, message):
    if settings and settings.print_details_to_console:
        print(f"{LOG_PREFIX} {message}")


def is_collection_instance(obj):
    return (
        obj is not None
        and obj.type == "EMPTY"
        and getattr(obj, "instance_type", None) == "COLLECTION"
        and getattr(obj, "instance_collection", None) is not None
    )


def is_external_linked_object(obj):
    if obj is None:
        return False
    if getattr(obj, "library", None) is not None:
        return True
    data = getattr(obj, "data", None)
    return data is not None and getattr(data, "library", None) is not None


def is_external_linked_mesh(mesh):
    return mesh is not None and getattr(mesh, "library", None) is not None


def object_is_library_override(obj):
    return obj is not None and getattr(obj, "override_library", None) is not None


def view_layer_object(context, obj_name):
    view_layer = getattr(context, "view_layer", None)
    if not view_layer:
        return None
    try:
        return view_layer.objects.get(obj_name)
    except Exception:
        return None


def deselect_view_layer_objects(context):
    view_layer = getattr(context, "view_layer", None)
    if not view_layer:
        return
    for obj in view_layer.objects:
        try:
            obj.select_set(False)
        except RuntimeError:
            pass


def select_object_safe(context, scene_obj, make_active=False):
    if scene_obj is None:
        return False, "Object is missing."
    obj = view_layer_object(context, scene_obj.name)
    if obj is None:
        return False, "Object is not in the current View Layer."
    try:
        obj.select_set(True)
        if make_active:
            context.view_layer.objects.active = obj
        return True, ""
    except RuntimeError as exc:
        return False, str(exc)


def tag_view3d_redraw(context):
    screen = getattr(context, "screen", None)
    if not screen:
        return
    for area in screen.areas:
        if area.type == "VIEW_3D":
            area.tag_redraw()


def active_layer_collection_name(context):
    layer_collection = getattr(context.view_layer, "active_layer_collection", None)
    collection = getattr(layer_collection, "collection", None)
    return collection.name if collection else ""


def first_collection_name(obj):
    collections = getattr(obj, "users_collection", None)
    if not collections:
        return ""
    return collections[0].name if collections[0] else ""


def object_pool(context):
    settings = context.scene.maplink_settings
    selected = list(context.selected_objects) if settings.selected_only else list(context.scene.objects)
    pool = list(selected)

    if settings.include_children:
        seen = {obj.name for obj in pool}
        for obj in selected:
            for child in obj.children_recursive:
                if child.name not in seen:
                    pool.append(child)
                    seen.add(child.name)

    if settings.include_same_collection:
        seen = {obj.name for obj in pool}
        collections = set()
        for obj in selected:
            for coll in obj.users_collection:
                collections.add(coll)
        for coll in collections:
            for obj in coll.objects:
                if obj.name not in seen:
                    pool.append(obj)
                    seen.add(obj.name)

    result = []
    for obj in pool:
        if not settings.include_hidden and obj.hide_viewport:
            continue
        if not settings.include_locked and obj.hide_select:
            continue
        result.append(obj)
    return result


def refresh_selection_info(context):
    scene = context.scene
    info = scene.maplink_selection_info
    selected = list(context.selected_objects)

    info.selected_count = len(selected)
    info.mesh_object_count = 0
    info.empty_object_count = 0
    info.collection_instance_count = 0
    info.shared_mesh_object_count = 0
    info.single_user_mesh_object_count = 0
    info.object_suffix_issue_count = 0
    info.mesh_suffix_issue_count = 0
    info.external_linked_count = 0
    info.library_override_count = 0

    seen_mesh_names = set()
    for obj in selected:
        if obj.type == "MESH":
            info.mesh_object_count += 1
            mesh = obj.data
            if mesh and mesh.users > 1:
                info.shared_mesh_object_count += 1
            elif mesh:
                info.single_user_mesh_object_count += 1
            if mesh and mesh.name not in seen_mesh_names:
                seen_mesh_names.add(mesh.name)
                if has_blender_numeric_suffix(mesh.name):
                    info.mesh_suffix_issue_count += 1
        if obj.type == "EMPTY":
            info.empty_object_count += 1
        if is_collection_instance(obj):
            info.collection_instance_count += 1
        if has_blender_numeric_suffix(obj.name):
            info.object_suffix_issue_count += 1
        if is_external_linked_object(obj):
            info.external_linked_count += 1
        if object_is_library_override(obj):
            info.library_override_count += 1


def reset_progress(progress, operation_name="", status="IDLE"):
    progress.is_running = False
    progress.status = status
    progress.operation_name = operation_name
    progress.total_count = 0
    progress.processed_count = 0
    progress.remaining_count = 0
    progress.progress_percent = 0.0
    progress.cancel_requested = False
    progress.current_message = ""
    progress.renamed_count = 0
    progress.skipped_count = 0
    progress.warning_count = 0
    progress.error_count = 0


def update_progress(progress, processed, total, current_message=""):
    progress.total_count = total
    progress.processed_count = processed
    progress.remaining_count = max(0, total - processed)
    progress.progress_percent = (processed / total * 100.0) if total else 0.0
    if current_message:
        progress.current_message = current_message


def set_workspace_status(context, message):
    workspace = getattr(context, "workspace", None)
    if workspace:
        workspace.status_text_set(message)


# -----------------------------------------------------------------------------
# Properties
# -----------------------------------------------------------------------------

class MapLinkToolsSettings(PropertyGroup):
    show_selection_overview: BoolProperty(default=True)
    show_quick_clean: BoolProperty(default=True)
    show_rename_tools: BoolProperty(default=True)
    show_sync_tools: BoolProperty(default=True)
    show_collection_instance_tools: BoolProperty(default=True)
    show_mesh_sharing_tools: BoolProperty(default=True)
    show_collection_based_rename: BoolProperty(default=False)
    show_safety_preview: BoolProperty(default=True)
    show_operation_progress: BoolProperty(default=True)
    show_advanced_options: BoolProperty(default=False)

    rename_mode: EnumProperty(items=RENAME_MODE_ITEMS, default="PATTERN")
    target_type: EnumProperty(items=TARGET_ITEMS, default="OBJECT")
    prefix: StringProperty(default="SM_")
    base_name: StringProperty(default="Wall_A")
    suffix: StringProperty(default="")
    separator: StringProperty(default="_")
    start_index: IntProperty(default=1, min=0)
    digits: IntProperty(default=2, min=1, max=6)

    find_text: StringProperty(default="")
    replace_text: StringProperty(default="")
    case_sensitive: BoolProperty(default=False)
    prefix_to_add: StringProperty(default="")
    suffix_to_add: StringProperty(default="")
    prefix_to_remove: StringProperty(default="")
    suffix_to_remove: StringProperty(default="")

    duplicate_handling: EnumProperty(items=DUPLICATE_ITEMS, default="AUTO_UNIQUE")
    custom_duplicate_suffix: StringProperty(default="_copy")

    sync_direction: EnumProperty(items=SYNC_DIRECTION_ITEMS, default="OBJECT_TO_MESH")
    shared_mesh_handling: EnumProperty(items=SHARED_MESH_ITEMS, default="SKIP")

    instance_prefix: StringProperty(default="INST_")
    instance_pattern: StringProperty(default="INST_{CollectionName}_{Index}")

    collection_source: EnumProperty(items=COLLECTION_SOURCE_ITEMS, default="FIRST")
    collection_pattern: StringProperty(default="{CollectionName}_{ObjectName}_{Index}")

    selected_only: BoolProperty(default=True)
    include_hidden: BoolProperty(default=False)
    include_locked: BoolProperty(default=False)
    include_children: BoolProperty(default=False)
    include_same_collection: BoolProperty(default=False)
    do_not_modify_external_linked_data: BoolProperty(default=True)
    warn_before_editing_shared_mesh_data: BoolProperty(default=True)

    show_result_popup: BoolProperty(default=True)
    print_details_to_console: BoolProperty(default=True)


class MapLinkSelectionInfo(PropertyGroup):
    selected_count: IntProperty(default=0)
    mesh_object_count: IntProperty(default=0)
    empty_object_count: IntProperty(default=0)
    collection_instance_count: IntProperty(default=0)
    shared_mesh_object_count: IntProperty(default=0)
    single_user_mesh_object_count: IntProperty(default=0)
    object_suffix_issue_count: IntProperty(default=0)
    mesh_suffix_issue_count: IntProperty(default=0)
    external_linked_count: IntProperty(default=0)
    library_override_count: IntProperty(default=0)


class MapLinkOperationProgress(PropertyGroup):
    is_running: BoolProperty(default=False)
    status: EnumProperty(items=PROGRESS_STATUS_ITEMS, default="IDLE")
    operation_name: StringProperty(default="")
    total_count: IntProperty(default=0)
    processed_count: IntProperty(default=0)
    remaining_count: IntProperty(default=0)
    progress_percent: FloatProperty(default=0.0, min=0.0, max=100.0)
    cancel_requested: BoolProperty(default=False)
    current_message: StringProperty(default="")
    renamed_count: IntProperty(default=0)
    skipped_count: IntProperty(default=0)
    warning_count: IntProperty(default=0)
    error_count: IntProperty(default=0)


class MapLinkPreviewItem(PropertyGroup):
    source_name: StringProperty(default="")
    target_name: StringProperty(default="")
    object_name: StringProperty(default="")
    data_block_type: EnumProperty(items=DATA_BLOCK_ITEMS, default="OBJECT")
    action: EnumProperty(items=PREVIEW_ACTION_ITEMS, default="NONE")
    status: EnumProperty(items=PREVIEW_STATUS_ITEMS, default="INFO")
    message: StringProperty(default="")
    object_ref: PointerProperty(type=bpy.types.Object)
    mesh_ref: PointerProperty(type=bpy.types.Mesh)
    collection_ref: PointerProperty(type=bpy.types.Collection)


def clear_preview(scene):
    scene.maplink_preview_items.clear()
    scene.maplink_preview_index = 0
    scene.maplink_preview_operation = ""
    scene.maplink_preview_message = ""


def begin_preview(scene, operation_name):
    scene.maplink_preview_items.clear()
    scene.maplink_preview_index = 0
    scene.maplink_preview_operation = operation_name
    scene.maplink_preview_message = ""


def add_preview_item(
    scene,
    source_name="",
    target_name="",
    object_name="",
    data_block_type="INFO",
    action="NONE",
    status="INFO",
    message="",
    obj=None,
    mesh=None,
    collection=None,
):
    item = scene.maplink_preview_items.add()
    item.source_name = source_name or ""
    item.target_name = target_name or ""
    item.object_name = object_name or (obj.name if obj else "")
    item.data_block_type = data_block_type
    item.action = action
    item.status = status
    item.message = message or ""
    if obj is not None:
        item.object_ref = obj
    if mesh is not None:
        item.mesh_ref = mesh
    if collection is not None:
        item.collection_ref = collection
    return item


def preview_counts(scene):
    counts = {"CHANGE": 0, "SKIP": 0, "WARNING": 0, "ERROR": 0, "INFO": 0}
    for item in scene.maplink_preview_items:
        counts[item.status] = counts.get(item.status, 0) + 1
    return counts


def add_object_rename_preview(scene, obj, desired_name, allocator, settings, message=""):
    if settings.do_not_modify_external_linked_data and is_external_linked_object(obj):
        add_preview_item(
            scene,
            obj.name,
            desired_name,
            obj.name,
            "OBJECT",
            "RENAME_OBJECT",
            "SKIP",
            "External linked object/data is protected.",
            obj=obj,
        )
        return

    target_name, status, duplicate_message = allocator.reserve(desired_name, obj.name)
    final_message = message or duplicate_message
    add_preview_item(
        scene,
        obj.name,
        target_name,
        obj.name,
        "OBJECT",
        "RENAME_OBJECT",
        status,
        final_message,
        obj=obj,
    )


def add_mesh_rename_preview(
    scene,
    obj,
    mesh,
    desired_name,
    allocator,
    settings,
    message="",
    allow_shared=True,
    force_skip_shared=False,
    make_single_user=False,
):
    if mesh is None:
        add_preview_item(
            scene,
            "",
            desired_name,
            obj.name if obj else "",
            "MESH",
            "RENAME_MESH",
            "SKIP",
            "Object has no mesh data.",
            obj=obj,
        )
        return

    if settings.do_not_modify_external_linked_data and (is_external_linked_object(obj) or is_external_linked_mesh(mesh)):
        add_preview_item(
            scene,
            mesh.name,
            desired_name,
            obj.name if obj else "",
            "MESH",
            "RENAME_MESH",
            "SKIP",
            "External linked mesh data is protected.",
            obj=obj,
            mesh=mesh,
        )
        return

    if mesh.users > 1 and force_skip_shared:
        add_preview_item(
            scene,
            mesh.name,
            desired_name,
            obj.name if obj else "",
            "MESH",
            "RENAME_MESH",
            "SKIP",
            f"Shared mesh data has {mesh.users} users.",
            obj=obj,
            mesh=mesh,
        )
        return

    target_name, status, duplicate_message = allocator.reserve(desired_name, mesh.name)
    action = "SINGLE_USER_RENAME" if make_single_user else "RENAME_MESH"
    final_message = message or duplicate_message
    if mesh.users > 1 and allow_shared and not make_single_user and status == "CHANGE":
        status = "WARNING"
        final_message = final_message or f"Shared mesh data has {mesh.users} users."

    add_preview_item(
        scene,
        mesh.name,
        target_name,
        obj.name if obj else "",
        "MESH",
        action,
        status,
        final_message,
        obj=obj,
        mesh=mesh,
    )


def mesh_allocator(settings):
    return NameAllocator({mesh.name for mesh in bpy.data.meshes}, settings)


def object_allocator(settings):
    return NameAllocator({obj.name for obj in bpy.data.objects}, settings)


# -----------------------------------------------------------------------------
# Preview builders
# -----------------------------------------------------------------------------

def preview_quick_clean(context, operation):
    scene = context.scene
    settings = scene.maplink_settings
    operation_name = {
        "REMOVE_SUFFIX": "Remove .001 Suffix",
        "CONVERT_SUFFIX": "Convert .001 to _01",
        "CLEAN_NAMES": "Clean Names",
    }[operation]
    begin_preview(scene, operation_name)

    objects = object_pool(context)
    obj_alloc = object_allocator(settings)
    mesh_alloc = mesh_allocator(settings)
    seen_meshes = set()

    for obj in objects:
        if settings.target_type in {"OBJECT", "BOTH"}:
            if operation == "REMOVE_SUFFIX":
                desired = remove_blender_numeric_suffix(obj.name)
            elif operation == "CONVERT_SUFFIX":
                desired = convert_blender_suffix_to_index(obj.name, settings.digits, settings.separator or "_")
            else:
                desired = clean_name(obj.name)
            add_object_rename_preview(scene, obj, desired, obj_alloc, settings)

        if settings.target_type in {"MESH", "BOTH"}:
            if obj.type != "MESH" or obj.data is None:
                continue
            mesh = obj.data
            key = mesh.as_pointer()
            if key in seen_meshes:
                continue
            seen_meshes.add(key)
            if operation == "REMOVE_SUFFIX":
                desired = remove_blender_numeric_suffix(mesh.name)
            elif operation == "CONVERT_SUFFIX":
                desired = convert_blender_suffix_to_index(mesh.name, settings.digits, settings.separator or "_")
            else:
                desired = clean_name(mesh.name)
            add_mesh_rename_preview(scene, obj, mesh, desired, mesh_alloc, settings, allow_shared=True)

    scene.maplink_preview_message = f"{len(scene.maplink_preview_items)} item(s) prepared."
    return len(scene.maplink_preview_items)


def rename_desired_name(settings, obj, index, active_name):
    mode = settings.rename_mode
    current = obj.name
    if mode == "PATTERN":
        return (
            f"{settings.prefix}"
            f"{settings.base_name}"
            f"{settings.separator or '_'}"
            f"{format_index(index, settings.digits)}"
            f"{settings.suffix}"
        )
    if mode == "FIND_REPLACE":
        if not settings.find_text:
            return current
        if settings.case_sensitive:
            return current.replace(settings.find_text, settings.replace_text)
        return re.sub(re.escape(settings.find_text), settings.replace_text, current, flags=re.IGNORECASE)
    if mode == "ADD_PREFIX_SUFFIX":
        return f"{settings.prefix_to_add}{current}{settings.suffix_to_add}"
    if mode == "REMOVE_PREFIX_SUFFIX":
        result = current
        if settings.prefix_to_remove and result.startswith(settings.prefix_to_remove):
            result = result[len(settings.prefix_to_remove):]
        if settings.suffix_to_remove and result.endswith(settings.suffix_to_remove):
            result = result[: -len(settings.suffix_to_remove)]
        return result or current
    if mode == "ACTIVE_OBJECT":
        base = active_name or current
        return f"{base}{settings.separator or '_'}{format_index(index, settings.digits)}"
    return current


def preview_rename(context):
    scene = context.scene
    settings = scene.maplink_settings
    mode_label = dict((key, label) for key, label, _desc in RENAME_MODE_ITEMS).get(settings.rename_mode, "Rename")
    begin_preview(scene, mode_label)

    objects = object_pool(context)
    active = context.view_layer.objects.active
    active_name = active.name if active else ""
    if settings.rename_mode == "ACTIVE_OBJECT" and active and len(objects) > 1:
        objects = [obj for obj in objects if obj != active]

    obj_alloc = object_allocator(settings)
    mesh_alloc = mesh_allocator(settings)
    seen_meshes = set()
    start = settings.start_index

    for offset, obj in enumerate(objects):
        index = start + offset
        desired = rename_desired_name(settings, obj, index, active_name)
        if settings.target_type in {"OBJECT", "BOTH"}:
            add_object_rename_preview(scene, obj, desired, obj_alloc, settings)
        if settings.target_type in {"MESH", "BOTH"}:
            if obj.type != "MESH" or obj.data is None:
                continue
            mesh = obj.data
            key = mesh.as_pointer()
            if key in seen_meshes:
                continue
            seen_meshes.add(key)
            add_mesh_rename_preview(scene, obj, mesh, desired, mesh_alloc, settings, allow_shared=True)

    scene.maplink_preview_message = f"{len(scene.maplink_preview_items)} item(s) prepared."
    return len(scene.maplink_preview_items)


def preview_sync(context):
    scene = context.scene
    settings = scene.maplink_settings
    direction_label = dict((key, label) for key, label, _desc in SYNC_DIRECTION_ITEMS).get(settings.sync_direction, "Sync")
    begin_preview(scene, direction_label)

    objects = [obj for obj in object_pool(context) if obj.type == "MESH" and obj.data is not None]
    obj_alloc = object_allocator(settings)
    mesh_alloc = mesh_allocator(settings)
    seen_meshes = set()
    matching = 0
    mismatching = 0

    if settings.sync_direction == "OBJECT_TO_MESH":
        for obj in objects:
            mesh = obj.data
            if mesh.name == obj.name:
                matching += 1
                add_preview_item(scene, mesh.name, obj.name, obj.name, "MESH", "NONE", "SKIP", "Already synced.", obj=obj, mesh=mesh)
                continue
            mismatching += 1
            key = mesh.as_pointer()
            if settings.shared_mesh_handling != "MAKE_SINGLE" and key in seen_meshes:
                add_preview_item(scene, mesh.name, obj.name, obj.name, "MESH", "RENAME_MESH", "SKIP", "Same mesh data is already scheduled.", obj=obj, mesh=mesh)
                continue
            seen_meshes.add(key)

            if mesh.users > 1 and settings.shared_mesh_handling == "SKIP":
                add_mesh_rename_preview(scene, obj, mesh, obj.name, mesh_alloc, settings, force_skip_shared=True)
            elif mesh.users > 1 and settings.shared_mesh_handling == "MAKE_SINGLE":
                add_mesh_rename_preview(scene, obj, mesh, obj.name, mesh_alloc, settings, make_single_user=True)
            else:
                add_mesh_rename_preview(scene, obj, mesh, obj.name, mesh_alloc, settings, allow_shared=True)

    elif settings.sync_direction == "MESH_TO_OBJECT":
        for obj in objects:
            mesh = obj.data
            if mesh.name == obj.name:
                matching += 1
                add_preview_item(scene, obj.name, mesh.name, obj.name, "OBJECT", "NONE", "SKIP", "Already synced.", obj=obj, mesh=mesh)
                continue
            mismatching += 1
            add_object_rename_preview(scene, obj, mesh.name, obj_alloc, settings)

    else:
        shared = 0
        for obj in objects:
            mesh = obj.data
            if mesh.users > 1:
                shared += 1
            if obj.name == mesh.name:
                matching += 1
                status = "INFO"
                message = "Object and mesh names match."
            else:
                mismatching += 1
                status = "WARNING"
                message = "Object and mesh names differ."
            add_preview_item(scene, obj.name, mesh.name, obj.name, "INFO", "NONE", status, message, obj=obj, mesh=mesh)
        scene.maplink_preview_message = f"Matching: {matching}, Mismatching: {mismatching}, Shared mesh objects: {shared}."
        return len(scene.maplink_preview_items)

    scene.maplink_preview_message = f"Matching: {matching}, Mismatching: {mismatching}."
    return len(scene.maplink_preview_items)


def preview_collection_instances(context):
    scene = context.scene
    settings = scene.maplink_settings
    begin_preview(scene, "Rename Collection Instances from Source")
    objects = [obj for obj in object_pool(context) if is_collection_instance(obj)]
    obj_alloc = object_allocator(settings)

    for offset, obj in enumerate(objects):
        source = obj.instance_collection
        index = settings.start_index + offset
        pattern = settings.instance_pattern or "INST_{CollectionName}_{Index}"
        desired = format_pattern(pattern, obj, source.name if source else "Collection", index, settings.digits)
        add_object_rename_preview(scene, obj, desired, obj_alloc, settings, "Collection instance object rename.")

    scene.maplink_preview_message = f"{len(scene.maplink_preview_items)} collection instance item(s) prepared."
    return len(scene.maplink_preview_items)


def preview_collection_based_rename(context):
    scene = context.scene
    settings = scene.maplink_settings
    begin_preview(scene, "Collection Based Rename")
    objects = object_pool(context)
    obj_alloc = object_allocator(settings)
    pattern = settings.collection_pattern or "{CollectionName}_{ObjectName}_{Index}"
    active_collection = active_layer_collection_name(context)

    for offset, obj in enumerate(objects):
        if settings.collection_source == "ACTIVE":
            collection_name = active_collection
        else:
            collection_name = first_collection_name(obj)
        if not collection_name:
            add_preview_item(scene, obj.name, "", obj.name, "OBJECT", "RENAME_OBJECT", "SKIP", "Object has no direct collection.", obj=obj)
            continue
        desired = format_pattern(pattern, obj, collection_name, settings.start_index + offset, settings.digits)
        add_object_rename_preview(scene, obj, desired, obj_alloc, settings, "Collection based rename.")

    scene.maplink_preview_message = f"{len(scene.maplink_preview_items)} item(s) prepared."
    return len(scene.maplink_preview_items)


# -----------------------------------------------------------------------------
# Operators: selection and preview
# -----------------------------------------------------------------------------

class MAPLINK_OT_refresh_selection_info(Operator):
    bl_idname = "maplink.refresh_selection_info"
    bl_label = "Refresh Selection Info"
    bl_description = "Refresh selected object statistics"

    def execute(self, context):
        refresh_selection_info(context)
        self.report({"INFO"}, "Selection info refreshed.")
        return {"FINISHED"}


class MAPLINK_OT_clear_preview(Operator):
    bl_idname = "maplink.clear_preview"
    bl_label = "Clear Preview"
    bl_description = "Clear the current safety preview"

    def execute(self, context):
        clear_preview(context.scene)
        self.report({"INFO"}, "Preview cleared.")
        return {"FINISHED"}


class MAPLINK_OT_preview_operation(Operator):
    bl_idname = "maplink.preview_operation"
    bl_label = "Preview Operation"
    bl_description = "Preview the selected rename operation"

    operation: EnumProperty(
        items=(
            ("RENAME", "Rename", ""),
            ("SYNC", "Sync", ""),
            ("COLLECTION_INSTANCE", "Collection Instance", ""),
            ("COLLECTION_BASED", "Collection Based", ""),
        ),
        default="RENAME",
    )

    def execute(self, context):
        if self.operation == "SYNC":
            count = preview_sync(context)
        elif self.operation == "COLLECTION_INSTANCE":
            count = preview_collection_instances(context)
        elif self.operation == "COLLECTION_BASED":
            count = preview_collection_based_rename(context)
        else:
            count = preview_rename(context)
        self.report({"INFO"}, f"Preview prepared: {count} item(s).")
        return {"FINISHED"}


class MAPLINK_OT_preview_remove_suffix(Operator):
    bl_idname = "maplink.preview_remove_suffix"
    bl_label = "Preview Remove .001 Suffix"
    bl_description = "Preview removing Blender numeric suffixes from selected names"

    def execute(self, context):
        count = preview_quick_clean(context, "REMOVE_SUFFIX")
        self.report({"INFO"}, f"Preview prepared: {count} item(s).")
        return {"FINISHED"}


class MAPLINK_OT_apply_remove_suffix(Operator):
    bl_idname = "maplink.apply_remove_suffix"
    bl_label = "Apply Remove .001 Suffix"
    bl_description = "Apply removing Blender numeric suffixes from selected names"

    def execute(self, context):
        preview_quick_clean(context, "REMOVE_SUFFIX")
        return bpy.ops.maplink.apply_previewed_operation("INVOKE_DEFAULT")


class MAPLINK_OT_preview_convert_suffix(Operator):
    bl_idname = "maplink.preview_convert_suffix"
    bl_label = "Preview Convert .001 to _01"
    bl_description = "Preview converting Blender numeric suffixes to underscore suffixes"

    def execute(self, context):
        count = preview_quick_clean(context, "CONVERT_SUFFIX")
        self.report({"INFO"}, f"Preview prepared: {count} item(s).")
        return {"FINISHED"}


class MAPLINK_OT_apply_convert_suffix(Operator):
    bl_idname = "maplink.apply_convert_suffix"
    bl_label = "Apply Convert .001 to _01"
    bl_description = "Apply converting Blender numeric suffixes to underscore suffixes"

    def execute(self, context):
        preview_quick_clean(context, "CONVERT_SUFFIX")
        return bpy.ops.maplink.apply_previewed_operation("INVOKE_DEFAULT")


class MAPLINK_OT_preview_clean_names(Operator):
    bl_idname = "maplink.preview_clean_names"
    bl_label = "Preview Clean Names"
    bl_description = "Preview cleaning selected names"

    def execute(self, context):
        count = preview_quick_clean(context, "CLEAN_NAMES")
        self.report({"INFO"}, f"Preview prepared: {count} item(s).")
        return {"FINISHED"}


class MAPLINK_OT_apply_clean_names(Operator):
    bl_idname = "maplink.apply_clean_names"
    bl_label = "Apply Clean Names"
    bl_description = "Apply cleaning selected names"

    def execute(self, context):
        preview_quick_clean(context, "CLEAN_NAMES")
        return bpy.ops.maplink.apply_previewed_operation("INVOKE_DEFAULT")


class MAPLINK_OT_preview_pattern_rename(Operator):
    bl_idname = "maplink.preview_pattern_rename"
    bl_label = "Preview Rename"
    bl_description = "Preview the current rename tool"

    def execute(self, context):
        count = preview_rename(context)
        self.report({"INFO"}, f"Preview prepared: {count} item(s).")
        return {"FINISHED"}


class MAPLINK_OT_apply_pattern_rename(Operator):
    bl_idname = "maplink.apply_pattern_rename"
    bl_label = "Apply Rename"
    bl_description = "Apply the current rename tool"

    def execute(self, context):
        preview_rename(context)
        return bpy.ops.maplink.apply_previewed_operation("INVOKE_DEFAULT")


class MAPLINK_OT_preview_find_replace(MAPLINK_OT_preview_pattern_rename):
    bl_idname = "maplink.preview_find_replace"


class MAPLINK_OT_apply_find_replace(MAPLINK_OT_apply_pattern_rename):
    bl_idname = "maplink.apply_find_replace"


class MAPLINK_OT_preview_add_prefix_suffix(MAPLINK_OT_preview_pattern_rename):
    bl_idname = "maplink.preview_add_prefix_suffix"


class MAPLINK_OT_apply_add_prefix_suffix(MAPLINK_OT_apply_pattern_rename):
    bl_idname = "maplink.apply_add_prefix_suffix"


class MAPLINK_OT_preview_remove_prefix_suffix(MAPLINK_OT_preview_pattern_rename):
    bl_idname = "maplink.preview_remove_prefix_suffix"


class MAPLINK_OT_apply_remove_prefix_suffix(MAPLINK_OT_apply_pattern_rename):
    bl_idname = "maplink.apply_remove_prefix_suffix"


class MAPLINK_OT_preview_rename_by_active(MAPLINK_OT_preview_pattern_rename):
    bl_idname = "maplink.preview_rename_by_active"


class MAPLINK_OT_apply_rename_by_active(MAPLINK_OT_apply_pattern_rename):
    bl_idname = "maplink.apply_rename_by_active"


class MAPLINK_OT_preview_sync_names(Operator):
    bl_idname = "maplink.preview_sync_names"
    bl_label = "Preview Sync"
    bl_description = "Preview object and mesh name sync"

    def execute(self, context):
        count = preview_sync(context)
        self.report({"INFO"}, f"Preview prepared: {count} item(s).")
        return {"FINISHED"}


class MAPLINK_OT_apply_sync_names(Operator):
    bl_idname = "maplink.apply_sync_names"
    bl_label = "Apply Sync"
    bl_description = "Apply object and mesh name sync"

    def execute(self, context):
        preview_sync(context)
        return bpy.ops.maplink.apply_previewed_operation("INVOKE_DEFAULT")


class MAPLINK_OT_compare_object_mesh_names(Operator):
    bl_idname = "maplink.compare_object_mesh_names"
    bl_label = "Compare Only"
    bl_description = "Compare selected object names and mesh data names"

    def execute(self, context):
        context.scene.maplink_settings.sync_direction = "COMPARE"
        count = preview_sync(context)
        self.report({"INFO"}, f"Compare preview prepared: {count} item(s).")
        return {"FINISHED"}


class MAPLINK_OT_preview_rename_collection_instances(Operator):
    bl_idname = "maplink.preview_rename_collection_instances"
    bl_label = "Preview Rename Instances from Source"
    bl_description = "Preview renaming selected collection instances from their source collection"

    def execute(self, context):
        count = preview_collection_instances(context)
        self.report({"INFO"}, f"Preview prepared: {count} item(s).")
        return {"FINISHED"}


class MAPLINK_OT_apply_rename_collection_instances(Operator):
    bl_idname = "maplink.apply_rename_collection_instances"
    bl_label = "Apply Rename Instances from Source"
    bl_description = "Apply renaming selected collection instances from their source collection"

    def execute(self, context):
        preview_collection_instances(context)
        return bpy.ops.maplink.apply_previewed_operation("INVOKE_DEFAULT")


class MAPLINK_OT_preview_collection_based_rename(Operator):
    bl_idname = "maplink.preview_collection_based_rename"
    bl_label = "Preview Collection Rename"
    bl_description = "Preview collection based rename"

    def execute(self, context):
        count = preview_collection_based_rename(context)
        self.report({"INFO"}, f"Preview prepared: {count} item(s).")
        return {"FINISHED"}


class MAPLINK_OT_apply_collection_based_rename(Operator):
    bl_idname = "maplink.apply_collection_based_rename"
    bl_label = "Apply Collection Rename"
    bl_description = "Apply collection based rename"

    def execute(self, context):
        preview_collection_based_rename(context)
        return bpy.ops.maplink.apply_previewed_operation("INVOKE_DEFAULT")


# -----------------------------------------------------------------------------
# Modal apply operator
# -----------------------------------------------------------------------------

def apply_preview_item(context, item):
    status = item.status
    if status not in {"CHANGE", "WARNING"}:
        return "SKIP", item.message or "Preview item is not marked for change."

    try:
        if item.action == "RENAME_OBJECT":
            obj = item.object_ref or context.scene.objects.get(item.object_name)
            if obj is None:
                return "ERROR", "Object is missing."
            obj.name = item.target_name
            return "CHANGE", obj.name

        if item.action == "RENAME_MESH":
            mesh = item.mesh_ref
            if mesh is None and item.object_ref and item.object_ref.type == "MESH":
                mesh = item.object_ref.data
            if mesh is None:
                return "ERROR", "Mesh data is missing."
            mesh.name = item.target_name
            return "WARNING" if status == "WARNING" else "CHANGE", mesh.name

        if item.action == "SINGLE_USER_RENAME":
            obj = item.object_ref or context.scene.objects.get(item.object_name)
            if obj is None or obj.type != "MESH" or obj.data is None:
                return "ERROR", "Mesh object is missing."
            if obj.data.users > 1:
                obj.data = obj.data.copy()
            obj.data.name = item.target_name
            return "WARNING" if status == "WARNING" else "CHANGE", obj.data.name

        if item.action == "SINGLE_USER":
            obj = item.object_ref or context.scene.objects.get(item.object_name)
            if obj is None or obj.type != "MESH" or obj.data is None:
                return "ERROR", "Mesh object is missing."
            if obj.data.users <= 1:
                return "SKIP", "Mesh data is already single-user."
            obj.data = obj.data.copy()
            obj.data.name = item.target_name or obj.data.name
            return "CHANGE", obj.name
    except Exception as exc:
        return "ERROR", str(exc)

    return "SKIP", "No applicable action."


class MAPLINK_OT_apply_previewed_operation(Operator):
    bl_idname = "maplink.apply_previewed_operation"
    bl_label = "Apply Previewed Operation"
    bl_description = "Apply the current preview using modal chunked processing"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return self._start(context)

    def execute(self, context):
        return self._start(context)

    def _start(self, context):
        scene = context.scene
        progress = scene.maplink_progress
        if progress.is_running:
            self.report({"WARNING"}, "Another Map Link Tools operation is already running.")
            return {"CANCELLED"}

        self._indices = [
            index for index, item in enumerate(scene.maplink_preview_items)
            if item.status in {"CHANGE", "WARNING"}
        ]
        if not self._indices:
            self.report({"WARNING"}, "No previewed changes to apply.")
            return {"CANCELLED"}

        reset_progress(progress, scene.maplink_preview_operation or "Apply Preview", "RUNNING")
        progress.is_running = True
        progress.cancel_requested = False
        progress.total_count = len(self._indices)
        progress.remaining_count = len(self._indices)
        progress.current_message = "Processing..."

        self._cursor = 0
        self._timer = context.window_manager.event_timer_add(TIMER_INTERVAL, window=context.window)
        context.window_manager.modal_handler_add(self)
        set_workspace_status(context, f"{progress.operation_name}: 0 / {progress.total_count}")
        tag_view3d_redraw(context)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        scene = context.scene
        progress = scene.maplink_progress

        if event.type == "ESC" or progress.cancel_requested:
            self._finish(context, canceled=True)
            return {"CANCELLED"}

        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        start = time.perf_counter()
        while self._cursor < len(self._indices):
            item = scene.maplink_preview_items[self._indices[self._cursor]]
            result, message = apply_preview_item(context, item)
            if result == "CHANGE":
                progress.renamed_count += 1
            elif result == "WARNING":
                progress.renamed_count += 1
                progress.warning_count += 1
            elif result == "ERROR":
                progress.error_count += 1
            else:
                progress.skipped_count += 1
            self._cursor += 1
            update_progress(progress, self._cursor, len(self._indices), message)

            if time.perf_counter() - start >= MAX_SECONDS_PER_TICK:
                break

        set_workspace_status(
            context,
            f"{progress.operation_name}: {progress.processed_count} / {progress.total_count}",
        )
        tag_view3d_redraw(context)

        if self._cursor >= len(self._indices):
            self._finish(context, canceled=False)
            return {"FINISHED"}

        return {"PASS_THROUGH"}

    def _finish(self, context, canceled=False):
        progress = context.scene.maplink_progress
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None

        progress.is_running = False
        progress.cancel_requested = False
        progress.status = "CANCELED" if canceled else "COMPLETED"
        update_progress(progress, self._cursor, len(self._indices), progress.current_message)
        if canceled:
            progress.current_message = "Canceled by user."
            self.report({"WARNING"}, f"Canceled after {progress.processed_count} / {progress.total_count}.")
        else:
            progress.current_message = (
                f"Completed. Changed: {progress.renamed_count}, "
                f"Skipped: {progress.skipped_count}, Warnings: {progress.warning_count}, "
                f"Errors: {progress.error_count}."
            )
            self.report({"INFO"}, progress.current_message)

        set_workspace_status(context, None)
        refresh_selection_info(context)
        tag_view3d_redraw(context)


class MAPLINK_OT_cancel_current_operation(Operator):
    bl_idname = "maplink.cancel_current_operation"
    bl_label = "Cancel Current Operation"
    bl_description = "Request cancellation of the current long operation"

    def execute(self, context):
        progress = context.scene.maplink_progress
        if not progress.is_running:
            self.report({"INFO"}, "No Map Link Tools operation is running.")
            return {"CANCELLED"}
        progress.cancel_requested = True
        self.report({"INFO"}, "Cancel requested.")
        return {"FINISHED"}


# -----------------------------------------------------------------------------
# Modal scene selection scans
# -----------------------------------------------------------------------------

class MapLinkSceneSelectBase:
    bl_options = {"REGISTER", "UNDO"}
    operation_name = "Select Objects"

    def invoke(self, context, event):
        return self._start(context)

    def execute(self, context):
        return self._start(context)

    def _prepare(self, context):
        return True

    def _matches(self, obj):
        return False

    def _start(self, context):
        scene = context.scene
        progress = scene.maplink_progress
        if progress.is_running:
            self.report({"WARNING"}, "Another Map Link Tools operation is already running.")
            return {"CANCELLED"}
        if not self._prepare(context):
            return {"CANCELLED"}

        settings = scene.maplink_settings
        self._objects = [
            obj for obj in scene.objects
            if settings.include_hidden or not obj.hide_viewport
        ]
        self._cursor = 0
        self._selected = 0
        self._skipped = 0
        self._made_active = False
        deselect_view_layer_objects(context)

        reset_progress(progress, self.operation_name, "RUNNING")
        progress.is_running = True
        progress.total_count = len(self._objects)
        progress.remaining_count = len(self._objects)
        progress.current_message = "Scanning scene..."
        self._timer = context.window_manager.event_timer_add(TIMER_INTERVAL, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        progress = context.scene.maplink_progress
        if event.type == "ESC" or progress.cancel_requested:
            self._finish(context, canceled=True)
            return {"CANCELLED"}
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        start = time.perf_counter()
        while self._cursor < len(self._objects):
            obj = self._objects[self._cursor]
            if self._matches(obj):
                ok, _reason = select_object_safe(context, obj, make_active=not self._made_active)
                if ok:
                    self._selected += 1
                    self._made_active = True
                else:
                    self._skipped += 1
            self._cursor += 1
            update_progress(progress, self._cursor, len(self._objects), obj.name)
            if time.perf_counter() - start >= MAX_SECONDS_PER_TICK:
                break

        tag_view3d_redraw(context)
        if self._cursor >= len(self._objects):
            self._finish(context, canceled=False)
            return {"FINISHED"}
        return {"PASS_THROUGH"}

    def _finish(self, context, canceled=False):
        progress = context.scene.maplink_progress
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        progress.is_running = False
        progress.cancel_requested = False
        progress.status = "CANCELED" if canceled else "COMPLETED"
        progress.renamed_count = self._selected
        progress.skipped_count = self._skipped
        progress.current_message = (
            f"Canceled. Selected {self._selected} object(s)."
            if canceled
            else f"Selected {self._selected} object(s); skipped {self._skipped}."
        )
        self.report({"INFO"}, progress.current_message)
        set_workspace_status(context, None)
        refresh_selection_info(context)
        tag_view3d_redraw(context)


class MAPLINK_OT_select_same_mesh_data(MapLinkSceneSelectBase, Operator):
    bl_idname = "maplink.select_same_mesh_data"
    bl_label = "Select Same Mesh Data"
    bl_description = "Select all visible objects using the active object's mesh data"
    operation_name = "Select Same Mesh Data"

    def _prepare(self, context):
        active = context.view_layer.objects.active
        if active is None or active.type != "MESH" or active.data is None:
            self.report({"WARNING"}, "Active object must be a mesh object.")
            return False
        self._mesh = active.data
        return True

    def _matches(self, obj):
        return obj.type == "MESH" and obj.data == self._mesh


class MAPLINK_OT_select_same_collection_source(MapLinkSceneSelectBase, Operator):
    bl_idname = "maplink.select_same_collection_source"
    bl_label = "Select Same Collection Source"
    bl_description = "Select all collection instances referencing the same source collection"
    operation_name = "Select Same Collection Source"

    def _prepare(self, context):
        active = context.view_layer.objects.active
        if not is_collection_instance(active):
            for obj in context.selected_objects:
                if is_collection_instance(obj):
                    active = obj
                    break
        if not is_collection_instance(active):
            self.report({"WARNING"}, "Select a collection instance object first.")
            return False
        self._collection = active.instance_collection
        return True

    def _matches(self, obj):
        return is_collection_instance(obj) and obj.instance_collection == self._collection


class MAPLINK_OT_select_shared_mesh_objects(MapLinkSceneSelectBase, Operator):
    bl_idname = "maplink.select_shared_mesh_objects"
    bl_label = "Select Objects with Shared Mesh"
    bl_description = "Select visible mesh objects whose mesh data has multiple users"
    operation_name = "Select Objects with Shared Mesh"

    def _matches(self, obj):
        return obj.type == "MESH" and obj.data is not None and obj.data.users > 1


class MAPLINK_OT_select_single_user_mesh_objects(MapLinkSceneSelectBase, Operator):
    bl_idname = "maplink.select_single_user_mesh_objects"
    bl_label = "Select Single User Mesh Objects"
    bl_description = "Select visible mesh objects whose mesh data is single-user"
    operation_name = "Select Single User Mesh Objects"

    def _matches(self, obj):
        return obj.type == "MESH" and obj.data is not None and obj.data.users <= 1


# -----------------------------------------------------------------------------
# Collection instance and mesh sharing reports
# -----------------------------------------------------------------------------

class MAPLINK_OT_show_collection_instance_source_info(Operator):
    bl_idname = "maplink.show_collection_instance_source_info"
    bl_label = "Show Instance Source Info"
    bl_description = "Show source collection information for selected collection instances"

    def execute(self, context):
        scene = context.scene
        begin_preview(scene, "Collection Instance Source Info")
        instances = [obj for obj in context.selected_objects if is_collection_instance(obj)]
        if not instances:
            self.report({"WARNING"}, "No selected collection instances.")
            return {"CANCELLED"}

        counts = {}
        for obj in context.scene.objects:
            if is_collection_instance(obj):
                counts[obj.instance_collection.name] = counts.get(obj.instance_collection.name, 0) + 1

        for obj in instances[:PREVIEW_LIST_LIMIT]:
            collection = obj.instance_collection
            count = counts.get(collection.name, 0)
            add_preview_item(
                scene,
                obj.name,
                collection.name,
                obj.name,
                "COLLECTION_INSTANCE",
                "NONE",
                "INFO",
                f"Source collection users: {count}",
                obj=obj,
                collection=collection,
            )

        scene.maplink_preview_message = f"Showing {min(len(instances), PREVIEW_LIST_LIMIT)} of {len(instances)} selected instance(s)."
        self.report({"INFO"}, scene.maplink_preview_message)
        return {"FINISHED"}


class MAPLINK_OT_count_collection_instance_users(Operator):
    bl_idname = "maplink.count_collection_instance_users"
    bl_label = "Count Collection Instance Users"
    bl_description = "Count scene collection instances grouped by referenced source collection"

    def execute(self, context):
        scene = context.scene
        begin_preview(scene, "Collection Instance User Counts")
        selected_sources = {
            obj.instance_collection
            for obj in context.selected_objects
            if is_collection_instance(obj)
        }
        counts = {}
        for obj in scene.objects:
            if is_collection_instance(obj):
                collection = obj.instance_collection
                if selected_sources and collection not in selected_sources:
                    continue
                counts[collection.name] = counts.get(collection.name, 0) + 1

        if not counts:
            self.report({"WARNING"}, "No collection instance users found.")
            return {"CANCELLED"}

        for name, count in sorted(counts.items())[:PREVIEW_LIST_LIMIT]:
            add_preview_item(scene, name, str(count), name, "INFO", "NONE", "INFO", f"{count} instance(s)")

        total = sum(counts.values())
        scene.maplink_preview_message = f"{len(counts)} collection source(s), {total} instance object(s)."
        self.report({"INFO"}, scene.maplink_preview_message)
        return {"FINISHED"}


class MAPLINK_OT_count_mesh_users(Operator):
    bl_idname = "maplink.count_mesh_users"
    bl_label = "Count Mesh Users"
    bl_description = "Count objects using the active object's mesh data"

    def execute(self, context):
        active = context.view_layer.objects.active
        if active is None or active.type != "MESH" or active.data is None:
            self.report({"WARNING"}, "Active object must be a mesh object.")
            return {"CANCELLED"}
        mesh = active.data
        scene_count = sum(1 for obj in context.scene.objects if obj.type == "MESH" and obj.data == mesh)
        selected_count = sum(1 for obj in context.selected_objects if obj.type == "MESH" and obj.data == mesh)
        context.scene.maplink_progress.current_message = (
            f"{mesh.name}: {scene_count} scene user(s), {selected_count} selected."
        )
        self.report({"INFO"}, context.scene.maplink_progress.current_message)
        return {"FINISHED"}


class MAPLINK_OT_show_shared_mesh_users(Operator):
    bl_idname = "maplink.show_shared_mesh_users"
    bl_label = "Show Shared Mesh Users"
    bl_description = "Show a preview list of objects using the active object's mesh data"

    def execute(self, context):
        active = context.view_layer.objects.active
        if active is None or active.type != "MESH" or active.data is None:
            self.report({"WARNING"}, "Active object must be a mesh object.")
            return {"CANCELLED"}
        mesh = active.data
        users = [obj for obj in context.scene.objects if obj.type == "MESH" and obj.data == mesh]
        begin_preview(context.scene, "Shared Mesh Users")
        for obj in users[:PREVIEW_LIST_LIMIT]:
            add_preview_item(context.scene, mesh.name, obj.name, obj.name, "INFO", "NONE", "INFO", "Uses active mesh data.", obj=obj, mesh=mesh)
        context.scene.maplink_preview_message = f"Showing first {min(len(users), PREVIEW_LIST_LIMIT)} of {len(users)} user(s)."
        self.report({"INFO"}, context.scene.maplink_preview_message)
        return {"FINISHED"}


# -----------------------------------------------------------------------------
# Modal make single user
# -----------------------------------------------------------------------------

class MAPLINK_OT_make_selected_mesh_single_user(Operator):
    bl_idname = "maplink.make_selected_mesh_single_user"
    bl_label = "Make Selected Mesh Single User"
    bl_description = "Make selected mesh objects use separate mesh data copies"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return self._start(context)

    def execute(self, context):
        return self._start(context)

    def _start(self, context):
        scene = context.scene
        settings = scene.maplink_settings
        progress = scene.maplink_progress
        if progress.is_running:
            self.report({"WARNING"}, "Another Map Link Tools operation is already running.")
            return {"CANCELLED"}

        self._objects = [obj for obj in object_pool(context) if obj.type == "MESH" and obj.data is not None]
        if not self._objects:
            self.report({"WARNING"}, "No selected mesh objects.")
            return {"CANCELLED"}

        self._settings = settings
        self._cursor = 0
        self._mesh_names = {mesh.name for mesh in bpy.data.meshes}
        reset_progress(progress, "Make Selected Mesh Single User", "RUNNING")
        progress.is_running = True
        progress.total_count = len(self._objects)
        progress.remaining_count = len(self._objects)
        progress.current_message = "Duplicating mesh data where needed..."
        self._timer = context.window_manager.event_timer_add(TIMER_INTERVAL, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        progress = context.scene.maplink_progress
        if event.type == "ESC" or progress.cancel_requested:
            self._finish(context, canceled=True)
            return {"CANCELLED"}
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        start = time.perf_counter()
        while self._cursor < len(self._objects):
            obj = self._objects[self._cursor]
            try:
                if self._settings.do_not_modify_external_linked_data and is_external_linked_object(obj):
                    progress.skipped_count += 1
                    progress.warning_count += 1
                    message = f"Skipped linked data: {obj.name}"
                elif obj.data.users <= 1:
                    progress.skipped_count += 1
                    message = f"Already single-user: {obj.name}"
                else:
                    obj.data = obj.data.copy()
                    target = make_unique_name(obj.name, self._mesh_names, self._settings.digits, self._settings.separator or "_")
                    obj.data.name = target
                    self._mesh_names.add(target)
                    progress.renamed_count += 1
                    message = f"Single-user mesh: {obj.name}"
            except Exception as exc:
                progress.error_count += 1
                message = str(exc)

            self._cursor += 1
            update_progress(progress, self._cursor, len(self._objects), message)
            if time.perf_counter() - start >= MAX_SECONDS_PER_TICK:
                break

        tag_view3d_redraw(context)
        if self._cursor >= len(self._objects):
            self._finish(context, canceled=False)
            return {"FINISHED"}
        return {"PASS_THROUGH"}

    def _finish(self, context, canceled=False):
        progress = context.scene.maplink_progress
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        progress.is_running = False
        progress.cancel_requested = False
        progress.status = "CANCELED" if canceled else "COMPLETED"
        progress.current_message = (
            f"Canceled. Processed {progress.processed_count} / {progress.total_count}."
            if canceled
            else f"Completed. Made single-user: {progress.renamed_count}, skipped: {progress.skipped_count}, errors: {progress.error_count}."
        )
        self.report({"INFO"}, progress.current_message)
        refresh_selection_info(context)
        tag_view3d_redraw(context)


class MAPLINK_OT_batch_make_single_user(MAPLINK_OT_make_selected_mesh_single_user):
    bl_idname = "maplink.batch_make_single_user"
    bl_label = "Batch Make Single User"
    bl_description = "Batch make selected mesh objects single-user"


class MAPLINK_OT_show_object_collections(Operator):
    bl_idname = "maplink.show_object_collections"
    bl_label = "Show Object Collections"
    bl_description = "Show direct collection memberships for selected objects"

    def execute(self, context):
        scene = context.scene
        begin_preview(scene, "Object Collections")
        objects = object_pool(context)
        for obj in objects[:PREVIEW_LIST_LIMIT]:
            names = ", ".join(coll.name for coll in obj.users_collection) or "[no direct collection]"
            add_preview_item(scene, obj.name, names, obj.name, "INFO", "NONE", "INFO", names, obj=obj)
        scene.maplink_preview_message = f"Showing {min(len(objects), PREVIEW_LIST_LIMIT)} of {len(objects)} selected object(s)."
        self.report({"INFO"}, scene.maplink_preview_message)
        return {"FINISHED"}


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------

class MAPLINK_UL_preview_items(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            icon_name = {
                "CHANGE": "CHECKMARK",
                "WARNING": "ERROR",
                "ERROR": "CANCEL",
                "SKIP": "RADIOBUT_OFF",
                "INFO": "INFO",
            }.get(item.status, "INFO")
            row = layout.row(align=True)
            text = item.object_name or item.source_name
            if item.target_name:
                text = f"{item.source_name} -> {item.target_name}"
            row.label(text=text, icon=icon_name)
            if item.message:
                row.label(text=item.message)
        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text="", icon="INFO")


def draw_foldout(layout, settings, prop_name, label, icon="TRIA_DOWN"):
    row = layout.row(align=True)
    opened = getattr(settings, prop_name)
    row.prop(
        settings,
        prop_name,
        text=label,
        icon="TRIA_DOWN" if opened else "TRIA_RIGHT",
        emboss=False,
    )
    return opened


def draw_preview_apply_row(layout, preview_id, apply_id, preview_text, apply_text):
    row = layout.row(align=True)
    row.operator(preview_id, text=preview_text, icon="VIEWZOOM")
    row.operator(apply_id, text=apply_text, icon="CHECKMARK")


class VIEW3D_PT_map_link_tools(Panel):
    bl_label = "Map Link Tools"
    bl_idname = "VIEW3D_PT_map_link_tools"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Map Link Tools"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        settings = scene.maplink_settings
        info = scene.maplink_selection_info
        progress = scene.maplink_progress

        if draw_foldout(layout, settings, "show_selection_overview", "01. Selection Overview"):
            box = layout.box()
            box.label(text=f"Selected Objects: {info.selected_count}", icon="OBJECT_DATA")
            box.label(text=f"Mesh Objects: {info.mesh_object_count}", icon="MESH_DATA")
            box.label(text=f"Empty Objects: {info.empty_object_count}", icon="EMPTY_DATA")
            box.label(text=f"Collection Instances: {info.collection_instance_count}", icon="OUTLINER_OB_GROUP_INSTANCE")
            box.label(text=f"Shared Mesh Objects: {info.shared_mesh_object_count}", icon="LINKED")
            box.label(text=f"Single User Mesh Objects: {info.single_user_mesh_object_count}", icon="UNLINKED")
            box.label(text=f"Objects with .001 Suffix: {info.object_suffix_issue_count}", icon="SORTALPHA")
            box.label(text=f"Mesh Data with .001 Suffix: {info.mesh_suffix_issue_count}", icon="MESH_DATA")
            box.label(text=f"External Linked Objects: {info.external_linked_count}", icon="LIBRARY_DATA_DIRECT")
            box.label(text=f"Library Overrides: {info.library_override_count}", icon="LIBRARY_DATA_OVERRIDE")
            box.operator("maplink.refresh_selection_info", icon="FILE_REFRESH")

        if draw_foldout(layout, settings, "show_quick_clean", "02. Quick Clean"):
            box = layout.box()
            box.prop(settings, "target_type", text="Target")
            box.prop(settings, "duplicate_handling", text="Duplicate")
            if settings.duplicate_handling == "CUSTOM":
                box.prop(settings, "custom_duplicate_suffix", text="Custom Suffix")
            draw_preview_apply_row(box, "maplink.preview_remove_suffix", "maplink.apply_remove_suffix", "Preview Remove .001", "Apply Remove .001")
            draw_preview_apply_row(box, "maplink.preview_convert_suffix", "maplink.apply_convert_suffix", "Preview .001 to _01", "Apply .001 to _01")
            draw_preview_apply_row(box, "maplink.preview_clean_names", "maplink.apply_clean_names", "Preview Clean", "Apply Clean")

        if draw_foldout(layout, settings, "show_rename_tools", "03. Rename Tools"):
            box = layout.box()
            box.prop(settings, "rename_mode", text="Mode")
            box.prop(settings, "target_type", text="Target")
            if settings.rename_mode == "PATTERN":
                box.prop(settings, "prefix", text="Prefix")
                box.prop(settings, "base_name", text="Base Name")
                box.prop(settings, "suffix", text="Suffix")
                box.prop(settings, "start_index", text="Start Index")
                box.prop(settings, "digits", text="Digits")
                box.prop(settings, "separator", text="Separator")
                example = f"{settings.prefix}{settings.base_name}{settings.separator or '_'}{format_index(settings.start_index, settings.digits)}{settings.suffix}"
                box.label(text=f"Example: {example}", icon="SORTALPHA")
            elif settings.rename_mode == "FIND_REPLACE":
                box.prop(settings, "find_text", text="Find")
                box.prop(settings, "replace_text", text="Replace")
                box.prop(settings, "case_sensitive", text="Case Sensitive")
            elif settings.rename_mode == "ADD_PREFIX_SUFFIX":
                box.prop(settings, "prefix_to_add", text="Prefix to Add")
                box.prop(settings, "suffix_to_add", text="Suffix to Add")
            elif settings.rename_mode == "REMOVE_PREFIX_SUFFIX":
                box.prop(settings, "prefix_to_remove", text="Prefix to Remove")
                box.prop(settings, "suffix_to_remove", text="Suffix to Remove")
            elif settings.rename_mode == "ACTIVE_OBJECT":
                active = context.view_layer.objects.active
                box.label(text=f"Active Base: {active.name if active else '[none]'}", icon="OBJECT_DATA")
                box.prop(settings, "start_index", text="Start Index")
                box.prop(settings, "digits", text="Digits")
                box.prop(settings, "separator", text="Separator")
            draw_preview_apply_row(box, "maplink.preview_pattern_rename", "maplink.apply_pattern_rename", "Preview Rename", "Apply Rename")

        if draw_foldout(layout, settings, "show_sync_tools", "04. Object / Mesh Name Sync"):
            box = layout.box()
            box.prop(settings, "sync_direction", text="Direction")
            box.prop(settings, "shared_mesh_handling", text="Shared Mesh")
            draw_preview_apply_row(box, "maplink.preview_sync_names", "maplink.apply_sync_names", "Preview Sync", "Apply Sync")
            box.operator("maplink.compare_object_mesh_names", text="Compare Only", icon="FILE_TEXT")

        if draw_foldout(layout, settings, "show_collection_instance_tools", "05. Collection Instance Tools"):
            selected_instances = [obj for obj in context.selected_objects if is_collection_instance(obj)]
            source_names = {obj.instance_collection.name for obj in selected_instances}
            box = layout.box()
            box.label(text=f"Selected Collection Instances: {len(selected_instances)}", icon="OUTLINER_OB_GROUP_INSTANCE")
            box.label(text=f"Referenced Collections: {len(source_names)}", icon="OUTLINER_COLLECTION")
            box.prop(settings, "instance_pattern", text="Pattern")
            box.prop(settings, "start_index", text="Start Index")
            box.prop(settings, "digits", text="Digits")
            draw_preview_apply_row(
                box,
                "maplink.preview_rename_collection_instances",
                "maplink.apply_rename_collection_instances",
                "Preview Rename Instances",
                "Apply Rename Instances",
            )
            box.operator("maplink.select_same_collection_source", icon="RESTRICT_SELECT_OFF")
            row = box.row(align=True)
            row.operator("maplink.show_collection_instance_source_info", text="Show Source Info", icon="INFO")
            row.operator("maplink.count_collection_instance_users", text="Count Users", icon="SORTSIZE")

        if draw_foldout(layout, settings, "show_mesh_sharing_tools", "06. Link / Mesh Sharing Tools"):
            active = context.view_layer.objects.active
            active_mesh = active.data if active and active.type == "MESH" else None
            box = layout.box()
            box.label(text="Active Object Mesh:", icon="MESH_DATA")
            box.label(text=active_mesh.name if active_mesh else "[no active mesh]")
            box.label(text=f"Mesh Users: {active_mesh.users if active_mesh else 0}", icon="LINKED")
            row = box.row(align=True)
            row.operator("maplink.select_same_mesh_data", text="Select Same Mesh", icon="RESTRICT_SELECT_OFF")
            row.operator("maplink.count_mesh_users", text="Count Users", icon="SORTSIZE")
            box.operator("maplink.show_shared_mesh_users", icon="INFO")
            row = box.row(align=True)
            row.operator("maplink.make_selected_mesh_single_user", text="Make Single User", icon="UNLINKED")
            row.operator("maplink.batch_make_single_user", text="Batch Single User", icon="DUPLICATE")
            row = box.row(align=True)
            row.operator("maplink.select_shared_mesh_objects", text="Select Shared", icon="LINKED")
            row.operator("maplink.select_single_user_mesh_objects", text="Select Single", icon="UNLINKED")

        if draw_foldout(layout, settings, "show_collection_based_rename", "07. Collection Based Rename"):
            box = layout.box()
            box.prop(settings, "collection_source", text="Collection Source")
            box.prop(settings, "collection_pattern", text="Pattern")
            draw_preview_apply_row(
                box,
                "maplink.preview_collection_based_rename",
                "maplink.apply_collection_based_rename",
                "Preview Collection Rename",
                "Apply Collection Rename",
            )
            box.operator("maplink.show_object_collections", icon="OUTLINER_COLLECTION")

        if draw_foldout(layout, settings, "show_safety_preview", "08. Safety Preview"):
            box = layout.box()
            counts = preview_counts(scene)
            box.label(text=f"Pending Operation: {scene.maplink_preview_operation or '[none]'}", icon="PREVIEW_RANGE")
            box.label(text=f"Affected Items: {len(scene.maplink_preview_items)}", icon="SORTSIZE")
            box.label(text=f"Will Change: {counts.get('CHANGE', 0)}", icon="CHECKMARK")
            box.label(text=f"Will Skip: {counts.get('SKIP', 0)}", icon="RADIOBUT_OFF")
            box.label(text=f"Warnings: {counts.get('WARNING', 0)}", icon="ERROR")
            box.label(text=f"Errors: {counts.get('ERROR', 0)}", icon="CANCEL")
            if scene.maplink_preview_message:
                box.label(text=scene.maplink_preview_message, icon="INFO")
            if len(scene.maplink_preview_items) > 0:
                box.template_list(
                    "MAPLINK_UL_preview_items",
                    "",
                    scene,
                    "maplink_preview_items",
                    scene,
                    "maplink_preview_index",
                    rows=min(8, max(1, len(scene.maplink_preview_items))),
                )
                if len(scene.maplink_preview_items) > PREVIEW_LIST_LIMIT:
                    box.label(text=f"Preview list contains {len(scene.maplink_preview_items)} items.", icon="INFO")
            row = box.row(align=True)
            row.operator("maplink.apply_previewed_operation", icon="CHECKMARK")
            row.operator("maplink.clear_preview", icon="X")

        if draw_foldout(layout, settings, "show_operation_progress", "09. Operation Progress"):
            box = layout.box()
            box.label(text=f"Status: {progress.status}", icon="TIME")
            box.label(text=f"Operation: {progress.operation_name or '[none]'}")
            box.label(text=f"Processed: {progress.processed_count} / {progress.total_count}")
            box.label(text=f"Remaining: {progress.remaining_count}")
            box.label(text=f"Progress: {progress.progress_percent:.1f}%")
            if progress.current_message:
                box.label(text=progress.current_message, icon="INFO")
            row = box.row(align=True)
            row.enabled = progress.is_running
            row.operator("maplink.cancel_current_operation", icon="CANCEL")

        if draw_foldout(layout, settings, "show_advanced_options", "10. Advanced Options"):
            box = layout.box()
            box.prop(settings, "duplicate_handling", text="Duplicate Name Handling")
            box.prop(settings, "selected_only", text="Selected Objects Only")
            box.prop(settings, "include_hidden", text="Include Hidden Objects")
            box.prop(settings, "include_locked", text="Include Locked Objects")
            box.prop(settings, "include_children", text="Include Children")
            box.prop(settings, "include_same_collection", text="Include Objects in Same Collection")
            box.prop(settings, "do_not_modify_external_linked_data", text="Do Not Modify External Linked Data")
            box.prop(settings, "warn_before_editing_shared_mesh_data", text="Warn Before Editing Shared Mesh Data")
            box.prop(settings, "show_result_popup", text="Show Result Popup")
            box.prop(settings, "print_details_to_console", text="Print Details to Console")


class MAPLINK_AddonPreferences(AddonPreferences):
    bl_idname = __package__ or __name__

    def draw(self, context):
        layout = self.layout
        layout.label(text="Documentation")
        op = layout.operator("wm.url_open", text="Open README on GitHub", icon="URL")
        op.url = DOCUMENTATION_URL


classes = (
    MAPLINK_AddonPreferences,
    MapLinkToolsSettings,
    MapLinkSelectionInfo,
    MapLinkOperationProgress,
    MapLinkPreviewItem,
    MAPLINK_UL_preview_items,
    MAPLINK_OT_refresh_selection_info,
    MAPLINK_OT_clear_preview,
    MAPLINK_OT_preview_operation,
    MAPLINK_OT_preview_remove_suffix,
    MAPLINK_OT_apply_remove_suffix,
    MAPLINK_OT_preview_convert_suffix,
    MAPLINK_OT_apply_convert_suffix,
    MAPLINK_OT_preview_clean_names,
    MAPLINK_OT_apply_clean_names,
    MAPLINK_OT_preview_pattern_rename,
    MAPLINK_OT_apply_pattern_rename,
    MAPLINK_OT_preview_find_replace,
    MAPLINK_OT_apply_find_replace,
    MAPLINK_OT_preview_add_prefix_suffix,
    MAPLINK_OT_apply_add_prefix_suffix,
    MAPLINK_OT_preview_remove_prefix_suffix,
    MAPLINK_OT_apply_remove_prefix_suffix,
    MAPLINK_OT_preview_rename_by_active,
    MAPLINK_OT_apply_rename_by_active,
    MAPLINK_OT_preview_sync_names,
    MAPLINK_OT_apply_sync_names,
    MAPLINK_OT_compare_object_mesh_names,
    MAPLINK_OT_preview_rename_collection_instances,
    MAPLINK_OT_apply_rename_collection_instances,
    MAPLINK_OT_preview_collection_based_rename,
    MAPLINK_OT_apply_collection_based_rename,
    MAPLINK_OT_apply_previewed_operation,
    MAPLINK_OT_cancel_current_operation,
    MAPLINK_OT_select_same_mesh_data,
    MAPLINK_OT_select_same_collection_source,
    MAPLINK_OT_select_shared_mesh_objects,
    MAPLINK_OT_select_single_user_mesh_objects,
    MAPLINK_OT_show_collection_instance_source_info,
    MAPLINK_OT_count_collection_instance_users,
    MAPLINK_OT_count_mesh_users,
    MAPLINK_OT_show_shared_mesh_users,
    MAPLINK_OT_make_selected_mesh_single_user,
    MAPLINK_OT_batch_make_single_user,
    MAPLINK_OT_show_object_collections,
    VIEW3D_PT_map_link_tools,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.maplink_settings = PointerProperty(type=MapLinkToolsSettings)
    bpy.types.Scene.maplink_selection_info = PointerProperty(type=MapLinkSelectionInfo)
    bpy.types.Scene.maplink_progress = PointerProperty(type=MapLinkOperationProgress)
    bpy.types.Scene.maplink_preview_items = CollectionProperty(type=MapLinkPreviewItem)
    bpy.types.Scene.maplink_preview_index = IntProperty(default=0, min=0)
    bpy.types.Scene.maplink_preview_operation = StringProperty(default="")
    bpy.types.Scene.maplink_preview_message = StringProperty(default="")


def unregister():
    props = (
        "maplink_settings",
        "maplink_selection_info",
        "maplink_progress",
        "maplink_preview_items",
        "maplink_preview_index",
        "maplink_preview_operation",
        "maplink_preview_message",
    )
    for prop_name in props:
        if hasattr(bpy.types.Scene, prop_name):
            delattr(bpy.types.Scene, prop_name)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
