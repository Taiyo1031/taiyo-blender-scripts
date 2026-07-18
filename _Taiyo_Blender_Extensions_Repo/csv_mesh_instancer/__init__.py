bl_info = {
    "name": "CSV Mesh Instancer",
    "author": "Taiyo",
    "version": (1, 0, 3),
    "blender": (4, 5, 9),
    "location": "View3D > Sidebar(N) > CSV Instancer",
    "description": "Create linked mesh objects from CSV transforms using Collection or FBX sources.",
    "category": "Import-Export",
}

import csv
import math
import os
import re
import time
import traceback
import bpy
from mathutils import Quaternion
from bpy.app.handlers import persistent
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import AddonPreferences, Operator, Panel, PropertyGroup


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
TIME_BUDGET_SECONDS = 0.012
TIMER_INTERVAL_SECONDS = 0.01
REMOVE_BATCH_SIZE = 4096
FBX_MANAGED_KEY = "csvmi_fbx_managed"
FBX_PATH_KEY = "csvmi_fbx_filepath"
OUTPUT_MANAGED_KEY = "csvmi_output_managed"
STAGING_NAME = "__CSVMI_OUTPUT_STAGING__"

# Tuple indexes for compact CSV row storage.
ROW_NAME = 0
ROW_PTNUM = 1
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
        "unique_names",
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
        unique_names,
        raw_count,
        empty_name_count,
        numeric_error_count,
        error_samples,
    ):
        self.path = path
        self.mtime_ns = mtime_ns
        self.size = size
        self.rows = rows
        self.unique_names = unique_names
        self.raw_count = raw_count
        self.empty_name_count = empty_name_count
        self.numeric_error_count = numeric_error_count
        self.error_samples = error_samples

    @property
    def invalid_count(self):
        return self.empty_name_count + self.numeric_error_count


_CSV_CACHE = {}


def _scene_key(scene):
    return scene.as_pointer()


def get_csv_cache(scene):
    return _CSV_CACHE.get(_scene_key(scene))


def set_csv_cache(scene, data):
    _CSV_CACHE[_scene_key(scene)] = data


def clear_csv_cache(scene):
    _CSV_CACHE.pop(_scene_key(scene), None)


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


def load_csv_data(path):
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

            ptnum_column = header_map.get("ptnum")
            for line_number, record in enumerate(reader, start=2):
                raw_count += 1
                objname = (record.get(header_map["objname"]) or "").strip()
                if not objname:
                    empty_name_count += 1
                    if len(error_samples) < 12:
                        error_samples.append(f"Line {line_number}: objname is empty")
                    continue

                try:
                    values = [float(record.get(header_map[name], "")) for name in REQUIRED_COLUMNS[1:]]
                    if not all(math.isfinite(value) for value in values):
                        raise ValueError("NaN or Infinity")
                except (TypeError, ValueError) as exc:
                    numeric_error_count += 1
                    if len(error_samples) < 12:
                        error_samples.append(f"Line {line_number}: invalid number ({exc})")
                    continue

                ptnum = (record.get(ptnum_column) or "").strip() if ptnum_column else ""
                if not ptnum:
                    ptnum = str(line_number)

                tx, ty, tz, rx, ry, rz, sx, sy, sz = values
                rows.append(
                    (
                        objname,
                        ptnum,
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
                    )
                )
                unique_names.add(objname)
        except csv.Error as exc:
            raise ValueError(f"CSV format error: {exc}") from exc

    if not rows:
        raise ValueError("CSV contains no valid placement rows.")

    mtime_ns, size = file_signature(path)
    return CSVData(
        path,
        mtime_ns,
        size,
        rows,
        frozenset(unique_names),
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

    source_objects = collect_collection_objects(source_collection, mesh_only=True)
    if not source_objects:
        raise ValueError("No source Mesh objects were found.")

    if output_collection is not None:
        output_pointers = {obj.as_pointer() for obj in collect_collection_objects(output_collection)}
        overlap = [obj.name for obj in source_objects if obj.as_pointer() in output_pointers]
        if overlap:
            raise ValueError("Source Mesh objects are also linked to the output: " + ", ".join(overlap[:5]))

    resolved, missing_names, collisions = resolve_source_names(
        cache.unique_names,
        source_objects,
        props.ignore_numeric_suffix,
    )
    if collisions:
        print("[CSV Mesh Instancer] Numeric suffix collisions:")
        for normalized, candidates in sorted(collisions.items()):
            print(f"  {normalized}: {', '.join(candidates)}")

    missing_name_set = set(missing_names)
    missing_row_count = sum(1 for row in cache.rows if row[ROW_NAME] in missing_name_set)
    if missing_names:
        print("[CSV Mesh Instancer] Missing Mesh names:")
        for name in missing_names:
            print(f"  {name}")

    props.source_mesh_count = len(source_objects)
    props.collision_group_count = len(collisions)
    props.missing_name_count = len(missing_names)
    props.missing_row_count = missing_row_count
    props.missing_name_preview = ", ".join(missing_names[:8])
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


def _set_running(props, operation, status):
    props.running = True
    props.cancel_requested = False
    props.active_operation = operation
    props.status = status
    props.progress = 0.0


def _set_idle(props):
    props.running = False
    props.cancel_requested = False
    props.active_operation = 'NONE'


def tag_view3d_redraw(context):
    screen = getattr(context, "screen", None)
    if screen is None:
        return
    for area in screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


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


class UpdateTask:
    def __init__(self, scene, cache, output_collection, resolved, missing_names, missing_row_count):
        self.scene = scene
        self.props = scene.csvmi_props
        self.cache = cache
        self.rows = sorted(cache.rows, key=lambda row: (row[ROW_NAME], row[ROW_LINE]))
        self.output_collection = output_collection
        self.resolved = resolved
        self.missing_names = missing_names
        self.missing_row_count = missing_row_count
        self.stage = None
        self.phase = 'CREATE'
        self.index = 0
        self.created_count = 0
        self.stage_objects = []
        self.stage_names = []
        self.name_allocator = generated_name_allocator(output_collection)
        self.old_objects = []
        self.old_collections = []
        self.cancelled = False
        self.finished = False
        self.commit_started = False
        self.started_at = time.perf_counter()
        self.max_step_seconds = 0.0
        self.visibility_guard = None

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
        self.stage_objects.append(obj)
        self.stage_names.append(desired_name)
        self.created_count += 1

    def _prepare_commit(self):
        self.commit_started = True
        if self.output_collection is None:
            self.output_collection = bpy.data.collections.new(self.props.output_collection_name.strip())
            self.scene.collection.children.link(self.output_collection)
        self.visibility_guard = TemporaryCollectionExclusion(self.scene, self.output_collection)
        self.output_collection[OUTPUT_MANAGED_KEY] = True
        self.old_objects = collect_collection_objects(self.output_collection)
        self.old_collections = collect_child_collections_postorder(self.output_collection)
        self.phase = 'CLEAR_OBJECTS'
        self.index = 0

    def _progress_factor(self):
        row_total = max(1, len(self.cache.rows))
        if self.phase == 'CREATE':
            return 0.82 * (self.index / row_total)
        if self.phase == 'CLEAR_OBJECTS':
            return 0.82 + 0.06 * (self.index / max(1, len(self.old_objects)))
        if self.phase == 'CLEAR_COLLECTIONS':
            return 0.88 + 0.02 * (self.index / max(1, len(self.old_collections)))
        if self.phase == 'LINK':
            return 0.90 + 0.10 * (self.index / max(1, len(self.stage_objects)))
        if self.phase == 'CANCEL_CLEANUP':
            remaining = max(0, self.index + 1)
            return 1.0 - remaining / max(1, len(self.stage_objects))
        return 1.0

    def _update_status(self):
        props = self.props
        props.progress = min(1.0, max(0.0, self._progress_factor()))
        if self.phase == 'CREATE':
            props.phase = "Creating placements"
            props.status = f"Creating placements: {self.index:,} / {len(self.cache.rows):,}"
        elif self.phase == 'CLEAR_OBJECTS':
            props.phase = "Clearing old output"
            props.status = f"Removing old objects: {self.index:,} / {len(self.old_objects):,}"
        elif self.phase == 'CLEAR_COLLECTIONS':
            props.phase = "Removing child Collections"
            props.status = f"Removing child Collections: {self.index:,} / {len(self.old_collections):,}"
        elif self.phase == 'LINK':
            props.phase = "Committing new placements"
            props.status = f"Committing placements: {self.index:,} / {len(self.stage_objects):,}"

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
        self._update_status()
        return self.finished

    def finish_props(self):
        props = self.props
        duration = time.perf_counter() - self.started_at
        props.process_seconds = duration
        props.max_tick_ms = self.max_step_seconds * 1000.0
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


class InPlaceUpdateTask:
    """Fast transactional update for an output made entirely by this add-on."""

    def __init__(self, scene, cache, output_collection, resolved, missing_names, missing_row_count):
        self.scene = scene
        self.props = scene.csvmi_props
        self.cache = cache
        self.rows = sorted(cache.rows, key=lambda row: (row[ROW_NAME], row[ROW_LINE]))
        self.output_collection = output_collection
        self.resolved = resolved
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
        self.result_objects = []
        self.desired_names = []
        self.name_allocator = generated_name_allocator(output_collection)
        self.rename_objects = []
        self.rename_names = []
        self.leftovers = []
        self.finished = False
        self.cancelled = False
        self.commit_started = False
        self.started_at = time.perf_counter()
        self.max_step_seconds = 0.0
        self.created_count = 0
        self.visibility_guard = TemporaryCollectionExclusion(scene, output_collection)

    @staticmethod
    def _snapshot(obj):
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

    def _progress_factor(self):
        if self.phase == 'UPDATE':
            return 0.80 * self.index / max(1, len(self.cache.rows))
        if self.phase == 'DELETE_LEFTOVERS':
            return 0.80 + 0.04 * self.index / max(1, len(self.leftovers))
        if self.phase == 'RENAME_TEMP':
            return 0.84 + 0.08 * self.index / max(1, len(self.rename_objects))
        if self.phase == 'RENAME_FINAL':
            return 0.92 + 0.08 * self.index / max(1, len(self.rename_objects))
        return 0.0

    def _update_status(self):
        self.props.progress = min(1.0, max(0.0, self._progress_factor()))
        if self.phase == 'UPDATE':
            self.props.phase = "Fast updating existing placements"
            self.props.status = f"Updating placements: {self.index:,} / {len(self.cache.rows):,}"
        elif self.phase == 'DELETE_LEFTOVERS':
            self.props.phase = "Removing obsolete objects"
            self.props.status = f"Removing obsolete objects: {self.index:,} / {len(self.leftovers):,}"
        elif self.phase in {'RENAME_TEMP', 'RENAME_FINAL'}:
            self.props.phase = "Finalizing object names"
            self.props.status = f"Finalizing object names: {self.index:,} / {len(self.rename_objects):,}"

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
                        self.desired_names.append(self.name_allocator.reserve(row[ROW_NAME]))
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
        self._update_status()
        return self.finished

    def finish_props(self):
        props = self.props
        duration = time.perf_counter() - self.started_at
        props.process_seconds = duration
        props.max_tick_ms = self.max_step_seconds * 1000.0
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


class RealizeTask:
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
        output = bpy.data.collections.get(scene.csvmi_props.output_collection_name.strip())
        self.visibility_guard = TemporaryCollectionExclusion(scene, output) if output else None

    def request_cancel(self):
        if self.phase == 'REALIZE':
            self.phase = 'ROLLBACK'
            self.index = len(self.changes) - 1
            self.props.status = "Cancelling: restoring shared Mesh data"

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
        if self.phase == 'REALIZE':
            self.props.progress = self.index / max(1, len(self.objects))
            self.props.phase = "Making Mesh data single-user"
            self.props.status = f"Making Mesh data single-user: {self.index:,} / {len(self.objects):,}"
        else:
            restored = len(self.changes) - max(0, self.index + 1)
            self.props.progress = restored / max(1, len(self.changes))
        return self.finished

    def finish_props(self):
        if self.visibility_guard is not None:
            self.visibility_guard.restore()
        props = self.props
        duration = time.perf_counter() - self.started_at
        props.process_seconds = duration
        props.max_tick_ms = self.max_step_seconds * 1000.0
        if self.cancelled:
            props.status = "Cancelled and restored shared Mesh data."
            props.phase = "Cancelled"
            props.progress = 0.0
        else:
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


class CSVMI_AddonPreferences(AddonPreferences):
    bl_idname = __package__ or "csv_mesh_instancer"

    def draw(self, context):
        layout = self.layout
        layout.label(text="CSV Mesh Instancer Documentation")
        operator = layout.operator("wm.url_open", text="Open User Guide", icon='URL')
        operator.url = DOCUMENTATION_URL


class CSVMI_Props(PropertyGroup):
    csv_path: StringProperty(name="CSV File", subtype='FILE_PATH', default="")
    source_mode: EnumProperty(
        name="Source Mode",
        items=[
            ('COLLECTION', "Collection", "Use a Collection already in this Blender file"),
            ('FBX', "FBX", "Import and use an external FBX file"),
        ],
        default='COLLECTION',
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
    )
    fbx_unit_scale: FloatProperty(
        name="Unit Scale",
        default=0.01,
        min=0.000001,
        soft_max=1.0,
        precision=4,
        description="Uniform Delta Scale applied to placements that use an FBX source",
    )
    fbx_rotation_x: FloatProperty(
        name="Local X Rotation",
        default=math.radians(90.0),
        subtype='ANGLE',
        unit='ROTATION',
        description="Local X rotation applied after each CSV rotation, like pressing R, X, X in Blender",
    )
    output_collection_name: StringProperty(name="Collection Name", default="CSV_Output")
    ignore_numeric_suffix: BoolProperty(name="Ignore .001 Numeric Suffixes", default=False)
    use_multi_tick: BoolProperty(
        name="Split Across Multiple Ticks",
        default=True,
        description="Split large object operations into short time slices to keep Blender responsive",
    )

    show_csv: BoolProperty(default=True)
    show_source: BoolProperty(default=True)
    show_matching: BoolProperty(default=True)
    show_output: BoolProperty(default=True)
    show_status: BoolProperty(default=True)

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
    progress: FloatProperty(default=0.0, min=0.0, max=1.0)
    process_seconds: FloatProperty(default=0.0)
    max_tick_ms: FloatProperty(default=0.0)
    running: BoolProperty(default=False)
    cancel_requested: BoolProperty(default=False)
    active_operation: EnumProperty(
        items=[
            ('NONE', "None", ""),
            ('FBX_IMPORT', "FBX Import", ""),
            ('UPDATE', "Update", ""),
            ('REALIZE', "Realize", ""),
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
            data = load_csv_data(props.csv_path)
        except Exception as exc:
            props.status = str(exc)
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        set_csv_cache(context.scene, data)
        props.csv_row_count = data.raw_count
        props.csv_valid_count = len(data.rows)
        props.csv_unique_name_count = len(data.unique_names)
        props.csv_error_count = data.invalid_count
        props.csv_error_preview = " / ".join(data.error_samples)
        props.status = (
            f"CSV loaded: {len(data.rows):,} valid rows / "
            f"{len(data.unique_names):,} object names / {data.invalid_count:,} errors"
        )
        props.phase = "CSV loaded"
        self.report({'INFO'}, props.status)
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

    def _start_modal_or_sync(self, context):
        props = context.scene.csvmi_props
        if props.use_multi_tick and context.window is not None:
            context.window_manager.progress_begin(0, 1000)
            self._timer = context.window_manager.event_timer_add(TIMER_INTERVAL_SECONDS, window=context.window)
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}

        try:
            while not self._task.step(3600.0):
                pass
            self._task.finish_props()
            _set_idle(props)
            return {'CANCELLED'} if self._task.cancelled else {'FINISHED'}
        except Exception as exc:
            self._handle_error(context, exc)
            return {'CANCELLED'}

    def modal(self, context, event):
        if event.type == 'ESC':
            context.scene.csvmi_props.cancel_requested = True
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        props = context.scene.csvmi_props
        if props.cancel_requested:
            self._task.request_cancel()

        try:
            finished = self._task.step(TIME_BUDGET_SECONDS)
        except Exception as exc:
            self._handle_error(context, exc)
            return {'CANCELLED'}

        context.window_manager.progress_update(int(props.progress * 1000))
        tag_view3d_redraw(context)
        if not finished:
            return {'RUNNING_MODAL'}

        self._task.finish_props()
        cancelled = self._task.cancelled
        self._finish_modal(context)
        return {'CANCELLED'} if cancelled else {'FINISHED'}

    def _finish_modal(self, context):
        props = context.scene.csvmi_props
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
        if self._timer is not None:
            self._finish_modal(context)
        else:
            _set_idle(props)
        self.report({'ERROR'}, props.status)

    def cancel(self, context):
        if self._task is not None:
            self._task.request_cancel()


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


class CSVMI_OT_cancel(Operator):
    bl_idname = "csvmi.cancel"
    bl_label = "Cancel Operation"
    bl_description = "Begin a safe cancellation after the current tick finishes"

    def execute(self, context):
        props = context.scene.csvmi_props
        if not props.running:
            return {'CANCELLED'}
        props.cancel_requested = True
        props.status = "Cancellation requested. The current tick will finish first."
        return {'FINISHED'}


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
            box.operator("csvmi.cancel", text="Cancel", icon='CANCEL')
            return

        if draw_foldout(layout, props, "show_csv", "CSV Data", 'FILE'):
            box = layout.box()
            column = box.column()
            column.enabled = controls_enabled
            column.prop(props, "csv_path")
            if cache is None:
                box.label(text="Status: Not imported", icon='INFO')
            else:
                box.label(text="Status: Loaded", icon='CHECKMARK')
                box.label(text=f"Rows: {props.csv_row_count:,}")
                box.label(text=f"Valid Rows: {props.csv_valid_count:,}")
                box.label(text=f"Object Names: {props.csv_unique_name_count:,}")
                if props.csv_error_count:
                    box.label(text=f"CSV Errors: {props.csv_error_count:,} rows", icon='ERROR')
                if csv_file_changed(scene):
                    box.label(text="The CSV file has changed", icon='ERROR')
            row = box.row()
            row.enabled = controls_enabled and bool(props.csv_path.strip())
            row.operator(
                "csvmi.import_csv",
                text="Re-import CSV" if cache is not None else "Import CSV",
                icon='FILE_REFRESH' if cache is not None else 'IMPORT',
            )

        if draw_foldout(layout, props, "show_source", "Mesh Source", 'MESH_DATA'):
            box = layout.box()
            column = box.column()
            column.enabled = controls_enabled
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

        if draw_foldout(layout, props, "show_matching", "Name Matching", 'SORTALPHA'):
            box = layout.box()
            row = box.row()
            row.enabled = controls_enabled
            row.prop(props, "ignore_numeric_suffix")
            box.label(text="Exact matches take priority")
            box.label(text=f"Suffix Collisions: {props.collision_group_count:,} groups")

        if draw_foldout(layout, props, "show_output", "Output", 'OUTLINER_COLLECTION'):
            box = layout.box()
            output = bpy.data.collections.get(props.output_collection_name.strip())
            row = box.row(align=True)
            row.enabled = controls_enabled
            row.label(text="", icon=collection_color_icon(output))
            row.prop(props, "output_collection_name", text="")
            box.label(text="Update replaces the contents of a same-named Collection", icon='ERROR')
            row = box.row()
            row.enabled = controls_enabled
            row.prop(props, "use_multi_tick")

        action_box = layout.box()
        if props.running:
            action_box.operator("csvmi.cancel", icon='CANCEL')
        else:
            source_valid = collection_source_for_scene(scene) is not None
            update_row = action_box.row()
            update_row.enabled = cache is not None and source_valid and bool(props.output_collection_name.strip())
            update_row.operator("csvmi.update", text="Update", icon='FILE_REFRESH')
            realize_row = action_box.row()
            realize_row.enabled = props.linked_instance_count > 0
            realize_row.operator("csvmi.realize", text="Make Meshes Single-User", icon='MESH_DATA')

        if draw_foldout(layout, props, "show_status", "Status", 'INFO'):
            box = layout.box()
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
        props.csv_row_count = 0
        props.csv_valid_count = 0
        props.csv_unique_name_count = 0
        props.csv_error_count = 0


CLASSES = (
    CSVMI_AddonPreferences,
    CSVMI_Props,
    CSVMI_OT_import_csv,
    CSVMI_OT_import_fbx,
    CSVMI_OT_update,
    CSVMI_OT_realize,
    CSVMI_OT_cancel,
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
    if hasattr(bpy.types.Scene, "csvmi_props"):
        del bpy.types.Scene.csvmi_props
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
