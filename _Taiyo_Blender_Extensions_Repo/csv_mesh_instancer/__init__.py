bl_info = {
    "name": "CSV Mesh Instancer",
    "author": "Taiyo",
    "version": (2, 0, 0),
    "blender": (4, 5, 9),
    "location": "View3D > Sidebar(N) > CSV Instancer",
    "description": "Create linked mesh objects from CSV transforms using Collection or FBX sources.",
    "category": "Import-Export",
}

import csv
import base64
import copy
import json
import math
import os
import re
import time
import traceback
import zlib
import bpy
from mathutils import Euler, Quaternion
from bpy.app.handlers import persistent
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

from . import v2_engine


DOCUMENTATION_URL = (
    "https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/"
    "_Taiyo_Blender_Extensions_Repo/csv_mesh_instancer/CSV_Mesh_Instancer_%E4%BD%BF%E7%94%A8%E6%9B%B8.md"
)

REQUIRED_COLUMNS = (
    "objname",
    "tx",
    "ty",
    "tz",
    "rx",
    "ry",
    "rz",
    "sx",
    "sy",
    "sz",
)
NUMERIC_SUFFIX_RE = re.compile(r"\.(\d{3,})$")
INTEGER_RE = re.compile(r"^[+-]?\d+$")
TIME_BUDGET_SECONDS = 0.012
LARGE_TASK_TIME_BUDGET_SECONDS = 0.012
LARGE_TASK_WORK_THRESHOLD = 20000
TIMER_INTERVAL_SECONDS = 0.01
UI_PUBLISH_INTERVAL_SECONDS = 0.2
REMOVE_BATCH_SIZE = 4096
MIN_REMOVE_BATCH_SIZE = 64
MAX_REMOVE_BATCH_SIZE = 65536
FBX_MANAGED_KEY = "csvmi_fbx_managed"
FBX_PATH_KEY = "csvmi_fbx_filepath"
OUTPUT_MANAGED_KEY = "csvmi_output_managed"
OUTPUT_SCHEMA_KEY = "csvmi_schema_version"
OUTPUT_STATE_TEXT_KEY = "csvmi_state_text"
OUTPUT_SCHEMA_VERSION = 2
OBJECT_ID_KEY = "csvmi_id"
OBJECT_SCHEMA_KEY = "csvmi_schema_version"
CSV_CUSTOM_KEYS_PROP = "csvmi_custom_property_keys"
RESERVED_CUSTOM_PREFIX = "csvmi_"
STAGING_NAME = "__CSVMI_OUTPUT_STAGING__"
DELETED_COLLECTION_NAME = "Deleted"
ZONE_COLLECTION_KEY = "csvmi_zone_collection"
ZONE_VALUE_KEY = "csvmi_zone_value"
DELETED_COLLECTION_KEY = "csvmi_deleted_collection"
STATE_TEXT_PREFIX = ".CSVMI_State_"
FILTER_VALUE_LIMIT = 256
REVIEW_PAGE_SIZE = 100
LOCATION_SCALE_TOLERANCE = 1.0e-5
ROTATION_TOLERANCE_RADIANS = 1.0e-4

# Tuple indexes for compact CSV row storage.
ROW_NAME = 0
ROW_ID = 1
# Kept as a private alias only so the retired v1 task classes remain importable.
ROW_PTNUM = ROW_ID
ROW_LINE = 2
ROW_TX = 3
ROW_TY = 4
ROW_TZ = 5
ROW_RX = 6
ROW_RY = 7
ROW_RZ = 8
ROW_SX = 9
ROW_SY = 10
ROW_SZ = 11
ROW_EXTRA = 12


def parse_custom_property_value(raw_value):
    """Convert an optional CSV cell once, before placement begins."""
    if raw_value is None:
        return None, None
    value = raw_value.strip()
    if not value:
        return None, None
    lowered = value.casefold()
    if lowered == "true":
        return True, "Boolean"
    if lowered == "false":
        return False, "Boolean"
    if INTEGER_RE.fullmatch(value):
        integer = int(value)
        if -(2**63) <= integer <= (2**63 - 1):
            return integer, "Integer"
        return value, "String"
    try:
        number = float(value)
    except ValueError:
        return value, "String"
    if math.isfinite(number):
        return number, "Float"
    return value, "String"


def summarize_custom_property_type(type_names):
    if not type_names:
        return "Empty"
    if len(type_names) == 1:
        return next(iter(type_names))
    if type_names <= {"Integer", "Float"}:
        return "Number"
    return "Mixed"


def managed_csv_property_names(obj):
    raw_names = obj.get(CSV_CUSTOM_KEYS_PROP, "")
    if not isinstance(raw_names, str) or not raw_names:
        return ()
    try:
        names = json.loads(raw_names)
    except (TypeError, ValueError):
        return ()
    if not isinstance(names, list):
        return ()
    return tuple(
        name
        for name in names
        if isinstance(name, str) and not name.casefold().startswith(RESERVED_CUSTOM_PREFIX)
    )


def selected_csv_attributes(props, cache):
    enabled_by_name = {item.name: item.enabled and not item.reserved for item in props.csv_attributes}
    return tuple(
        (index, name)
        for index, name in enumerate(cache.extra_columns)
        if enabled_by_name.get(name, False)
    )


def apply_csv_custom_properties(obj, row, selected_attributes):
    """Replace only Custom Properties previously managed from extra CSV columns."""
    names_to_remove = set(managed_csv_property_names(obj))
    names_to_remove.update(name for _index, name in selected_attributes)
    for name in names_to_remove:
        if name in obj:
            del obj[name]
    if CSV_CUSTOM_KEYS_PROP in obj:
        del obj[CSV_CUSTOM_KEYS_PROP]

    assigned_names = []
    extra_values = row[ROW_EXTRA]
    for index, name in selected_attributes:
        value = extra_values[index]
        if value is None:
            continue
        obj[name] = value
        assigned_names.append(name)
    if assigned_names:
        obj[CSV_CUSTOM_KEYS_PROP] = json.dumps(assigned_names, ensure_ascii=False)


def apply_csv_transform(obj, row, props):
    """Apply CSV values and a separate FBX unit/axis correction."""
    obj.location = (row[ROW_TX], row[ROW_TY], row[ROW_TZ])
    obj.rotation_mode = 'XYZ'
    obj.rotation_euler = (row[ROW_RX], row[ROW_RY], row[ROW_RZ])
    obj.scale = (row[ROW_SX], row[ROW_SY], row[ROW_SZ])
    obj.delta_location = (0.0, 0.0, 0.0)
    if props.source_mode == 'FBX' and props.apply_fbx_correction:
        correction = props.fbx_unit_scale
        csv_rotation = obj.rotation_euler.to_quaternion()
        local_x_rotation = Quaternion((1.0, 0.0, 0.0), props.fbx_rotation_x)
        world_delta = csv_rotation @ local_x_rotation @ csv_rotation.conjugated()
        obj.delta_rotation_euler = world_delta.to_euler('XYZ')
        obj.delta_scale = (correction, correction, correction)
    else:
        obj.delta_rotation_euler = (0.0, 0.0, 0.0)
        obj.delta_scale = (1.0, 1.0, 1.0)


class CSVData:
    __slots__ = (
        "path",
        "mtime_ns",
        "size",
        "rows",
        "rows_by_id",
        "unique_names",
        "headers",
        "identity_column",
        "extra_columns",
        "extra_types",
        "attribute_values",
        "raw_count",
        "empty_name_count",
        "numeric_error_count",
        "error_samples",
    )

    def __init__(
        self,
        path,
        mtime_ns,
        size,
        rows,
        rows_by_id,
        unique_names,
        headers,
        identity_column,
        extra_columns,
        extra_types,
        attribute_values,
        raw_count,
        empty_name_count,
        numeric_error_count,
        error_samples,
    ):
        self.path = path
        self.mtime_ns = mtime_ns
        self.size = size
        self.rows = rows
        self.rows_by_id = rows_by_id
        self.unique_names = unique_names
        self.headers = headers
        self.identity_column = identity_column
        self.extra_columns = extra_columns
        self.extra_types = extra_types
        self.attribute_values = attribute_values
        self.raw_count = raw_count
        self.empty_name_count = empty_name_count
        self.numeric_error_count = numeric_error_count
        self.error_samples = error_samples

    @property
    def invalid_count(self):
        return self.empty_name_count + self.numeric_error_count


_CSV_CACHE = {}
_PREVIEW_CACHE = {}
_SEARCH_DEBOUNCE_TOKENS = {}


def _scene_key(scene):
    return scene.as_pointer()


def get_csv_cache(scene):
    return _CSV_CACHE.get(_scene_key(scene))


def set_csv_cache(scene, data):
    _CSV_CACHE[_scene_key(scene)] = data


def clear_csv_cache(scene):
    _CSV_CACHE.pop(_scene_key(scene), None)


def get_preview_cache(scene):
    return _PREVIEW_CACHE.get(_scene_key(scene))


def clear_preview_cache(scene, clear_rows=True):
    _PREVIEW_CACHE.pop(_scene_key(scene), None)
    if clear_rows and hasattr(scene, "csvmi_props"):
        props = scene.csvmi_props
        if hasattr(props, "review_rows"):
            props.review_rows.clear()
            props.review_page = 0
            props.review_total_pages = 0
            props.preview_valid = False


def absolute_path(path):
    return os.path.normpath(bpy.path.abspath(path)) if path else ""


def file_signature(path):
    stat = os.stat(path)
    return stat.st_mtime_ns, stat.st_size


def csv_file_changed(scene):
    cache = get_csv_cache(scene)
    if cache is None:
        return False
    current_path = absolute_path(scene.csvmi_props.csv_path)
    if current_path != cache.path:
        return True
    try:
        return file_signature(current_path) != (cache.mtime_ns, cache.size)
    except OSError:
        return True


def load_csv_data(path, identity_column="id"):
    path = absolute_path(path)
    if not path:
        raise ValueError("Select a CSV file.")
    if not os.path.isfile(path):
        raise ValueError(f"CSV file not found: {path}")

    rows = []
    unique_names = set()
    raw_count = 0
    empty_name_count = 0
    numeric_error_count = 0
    error_samples = []
    extra_columns = ()
    extra_type_names = []
    attribute_value_counts = []
    identity_first_lines = {}
    duplicate_id_samples = []

    try:
        handle = open(path, "r", encoding="utf-8-sig", newline="")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"Could not open CSV: {exc}") from exc

    with handle:
        try:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ValueError("CSV header is missing.")

            header_map = {}
            for original in reader.fieldnames:
                if original is None:
                    continue
                normalized = original.strip().lstrip("\ufeff")
                if normalized and normalized not in header_map:
                    header_map[normalized] = original

            missing = [name for name in REQUIRED_COLUMNS if name not in header_map]
            if missing:
                raise ValueError("Missing required columns: " + ", ".join(missing))

            identity_column = identity_column.strip()
            if not identity_column:
                raise ValueError("Enter an Identity Column.")
            if identity_column not in header_map:
                raise ValueError(f"Identity column not found: {identity_column}")

            excluded_columns = set(REQUIRED_COLUMNS) | {"ptnum", identity_column}
            extra_columns = tuple(name for name in header_map if name not in excluded_columns)
            extra_type_names = [set() for _name in extra_columns]
            attribute_value_counts = [dict() for _name in extra_columns]
            for line_number, record in enumerate(reader, start=2):
                raw_count += 1
                objname = (record.get(header_map["objname"]) or "").strip()
                if not objname:
                    empty_name_count += 1
                    if len(error_samples) < 12:
                        error_samples.append(f"Line {line_number}: objname is empty")
                    continue

                identity = (record.get(header_map[identity_column]) or "").strip()
                if not identity:
                    raise ValueError(f"Identity is empty at CSV line {line_number}: {identity_column}")
                first_line = identity_first_lines.get(identity)
                if first_line is not None:
                    if len(duplicate_id_samples) < 20:
                        duplicate_id_samples.append((identity, first_line, line_number))
                else:
                    identity_first_lines[identity] = line_number

                try:
                    values = [float(record.get(header_map[name], "")) for name in REQUIRED_COLUMNS[1:]]
                    if not all(math.isfinite(value) for value in values):
                        raise ValueError("NaN or Infinity")
                except (TypeError, ValueError) as exc:
                    numeric_error_count += 1
                    if len(error_samples) < 12:
                        error_samples.append(f"Line {line_number}: invalid number ({exc})")
                    continue

                extra_values = []
                for index, name in enumerate(extra_columns):
                    value, type_name = parse_custom_property_value(record.get(header_map[name]))
                    extra_values.append(value)
                    if type_name is not None:
                        extra_type_names[index].add(type_name)
                    value_key = "" if value is None else str(value)
                    counts = attribute_value_counts[index]
                    counts[value_key] = counts.get(value_key, 0) + 1

                tx, ty, tz, rx, ry, rz, sx, sy, sz = values
                rows.append(
                    (
                        objname,
                        identity,
                        line_number,
                        tx,
                        ty,
                        tz,
                        math.radians(rx),
                        math.radians(ry),
                        math.radians(rz),
                        sx,
                        sy,
                        sz,
                        tuple(extra_values),
                    )
                )
                unique_names.add(objname)
        except csv.Error as exc:
            raise ValueError(f"CSV format error: {exc}") from exc

    if duplicate_id_samples:
        details = "; ".join(
            f"{identity!r} (lines {first_line} and {line_number})"
            for identity, first_line, line_number in duplicate_id_samples
        )
        raise ValueError(
            f"Identity column '{identity_column}' contains duplicate values: {details}"
        )

    if not rows:
        raise ValueError("CSV contains no valid placement rows.")

    mtime_ns, size = file_signature(path)
    return CSVData(
        path,
        mtime_ns,
        size,
        rows,
        {row[ROW_ID]: row for row in rows},
        frozenset(unique_names),
        tuple(header_map),
        identity_column,
        extra_columns,
        tuple(summarize_custom_property_type(names) for names in extra_type_names),
        {
            name: tuple(sorted(counts.items(), key=lambda item: item[0]))
            for name, counts in zip(extra_columns, attribute_value_counts)
        },
        raw_count,
        empty_name_count,
        numeric_error_count,
        tuple(error_samples),
    )


def iter_collection_tree(root):
    if root is None:
        return
    stack = [root]
    seen = set()
    while stack:
        collection = stack.pop()
        pointer = collection.as_pointer()
        if pointer in seen:
            continue
        seen.add(pointer)
        yield collection
        stack.extend(reversed(collection.children[:]))


def collection_contains(root, target):
    if root is None or target is None:
        return False
    target_pointer = target.as_pointer()
    return any(collection.as_pointer() == target_pointer for collection in iter_collection_tree(root))


def collect_collection_objects(root, mesh_only=False):
    objects = []
    seen = set()
    for collection in iter_collection_tree(root):
        for obj in collection.objects:
            pointer = obj.as_pointer()
            if pointer in seen or (mesh_only and obj.type != 'MESH'):
                continue
            seen.add(pointer)
            objects.append(obj)
    return objects


def collect_child_collections_postorder(root):
    children = []

    def visit(collection):
        for child in collection.children:
            visit(child)
            children.append(child)

    if root is not None:
        visit(root)
    return children


def collect_collection_parent_links(collection):
    parents = []
    seen = set()
    candidates = [scene.collection for scene in bpy.data.scenes]
    candidates.extend(bpy.data.collections)
    for parent in candidates:
        pointer = parent.as_pointer()
        if pointer in seen:
            continue
        seen.add(pointer)
        if collection in parent.children[:]:
            parents.append(parent)
    return parents


def strip_numeric_suffix(name):
    return NUMERIC_SUFFIX_RE.sub("", name)


def source_choice_key(obj):
    match = NUMERIC_SUFFIX_RE.search(obj.name)
    if match is None:
        return (0, -1, obj.name)
    return (1, int(match.group(1)), obj.name)


def build_source_index(objects, ignore_suffix):
    exact = {obj.name: obj for obj in objects}
    normalized = {}
    collisions = {}
    if ignore_suffix:
        for obj in objects:
            normalized.setdefault(strip_numeric_suffix(obj.name), []).append(obj)
        for name, candidates in normalized.items():
            candidates.sort(key=source_choice_key)
            if len(candidates) > 1:
                collisions[name] = tuple(obj.name for obj in candidates)
    return exact, normalized, collisions


def resolve_source_names(unique_names, objects, ignore_suffix):
    exact, normalized, collisions = build_source_index(objects, ignore_suffix)
    resolved = {}
    missing = []
    for name in unique_names:
        source = exact.get(name)
        if source is None and ignore_suffix:
            candidates = normalized.get(strip_numeric_suffix(name), ())
            if candidates:
                source = candidates[0]
        if source is None:
            missing.append(name)
        else:
            resolved[name] = source
    return resolved, tuple(sorted(missing)), collisions


def collection_color_icon(collection):
    if collection is None:
        return 'OUTLINER_COLLECTION'
    color_tag = getattr(collection, "color_tag", "NONE")
    if color_tag.startswith("COLOR_"):
        return "COLLECTION_" + color_tag
    return 'OUTLINER_COLLECTION'


def collection_source_for_scene(scene):
    props = scene.csvmi_props
    if props.source_mode == 'COLLECTION':
        return props.source_collection
    collection = props.fbx_managed_collection
    if collection is not None and bool(collection.get(FBX_MANAGED_KEY, False)):
        return collection
    return None


def validate_source_and_output(scene, cache):
    profile_enabled = os.environ.get("CSVMI_PROFILE") == "1"
    profile_started = time.perf_counter()
    props = scene.csvmi_props
    source_collection = collection_source_for_scene(scene)
    if source_collection is None:
        if props.source_mode == 'FBX':
            raise ValueError("Import an FBX source first.")
        raise ValueError("Select a source Collection.")

    output_name = props.output_collection_name.strip()
    if not output_name:
        raise ValueError("Enter an output Collection name.")

    output_collection = bpy.data.collections.get(output_name)
    if output_collection is not None:
        if collection_contains(source_collection, output_collection):
            raise ValueError("The output Collection is inside the source Collection.")
        if collection_contains(output_collection, source_collection):
            raise ValueError("The source Collection is inside the output Collection.")
    collections_done = time.perf_counter()

    source_objects = collect_collection_objects(source_collection, mesh_only=True)
    if not source_objects:
        raise ValueError("No source Mesh objects were found.")
    sources_done = time.perf_counter()

    if output_collection is not None:
        output_object_pointers = {
            obj.as_pointer() for obj in collect_collection_objects(output_collection)
        }
        overlap = [obj.name for obj in source_objects if obj.as_pointer() in output_object_pointers]
        if overlap:
            raise ValueError("Source Mesh objects are also linked to the output: " + ", ".join(overlap[:5]))
    overlap_done = time.perf_counter()

    resolved, missing_names, collisions = resolve_source_names(
        cache.unique_names,
        source_objects,
        props.ignore_numeric_suffix,
    )
    resolve_done = time.perf_counter()
    if collisions:
        print("[CSV Mesh Instancer] Numeric suffix collisions:")
        for normalized, candidates in sorted(collisions.items()):
            print(f"  {normalized}: {', '.join(candidates)}")

    missing_name_set = set(missing_names)
    missing_row_count = sum(1 for row in cache.rows if row[ROW_NAME] in missing_name_set)
    missing_done = time.perf_counter()
    if missing_names:
        print("[CSV Mesh Instancer] Missing Mesh names:")
        for name in missing_names:
            print(f"  {name}")

    props.source_mesh_count = len(source_objects)
    props.collision_group_count = len(collisions)
    props.missing_name_count = len(missing_names)
    props.missing_row_count = missing_row_count
    props.missing_name_preview = ", ".join(missing_names[:8])
    if profile_enabled:
        finished = time.perf_counter()
        print(
            f"[CSVMI VALIDATE PROFILE] collections={collections_done - profile_started:.3f}s "
            f"sources={sources_done - collections_done:.3f}s "
            f"overlap={overlap_done - sources_done:.3f}s "
            f"resolve={resolve_done - overlap_done:.3f}s "
            f"missing={missing_done - resolve_done:.3f}s props={finished - missing_done:.3f}s",
            flush=True,
        )
    return source_collection, output_collection, resolved, missing_names, missing_row_count


def remove_collection_with_contents(collection):
    if collection is None:
        return
    objects = collect_collection_objects(collection)
    if objects:
        bpy.data.batch_remove(objects)
    for child in collect_child_collections_postorder(collection):
        if child.name in bpy.data.collections:
            bpy.data.collections.remove(child)
    if collection.name in bpy.data.collections:
        bpy.data.collections.remove(collection)


def find_layer_collection(layer_collection, collection):
    if layer_collection.collection == collection:
        return layer_collection
    for child in layer_collection.children:
        match = find_layer_collection(child, collection)
        if match is not None:
            return match
    return None


def isolate_fbx_source_collection(scene, collection):
    """Exclude an FBX source from every View Layer, or hide it globally as fallback."""
    layer_collections = []
    for view_layer in scene.view_layers:
        layer_collection = find_layer_collection(view_layer.layer_collection, collection)
        if layer_collection is None:
            layer_collections = []
            break
        layer_collections.append(layer_collection)

    if layer_collections:
        try:
            for layer_collection in layer_collections:
                layer_collection.exclude = True
            if all(layer_collection.exclude for layer_collection in layer_collections):
                return 'VIEW_LAYER_EXCLUDE'
        except (AttributeError, RuntimeError, TypeError):
            pass

    collection.hide_viewport = True
    collection.hide_render = True
    return 'COLLECTION_HIDE'


def _property_update_source_collection(self, context):
    if context is None or context.scene is None:
        return
    props = context.scene.csvmi_props
    props.source_mesh_count = len(collect_collection_objects(props.source_collection, mesh_only=True))
    clear_preview_cache(context.scene)


def _set_running(props, operation, status):
    props.running = True
    props.cancel_requested = False
    props.active_operation = operation
    props.status = status
    props.progress = 0.0
    props.eta_text = "Estimating remaining time…"
    props.ui_publish_count = 0


def _set_idle(props):
    props.running = False
    props.cancel_requested = False
    props.active_operation = 'NONE'
    props.eta_text = ""


def tag_view3d_redraw(context):
    screen = getattr(context, "screen", None)
    if screen is None:
        return
    for area in screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


def format_remaining_time(seconds):
    seconds = max(0, int(round(seconds)))
    if seconds < 60:
        return f"~{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"~{minutes}m {seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"~{hours}h {minutes:02d}m"


def reset_output_stats(props):
    props.generated_count = 0
    props.skipped_count = 0
    props.missing_name_count = 0
    props.missing_row_count = 0
    props.linked_instance_count = 0
    props.missing_name_preview = ""
    props.process_seconds = 0.0
    props.max_tick_ms = 0.0


def set_managed_collection_visibility(scene, collection, show):
    collection.hide_viewport = not show
    collection.hide_render = not show
    if show:
        for view_layer in scene.view_layers:
            layer_collection = find_layer_collection(view_layer.layer_collection, collection)
            if layer_collection is not None:
                try:
                    layer_collection.exclude = False
                except (AttributeError, ReferenceError, RuntimeError):
                    pass


class ProgressTaskMixin:
    """Publish task progress at a low frequency to avoid GUI notifier overhead."""

    cancellable = True

    def _init_progress_tracking(self):
        self._last_publish_time = self.started_at
        self._last_published_units = 0
        self._published_progress = 0.0
        self._ema_units_per_second = 0.0
        self._rate_sample_count = 0
        self.ui_publish_count = 0

    def progress_snapshot(self):
        raise NotImplementedError

    def publish_progress(self, force=False):
        now = time.perf_counter()
        if not force and now - self._last_publish_time < UI_PUBLISH_INTERVAL_SECONDS:
            return False

        completed, total, phase, status = self.progress_snapshot()
        completed = max(0, completed)
        total = max(1, total)
        factor = min(1.0, completed / total)
        if not self.finished:
            factor = min(factor, 0.999)
        factor = max(self._published_progress, factor)

        elapsed = max(0.0, now - self._last_publish_time)
        unit_delta = max(0, completed - self._last_published_units)
        if elapsed > 0.0 and unit_delta > 0:
            current_rate = unit_delta / elapsed
            if self._rate_sample_count == 0:
                self._ema_units_per_second = current_rate
            else:
                self._ema_units_per_second = 0.25 * current_rate + 0.75 * self._ema_units_per_second
            self._rate_sample_count += 1

        remaining = max(0, total - completed)
        if self.finished or remaining == 0:
            eta_text = ""
        elif self._rate_sample_count < 2 or self._ema_units_per_second <= 0.0:
            eta_text = "Estimating remaining time…"
        else:
            eta_text = "Remaining: " + format_remaining_time(remaining / self._ema_units_per_second)

        self.props.progress = factor
        self.props.phase = phase
        self.props.status = status
        self.props.eta_text = eta_text
        self._published_progress = factor
        self._last_publish_time = now
        self._last_published_units = completed
        self.ui_publish_count += 1
        return True


class BlenderNameAllocator:
    """Reserve deterministic Blender-style Object names without touching bpy data."""

    def __init__(self, used_names):
        self.used_names = set(used_names)
        self.next_suffix = {}

    def reserve(self, requested_name):
        if requested_name not in self.used_names:
            self.used_names.add(requested_name)
            return requested_name

        match = NUMERIC_SUFFIX_RE.search(requested_name)
        if match:
            stem = requested_name[:match.start()]
            start = int(match.group(1)) + 1
        else:
            stem = requested_name
            start = 1

        suffix = max(start, self.next_suffix.get(stem, start))
        while True:
            candidate = f"{stem}.{suffix:03d}"
            suffix += 1
            if candidate not in self.used_names:
                self.next_suffix[stem] = suffix
                self.used_names.add(candidate)
                return candidate


def generated_name_allocator(output_collection):
    output_objects = set(collect_collection_objects(output_collection)) if output_collection else set()
    return BlenderNameAllocator(obj.name for obj in bpy.data.objects if obj not in output_objects)


class TemporaryCollectionExclusion:
    """Suspend View Layer evaluation while a large Collection is being changed."""

    def __init__(self, scene, collection):
        self.collection = collection
        self.layer_states = []
        self.hide_viewport = collection.hide_viewport
        self.used_hide_fallback = False
        for view_layer in scene.view_layers:
            layer_collection = find_layer_collection(view_layer.layer_collection, collection)
            if layer_collection is not None:
                self.layer_states.append((layer_collection, layer_collection.exclude))

        if self.layer_states and len(self.layer_states) == len(scene.view_layers):
            for layer_collection, _exclude in self.layer_states:
                layer_collection.exclude = True
        else:
            collection.hide_viewport = True
            self.used_hide_fallback = True

    def restore(self):
        if self.collection is None or self.collection.name not in bpy.data.collections:
            return
        for layer_collection, exclude in self.layer_states:
            try:
                layer_collection.exclude = exclude
            except (ReferenceError, RuntimeError):
                pass
        if self.used_hide_fallback:
            self.collection.hide_viewport = self.hide_viewport
        self.collection = None


class UpdateTask(ProgressTaskMixin):
    def __init__(self, scene, cache, output_collection, resolved, missing_names, missing_row_count):
        self.scene = scene
        self.props = scene.csvmi_props
        self.cache = cache
        self.rows = sorted(cache.rows, key=lambda row: (row[ROW_NAME], row[ROW_LINE]))
        self.output_collection = output_collection
        self.resolved = resolved
        self.selected_attributes = selected_csv_attributes(self.props, cache)
        self.missing_names = missing_names
        self.missing_row_count = missing_row_count
        self.phase = 'CREATE'
        self.index = 0
        self.created_count = 0
        self.stage_objects = []
        self.stage_names = []
        self.name_allocator = generated_name_allocator(output_collection)
        self.old_objects = collect_collection_objects(output_collection) if output_collection else []
        self.old_collections = collect_child_collections_postorder(output_collection) if output_collection else []
        self.expected_created_count = len(self.rows) - missing_row_count
        self.work_total = (
            len(self.rows)
            + len(self.old_objects)
            + len(self.old_collections)
            + self.expected_created_count
            + 1
        )
        self.cancelled = False
        self.finished = False
        self.commit_started = False
        self.created_new_output = False
        self.started_at = time.perf_counter()
        self.max_step_seconds = 0.0
        self.visibility_guard = None
        self._init_progress_tracking()

    def request_cancel(self):
        if self.commit_started:
            self.props.status = "The new placement is being committed and will finish safely."
            return
        if self.phase != 'CANCEL_CLEANUP':
            self.phase = 'CANCEL_CLEANUP'
            self.index = len(self.stage_objects) - 1
            self.props.status = "Cancelling: removing temporary objects"

    def _create_one(self, row):
        source = self.resolved.get(row[ROW_NAME])
        if source is None:
            return
        desired_name = self.name_allocator.reserve(row[ROW_NAME])
        obj = bpy.data.objects.new(desired_name, source.data)
        apply_csv_transform(obj, row, self.props)
        obj["csvmi_generated"] = True
        obj["csvmi_linked_mesh"] = True
        obj["csvmi_objname"] = row[ROW_NAME]
        obj["csvmi_ptnum"] = row[ROW_PTNUM]
        obj["csvmi_csv_line"] = row[ROW_LINE]
        obj["csvmi_source_object"] = source.name
        apply_csv_custom_properties(obj, row, self.selected_attributes)
        self.stage_objects.append(obj)
        self.stage_names.append(desired_name)
        self.created_count += 1

    def _prepare_commit(self):
        self.commit_started = True
        if self.output_collection is None:
            self.output_collection = bpy.data.collections.new(self.props.output_collection_name.strip())
            self.created_new_output = True
        else:
            self.visibility_guard = TemporaryCollectionExclusion(self.scene, self.output_collection)
        self.output_collection[OUTPUT_MANAGED_KEY] = True
        self.phase = 'CLEAR_OBJECTS'
        self.index = 0

    def progress_snapshot(self):
        row_total = len(self.rows)
        old_object_total = len(self.old_objects)
        old_collection_total = len(self.old_collections)
        if self.phase == 'CREATE':
            completed = self.index
            phase = "Creating placements"
            status = f"Creating placements: {self.index:,} / {row_total:,}"
        elif self.phase == 'CLEAR_OBJECTS':
            completed = row_total + self.index
            phase = "Clearing old output"
            status = f"Removing old objects: {self.index:,} / {old_object_total:,}"
        elif self.phase == 'CLEAR_COLLECTIONS':
            completed = row_total + old_object_total + self.index
            phase = "Removing child Collections"
            status = f"Removing child Collections: {self.index:,} / {old_collection_total:,}"
        elif self.phase == 'LINK':
            completed = row_total + old_object_total + old_collection_total + self.index
            phase = "Committing new placements"
            status = f"Committing placements: {self.index:,} / {len(self.stage_objects):,}"
        elif self.phase == 'FINALIZE':
            completed = self.work_total - 1
            phase = "Finalizing output"
            status = "Linking and hiding the completed output Collection"
        elif self.phase == 'DONE':
            completed = self.work_total
            phase = "Complete"
            status = "Placement update complete"
        else:
            completed = int(self._published_progress * self.work_total)
            phase = "Cancelling"
            status = "Removing temporary objects"
        return completed, self.work_total, phase, status

    def step(self, budget_seconds=TIME_BUDGET_SECONDS):
        if self.finished:
            return True
        started = time.perf_counter()
        deadline = started + max(0.0001, budget_seconds)
        did_work = False

        while not self.finished and (not did_work or time.perf_counter() < deadline):
            did_work = True
            if self.phase == 'CREATE':
                if self.index < len(self.rows):
                    self._create_one(self.rows[self.index])
                    self.index += 1
                else:
                    self._prepare_commit()

            elif self.phase == 'CLEAR_OBJECTS':
                if self.index < len(self.old_objects):
                    end = min(self.index + REMOVE_BATCH_SIZE, len(self.old_objects))
                    batch = self.old_objects[self.index:end]
                    bpy.data.batch_remove(batch)
                    self.index = end
                else:
                    self.phase = 'CLEAR_COLLECTIONS'
                    self.index = 0

            elif self.phase == 'CLEAR_COLLECTIONS':
                if self.index < len(self.old_collections):
                    collection = self.old_collections[self.index]
                    if collection and collection.name in bpy.data.collections:
                        bpy.data.collections.remove(collection)
                    self.index += 1
                else:
                    self.phase = 'LINK'
                    self.index = 0

            elif self.phase == 'LINK':
                if self.index < len(self.stage_objects):
                    obj = self.stage_objects[self.index]
                    desired_name = self.stage_names[self.index]
                    if obj.name != desired_name:
                        obj.name = desired_name
                    self.output_collection.objects.link(obj)
                    self.index += 1
                else:
                    self.phase = 'FINALIZE'
                    self.index = 0

            elif self.phase == 'FINALIZE':
                set_managed_collection_visibility(self.scene, self.output_collection, False)
                if self.created_new_output:
                    self.scene.collection.children.link(self.output_collection)
                if self.visibility_guard is not None:
                    self.visibility_guard.restore()
                self.phase = 'DONE'
                self.finished = True

            elif self.phase == 'CANCEL_CLEANUP':
                if self.index >= 0:
                    start = max(0, self.index - (REMOVE_BATCH_SIZE - 1))
                    batch = self.stage_objects[start:self.index + 1]
                    bpy.data.batch_remove(batch)
                    self.index = start - 1
                else:
                    self.cancelled = True
                    self.finished = True

            else:
                self.finished = True

        elapsed = time.perf_counter() - started
        self.max_step_seconds = max(self.max_step_seconds, elapsed)
        return self.finished

    def finish_props(self):
        props = self.props
        duration = time.perf_counter() - self.started_at
        props.process_seconds = duration
        props.max_tick_ms = self.max_step_seconds * 1000.0
        props.eta_text = ""
        if self.cancelled:
            props.status = "Cancelled. The previous output was preserved."
            props.phase = "Cancelled"
            props.progress = 0.0
            return
        props.generated_count = self.created_count
        props.skipped_count = self.cache.invalid_count + self.missing_row_count
        props.linked_instance_count = self.created_count
        props.progress = 1.0
        props.phase = "Complete"
        props.status = (
            f"Complete: {self.created_count:,} created / {props.skipped_count:,} skipped / "
            f"{duration:.2f}s"
        )

    def cleanup_after_error(self):
        live_objects = [obj for obj in self.stage_objects if obj and obj.name in bpy.data.objects]
        if live_objects:
            bpy.data.batch_remove(live_objects)
        if self.visibility_guard is not None:
            self.visibility_guard.restore()
        if self.created_new_output and self.output_collection and self.output_collection.name in bpy.data.collections:
            bpy.data.collections.remove(self.output_collection)


class InPlaceUpdateTask(ProgressTaskMixin):
    """Fast transactional update for an output made entirely by this add-on."""

    def __init__(self, scene, cache, output_collection, resolved, missing_names, missing_row_count):
        self.scene = scene
        self.props = scene.csvmi_props
        self.cache = cache
        self.rows = sorted(cache.rows, key=lambda row: (row[ROW_NAME], row[ROW_LINE]))
        self.output_collection = output_collection
        self.resolved = resolved
        self.selected_attributes = selected_csv_attributes(self.props, cache)
        self.missing_names = missing_names
        self.missing_row_count = missing_row_count
        self.phase = 'UPDATE'
        self.index = 0
        self.existing_by_line = {}
        self.extra_existing = []
        for obj in output_collection.objects:
            line = int(obj.get("csvmi_csv_line", -1))
            if line in self.existing_by_line:
                self.extra_existing.append(obj)
            else:
                self.existing_by_line[line] = obj
        self.snapshots = []
        self.created_objects = []
        self.name_allocator = generated_name_allocator(self.output_collection)
        self.result_objects = []
        self.desired_names = []
        self.name_allocator = generated_name_allocator(output_collection)
        self.planned_names_by_line = {}
        expected_lines = set()
        predicted_rename_count = 0
        for row in self.rows:
            if self.resolved.get(row[ROW_NAME]) is None:
                continue
            line = row[ROW_LINE]
            desired_name = self.name_allocator.reserve(row[ROW_NAME])
            self.planned_names_by_line[line] = desired_name
            expected_lines.add(line)
            existing = self.existing_by_line.get(line)
            if existing is None or existing.name != desired_name:
                predicted_rename_count += 1
        predicted_leftover_count = len(self.extra_existing) + sum(
            1 for line in self.existing_by_line if line not in expected_lines
        )
        self.predicted_rename_count = predicted_rename_count
        self.predicted_leftover_count = predicted_leftover_count
        self.rename_objects = []
        self.rename_names = []
        self.leftovers = []
        self.finished = False
        self.cancelled = False
        self.commit_started = False
        self.started_at = time.perf_counter()
        self.max_step_seconds = 0.0
        self.created_count = 0
        self.work_total = len(self.rows) + predicted_leftover_count + 2 * predicted_rename_count + 1
        self.visibility_guard = TemporaryCollectionExclusion(scene, output_collection)
        self._init_progress_tracking()

    @staticmethod
    def _snapshot(obj):
        managed_names = managed_csv_property_names(obj)
        return (
            obj,
            obj.data,
            obj.location.copy(),
            obj.rotation_euler.copy(),
            obj.scale.copy(),
            obj.delta_location.copy(),
            obj.delta_rotation_euler.copy(),
            obj.delta_scale.copy(),
            bool(obj.get("csvmi_linked_mesh", False)),
            obj.get("csvmi_objname", ""),
            obj.get("csvmi_ptnum", ""),
            int(obj.get("csvmi_csv_line", -1)),
            obj.get("csvmi_source_object", ""),
            CSV_CUSTOM_KEYS_PROP in obj,
            obj.get(CSV_CUSTOM_KEYS_PROP, ""),
            {name: obj[name] for name in managed_names if name in obj},
        )

    def _apply(self, obj, row, source):
        obj.data = source.data
        apply_csv_transform(obj, row, self.props)
        obj["csvmi_generated"] = True
        obj["csvmi_linked_mesh"] = True
        obj["csvmi_objname"] = row[ROW_NAME]
        obj["csvmi_ptnum"] = row[ROW_PTNUM]
        obj["csvmi_csv_line"] = row[ROW_LINE]
        obj["csvmi_source_object"] = source.name
        apply_csv_custom_properties(obj, row, self.selected_attributes)

    @staticmethod
    def _restore(snapshot):
        (
            obj,
            mesh,
            location,
            rotation,
            scale,
            delta_location,
            delta_rotation,
            delta_scale,
            linked,
            objname,
            ptnum,
            line,
            source_name,
            custom_marker_exists,
            custom_marker,
            custom_values,
        ) = snapshot
        obj.data = mesh
        obj.location = location
        obj.rotation_mode = 'XYZ'
        obj.rotation_euler = rotation
        obj.scale = scale
        obj.delta_location = delta_location
        obj.delta_rotation_euler = delta_rotation
        obj.delta_scale = delta_scale
        obj["csvmi_generated"] = True
        obj["csvmi_linked_mesh"] = linked
        obj["csvmi_objname"] = objname
        obj["csvmi_ptnum"] = ptnum
        obj["csvmi_csv_line"] = line
        obj["csvmi_source_object"] = source_name
        for name in managed_csv_property_names(obj):
            if name in obj:
                del obj[name]
        if CSV_CUSTOM_KEYS_PROP in obj:
            del obj[CSV_CUSTOM_KEYS_PROP]
        for name, value in custom_values.items():
            obj[name] = value
        if custom_marker_exists:
            obj[CSV_CUSTOM_KEYS_PROP] = custom_marker

    def request_cancel(self):
        if self.commit_started:
            self.props.status = "The new placement is being committed and will finish safely."
            return
        if self.phase not in {'CANCEL_CREATED', 'CANCEL_RESTORE'}:
            self.phase = 'CANCEL_CREATED'
            self.index = len(self.created_objects) - 1
            self.props.status = "Cancelling: removing newly created objects"

    def _prepare_commit(self):
        self.commit_started = True
        self.leftovers = list(self.existing_by_line.values()) + self.extra_existing
        for obj, desired_name in zip(self.result_objects, self.desired_names):
            if obj.name != desired_name:
                self.rename_objects.append(obj)
                self.rename_names.append(desired_name)
        self.phase = 'DELETE_LEFTOVERS'
        self.index = 0

    def progress_snapshot(self):
        row_total = len(self.rows)
        leftover_total = len(self.leftovers) if self.commit_started else self.predicted_leftover_count
        if self.phase == 'UPDATE':
            completed = self.index
            phase = "Fast updating existing placements"
            status = f"Updating placements: {self.index:,} / {row_total:,}"
        elif self.phase == 'DELETE_LEFTOVERS':
            completed = row_total + self.index
            phase = "Removing obsolete objects"
            status = f"Removing obsolete objects: {self.index:,} / {len(self.leftovers):,}"
        elif self.phase in {'RENAME_TEMP', 'RENAME_FINAL'}:
            rename_offset = len(self.rename_objects) if self.phase == 'RENAME_FINAL' else 0
            completed = row_total + leftover_total + rename_offset + self.index
            phase = "Finalizing object names"
            status = f"Finalizing object names: {self.index:,} / {len(self.rename_objects):,}"
        elif self.phase == 'FINALIZE':
            completed = self.work_total - 1
            phase = "Finalizing output"
            status = "Hiding the completed output Collection"
        elif self.phase == 'DONE':
            completed = self.work_total
            phase = "Complete"
            status = "Placement update complete"
        else:
            completed = int(self._published_progress * self.work_total)
            phase = "Cancelling"
            status = "Restoring the previous output"
        return completed, self.work_total, phase, status

    def step(self, budget_seconds=TIME_BUDGET_SECONDS):
        if self.finished:
            return True
        started = time.perf_counter()
        deadline = started + max(0.0001, budget_seconds)
        did_work = False

        while not self.finished and (not did_work or time.perf_counter() < deadline):
            did_work = True
            if self.phase == 'UPDATE':
                if self.index < len(self.rows):
                    row = self.rows[self.index]
                    source = self.resolved.get(row[ROW_NAME])
                    if source is not None:
                        obj = self.existing_by_line.pop(row[ROW_LINE], None)
                        if obj is None:
                            obj = bpy.data.objects.new(f"__CSVMI_REUSE_NEW_{len(self.created_objects):08d}", source.data)
                            self.output_collection.objects.link(obj)
                            self.created_objects.append(obj)
                        else:
                            self.snapshots.append(self._snapshot(obj))
                        self._apply(obj, row, source)
                        self.result_objects.append(obj)
                        self.desired_names.append(self.planned_names_by_line[row[ROW_LINE]])
                    self.index += 1
                else:
                    self.created_count = len(self.result_objects)
                    self._prepare_commit()

            elif self.phase == 'DELETE_LEFTOVERS':
                if self.index < len(self.leftovers):
                    end = min(self.index + REMOVE_BATCH_SIZE, len(self.leftovers))
                    bpy.data.batch_remove(self.leftovers[self.index:end])
                    self.index = end
                else:
                    self.phase = 'RENAME_TEMP'
                    self.index = 0

            elif self.phase == 'RENAME_TEMP':
                if self.index < len(self.rename_objects):
                    self.rename_objects[self.index].name = f"__CSVMI_RENAME_{self.index:08d}"
                    self.index += 1
                else:
                    self.phase = 'RENAME_FINAL'
                    self.index = 0

            elif self.phase == 'RENAME_FINAL':
                if self.index < len(self.rename_objects):
                    self.rename_objects[self.index].name = self.rename_names[self.index]
                    self.index += 1
                else:
                    self.phase = 'FINALIZE'
                    self.index = 0

            elif self.phase == 'FINALIZE':
                set_managed_collection_visibility(self.scene, self.output_collection, False)
                self.visibility_guard.restore()
                self.finished = True
                self.phase = 'DONE'

            elif self.phase == 'CANCEL_CREATED':
                if self.index >= 0:
                    start = max(0, self.index - (REMOVE_BATCH_SIZE - 1))
                    bpy.data.batch_remove(self.created_objects[start:self.index + 1])
                    self.index = start - 1
                else:
                    self.phase = 'CANCEL_RESTORE'
                    self.index = len(self.snapshots) - 1

            elif self.phase == 'CANCEL_RESTORE':
                if self.index >= 0:
                    self._restore(self.snapshots[self.index])
                    self.index -= 1
                else:
                    self.visibility_guard.restore()
                    self.cancelled = True
                    self.finished = True

            else:
                self.finished = True

        elapsed = time.perf_counter() - started
        self.max_step_seconds = max(self.max_step_seconds, elapsed)
        return self.finished

    def finish_props(self):
        props = self.props
        duration = time.perf_counter() - self.started_at
        props.process_seconds = duration
        props.max_tick_ms = self.max_step_seconds * 1000.0
        props.eta_text = ""
        if self.cancelled:
            props.status = "Cancelled and restored the previous placements."
            props.phase = "Cancelled"
            props.progress = 0.0
            return
        props.generated_count = self.created_count
        props.skipped_count = self.cache.invalid_count + self.missing_row_count
        props.linked_instance_count = self.created_count
        props.progress = 1.0
        props.phase = "Complete"
        props.status = (
            f"Fast update complete: {self.created_count:,} objects / {props.skipped_count:,} skipped / "
            f"{duration:.2f}s"
        )

    def cleanup_after_error(self):
        live_created = [obj for obj in self.created_objects if obj and obj.name in bpy.data.objects]
        if live_created:
            bpy.data.batch_remove(live_created)
        for snapshot in reversed(self.snapshots):
            obj = snapshot[0]
            if obj and obj.name in bpy.data.objects:
                self._restore(snapshot)
        self.visibility_guard.restore()


def create_update_task(scene, cache, output_collection, resolved, missing_names, missing_row_count):
    can_reuse = (
        output_collection is not None
        and len(output_collection.children) == 0
        and len(output_collection.objects) > 0
        and all(bool(obj.get("csvmi_generated", False)) for obj in output_collection.objects)
    )
    task_type = InPlaceUpdateTask if can_reuse else UpdateTask
    return task_type(
        scene,
        cache,
        output_collection,
        resolved,
        missing_names,
        missing_row_count,
    )


def _safe_collection_token(value):
    token = re.sub(r"[^0-9A-Za-z_.-]+", "_", str(value)).strip("_.")
    return (token or "Empty")[:48]


def find_v2_child(root, marker_key, marker_value=True):
    for child in root.children:
        if child.get(marker_key) == marker_value:
            return child
    return None


def ensure_deleted_collection(root):
    collection = find_v2_child(root, DELETED_COLLECTION_KEY, True)
    if collection is None:
        collection = bpy.data.collections.new(DELETED_COLLECTION_NAME)
        collection[DELETED_COLLECTION_KEY] = True
        root.children.link(collection)
    collection.hide_viewport = True
    collection.hide_render = True
    return collection


def ensure_zone_collection(root, attribute, value):
    value = "" if value is None else str(value)
    for child in root.children:
        if bool(child.get(ZONE_COLLECTION_KEY, False)) and child.get(ZONE_VALUE_KEY, "") == value:
            return child
    base_name = f"{_safe_collection_token(attribute)}_{_safe_collection_token(value)}"
    collection = bpy.data.collections.new(base_name)
    collection[ZONE_COLLECTION_KEY] = True
    collection[ZONE_VALUE_KEY] = value
    root.children.link(collection)
    return collection


def move_object_exclusively(obj, target, managed_root):
    if target not in obj.users_collection:
        target.objects.link(obj)
    managed_collections = {collection.as_pointer() for collection in iter_collection_tree(managed_root)}
    for collection in list(obj.users_collection):
        if collection != target and collection.as_pointer() in managed_collections:
            collection.objects.unlink(obj)


def target_collection_for_row(root, props, cache, row):
    if not props.split_by_attribute or row is None:
        return root
    try:
        index = cache.extra_columns.index(props.split_attribute)
    except ValueError:
        return root
    return ensure_zone_collection(root, props.split_attribute, row[ROW_EXTRA][index])


def set_v2_object_metadata(obj, cache, row, source=None, linked=True):
    identity = row[ROW_ID]
    obj[OBJECT_ID_KEY] = identity
    obj[cache.identity_column] = identity
    for legacy_key in ("csvmi_ptnum", "csvmi_csv_line"):
        if legacy_key in obj:
            del obj[legacy_key]


class V2ApplyTask(ProgressTaskMixin):
    """Apply reviewed v2 changes transactionally and swap persistent state last."""

    def __init__(self, scene, preview):
        self.scene = scene
        self.props = scene.csvmi_props
        self.preview = preview
        self.cache = preview.cache
        self.output_collection = preview.output
        self.created_new_output = self.output_collection is None
        if self.created_new_output:
            self.output_collection = bpy.data.collections.new(self.props.output_collection_name.strip())
            self.output_collection[OUTPUT_MANAGED_KEY] = True
            self.output_collection[OUTPUT_SCHEMA_KEY] = OUTPUT_SCHEMA_VERSION
            # Link an empty, already hidden Collection, then exclude it before
            # population. Linking a completed 60k-Object Collection forces one
            # huge depsgraph rebuild; exclusion keeps both creation and finalize
            # responsive without paying that cost.
            self.output_collection.hide_viewport = True
            self.output_collection.hide_render = True
            self.scene.collection.children.link(self.output_collection)
        self.name_allocator = generated_name_allocator(self.output_collection)
        self.new_state = copy.deepcopy(preview.state)
        self.new_state["schema"] = OUTPUT_SCHEMA_VERSION
        self.new_state["id_column"] = self.cache.identity_column
        self.new_state.setdefault("records", {})
        self.phase = 'APPLY'
        self.index = 0
        self.snapshots = []
        self.snapshot_pointers = set()
        self.created_objects = []
        self.replaced_tombstones = []
        self.profile_enabled = os.environ.get("CSVMI_PROFILE") == "1"
        self.profile_times = {}
        self.cancelled = False
        self.finished = False
        self.started_at = time.perf_counter()
        self.max_step_seconds = 0.0
        self.max_step_phase = ""
        self.max_item_seconds = 0.0
        self.state_record_total = len(
            set(self.cache.rows_by_id) | set(self.new_state.get("records", {}))
        )
        self.work_total = max(1, len(preview.changes) + self.state_record_total + 1)
        self.state_writer = None
        self.visibility_guard = TemporaryCollectionExclusion(scene, self.output_collection)
        self._init_progress_tracking()

    def _snapshot(self, obj):
        pointer = obj.as_pointer()
        if pointer in self.snapshot_pointers:
            return
        self.snapshot_pointers.add(pointer)
        self.snapshots.append(
            (
                obj,
                obj.name,
                obj.data,
                obj.location.copy(),
                obj.rotation_euler.copy(),
                obj.scale.copy(),
                obj.delta_location.copy(),
                obj.delta_rotation_euler.copy(),
                obj.delta_scale.copy(),
                tuple(obj.users_collection),
                bool(obj.hide_viewport),
                bool(obj.hide_render),
                {key: copy.deepcopy(obj[key]) for key in obj.keys()},
            )
        )

    def _restore_snapshot(self, snapshot):
        (
            obj, name, mesh, location, rotation, scale, delta_location, delta_rotation,
            delta_scale, collections, hide_viewport, hide_render, custom_properties,
        ) = snapshot
        if obj is None or obj.name not in bpy.data.objects:
            return
        obj.name = name
        obj.data = mesh
        obj.location = location
        obj.rotation_mode = 'XYZ'
        obj.rotation_euler = rotation
        obj.scale = scale
        obj.delta_location = delta_location
        obj.delta_rotation_euler = delta_rotation
        obj.delta_scale = delta_scale
        obj.hide_viewport = hide_viewport
        obj.hide_render = hide_render
        for collection in list(obj.users_collection):
            collection.objects.unlink(obj)
        for collection in collections:
            if collection and collection.name in bpy.data.collections:
                collection.objects.link(obj)
        for key in list(obj.keys()):
            del obj[key]
        for key, value in custom_properties.items():
            obj[key] = value

    def _new_object(self, row, source):
        name = self.name_allocator.reserve(row[ROW_NAME])
        obj = bpy.data.objects.new(name, source.data if source is not None else None)
        self.created_objects.append(obj)
        return obj

    def _replace_tombstone(self, identity, tombstone, row, source):
        """Replace an Empty with a Mesh Object while keeping rollback possible."""
        self._snapshot(tombstone)
        original_name = tombstone.name
        for collection in list(tombstone.users_collection):
            collection.objects.unlink(tombstone)
        tombstone.name = f"__CSVMI_DELETED_{identity}"
        obj = self._new_object(row, source)
        obj.name = original_name
        self.replaced_tombstones.append(tombstone)
        return obj

    def _apply_selected_properties(self, obj, row):
        selected = selected_csv_attributes(self.props, self.cache)
        apply_csv_custom_properties(obj, row, selected)

    def _make_tombstone(self, identity, obj, record, row=None):
        if obj is None:
            name = record.get("objname", identity)
            obj = bpy.data.objects.new(name, None)
            self.created_objects.append(obj)
            transform = record.get("transform_override") or record.get("csv_transform")
            if transform:
                obj.location = transform[:3]
                obj.rotation_mode = 'XYZ'
                obj.rotation_euler = transform[3:6]
                obj.scale = transform[6:9]
        else:
            # Blender Object types cannot be reliably changed from MESH back to
            # EMPTY by assigning data=None. Replace it transactionally instead.
            old_obj = obj
            self._snapshot(old_obj)
            original_name = old_obj.name
            transform = (
                old_obj.location.copy(), old_obj.rotation_euler.copy(), old_obj.scale.copy(),
                old_obj.delta_location.copy(), old_obj.delta_rotation_euler.copy(),
                old_obj.delta_scale.copy(),
            )
            for collection in list(old_obj.users_collection):
                collection.objects.unlink(old_obj)
            old_obj.name = f"__CSVMI_REPLACED_{identity}"
            obj = bpy.data.objects.new(original_name, None)
            self.created_objects.append(obj)
            self.replaced_tombstones.append(old_obj)
            (
                obj.location, obj.rotation_euler, obj.scale,
                obj.delta_location, obj.delta_rotation_euler, obj.delta_scale,
            ) = transform
        deleted = ensure_deleted_collection(self.output_collection)
        move_object_exclusively(obj, deleted, self.output_collection)
        obj.empty_display_type = 'PLAIN_AXES'
        obj.hide_viewport = True
        obj.hide_render = True
        obj[OBJECT_ID_KEY] = identity
        obj[self.cache.identity_column] = identity
        record["deleted"] = True
        record["skipped"] = False
        return obj

    def _fresh_record(self, row, source):
        selected_props = v2_engine.selected_row_properties(
            self.cache, row, self.preview.selected_names
        )
        source_mesh = source.data.name if source is not None else ""
        return v2_engine.state_record_from_row(self.cache, row, source_mesh, selected_props)

    def _apply_change(self, change):
        if change["filtered"]:
            return
        identity = change["identity"]
        row = change["row"]
        source = change["source"]
        obj = change["obj"]
        records = self.new_state["records"]
        old_record = records.get(identity)

        if change["object_kind"] == "NEW":
            profile_start = time.perf_counter() if self.profile_enabled else 0.0
            record = self._fresh_record(row, source)
            if self.profile_enabled:
                now = time.perf_counter()
                self.profile_times["record"] = self.profile_times.get("record", 0.0) + now - profile_start
                profile_start = now
            if change["object_decision"] == "CREATE" and source is not None:
                obj = self._new_object(row, source)
                if self.profile_enabled:
                    now = time.perf_counter()
                    self.profile_times["object_new"] = self.profile_times.get("object_new", 0.0) + now - profile_start
                    profile_start = now
                apply_csv_transform(obj, row, self.props)
                if self.profile_enabled:
                    now = time.perf_counter()
                    self.profile_times["transform"] = self.profile_times.get("transform", 0.0) + now - profile_start
                    profile_start = now
                set_v2_object_metadata(obj, self.cache, row, source, True)
                if self.profile_enabled:
                    now = time.perf_counter()
                    self.profile_times["metadata"] = self.profile_times.get("metadata", 0.0) + now - profile_start
                    profile_start = now
                self._apply_selected_properties(obj, row)
                if self.profile_enabled:
                    now = time.perf_counter()
                    self.profile_times["properties"] = self.profile_times.get("properties", 0.0) + now - profile_start
                    profile_start = now
                target = target_collection_for_row(
                    self.output_collection, self.props, self.cache, row
                )
                target.objects.link(obj)
                record["object_name"] = obj.name
                if self.profile_enabled:
                    now = time.perf_counter()
                    self.profile_times["link"] = self.profile_times.get("link", 0.0) + now - profile_start
            else:
                record["skipped"] = True
            records[identity] = record
            return

        if change["object_kind"] == "CSV_DELETED":
            record = copy.deepcopy(old_record)
            if change["object_decision"] == "MOVE_DELETED":
                obj = self._make_tombstone(identity, obj, record)
                record["object_name"] = obj.name
            else:
                record["csv_missing_override"] = True
            records[identity] = record
            return

        if change["object_kind"] == "BLENDER_DELETED":
            record = copy.deepcopy(old_record)
            if change["object_decision"] == "RESTORE" and source is not None:
                obj = self._new_object(row, source)
                target_collection_for_row(
                    self.output_collection, self.props, self.cache, row
                ).objects.link(obj)
                apply_csv_transform(obj, row, self.props)
                set_v2_object_metadata(obj, self.cache, row, source, True)
                self._apply_selected_properties(obj, row)
                record = self._fresh_record(row, source)
                record["object_name"] = obj.name
            else:
                obj = self._make_tombstone(identity, None, record, row)
                record["object_name"] = obj.name
            records[identity] = record
            return

        if change["object_kind"] == "DELETED":
            record = copy.deepcopy(old_record)
            if change["object_decision"] == "RESTORE" and source is not None:
                if obj is None:
                    obj = self._new_object(row, source)
                else:
                    obj = self._replace_tombstone(identity, obj, row, source)
                obj.hide_viewport = False
                obj.hide_render = False
                move_object_exclusively(
                    obj,
                    target_collection_for_row(self.output_collection, self.props, self.cache, row),
                    self.output_collection,
                )
                apply_csv_transform(obj, row, self.props)
                set_v2_object_metadata(obj, self.cache, row, source, True)
                self._apply_selected_properties(obj, row)
                record = self._fresh_record(row, source)
                record["object_name"] = obj.name
            records[identity] = record
            return

        if obj is None or row is None:
            return
        self._snapshot(obj)
        record = copy.deepcopy(old_record)
        current_transform = list(v2_engine.object_transform(obj))
        current_mesh = obj.data.name if obj.type == 'MESH' and obj.data else ""
        current_props = v2_engine.current_object_properties(
            obj,
            set(record.get("csv_props", {})) | set(change["selected_props"]),
        )

        if change["transform_kind"]:
            record["csv_transform"] = list(v2_engine.row_transform(row))
            if change["transform_decision"] == "APPLY":
                apply_csv_transform(obj, row, self.props)
                record["transform_override"] = None
            else:
                record["transform_override"] = current_transform

        if change["mesh_kind"]:
            record["objname"] = row[ROW_NAME]
            record["source_mesh"] = change["new_source_mesh"]
            if change["mesh_decision"] == "RELINK" and source is not None:
                obj.data = source.data
                record["mesh_override"] = None
            else:
                record["mesh_override"] = current_mesh

        if change["props_kind"]:
            record["csv_props"] = dict(change["selected_props"])
            if change["props_decision"] == "APPLY":
                self._apply_selected_properties(obj, row)
                record["props_override"] = None
            else:
                record["props_override"] = current_props

        record["attrs"] = dict(change["attributes"])
        record["objname"] = row[ROW_NAME]
        record["deleted"] = False
        record["skipped"] = False
        record["object_name"] = obj.name
        set_v2_object_metadata(
            obj,
            self.cache,
            row,
            source,
            record.get("mesh_override") is None,
        )
        target = target_collection_for_row(self.output_collection, self.props, self.cache, row)
        move_object_exclusively(obj, target, self.output_collection)
        records[identity] = record

    def request_cancel(self):
        if self.phase in {'APPLY', 'STATE_ENCODE'}:
            self.phase = 'ROLLBACK'
            self.index = len(self.snapshots) - 1
            self.props.status = "Cancelling: restoring the previous v2 output"

    def progress_snapshot(self):
        if self.phase == 'APPLY':
            return (
                self.index,
                self.work_total,
                "Applying reviewed changes",
                f"Applying changes: {self.index:,} / {len(self.preview.changes):,}",
            )
        if self.phase == 'STATE_ENCODE':
            encoded = self.state_writer.index if self.state_writer is not None else 0
            return (
                len(self.preview.changes) + encoded,
                self.work_total,
                "Saving v2 state",
                f"Encoding stable IDs: {encoded:,} / {self.state_record_total:,}",
            )
        if self.phase == 'STATE_COMMIT':
            return self.work_total - 1, self.work_total, "Saving v2 state", "Committing the stable ID registry"
        if self.phase == 'DONE':
            return self.work_total, self.work_total, "Complete", "Reviewed changes applied"
        return 0, self.work_total, "Cancelling", "Restoring the previous output"

    def step(self, budget_seconds=TIME_BUDGET_SECONDS):
        if self.finished:
            return True
        started = time.perf_counter()
        started_phase = self.phase
        deadline = started + max(0.0001, budget_seconds)
        did_work = False
        while not self.finished and (not did_work or time.perf_counter() < deadline):
            did_work = True
            if self.phase == 'APPLY':
                if self.index < len(self.preview.changes):
                    item_started = time.perf_counter()
                    self._apply_change(self.preview.changes[self.index])
                    self.max_item_seconds = max(
                        self.max_item_seconds, time.perf_counter() - item_started
                    )
                    self.index += 1
                else:
                    self.state_writer = v2_engine.StateTextWriter(
                        self.output_collection, self.new_state
                    )
                    self.phase = 'STATE_ENCODE'
                    self.index = 0
            elif self.phase == 'STATE_ENCODE':
                remaining_budget = max(0.0001, deadline - time.perf_counter())
                if self.state_writer.step(remaining_budget):
                    self.phase = 'STATE_COMMIT'
            elif self.phase == 'STATE_COMMIT':
                finalize_started = time.perf_counter() if self.profile_enabled else 0.0
                live_replaced = [
                    obj for obj in self.replaced_tombstones
                    if obj and obj.name in bpy.data.objects
                ]
                if live_replaced:
                    bpy.data.batch_remove(live_replaced)
                if self.profile_enabled:
                    now = time.perf_counter()
                    self.profile_times["final_remove"] = now - finalize_started
                    finalize_started = now
                self.state_writer.commit()
                if self.profile_enabled:
                    now = time.perf_counter()
                    self.profile_times["state_commit"] = now - finalize_started
                    finalize_started = now
                set_managed_collection_visibility(self.scene, self.output_collection, False)
                if self.profile_enabled:
                    self.profile_times["final_visibility"] = time.perf_counter() - finalize_started
                # Keep the successful output excluded/hidden. The managed
                # output Show button explicitly re-enables its View Layer.
                self.phase = 'DONE'
                self.finished = True
            elif self.phase == 'ROLLBACK':
                if self.index >= 0:
                    self._restore_snapshot(self.snapshots[self.index])
                    self.index -= 1
                else:
                    live_created = [
                        obj for obj in self.created_objects if obj and obj.name in bpy.data.objects
                    ]
                    if live_created:
                        bpy.data.batch_remove(live_created)
                    # Replacement Objects may temporarily own the original name.
                    # Restore snapshots once more after removing them so Blender
                    # can give each tombstone its exact pre-cancel name back.
                    for snapshot in self.snapshots:
                        self._restore_snapshot(snapshot)
                    if self.created_new_output and self.output_collection.name in bpy.data.collections:
                        remove_collection_with_contents(self.output_collection)
                    if self.visibility_guard is not None:
                        self.visibility_guard.restore()
                    self.cancelled = True
                    self.finished = True
            else:
                self.finished = True
        elapsed = time.perf_counter() - started
        if elapsed > self.max_step_seconds:
            self.max_step_seconds = elapsed
            self.max_step_phase = started_phase
        return self.finished

    def finish_props(self):
        duration = time.perf_counter() - self.started_at
        self.props.process_seconds = duration
        self.props.max_tick_ms = self.max_step_seconds * 1000.0
        self.props.eta_text = ""
        if self.cancelled:
            self.props.phase = "Cancelled"
            self.props.status = "Cancelled and restored the previous v2 output."
            self.props.progress = 0.0
            return
        records = self.new_state.get("records", {})
        live_records = [
            record for record in records.values()
            if not record.get("deleted", False) and not record.get("skipped", False)
        ]
        self.props.generated_count = len(live_records)
        self.props.linked_instance_count = sum(
            1 for record in live_records if record.get("mesh_override") is None
        )
        self.props.phase = "Complete"
        self.props.status = f"Applied reviewed changes in {duration:.2f}s"
        self.props.progress = 1.0
        if self.profile_enabled:
            print("[CSVMI PROFILE] " + " ".join(
                f"{name}={seconds:.3f}s" for name, seconds in sorted(self.profile_times.items())
            ), flush=True)
        clear_preview_cache(self.scene)

    def cleanup_after_error(self):
        for snapshot in reversed(self.snapshots):
            self._restore_snapshot(snapshot)
        live_created = [obj for obj in self.created_objects if obj and obj.name in bpy.data.objects]
        if live_created:
            bpy.data.batch_remove(live_created)
        if self.created_new_output and self.output_collection.name in bpy.data.collections:
            remove_collection_with_contents(self.output_collection)
        if self.visibility_guard is not None:
            self.visibility_guard.restore()


class RealizeTask(ProgressTaskMixin):
    def __init__(self, scene, objects):
        self.scene = scene
        self.props = scene.csvmi_props
        self.objects = objects
        self.index = 0
        self.changes = []
        self.phase = 'REALIZE'
        self.cancelled = False
        self.finished = False
        self.started_at = time.perf_counter()
        self.max_step_seconds = 0.0
        self.work_total = max(1, len(objects))
        output = bpy.data.collections.get(scene.csvmi_props.output_collection_name.strip())
        self.visibility_guard = TemporaryCollectionExclusion(scene, output) if output else None
        self._init_progress_tracking()

    def request_cancel(self):
        if self.phase == 'REALIZE':
            self.phase = 'ROLLBACK'
            self.index = len(self.changes) - 1
            self.props.status = "Cancelling: restoring shared Mesh data"

    def progress_snapshot(self):
        if self.phase == 'REALIZE':
            return (
                self.index,
                self.work_total,
                "Making Mesh data single-user",
                f"Making Mesh data single-user: {self.index:,} / {len(self.objects):,}",
            )
        restored = len(self.changes) - max(0, self.index + 1)
        return (
            max(self._last_published_units, restored),
            self.work_total,
            "Cancelling",
            "Restoring shared Mesh data",
        )

    def step(self, budget_seconds=TIME_BUDGET_SECONDS):
        if self.finished:
            return True
        started = time.perf_counter()
        deadline = started + max(0.0001, budget_seconds)
        did_work = False

        while not self.finished and (not did_work or time.perf_counter() < deadline):
            did_work = True
            if self.phase == 'REALIZE':
                if self.index < len(self.objects):
                    obj = self.objects[self.index]
                    old_mesh = obj.data
                    new_mesh = old_mesh.copy()
                    obj.data = new_mesh
                    obj["csvmi_linked_mesh"] = False
                    self.changes.append((obj, old_mesh, new_mesh))
                    self.index += 1
                else:
                    self.finished = True
            elif self.phase == 'ROLLBACK':
                if self.index >= 0:
                    obj, old_mesh, new_mesh = self.changes[self.index]
                    if obj and obj.name in bpy.data.objects:
                        obj.data = old_mesh
                        obj["csvmi_linked_mesh"] = True
                    if new_mesh and new_mesh.users == 0:
                        bpy.data.meshes.remove(new_mesh)
                    self.index -= 1
                else:
                    self.cancelled = True
                    self.finished = True

        elapsed = time.perf_counter() - started
        self.max_step_seconds = max(self.max_step_seconds, elapsed)
        return self.finished

    def finish_props(self):
        if self.visibility_guard is not None:
            self.visibility_guard.restore()
        props = self.props
        duration = time.perf_counter() - self.started_at
        props.process_seconds = duration
        props.max_tick_ms = self.max_step_seconds * 1000.0
        props.eta_text = ""
        if self.cancelled:
            props.status = "Cancelled and restored shared Mesh data."
            props.phase = "Cancelled"
            props.progress = 0.0
        else:
            clear_preview_cache(self.scene)
            props.linked_instance_count = 0
            props.status = f"Single-user conversion complete: {len(self.objects):,} objects / {duration:.2f}s"
            props.phase = "Complete"
            props.progress = 1.0

    def cleanup_after_error(self):
        for obj, old_mesh, new_mesh in reversed(self.changes):
            if obj and obj.name in bpy.data.objects:
                obj.data = old_mesh
                obj["csvmi_linked_mesh"] = True
            if new_mesh and new_mesh.users == 0:
                bpy.data.meshes.remove(new_mesh)
        if self.visibility_guard is not None:
            self.visibility_guard.restore()


class CollectionCleanupTask(ProgressTaskMixin):
    """Fast, non-undo cleanup for Collections owned by this add-on."""

    cancellable = False

    def __init__(self, scene, collection, delete_root, split_across_ticks):
        self.scene = scene
        self.props = scene.csvmi_props
        self.collection = collection
        self.collection_name = collection.name
        try:
            self.state_identity_column = v2_engine.read_output_state(collection).get("id_column", "id")
        except ValueError:
            self.state_identity_column = "id"
        self.delete_root = delete_root
        self.objects = collect_collection_objects(collection)
        self.child_collections = collect_child_collections_postorder(collection)
        self.parent_links = collect_collection_parent_links(collection)
        self.phase = 'DETACH'
        self.index = 0
        self.finished = False
        self.cancelled = False
        self.started_at = time.perf_counter()
        self.max_step_seconds = 0.0
        self.batch_size = REMOVE_BATCH_SIZE if split_across_ticks else max(1, len(self.objects))
        self.single_batch = not split_across_ticks
        self.work_total = len(self.objects) + len(self.child_collections) + (1 if delete_root else 0) + 2
        self.detached = False
        self._init_progress_tracking()

    def request_cancel(self):
        self.props.status = "Deletion cannot be cancelled after confirmation."

    def progress_snapshot(self):
        object_total = len(self.objects)
        child_total = len(self.child_collections)
        if self.phase == 'DETACH':
            completed = 0
            phase = "Preparing fast deletion"
            status = "Temporarily detaching the managed Collection from the Scene"
        elif self.phase == 'REMOVE_OBJECTS':
            completed = 1 + self.index
            phase = "Deleting generated objects"
            status = f"Deleting objects: {self.index:,} / {object_total:,}"
        elif self.phase == 'REMOVE_CHILDREN':
            completed = 1 + object_total + self.index
            phase = "Deleting child Collections"
            status = f"Deleting child Collections: {self.index:,} / {child_total:,}"
        elif self.phase == 'DELETE_ROOT':
            completed = 1 + object_total + child_total
            phase = "Deleting output Collection"
            status = f"Deleting Collection: {self.collection_name}"
        elif self.phase == 'DONE':
            completed = self.work_total
            phase = "Complete"
            status = "Collection deletion complete" if self.delete_root else "Collection contents cleared"
        else:
            completed = self.work_total - 1
            phase = "Finalizing"
            status = "Finalizing Collection cleanup"
        return completed, self.work_total, phase, status

    def _remove_ids(self, ids, budget_seconds, force_single_batch=False):
        if self.index >= len(ids):
            return
        if self.single_batch or force_single_batch:
            end = len(ids)
        else:
            end = min(len(ids), self.index + self.batch_size)
        batch = ids[self.index:end]
        started = time.perf_counter()
        if batch:
            bpy.data.batch_remove(batch)
        elapsed = max(0.000001, time.perf_counter() - started)
        self.index = end
        if not self.single_batch and not force_single_batch:
            target = max(0.001, budget_seconds * 0.7)
            adjusted = int(self.batch_size * target / elapsed)
            adjusted = max(MIN_REMOVE_BATCH_SIZE, min(MAX_REMOVE_BATCH_SIZE, adjusted))
            self.batch_size = max(
                MIN_REMOVE_BATCH_SIZE,
                min(MAX_REMOVE_BATCH_SIZE, (self.batch_size + adjusted) // 2),
            )

    def step(self, budget_seconds=TIME_BUDGET_SECONDS):
        if self.finished:
            return True
        started = time.perf_counter()
        deadline = started + max(0.0001, budget_seconds)
        did_work = False

        while not self.finished and (not did_work or time.perf_counter() < deadline):
            did_work = True
            if self.phase == 'DETACH':
                v2_engine.remove_output_state(self.collection)
                for parent in self.parent_links:
                    if self.collection in parent.children[:]:
                        parent.children.unlink(self.collection)
                self.detached = True
                self.phase = 'REMOVE_OBJECTS'
                self.index = 0
            elif self.phase == 'REMOVE_OBJECTS':
                if self.index < len(self.objects):
                    # Splitting Object ID removal makes Blender rescan all remaining IDs for every
                    # batch and is dramatically slower (60k: seconds vs. over a minute). Keep this
                    # one operation atomic after detaching the Collection from the Scene.
                    self._remove_ids(self.objects, budget_seconds, force_single_batch=True)
                else:
                    self.phase = 'REMOVE_CHILDREN'
                    self.index = 0
            elif self.phase == 'REMOVE_CHILDREN':
                if self.index < len(self.child_collections):
                    self._remove_ids(self.child_collections, budget_seconds)
                else:
                    self.phase = 'DELETE_ROOT' if self.delete_root else 'FINALIZE'
                    self.index = 0
            elif self.phase == 'DELETE_ROOT':
                if self.collection and self.collection.name in bpy.data.collections:
                    bpy.data.batch_remove([self.collection])
                self.phase = 'FINALIZE'
            elif self.phase == 'FINALIZE':
                if not self.delete_root and self.collection and self.collection.name in bpy.data.collections:
                    self.collection[OUTPUT_MANAGED_KEY] = True
                    self.collection[OUTPUT_SCHEMA_KEY] = OUTPUT_SCHEMA_VERSION
                    v2_engine.write_output_state(
                        self.collection,
                        {
                            "schema": OUTPUT_SCHEMA_VERSION,
                            "id_column": self.state_identity_column,
                            "records": {},
                        },
                    )
                    for parent in self.parent_links:
                        if self.collection not in parent.children[:]:
                            parent.children.link(self.collection)
                self.detached = False
                self.phase = 'DONE'
                self.finished = True

        elapsed = time.perf_counter() - started
        self.max_step_seconds = max(self.max_step_seconds, elapsed)
        return self.finished

    def finish_props(self):
        props = self.props
        duration = time.perf_counter() - self.started_at
        if props.output_collection_name.strip() == self.collection_name:
            reset_output_stats(props)
        props.process_seconds = duration
        props.max_tick_ms = self.max_step_seconds * 1000.0
        props.managed_collection_index = min(
            props.managed_collection_index,
            max(0, len(bpy.data.collections) - 1),
        )
        props.progress = 1.0
        props.eta_text = ""
        props.phase = "Complete"
        action = "Deleted Collection" if self.delete_root else "Cleared Collection"
        props.status = (
            f"{action} {self.collection_name}: {len(self.objects):,} objects / "
            f"{len(self.child_collections):,} child Collections / {duration:.2f}s"
        )
        clear_preview_cache(self.scene)

    def cleanup_after_error(self):
        # Deletion is intentionally non-transactional after the confirmation dialog.
        if (
            self.detached
            and not self.delete_root
            and self.collection
            and self.collection.name in bpy.data.collections
        ):
            for parent in self.parent_links:
                if self.collection not in parent.children[:]:
                    parent.children.link(self.collection)
            self.detached = False


class CSVMI_AddonPreferences(AddonPreferences):
    bl_idname = __package__ or "csv_mesh_instancer"

    def draw(self, context):
        layout = self.layout
        layout.label(text="CSV Mesh Instancer Documentation")
        operator = layout.operator("wm.url_open", text="Open User Guide", icon='URL')
        operator.url = DOCUMENTATION_URL


def invalidate_preview_setting(_self, context):
    if context is not None and context.scene is not None and hasattr(context.scene, "csvmi_props"):
        if not context.scene.csvmi_props.running:
            clear_preview_cache(context.scene)


def filter_attribute_items(_self, context):
    if context is None or context.scene is None:
        return [("", "No CSV", "Import a CSV first")]
    cache = get_csv_cache(context.scene)
    if cache is None or not cache.extra_columns:
        return [("", "No Attributes", "The loaded CSV has no filter attributes")]
    return [(name, name, f"Filter by exact {name} values") for name in cache.extra_columns]


def sync_filter_rule_values(rule, cache):
    previous = {item.value: item.selected for item in rule.values}
    rule.values.clear()
    values = cache.attribute_values.get(rule.attribute, ())
    for value, count in values[:FILTER_VALUE_LIMIT]:
        item = rule.values.add()
        item.value = value
        item.count = count
        item.selected = previous.get(value, True)


def filter_attribute_changed(self, context):
    if context is None or context.scene is None:
        return
    cache = get_csv_cache(context.scene)
    if cache is not None:
        sync_filter_rule_values(self, cache)
    invalidate_preview_setting(self, context)


def _refresh_review_timer(scene_pointer, token):
    if _SEARCH_DEBOUNCE_TOKENS.get(scene_pointer) != token:
        return None
    scene = next((item for item in bpy.data.scenes if item.as_pointer() == scene_pointer), None)
    if scene is not None and hasattr(scene, "csvmi_props"):
        refresh_review_page(scene)
    return None


def schedule_review_refresh(_self, context):
    if context is None or context.scene is None:
        return
    scene = context.scene
    if bpy.app.background:
        refresh_review_page(scene)
        return
    pointer = scene.as_pointer()
    token = time.time_ns()
    _SEARCH_DEBOUNCE_TOKENS[pointer] = token
    bpy.app.timers.register(
        lambda: _refresh_review_timer(pointer, token),
        first_interval=0.25,
    )


class CSVMI_CSVAttribute(PropertyGroup):
    name: StringProperty(name="Attribute")
    enabled: BoolProperty(
        name="Write to Objects",
        default=False,
        description="Write this CSV column to each generated Object as a Custom Property",
        update=invalidate_preview_setting,
    )
    data_type: StringProperty(name="Detected Type", default="Empty")
    reserved: BoolProperty(default=False)


class CSVMI_FilterValue(PropertyGroup):
    value: StringProperty()
    selected: BoolProperty(default=True, update=invalidate_preview_setting)
    count: IntProperty(default=0, min=0)


class CSVMI_FilterRule(PropertyGroup):
    enabled: BoolProperty(default=True, update=invalidate_preview_setting)
    attribute: EnumProperty(items=filter_attribute_items, update=filter_attribute_changed)
    values: CollectionProperty(type=CSVMI_FilterValue)
    value_index: IntProperty(default=0, min=0)
    manual_values: StringProperty(
        name="Additional Exact Values",
        description="Comma-separated exact values, useful for high-cardinality attributes",
        update=invalidate_preview_setting,
    )


class CSVMI_PreviewRow(PropertyGroup):
    change_index: IntProperty(default=-1)
    status: StringProperty()
    identity: StringProperty()
    zone: StringProperty()
    objname: StringProperty()
    transform_label: StringProperty()
    mesh_label: StringProperty()
    props_label: StringProperty()
    decision_label: StringProperty()


def sync_csv_attributes(props, data):
    previous = {item.name: item.enabled for item in props.csv_attributes}
    props.csv_attributes.clear()
    for name, data_type in zip(data.extra_columns, data.extra_types):
        item = props.csv_attributes.add()
        item.name = name
        item.data_type = data_type
        item.reserved = name.casefold().startswith(RESERVED_CUSTOM_PREFIX)
        item.enabled = False if item.reserved else previous.get(name, True)
    props.csv_attribute_index = min(
        props.csv_attribute_index,
        max(0, len(props.csv_attributes) - 1),
    )


class CSVMI_Props(PropertyGroup):
    csv_path: StringProperty(
        name="CSV File", subtype='FILE_PATH', default="", update=invalidate_preview_setting
    )
    identity_column: StringProperty(
        name="Identity Column",
        default="id",
        description="Required globally unique, persistent CSV identity attribute",
        update=invalidate_preview_setting,
    )
    source_mode: EnumProperty(
        name="Source Mode",
        items=[
            ('COLLECTION', "Collection", "Use a Collection already in this Blender file"),
            ('FBX', "FBX", "Import and use an external FBX file"),
        ],
        default='COLLECTION',
        update=invalidate_preview_setting,
    )
    source_collection: PointerProperty(
        name="Mesh Collection",
        type=bpy.types.Collection,
        update=_property_update_source_collection,
    )
    fbx_path: StringProperty(name="FBX File", subtype='FILE_PATH', default="")
    fbx_collection_name: StringProperty(name="Managed Collection", default="CSVMI_FBX_Source")
    fbx_managed_collection: PointerProperty(type=bpy.types.Collection)
    apply_fbx_correction: BoolProperty(
        name="Apply FBX Unit / Axis Correction",
        default=True,
        description="Keep CSV transforms unchanged and correct the linked FBX mesh with Delta Transform",
        update=invalidate_preview_setting,
    )
    fbx_unit_scale: FloatProperty(
        name="Unit Scale",
        default=0.01,
        min=0.000001,
        soft_max=1.0,
        precision=4,
        description="Uniform Delta Scale applied to placements that use an FBX source",
        update=invalidate_preview_setting,
    )
    fbx_rotation_x: FloatProperty(
        name="Local X Rotation",
        default=math.radians(90.0),
        subtype='ANGLE',
        unit='ROTATION',
        description="Local X rotation applied after each CSV rotation, like pressing R, X, X in Blender",
        update=invalidate_preview_setting,
    )
    output_collection_name: StringProperty(
        name="Collection Name", default="CSV_Output", update=invalidate_preview_setting
    )
    ignore_numeric_suffix: BoolProperty(
        name="Ignore .001 Numeric Suffixes", default=False, update=invalidate_preview_setting
    )
    split_by_attribute: BoolProperty(
        name="Split by Attribute",
        default=False,
        description="Create one managed child Collection per attribute value",
        update=invalidate_preview_setting,
    )
    split_attribute: StringProperty(
        name="Split Attribute",
        default="Zone",
        update=invalidate_preview_setting,
    )
    use_multi_tick: BoolProperty(
        name="Split Across Multiple Ticks",
        default=True,
        description="Split large object operations into short time slices to keep Blender responsive",
    )

    show_csv: BoolProperty(default=True)
    show_attributes: BoolProperty(default=True)
    show_source: BoolProperty(default=True)
    show_rules: BoolProperty(default=True)
    show_filters: BoolProperty(default=True)
    show_preview: BoolProperty(default=True)
    show_advanced: BoolProperty(default=False)
    show_matching: BoolProperty(default=True)
    show_output: BoolProperty(default=True)
    show_managed_outputs: BoolProperty(default=True)
    show_status: BoolProperty(default=True)
    managed_collection_index: IntProperty(default=0, min=0)
    csv_attributes: CollectionProperty(type=CSVMI_CSVAttribute)
    csv_attribute_index: IntProperty(default=0, min=0)
    attribute_filters: CollectionProperty(type=CSVMI_FilterRule)
    attribute_filter_index: IntProperty(default=0, min=0)
    review_rows: CollectionProperty(type=CSVMI_PreviewRow)
    review_row_index: IntProperty(default=0, min=0)
    review_search: StringProperty(name="Search", update=schedule_review_refresh)
    review_status_filter: EnumProperty(
        name="Status",
        items=[
            ('ALL', "All Statuses", ""),
            ('NEW', "New", ""),
            ('CSV_CHANGED', "CSV Changed", ""),
            ('BLENDER_EDITED', "Blender Edited", ""),
            ('CONFLICT', "Conflict", ""),
            ('MESH_CHANGED', "Mesh Changed", ""),
            ('CSV_DELETED', "CSV Deleted", ""),
            ('BLENDER_DELETED', "Blender Deleted", ""),
            ('DELETED', "Deleted", ""),
            ('FILTERED_OUT', "Filtered Out", ""),
            ('MISSING_SOURCE', "Missing Source", ""),
        ],
        default='ALL',
        update=schedule_review_refresh,
    )
    review_zone_filter: StringProperty(name="Zone", update=schedule_review_refresh)
    review_change_filter: EnumProperty(
        name="Change Type",
        items=[
            ('ALL', "All Changes", ""),
            ('TRANSFORM', "Transform", ""),
            ('MESH', "Mesh", ""),
            ('PROPS', "Custom Properties", ""),
            ('OBJECT', "Create / Delete", ""),
        ],
        default='ALL',
        update=schedule_review_refresh,
    )
    review_page: IntProperty(default=0, min=0)
    review_total_pages: IntProperty(default=0, min=0)
    preview_valid: BoolProperty(default=False)

    csv_row_count: IntProperty(default=0)
    csv_valid_count: IntProperty(default=0)
    csv_unique_name_count: IntProperty(default=0)
    csv_error_count: IntProperty(default=0)
    source_mesh_count: IntProperty(default=0)
    fbx_total_count: IntProperty(default=0)
    fbx_mesh_count: IntProperty(default=0)
    fbx_unapplied_transform_count: IntProperty(default=0)
    collision_group_count: IntProperty(default=0)
    generated_count: IntProperty(default=0)
    skipped_count: IntProperty(default=0)
    missing_name_count: IntProperty(default=0)
    missing_row_count: IntProperty(default=0)
    linked_instance_count: IntProperty(default=0)
    missing_name_preview: StringProperty(default="")
    csv_error_preview: StringProperty(default="")
    status: StringProperty(default="Ready")
    phase: StringProperty(default="Idle")
    eta_text: StringProperty(default="")
    progress: FloatProperty(default=0.0, min=0.0, max=1.0)
    process_seconds: FloatProperty(default=0.0)
    max_tick_ms: FloatProperty(default=0.0)
    ui_publish_count: IntProperty(default=0)
    preview_change_count: IntProperty(default=0)
    preview_new_count: IntProperty(default=0)
    preview_csv_changed_count: IntProperty(default=0)
    preview_blender_edited_count: IntProperty(default=0)
    preview_conflict_count: IntProperty(default=0)
    preview_mesh_changed_count: IntProperty(default=0)
    preview_csv_deleted_count: IntProperty(default=0)
    preview_blender_deleted_count: IntProperty(default=0)
    preview_filtered_count: IntProperty(default=0)
    running: BoolProperty(default=False)
    cancel_requested: BoolProperty(default=False)
    active_operation: EnumProperty(
        items=[
            ('NONE', "None", ""),
            ('FBX_IMPORT', "FBX Import", ""),
            ('UPDATE', "Update", ""),
            ('PREVIEW', "Preview", ""),
            ('APPLY', "Apply", ""),
            ('REALIZE', "Realize", ""),
            ('CLEAR_OUTPUT', "Clear Output", ""),
            ('DELETE_OUTPUT', "Delete Output", ""),
        ],
        default='NONE',
    )


class CSVMI_OT_import_csv(Operator):
    bl_idname = "csvmi.import_csv"
    bl_label = "Import CSV"
    bl_description = "Validate the CSV and cache only valid placement rows"

    def execute(self, context):
        props = context.scene.csvmi_props
        if props.running:
            self.report({'ERROR'}, "An operation is already running.")
            return {'CANCELLED'}
        try:
            data = load_csv_data(props.csv_path, props.identity_column)
        except Exception as exc:
            props.status = str(exc)
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        set_csv_cache(context.scene, data)
        clear_preview_cache(context.scene)
        sync_csv_attributes(props, data)
        for rule in props.attribute_filters:
            if rule.attribute in data.extra_columns:
                sync_filter_rule_values(rule, data)
        props.csv_row_count = data.raw_count
        props.csv_valid_count = len(data.rows)
        props.csv_unique_name_count = len(data.unique_names)
        props.csv_error_count = data.invalid_count
        props.csv_error_preview = " / ".join(data.error_samples)
        props.status = (
            f"CSV loaded: {len(data.rows):,} valid rows / "
            f"{len(data.unique_names):,} object names / ID: {data.identity_column} / "
            f"{len(data.extra_columns):,} extra attributes / "
            f"{data.invalid_count:,} errors"
        )
        props.phase = "CSV loaded"
        self.report({'INFO'}, props.status)
        return {'FINISHED'}


def review_change_matches(change, props):
    query = props.review_search.strip().casefold()
    if query and query not in change["search_blob"]:
        return False
    if props.review_status_filter != 'ALL' and change["status"] != props.review_status_filter:
        return False
    zone_filter = props.review_zone_filter.strip().casefold()
    if zone_filter and zone_filter not in change["zone"].casefold():
        return False
    change_filter = props.review_change_filter
    if change_filter == 'TRANSFORM' and not change["transform_kind"]:
        return False
    if change_filter == 'MESH' and not change["mesh_kind"]:
        return False
    if change_filter == 'PROPS' and not (change["props_kind"] or change["attribute_changed"]):
        return False
    if change_filter == 'OBJECT' and not change["object_kind"]:
        return False
    return True


def review_decision_label(change):
    if change["object_decision"] != 'NONE':
        return change["object_decision"].replace('_', ' ').title()
    labels = []
    if change["transform_decision"] != 'NONE':
        labels.append("T:" + change["transform_decision"].title())
    if change["mesh_decision"] != 'NONE':
        labels.append("M:" + change["mesh_decision"].title())
    if change["props_decision"] != 'NONE':
        labels.append("P:" + change["props_decision"].title())
    return " ".join(labels) or "Metadata"


def refresh_review_page(scene):
    if not hasattr(scene, "csvmi_props"):
        return
    props = scene.csvmi_props
    preview = get_preview_cache(scene)
    props.review_rows.clear()
    if preview is None:
        props.review_total_pages = 0
        props.preview_valid = False
        return
    indices = [
        index for index, change in enumerate(preview.changes)
        if review_change_matches(change, props)
    ]
    preview.filtered_indices = indices
    total_pages = max(1, math.ceil(len(indices) / REVIEW_PAGE_SIZE)) if indices else 0
    props.review_total_pages = total_pages
    props.review_page = min(props.review_page, max(0, total_pages - 1))
    start = props.review_page * REVIEW_PAGE_SIZE
    for change_index in indices[start:start + REVIEW_PAGE_SIZE]:
        change = preview.changes[change_index]
        item = props.review_rows.add()
        item.change_index = change_index
        item.status = v2_engine.STATUS_LABELS.get(change["status"], change["status"])
        item.identity = change["identity"]
        item.zone = change["zone"]
        item.objname = change["objname"]
        item.transform_label = change["transform_kind"].title() if change["transform_kind"] else "—"
        item.mesh_label = change["mesh_kind"].title() if change["mesh_kind"] else "—"
        item.props_label = (
            str(len(change["changed_properties"]))
            if change["changed_properties"] else "—"
        )
        item.decision_label = review_decision_label(change)
    props.review_row_index = min(props.review_row_index, max(0, len(props.review_rows) - 1))


def _set_preview_summary(props, preview):
    summary = preview.summary
    props.preview_change_count = len(preview.changes)
    props.preview_new_count = summary.get("NEW", 0)
    props.preview_csv_changed_count = summary.get("CSV_CHANGED", 0)
    props.preview_blender_edited_count = summary.get("BLENDER_EDITED", 0)
    props.preview_conflict_count = summary.get("CONFLICT", 0)
    props.preview_mesh_changed_count = summary.get("MESH_CHANGED", 0)
    props.preview_csv_deleted_count = summary.get("CSV_DELETED", 0)
    props.preview_blender_deleted_count = summary.get("BLENDER_DELETED", 0)
    props.preview_filtered_count = summary.get("FILTERED_OUT", 0)


class CSVMI_OT_add_filter(Operator):
    bl_idname = "csvmi.add_filter"
    bl_label = "Add Attribute Filter"

    def execute(self, context):
        props = context.scene.csvmi_props
        cache = get_csv_cache(context.scene)
        if cache is None or not cache.extra_columns:
            self.report({'ERROR'}, "Import a CSV with additional attributes first.")
            return {'CANCELLED'}
        rule = props.attribute_filters.add()
        preferred = props.split_attribute if props.split_attribute in cache.extra_columns else cache.extra_columns[0]
        rule.attribute = preferred
        rule.enabled = True
        sync_filter_rule_values(rule, cache)
        props.attribute_filter_index = len(props.attribute_filters) - 1
        clear_preview_cache(context.scene)
        return {'FINISHED'}


class CSVMI_OT_remove_filter(Operator):
    bl_idname = "csvmi.remove_filter"
    bl_label = "Remove Attribute Filter"

    def execute(self, context):
        props = context.scene.csvmi_props
        if not props.attribute_filters:
            return {'CANCELLED'}
        index = min(props.attribute_filter_index, len(props.attribute_filters) - 1)
        props.attribute_filters.remove(index)
        props.attribute_filter_index = min(index, max(0, len(props.attribute_filters) - 1))
        clear_preview_cache(context.scene)
        return {'FINISHED'}


class CSVMI_OT_preview_changes(Operator):
    bl_idname = "csvmi.preview_changes"
    bl_label = "Preview Changes"
    bl_description = "Analyze stable-ID changes without modifying the Scene"

    def execute(self, context):
        scene = context.scene
        props = scene.csvmi_props
        if props.running:
            return {'CANCELLED'}
        cache = get_csv_cache(scene)
        if cache is None:
            self.report({'ERROR'}, "Import a valid CSV first.")
            return {'CANCELLED'}
        if csv_file_changed(scene):
            self.report({'ERROR'}, "The CSV file changed. Re-import it before Preview.")
            return {'CANCELLED'}
        if props.split_by_attribute and props.split_attribute not in cache.extra_columns:
            self.report({'ERROR'}, f"Split attribute not found: {props.split_attribute}")
            return {'CANCELLED'}
        started = time.perf_counter()
        try:
            _, output, resolved, _missing_names, _missing_rows = validate_source_and_output(scene, cache)
            validate_done = time.perf_counter()
            selected_names = tuple(
                item.name for item in props.csv_attributes if item.enabled and not item.reserved
            )
            preview = v2_engine.build_preview(cache, output, resolved, props, selected_names)
            build_done = time.perf_counter()
        except Exception as exc:
            clear_preview_cache(scene)
            props.phase = "Preview error"
            props.status = str(exc)
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        _PREVIEW_CACHE[_scene_key(scene)] = preview
        props.preview_valid = True
        props.review_page = 0
        _set_preview_summary(props, preview)
        refresh_review_page(scene)
        ui_done = time.perf_counter()
        duration = time.perf_counter() - started
        if os.environ.get("CSVMI_PROFILE") == "1":
            print(
                f"[CSVMI PREVIEW OP PROFILE] validate={validate_done - started:.3f}s "
                f"build={build_done - validate_done:.3f}s ui={ui_done - build_done:.3f}s",
                flush=True,
            )
        props.process_seconds = duration
        props.phase = "Preview ready"
        props.status = f"Preview: {len(preview.changes):,} changed IDs / {duration:.2f}s"
        self.report({'INFO'}, props.status)
        return {'FINISHED'}


class CSVMI_OT_review_page(Operator):
    bl_idname = "csvmi.review_page"
    bl_label = "Change Review Page"

    delta: IntProperty(default=0, options={'HIDDEN', 'SKIP_SAVE'})

    def execute(self, context):
        props = context.scene.csvmi_props
        props.review_page = max(
            0,
            min(max(0, props.review_total_pages - 1), props.review_page + self.delta),
        )
        refresh_review_page(context.scene)
        return {'FINISHED'}


class CSVMI_OT_set_change_decision(Operator):
    bl_idname = "csvmi.set_change_decision"
    bl_label = "Set Change Decision"

    change_index: IntProperty(default=-1, options={'HIDDEN', 'SKIP_SAVE'})
    domain: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})
    decision: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def execute(self, context):
        preview = get_preview_cache(context.scene)
        if preview is None or not (0 <= self.change_index < len(preview.changes)):
            return {'CANCELLED'}
        change = preview.changes[self.change_index]
        property_name = f"{self.domain}_decision"
        if property_name not in change:
            return {'CANCELLED'}
        change[property_name] = self.decision
        refresh_review_page(context.scene)
        return {'FINISHED'}


class CSVMI_OT_bulk_decision(Operator):
    bl_idname = "csvmi.bulk_decision"
    bl_label = "Set Filtered Decisions"

    mode: EnumProperty(
        items=[
            ('APPLY', "Apply CSV to Filtered", ""),
            ('KEEP', "Keep Blender for Filtered", ""),
            ('RELINK', "Relink Unedited Meshes", ""),
            ('KEEP_CONFLICTS', "Keep All Conflicts", ""),
        ],
        default='APPLY',
        options={'HIDDEN', 'SKIP_SAVE'},
    )

    def execute(self, context):
        preview = get_preview_cache(context.scene)
        if preview is None:
            return {'CANCELLED'}
        for index in preview.filtered_indices:
            change = preview.changes[index]
            if change["filtered"]:
                continue
            if self.mode == 'APPLY':
                if change["transform_kind"]:
                    change["transform_decision"] = 'APPLY'
                if change["props_kind"]:
                    change["props_decision"] = 'APPLY'
                if change["mesh_kind"] and change["source"] is not None:
                    change["mesh_decision"] = 'RELINK'
            elif self.mode == 'KEEP':
                if change["transform_kind"]:
                    change["transform_decision"] = 'KEEP'
                if change["props_kind"]:
                    change["props_decision"] = 'KEEP'
                if change["mesh_kind"]:
                    change["mesh_decision"] = 'KEEP'
            elif self.mode == 'RELINK':
                if change["mesh_kind"] == 'CSV' and change["source"] is not None:
                    change["mesh_decision"] = 'RELINK'
            elif self.mode == 'KEEP_CONFLICTS':
                if change["transform_kind"] == 'CONFLICT':
                    change["transform_decision"] = 'KEEP'
                if change["mesh_kind"] == 'CONFLICT':
                    change["mesh_decision"] = 'KEEP'
                if change["props_kind"] == 'CONFLICT':
                    change["props_decision"] = 'KEEP'
        refresh_review_page(context.scene)
        return {'FINISHED'}


class CSVMI_OT_focus_change(Operator):
    bl_idname = "csvmi.focus_change"
    bl_label = "Focus Change"
    bl_description = "Show and frame this changed Object or its last recorded location"

    change_index: IntProperty(default=-1, options={'HIDDEN', 'SKIP_SAVE'})

    def execute(self, context):
        preview = get_preview_cache(context.scene)
        if preview is None or not (0 <= self.change_index < len(preview.changes)):
            return {'CANCELLED'}
        change = preview.changes[self.change_index]
        obj = change["obj"]
        if obj is not None and obj.name in bpy.data.objects:
            if preview.output is not None:
                set_managed_collection_visibility(context.scene, preview.output, True)
            for collection in obj.users_collection:
                collection.hide_viewport = False
            obj.hide_viewport = False
            obj.hide_set(False)
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj
            try:
                if context.area and context.area.type == 'VIEW_3D':
                    window_region = next(r for r in context.area.regions if r.type == 'WINDOW')
                    with context.temp_override(region=window_region):
                        bpy.ops.view3d.view_selected(use_all_regions=False)
            except (StopIteration, RuntimeError):
                pass
        else:
            transform = None
            if change["row"] is not None:
                transform = v2_engine.row_transform(change["row"])
            elif change["old"]:
                transform = change["old"].get("transform_override") or change["old"].get("csv_transform")
            if transform and context.space_data and hasattr(context.space_data, "region_3d"):
                context.space_data.region_3d.view_location = transform[:3]
        return {'FINISHED'}


def _cleanup_new_import_data(new_objects, new_collections, temp_collection):
    for obj in list(new_objects):
        if obj and obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    for collection in list(new_collections):
        if collection == temp_collection:
            continue
        if collection and collection.name in bpy.data.collections:
            bpy.data.collections.remove(collection)
    if temp_collection and temp_collection.name in bpy.data.collections:
        bpy.data.collections.remove(temp_collection)


def _has_unapplied_transform(obj, tolerance=1.0e-5):
    if any(abs(value) > tolerance for value in obj.location):
        return True
    if any(abs(value) > tolerance for value in obj.rotation_euler):
        return True
    return any(abs(value - 1.0) > tolerance for value in obj.scale)


class CSVMI_OT_import_fbx(Operator):
    bl_idname = "csvmi.import_fbx"
    bl_label = "Import FBX"
    bl_description = "Import FBX into a temporary Collection and replace the old source only after validation"

    _timer = None
    _path = ""
    _desired_name = ""
    _old_managed = None

    def execute(self, context):
        scene = context.scene
        props = scene.csvmi_props
        if props.running:
            self.report({'ERROR'}, "An operation is already running.")
            return {'CANCELLED'}

        path = absolute_path(props.fbx_path)
        desired_name = props.fbx_collection_name.strip()
        if not path or not os.path.isfile(path):
            self.report({'ERROR'}, "FBX file not found.")
            return {'CANCELLED'}
        if not desired_name:
            self.report({'ERROR'}, "Enter a managed Collection name.")
            return {'CANCELLED'}

        old_managed = props.fbx_managed_collection
        existing = bpy.data.collections.get(desired_name)
        if existing is not None and existing != old_managed:
            self.report({'ERROR'}, f"{desired_name} is an existing regular Collection. Choose another name.")
            return {'CANCELLED'}
        if old_managed is not None and not bool(old_managed.get(FBX_MANAGED_KEY, False)):
            self.report({'ERROR'}, "The current FBX Collection is missing its management marker.")
            return {'CANCELLED'}

        self._path = path
        self._desired_name = desired_name
        self._old_managed = old_managed
        _set_running(props, 'FBX_IMPORT', "Preparing FBX import")
        props.phase = "FBX import"
        tag_view3d_redraw(context)

        if bpy.app.background or context.window is None:
            try:
                return self._import_fbx(context)
            finally:
                _set_idle(props)

        self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _import_fbx(self, context):
        scene = context.scene
        props = scene.csvmi_props
        path = self._path
        desired_name = self._desired_name
        old_managed = self._old_managed

        before_objects = {obj.as_pointer() for obj in bpy.data.objects}
        before_collections = {collection.as_pointer() for collection in bpy.data.collections}
        temp_collection = bpy.data.collections.new("__CSVMI_FBX_IMPORT__")
        scene.collection.children.link(temp_collection)
        new_objects = []
        new_collections = []

        try:
            result = bpy.ops.wm.fbx_import(
                filepath=path,
                use_anim=False,
                validate_meshes=True,
            )
            if 'FINISHED' not in result:
                raise RuntimeError("Blender did not complete the FBX import.")

            new_objects = [obj for obj in bpy.data.objects if obj.as_pointer() not in before_objects]
            new_collections = [
                collection
                for collection in bpy.data.collections
                if collection.as_pointer() not in before_collections and collection != temp_collection
            ]
            if props.cancel_requested:
                raise InterruptedError("FBX import cancelled.")
            mesh_objects = [obj for obj in new_objects if obj.type == 'MESH']
            if not mesh_objects:
                raise RuntimeError("The FBX contains no Mesh objects.")

            for obj in new_objects:
                if temp_collection not in obj.users_collection:
                    temp_collection.objects.link(obj)
                for collection in list(obj.users_collection):
                    if collection != temp_collection:
                        collection.objects.unlink(obj)
                obj[FBX_MANAGED_KEY] = True

            for collection in reversed(new_collections):
                if collection.name in bpy.data.collections:
                    bpy.data.collections.remove(collection)

            unapplied = sum(1 for obj in mesh_objects if _has_unapplied_transform(obj))
            if old_managed is not None:
                remove_collection_with_contents(old_managed)

            temp_collection.name = desired_name
            temp_collection[FBX_MANAGED_KEY] = True
            temp_collection[FBX_PATH_KEY] = path
            visibility_mode = isolate_fbx_source_collection(scene, temp_collection)
            props.fbx_managed_collection = temp_collection
            props.fbx_total_count = len(new_objects)
            props.fbx_mesh_count = len(mesh_objects)
            props.fbx_unapplied_transform_count = unapplied
            props.source_mesh_count = len(mesh_objects)
            clear_preview_cache(scene)
            props.status = f"FBX imported: {len(mesh_objects):,} Mesh / {len(new_objects):,} total objects"
            if visibility_mode == 'VIEW_LAYER_EXCLUDE':
                props.status += " / source excluded from View Layers"
            else:
                props.status += " / source Collection hidden"
            if unapplied:
                props.status += f" / {unapplied:,} unapplied transforms"
            props.phase = "FBX loaded"
            self.report({'WARNING'} if unapplied else {'INFO'}, props.status)
            return {'FINISHED'}
        except InterruptedError:
            _cleanup_new_import_data(new_objects, new_collections, temp_collection)
            props.status = "FBX import cancelled. The previous source was preserved."
            props.phase = "Cancelled"
            self.report({'INFO'}, props.status)
            return {'CANCELLED'}
        except Exception as exc:
            traceback.print_exc()
            _cleanup_new_import_data(new_objects, new_collections, temp_collection)
            props.status = f"FBX import failed: {exc}"
            self.report({'ERROR'}, props.status)
            return {'CANCELLED'}

    def _finish_modal(self, context):
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        _set_idle(context.scene.csvmi_props)
        tag_view3d_redraw(context)

    def modal(self, context, event):
        props = context.scene.csvmi_props
        if event.type == 'ESC':
            props.cancel_requested = True
        if props.cancel_requested:
            props.status = "FBX import cancelled before the Blender import step."
            props.phase = "Cancelled"
            self._finish_modal(context)
            return {'CANCELLED'}
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        props.status = "Importing FBX. Cancellation is applied after Blender finishes this step."
        tag_view3d_redraw(context)
        try:
            return self._import_fbx(context)
        finally:
            self._finish_modal(context)

    def cancel(self, context):
        context.scene.csvmi_props.cancel_requested = True


class _ModalTaskOperator:
    _timer = None
    _task = None

    def _modal_time_budget(self):
        if getattr(self._task, "work_total", 0) >= LARGE_TASK_WORK_THRESHOLD:
            return LARGE_TASK_TIME_BUDGET_SECONDS
        return TIME_BUDGET_SECONDS

    def _start_modal_or_sync(self, context):
        props = context.scene.csvmi_props
        if props.use_multi_tick and context.window is not None:
            context.window_manager.progress_begin(0, 1000)
            self._task.publish_progress(force=True)
            context.window_manager.progress_update(int(props.progress * 1000))
            tag_view3d_redraw(context)
            self._timer = context.window_manager.event_timer_add(TIMER_INTERVAL_SECONDS, window=context.window)
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}

        try:
            self._task.publish_progress(force=True)
            while not self._task.step(3600.0):
                pass
            self._task.finish_props()
            props.ui_publish_count = self._task.ui_publish_count
            _set_idle(props)
            return {'CANCELLED'} if self._task.cancelled else {'FINISHED'}
        except Exception as exc:
            self._handle_error(context, exc)
            return {'CANCELLED'}

    def modal(self, context, event):
        if event.type == 'ESC' and self._task.cancellable:
            context.scene.csvmi_props.cancel_requested = True
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        props = context.scene.csvmi_props
        if props.cancel_requested and self._task.cancellable:
            self._task.request_cancel()

        try:
            finished = self._task.step(self._modal_time_budget())
        except Exception as exc:
            self._handle_error(context, exc)
            return {'CANCELLED'}

        if self._task.publish_progress(force=finished):
            context.window_manager.progress_update(int(props.progress * 1000))
            tag_view3d_redraw(context)
        if not finished:
            return {'RUNNING_MODAL'}

        self._task.finish_props()
        context.window_manager.progress_update(int(props.progress * 1000))
        cancelled = self._task.cancelled
        self._finish_modal(context)
        return {'CANCELLED'} if cancelled else {'FINISHED'}

    def _finish_modal(self, context):
        props = context.scene.csvmi_props
        if self._task is not None:
            props.ui_publish_count = self._task.ui_publish_count
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        context.window_manager.progress_end()
        _set_idle(props)
        tag_view3d_redraw(context)

    def _handle_error(self, context, exc):
        traceback.print_exc()
        props = context.scene.csvmi_props
        if hasattr(self._task, "cleanup_after_error"):
            self._task.cleanup_after_error()
        props.status = f"Operation failed: {exc}"
        props.phase = "Error"
        props.eta_text = ""
        if self._timer is not None:
            self._finish_modal(context)
        else:
            _set_idle(props)
        self.report({'ERROR'}, props.status)

    def cancel(self, context):
        if self._task is not None and self._task.cancellable:
            self._task.request_cancel()


class CSVMI_OT_apply_reviewed(_ModalTaskOperator, Operator):
    bl_idname = "csvmi.apply_reviewed"
    bl_label = "Apply Reviewed Changes"
    bl_description = "Apply the current per-domain decisions and save v2 stable-ID state"

    def execute(self, context):
        scene = context.scene
        props = scene.csvmi_props
        preview = get_preview_cache(scene)
        if preview is None or not props.preview_valid:
            self.report({'ERROR'}, "Run Preview Changes first.")
            return {'CANCELLED'}
        if csv_file_changed(scene):
            clear_preview_cache(scene)
            self.report({'ERROR'}, "The CSV changed. Re-import and Preview again.")
            return {'CANCELLED'}
        for change in preview.changes:
            if v2_engine.object_preview_signature(change["obj"]) != change["object_signature"]:
                clear_preview_cache(scene)
                self.report({'ERROR'}, "The Scene changed after Preview. Run Preview Changes again.")
                return {'CANCELLED'}
        try:
            self._task = V2ApplyTask(scene, preview)
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        _set_running(props, 'APPLY', "Applying reviewed stable-ID changes")
        return self._start_modal_or_sync(context)


class CSVMI_OT_update(_ModalTaskOperator, Operator):
    bl_idname = "csvmi.update"
    bl_label = "Update"
    bl_description = "Rebuild the output from the loaded CSV and current Mesh source"

    def execute(self, context):
        scene = context.scene
        props = scene.csvmi_props
        if props.running:
            self.report({'ERROR'}, "An operation is already running.")
            return {'CANCELLED'}
        cache = get_csv_cache(scene)
        if cache is None:
            self.report({'ERROR'}, "Import a CSV first.")
            return {'CANCELLED'}

        try:
            props.status = "Validating CSV and source"
            _, output_collection, resolved, missing_names, missing_row_count = validate_source_and_output(scene, cache)
            self._task = create_update_task(
                scene,
                cache,
                output_collection,
                resolved,
                missing_names,
                missing_row_count,
            )
        except Exception as exc:
            props.status = str(exc)
            props.phase = "Validation error"
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        _set_running(props, 'UPDATE', "Creating placements")
        return self._start_modal_or_sync(context)


class CSVMI_OT_realize(_ModalTaskOperator, Operator):
    bl_idname = "csvmi.realize"
    bl_label = "Make Meshes Single-User"
    bl_description = "Copy the shared Mesh datablock for every generated object"
    _confirm_count = 0

    @classmethod
    def poll(cls, context):
        return not context.scene.csvmi_props.running

    def _linked_objects(self, scene):
        output = bpy.data.collections.get(scene.csvmi_props.output_collection_name.strip())
        if output is None:
            return []
        return [
            obj
            for obj in collect_collection_objects(output, mesh_only=True)
            if bool(obj.get("csvmi_generated", False)) and bool(obj.get("csvmi_linked_mesh", False))
        ]

    def invoke(self, context, event):
        objects = self._linked_objects(context.scene)
        if not objects:
            self.report({'ERROR'}, "No generated objects currently use linked Mesh data.")
            return {'CANCELLED'}
        self._confirm_count = len(objects)
        return context.window_manager.invoke_props_dialog(self, width=430)

    def draw(self, context):
        layout = self.layout
        layout.label(text=f"Make Mesh data single-user for {self._confirm_count:,} objects?", icon='ERROR')
        layout.label(text="This can greatly increase Mesh datablocks and memory usage.")

    def execute(self, context):
        scene = context.scene
        props = scene.csvmi_props
        if props.running:
            self.report({'ERROR'}, "An operation is already running.")
            return {'CANCELLED'}
        objects = self._linked_objects(scene)
        if not objects:
            self.report({'ERROR'}, "No generated objects currently use linked Mesh data.")
            return {'CANCELLED'}
        self._task = RealizeTask(scene, objects)
        _set_running(props, 'REALIZE', "Making Mesh data single-user")
        return self._start_modal_or_sync(context)


def require_managed_output(collection_name):
    collection = bpy.data.collections.get(collection_name)
    if collection is None:
        raise ValueError(f"Collection not found: {collection_name}")
    if not bool(collection.get(OUTPUT_MANAGED_KEY, False)):
        raise ValueError("The Collection is not managed by CSV Mesh Instancer.")
    return collection


class CSVMI_OT_set_output_visibility(Operator):
    bl_idname = "csvmi.set_output_visibility"
    bl_label = "Show or Hide Output"
    bl_description = "Show or hide this managed output in both the viewport and render"

    collection_name: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})
    show: BoolProperty(options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return not context.scene.csvmi_props.running

    def execute(self, context):
        try:
            collection = require_managed_output(self.collection_name)
        except ValueError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        set_managed_collection_visibility(context.scene, collection, self.show)
        state = "Shown" if self.show else "Hidden"
        context.scene.csvmi_props.status = f"{state}: {collection.name} (Viewport and Render)"
        tag_view3d_redraw(context)
        return {'FINISHED'}


class _CollectionCleanupOperator(_ModalTaskOperator):
    delete_root = False
    _confirm_object_count = 0
    _confirm_child_count = 0

    @classmethod
    def poll(cls, context):
        return not context.scene.csvmi_props.running

    def _resolve(self):
        return require_managed_output(self.collection_name)

    def invoke(self, context, event):
        try:
            collection = self._resolve()
        except ValueError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self._confirm_object_count = len(collect_collection_objects(collection))
        self._confirm_child_count = len(collect_child_collections_postorder(collection))
        return context.window_manager.invoke_props_dialog(self, width=470)

    def draw(self, context):
        layout = self.layout
        action = "Delete Collection" if self.delete_root else "Clear Contents"
        layout.label(text=f"{action}: {self.collection_name}?", icon='ERROR')
        layout.label(text=f"Objects: {self._confirm_object_count:,}")
        layout.label(text=f"Child Collections: {self._confirm_child_count:,}")
        layout.separator()
        layout.label(text="This operation is not undoable and cannot be cancelled after it starts.")

    def execute(self, context):
        props = context.scene.csvmi_props
        if props.running:
            self.report({'ERROR'}, "An operation is already running.")
            return {'CANCELLED'}
        try:
            collection = self._resolve()
            self._task = CollectionCleanupTask(
                context.scene,
                collection,
                self.delete_root,
                props.use_multi_tick,
            )
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        operation = 'DELETE_OUTPUT' if self.delete_root else 'CLEAR_OUTPUT'
        status = "Deleting managed Collection" if self.delete_root else "Clearing managed Collection contents"
        _set_running(props, operation, status)
        return self._start_modal_or_sync(context)


class CSVMI_OT_clear_output(_CollectionCleanupOperator, Operator):
    bl_idname = "csvmi.clear_output"
    bl_label = "Clear Contents"
    bl_description = "Quickly delete all objects and child Collections while preserving the managed Collection"
    delete_root = False

    collection_name: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})


class CSVMI_OT_delete_output(_CollectionCleanupOperator, Operator):
    bl_idname = "csvmi.delete_output"
    bl_label = "Delete Collection"
    bl_description = "Quickly delete all contents and the managed Collection itself"
    delete_root = True

    collection_name: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})


class CSVMI_OT_cancel(Operator):
    bl_idname = "csvmi.cancel"
    bl_label = "Cancel Operation"
    bl_description = "Begin a safe cancellation after the current tick finishes"

    def execute(self, context):
        props = context.scene.csvmi_props
        if not props.running:
            return {'CANCELLED'}
        if props.active_operation in {'CLEAR_OUTPUT', 'DELETE_OUTPUT'}:
            self.report({'WARNING'}, "Fast deletion cannot be cancelled after confirmation.")
            return {'CANCELLED'}
        props.cancel_requested = True
        props.status = "Cancellation requested. The current tick will finish first."
        return {'FINISHED'}


class CSVMI_UL_csv_attributes(UIList):
    bl_idname = "CSVMI_UL_csv_attributes"

    def draw_item(
        self,
        context,
        layout,
        data,
        item,
        icon,
        active_data,
        active_property,
        index=0,
        flt_flag=0,
    ):
        row = layout.row(align=True)
        row.enabled = not item.reserved
        row.prop(item, "enabled", text="")
        row.label(text=item.name, icon='LOCKED' if item.reserved else 'PROPERTIES')
        row.label(text=item.data_type)


class CSVMI_UL_filter_values(UIList):
    bl_idname = "CSVMI_UL_filter_values"

    def draw_item(
        self, context, layout, data, item, icon, active_data, active_property,
        index=0, flt_flag=0,
    ):
        row = layout.row(align=True)
        row.prop(item, "selected", text="")
        row.label(text=item.value if item.value else "<empty>")
        row.label(text=f"{item.count:,}")


class CSVMI_UL_review_rows(UIList):
    bl_idname = "CSVMI_UL_review_rows"

    def draw_item(
        self, context, layout, data, item, icon, active_data, active_property,
        index=0, flt_flag=0,
    ):
        row = layout.row(align=True)
        status_icon = 'ERROR' if item.status == "Conflict" else 'INFO'
        row.label(text=item.status, icon=status_icon)
        row.label(text=item.identity)
        if item.zone:
            row.label(text=item.zone)
        row.label(text=item.objname)
        row.label(text=f"T:{item.transform_label} M:{item.mesh_label} P:{item.props_label}")
        row.label(text=item.decision_label)
        focus = row.operator("csvmi.focus_change", text="", icon='VIEWZOOM')
        focus.change_index = item.change_index


class CSVMI_UL_managed_outputs(UIList):
    bl_idname = "CSVMI_UL_managed_outputs"

    def filter_items(self, context, data, property_name):
        items = getattr(data, property_name)
        flags = [
            self.bitflag_filter_item if bool(collection.get(OUTPUT_MANAGED_KEY, False)) else 0
            for collection in items
        ]
        return flags, []

    def draw_item(
        self,
        context,
        layout,
        data,
        item,
        icon,
        active_data,
        active_property,
        index=0,
        flt_flag=0,
    ):
        if not bool(item.get(OUTPUT_MANAGED_KEY, False)):
            return
        row = layout.row(align=True)
        row.label(text=item.name, icon=collection_color_icon(item))
        row.label(text=f"{len(item.objects):,} O / {len(item.children):,} C")
        is_hidden = item.hide_viewport or item.hide_render
        visibility = row.operator(
            "csvmi.set_output_visibility",
            text="",
            icon='HIDE_OFF' if is_hidden else 'HIDE_ON',
        )
        visibility.collection_name = item.name
        visibility.show = is_hidden
        clear = row.operator("csvmi.clear_output", text="", icon='X')
        clear.collection_name = item.name
        delete = row.operator("csvmi.delete_output", text="", icon='TRASH')
        delete.collection_name = item.name


def draw_foldout(layout, props, property_name, label, icon='NONE'):
    row = layout.row(align=True)
    expanded = getattr(props, property_name)
    row.prop(
        props,
        property_name,
        text=label,
        icon='TRIA_DOWN' if expanded else 'TRIA_RIGHT',
        emboss=False,
    )
    if icon != 'NONE':
        row.label(text="", icon=icon)
    return expanded


class CSVMI_PT_panel(Panel):
    bl_label = "CSV Mesh Instancer"
    bl_idname = "CSVMI_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "CSV Instancer"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = scene.csvmi_props
        cache = get_csv_cache(scene)
        controls_enabled = not props.running

        if props.running:
            box = layout.box()
            box.label(text=props.phase, icon='INFO')
            box.label(text=props.status)
            if props.active_operation != 'FBX_IMPORT' and (props.progress > 0.0 or hasattr(box, "progress")):
                if hasattr(box, "progress"):
                    box.progress(
                        factor=props.progress,
                        type='BAR',
                        text=f"{int(props.progress * 100)}%",
                    )
                else:
                    box.label(text=f"Progress: {int(props.progress * 100)}%")
                if props.eta_text:
                    box.label(text=props.eta_text, icon='TIME')
            if props.active_operation not in {'CLEAR_OUTPUT', 'DELETE_OUTPUT'}:
                box.operator("csvmi.cancel", text="Cancel", icon='CANCEL')
            else:
                box.label(text="Fast deletion is finishing safely and cannot be cancelled.", icon='LOCKED')
            return

        if draw_foldout(layout, props, "show_csv", "CSV & Identity", 'FILE'):
            box = layout.box()
            box.prop(props, "csv_path")
            box.prop(props, "identity_column")
            if cache is None:
                box.label(text="Import a CSV with a globally unique ID column", icon='INFO')
            else:
                box.label(text=f"Loaded: {props.csv_valid_count:,} rows / ID: {cache.identity_column}", icon='CHECKMARK')
                box.label(text=f"Object Names: {props.csv_unique_name_count:,}")
                if csv_file_changed(scene):
                    box.label(text="The CSV file changed; re-import is required", icon='ERROR')
            row = box.row()
            row.enabled = bool(props.csv_path.strip() and props.identity_column.strip())
            row.operator(
                "csvmi.import_csv",
                text="Re-import CSV" if cache is not None else "Import CSV",
                icon='FILE_REFRESH' if cache is not None else 'IMPORT',
            )

        if draw_foldout(layout, props, "show_source", "Source", 'MESH_DATA'):
            box = layout.box()
            column = box.column()
            column.prop(props, "source_mode", expand=True)
            if props.source_mode == 'COLLECTION':
                row = column.row(align=True)
                row.label(text="", icon=collection_color_icon(props.source_collection))
                row.prop(props, "source_collection", text="")
                box.label(text=f"Source Meshes: {props.source_mesh_count:,}")
                box.label(text="Includes child Collections", icon='OUTLINER_COLLECTION')
            else:
                column.prop(props, "fbx_path")
                row = column.row(align=True)
                row.label(text="", icon=collection_color_icon(props.fbx_managed_collection))
                row.prop(props, "fbx_collection_name")
                import_row = column.row()
                import_row.enabled = bool(props.fbx_path.strip() and props.fbx_collection_name.strip())
                import_row.operator(
                    "csvmi.import_fbx",
                    text="Re-import FBX" if props.fbx_managed_collection else "Import FBX",
                    icon='FILE_REFRESH' if props.fbx_managed_collection else 'IMPORT',
                )
                if props.fbx_managed_collection:
                    box.label(text=f"Mesh: {props.fbx_mesh_count:,}")
                    box.label(text=f"All Objects: {props.fbx_total_count:,}")
                    if props.fbx_unapplied_transform_count:
                        box.label(
                            text=f"Unapplied Transforms: {props.fbx_unapplied_transform_count:,}",
                            icon='ERROR',
                        )
                else:
                    box.label(text="Status: Not imported", icon='INFO')
                correction = column.column(align=True)
                correction.prop(props, "apply_fbx_correction")
                if props.apply_fbx_correction:
                    correction.prop(props, "fbx_unit_scale")
                    correction.prop(props, "fbx_rotation_x")

        if draw_foldout(layout, props, "show_rules", "Update Rules", 'OPTIONS'):
            box = layout.box()
            output = bpy.data.collections.get(props.output_collection_name.strip())
            row = box.row(align=True)
            row.label(text="", icon=collection_color_icon(output))
            row.prop(props, "output_collection_name", text="")
            box.prop(props, "split_by_attribute")
            if props.split_by_attribute:
                box.prop(props, "split_attribute")
            box.prop(props, "ignore_numeric_suffix")
            box.label(text="Exact matches take priority")
            box.separator()
            box.label(text="Object Custom Properties")
            if cache is None:
                box.label(text="Import CSV to detect attributes", icon='INFO')
            elif props.csv_attributes:
                box.template_list(
                    "CSVMI_UL_csv_attributes", "", props, "csv_attributes",
                    props, "csv_attribute_index", rows=min(6, max(2, len(props.csv_attributes))),
                )
                box.label(text=f"Identity '{cache.identity_column}' is always stored")
            else:
                box.label(text="No additional attributes")

        if draw_foldout(layout, props, "show_filters", "Attribute Filters", 'FILTER'):
            box = layout.box()
            if cache is None:
                box.label(text="Import CSV to configure exact-value filters", icon='INFO')
            else:
                for index, rule in enumerate(props.attribute_filters):
                    row = box.row(align=True)
                    row.prop(rule, "enabled", text="")
                    row.prop(rule, "attribute", text=f"Filter {index + 1}")
                controls = box.row(align=True)
                controls.operator("csvmi.add_filter", text="Add Filter", icon='ADD')
                remove = controls.row(align=True)
                remove.enabled = bool(props.attribute_filters)
                remove.operator("csvmi.remove_filter", text="Remove", icon='REMOVE')
                if props.attribute_filters:
                    index = min(props.attribute_filter_index, len(props.attribute_filters) - 1)
                    rule = props.attribute_filters[index]
                    box.template_list(
                        "CSVMI_UL_filter_values", "", rule, "values", rule, "value_index",
                        rows=min(6, max(2, len(rule.values))),
                    )
                    if len(cache.attribute_values.get(rule.attribute, ())) > FILTER_VALUE_LIMIT:
                        box.label(text=f"First {FILTER_VALUE_LIMIT} values shown", icon='INFO')
                    box.prop(rule, "manual_values")
                box.label(text="OR within one attribute / AND between filters")

        if draw_foldout(layout, props, "show_preview", "Preview & Apply", 'PREVIEW_RANGE'):
            box = layout.box()
            source_valid = collection_source_for_scene(scene) is not None
            row = box.row()
            row.enabled = cache is not None and source_valid and bool(props.output_collection_name.strip())
            row.operator("csvmi.preview_changes", text="Preview Changes", icon='VIEWZOOM')
            if props.preview_valid:
                counts = box.column(align=True)
                counts.label(text=f"Changed IDs: {props.preview_change_count:,}")
                counts.label(text=f"New {props.preview_new_count:,} / CSV {props.preview_csv_changed_count:,} / Blender {props.preview_blender_edited_count:,}")
                counts.label(text=f"Conflicts {props.preview_conflict_count:,} / Mesh {props.preview_mesh_changed_count:,}")
                counts.label(text=f"CSV Deleted {props.preview_csv_deleted_count:,} / Blender Deleted {props.preview_blender_deleted_count:,}")
                if props.preview_filtered_count:
                    counts.label(text=f"Filtered Out: {props.preview_filtered_count:,}")
                search = box.row(align=True)
                search.prop(props, "review_search", text="", icon='VIEWZOOM')
                search.prop(props, "review_status_filter", text="")
                search = box.row(align=True)
                search.prop(props, "review_zone_filter")
                search.prop(props, "review_change_filter", text="")
                if props.review_rows:
                    box.template_list(
                        "CSVMI_UL_review_rows", "", props, "review_rows",
                        props, "review_row_index", rows=min(8, max(3, len(props.review_rows))),
                    )
                    pages = box.row(align=True)
                    previous_page = pages.operator("csvmi.review_page", text="", icon='TRIA_LEFT')
                    previous_page.delta = -1
                    pages.label(text=f"Page {props.review_page + 1} / {max(1, props.review_total_pages)}")
                    next_page = pages.operator("csvmi.review_page", text="", icon='TRIA_RIGHT')
                    next_page.delta = 1
                    current = props.review_rows[min(props.review_row_index, len(props.review_rows) - 1)]
                    preview = get_preview_cache(scene)
                    change = preview.changes[current.change_index] if preview else None
                    if change:
                        detail = box.box()
                        detail.label(text=f"{current.status} / ID {current.identity} / {current.objname}")
                        if change["transform_kind"]:
                            detail.label(text=f"Transform: {change['transform_kind'].title()}")
                            buttons = detail.row(align=True)
                            apply_op = buttons.operator("csvmi.set_change_decision", text="Apply CSV")
                            apply_op.change_index, apply_op.domain, apply_op.decision = current.change_index, 'transform', 'APPLY'
                            keep_op = buttons.operator("csvmi.set_change_decision", text="Keep Blender")
                            keep_op.change_index, keep_op.domain, keep_op.decision = current.change_index, 'transform', 'KEEP'
                        if change["mesh_kind"]:
                            old_mesh = (change.get("old") or {}).get("source_mesh", "—")
                            detail.label(text=f"Mesh: {old_mesh} → {change['new_source_mesh'] or 'Missing'}")
                            buttons = detail.row(align=True)
                            relink = buttons.operator("csvmi.set_change_decision", text="Relink Mesh")
                            relink.change_index, relink.domain, relink.decision = current.change_index, 'mesh', 'RELINK'
                            keep_mesh = buttons.operator("csvmi.set_change_decision", text="Keep Current Mesh")
                            keep_mesh.change_index, keep_mesh.domain, keep_mesh.decision = current.change_index, 'mesh', 'KEEP'
                        if change["props_kind"] or change["attribute_changed"]:
                            names = ", ".join(change["changed_properties"][:8]) or "metadata"
                            detail.label(text="Properties: " + names)
                            if change["props_kind"]:
                                buttons = detail.row(align=True)
                                apply_props = buttons.operator("csvmi.set_change_decision", text="Apply CSV Properties")
                                apply_props.change_index, apply_props.domain, apply_props.decision = current.change_index, 'props', 'APPLY'
                                keep_props = buttons.operator("csvmi.set_change_decision", text="Keep Blender Properties")
                                keep_props.change_index, keep_props.domain, keep_props.decision = current.change_index, 'props', 'KEEP'
                        object_actions = {
                            'NEW': [('Create', 'CREATE'), ('Skip', 'SKIP')],
                            'CSV_DELETED': [('Move to Deleted', 'MOVE_DELETED'), ('Keep', 'KEEP')],
                            'BLENDER_DELETED': [('Keep Deleted', 'KEEP_DELETED'), ('Restore', 'RESTORE')],
                            'DELETED': [('Keep Deleted', 'KEEP_DELETED'), ('Restore', 'RESTORE')],
                        }.get(change["object_kind"], ())
                        if object_actions:
                            buttons = detail.row(align=True)
                            for label, decision in object_actions:
                                action = buttons.operator("csvmi.set_change_decision", text=label)
                                action.change_index, action.domain, action.decision = current.change_index, 'object', decision
                else:
                    box.label(text="No changed IDs match the review filters", icon='CHECKMARK')
                bulk = box.row(align=True)
                for mode, label in (
                    ('APPLY', "Apply CSV"), ('KEEP', "Keep Blender"),
                    ('RELINK', "Relink Meshes"), ('KEEP_CONFLICTS', "Keep Conflicts"),
                ):
                    op = bulk.operator("csvmi.bulk_decision", text=label)
                    op.mode = mode
                apply_row = box.row()
                apply_row.enabled = props.preview_valid
                apply_row.operator("csvmi.apply_reviewed", text="Apply Reviewed Changes", icon='CHECKMARK')
            else:
                box.label(text="Preview is required before Apply", icon='INFO')

        if draw_foldout(layout, props, "show_managed_outputs", "Managed Outputs", 'OUTLINER_COLLECTION'):
            box = layout.box()
            managed_count = sum(
                1 for collection in bpy.data.collections if bool(collection.get(OUTPUT_MANAGED_KEY, False))
            )
            if managed_count:
                box.template_list(
                    "CSVMI_UL_managed_outputs",
                    "",
                    bpy.data,
                    "collections",
                    props,
                    "managed_collection_index",
                    rows=min(5, max(2, managed_count)),
                )
                box.label(text="Eye: Viewport + Render / X: Clear / Trash: Delete")
            else:
                box.label(text="No managed output Collections", icon='INFO')

        if draw_foldout(layout, props, "show_advanced", "Advanced", 'PREFERENCES'):
            box = layout.box()
            box.prop(props, "use_multi_tick")
            box.label(text=f"Suffix Collisions: {props.collision_group_count:,} groups")
            realize_row = box.row()
            realize_row.enabled = props.linked_instance_count > 0
            realize_row.operator("csvmi.realize", text="Make Meshes Single-User", icon='MESH_DATA')
            box.separator()
            box.label(text=props.phase)
            box.label(text=props.status)
            if props.running or props.progress > 0.0:
                if hasattr(box, "progress"):
                    box.progress(
                        factor=props.progress,
                        type='BAR',
                        text=f"{int(props.progress * 100)}%",
                    )
                else:
                    box.label(text=f"Progress: {int(props.progress * 100)}%")
                if props.eta_text:
                    box.label(text=props.eta_text, icon='TIME')
            box.label(text=f"Created: {props.generated_count:,}")
            box.label(text=f"Skipped: {props.skipped_count:,}")
            box.label(text=f"Missing Meshes: {props.missing_name_count:,} names / {props.missing_row_count:,} rows")
            if props.missing_name_preview:
                box.label(text="Missing Examples: " + props.missing_name_preview)
            box.label(text=f"Processing Time: {props.process_seconds:.2f}s")
            if props.max_tick_ms:
                box.label(text=f"Max Tick: {props.max_tick_ms:.1f}ms")


@persistent
def csvmi_load_post(_dummy):
    _CSV_CACHE.clear()
    _PREVIEW_CACHE.clear()
    for scene in bpy.data.scenes:
        if not hasattr(scene, "csvmi_props"):
            continue
        props = scene.csvmi_props
        props.running = False
        props.cancel_requested = False
        props.active_operation = 'NONE'
        props.status = "Re-import the CSV to restore runtime data."
        props.phase = "Idle"
        props.progress = 0.0
        props.eta_text = ""
        props.csv_row_count = 0
        props.csv_valid_count = 0
        props.csv_unique_name_count = 0
        props.csv_error_count = 0
        props.csv_attributes.clear()
        props.csv_attribute_index = 0
        props.review_rows.clear()
        props.preview_valid = False
        props.review_page = 0
        props.review_total_pages = 0


CLASSES = (
    CSVMI_AddonPreferences,
    CSVMI_CSVAttribute,
    CSVMI_FilterValue,
    CSVMI_FilterRule,
    CSVMI_PreviewRow,
    CSVMI_Props,
    CSVMI_OT_import_csv,
    CSVMI_OT_import_fbx,
    CSVMI_OT_add_filter,
    CSVMI_OT_remove_filter,
    CSVMI_OT_preview_changes,
    CSVMI_OT_review_page,
    CSVMI_OT_set_change_decision,
    CSVMI_OT_bulk_decision,
    CSVMI_OT_focus_change,
    CSVMI_OT_apply_reviewed,
    CSVMI_OT_realize,
    CSVMI_OT_set_output_visibility,
    CSVMI_OT_clear_output,
    CSVMI_OT_delete_output,
    CSVMI_OT_cancel,
    CSVMI_UL_csv_attributes,
    CSVMI_UL_filter_values,
    CSVMI_UL_review_rows,
    CSVMI_UL_managed_outputs,
    CSVMI_PT_panel,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.csvmi_props = PointerProperty(type=CSVMI_Props)
    if csvmi_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(csvmi_load_post)


def unregister():
    if csvmi_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(csvmi_load_post)
    _CSV_CACHE.clear()
    _PREVIEW_CACHE.clear()
    if hasattr(bpy.types.Scene, "csvmi_props"):
        del bpy.types.Scene.csvmi_props
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
