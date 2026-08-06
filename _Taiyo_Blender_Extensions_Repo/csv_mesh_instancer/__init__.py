bl_info = {
    "name": "CSV Mesh Instancer",
    "author": "Taiyo",
    "version": (3, 0, 0),
    "blender": (4, 5, 9),
    "location": "View3D > Sidebar(N) > CSV Instancer",
    "description": "Import CSV and FBX files and place linked mesh objects quickly.",
    "category": "Object",
}

import csv
import math
import os
import re
import time
import traceback

import bpy
from bpy.props import BoolProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup
from mathutils import Quaternion


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
NUMERIC_SUFFIX_RE = re.compile(r"\.\d{3,}$")
FBX_MANAGED_KEY = "csvmi_fbx_managed"
FBX_PATH_KEY = "csvmi_fbx_filepath"
FBX_CANONICAL_OBJECT_KEY = "csvmi_fbx_canonical_object_name"
FBX_CANONICAL_MESH_KEY = "csvmi_fbx_canonical_mesh_name"
FBX_PREVIOUS_MESH_KEY = "csvmi_fbx_previous_mesh"
OUTPUT_MANAGED_KEY = "csvmi_simple_output"
OUTPUT_VERSION_KEY = "csvmi_simple_version"
OUTPUT_VERSION = 3
TARGET_TICK_SECONDS = 0.012
UI_UPDATE_SECONDS = 0.2
TIMER_INTERVAL_SECONDS = 0.01
MIN_CHUNK_SIZE = 32
MAX_CHUNK_SIZE = 8192


_CSV_CACHE = {}
_ACTIVE_TASKS = {}


class CSVData:
    __slots__ = ("path", "mtime_ns", "size", "rows", "unique_names")

    def __init__(self, path, mtime_ns, size, rows):
        self.path = path
        self.mtime_ns = mtime_ns
        self.size = size
        self.rows = tuple(rows)
        self.unique_names = tuple(sorted({row[0] for row in rows}))


def scene_key(scene):
    return scene.as_pointer()


def get_csv_cache(scene):
    return _CSV_CACHE.get(scene_key(scene))


def clear_csv_cache(scene):
    _CSV_CACHE.pop(scene_key(scene), None)


def update_csv_path(props, context):
    if context and context.scene:
        clear_csv_cache(context.scene)
        props.csv_count = 0
        props.csv_name_count = 0


def absolute_path(value):
    return os.path.abspath(bpy.path.abspath(value.strip()))


def parse_csv_file(path):
    stat = os.stat(path)
    rows = []
    problems = []
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError("The CSV file is empty.") from exc
        normalized = [value.strip() for value in header]
        if len(normalized) != len(set(normalized)):
            raise ValueError("The CSV header contains duplicate column names.")
        header_map = {name: index for index, name in enumerate(normalized)}
        missing = [name for name in REQUIRED_COLUMNS if name not in header_map]
        if missing:
            raise ValueError("Missing required CSV columns: " + ", ".join(missing))

        for physical_line, values in enumerate(reader, start=2):
            if not values or not any(value.strip() for value in values):
                continue
            try:
                name = values[header_map["objname"]].strip()
            except IndexError:
                name = ""
            if not name:
                problems.append(f"line {physical_line}: objname is empty")
                if len(problems) >= 20:
                    break
                continue
            numbers = []
            for column in REQUIRED_COLUMNS[1:]:
                try:
                    number = float(values[header_map[column]].strip())
                    if not math.isfinite(number):
                        raise ValueError
                except (IndexError, ValueError):
                    problems.append(
                        f"line {physical_line}: {column} must be a finite number"
                    )
                    break
                numbers.append(number)
            if len(numbers) == 9:
                rows.append(
                    (
                        name,
                        *numbers[:3],
                        *(math.radians(value) for value in numbers[3:6]),
                        *numbers[6:],
                        physical_line,
                    )
                )
            if len(problems) >= 20:
                break

    if problems:
        raise ValueError("Invalid CSV data: " + "; ".join(problems))
    if not rows:
        raise ValueError("The CSV contains no valid placement rows.")
    return CSVData(path, stat.st_mtime_ns, stat.st_size, rows)


def csv_cache_is_stale(cache):
    if cache is None:
        return False
    try:
        stat = os.stat(cache.path)
    except OSError:
        return True
    return stat.st_mtime_ns != cache.mtime_ns or stat.st_size != cache.size


def strip_numeric_suffix(name):
    return NUMERIC_SUFFIX_RE.sub("", name)


def source_object_name(obj):
    canonical = obj.get(FBX_CANONICAL_OBJECT_KEY, "")
    return canonical if isinstance(canonical, str) and canonical else obj.name


def source_choice_key(obj):
    name = source_object_name(obj)
    match = NUMERIC_SUFFIX_RE.search(name)
    if match is None:
        return (0, -1, name, obj.name)
    return (1, int(match.group()[1:]), name, obj.name)


def collect_collection_objects(collection, mesh_only=False):
    if collection is None:
        return []
    result = []
    stack = [collection]
    visited = set()
    while stack:
        current = stack.pop()
        pointer = current.as_pointer()
        if pointer in visited:
            continue
        visited.add(pointer)
        for obj in current.objects:
            if not mesh_only or obj.type == 'MESH':
                result.append(obj)
        stack.extend(current.children)
    return result


def build_source_index(collection, ignore_suffix):
    objects = collect_collection_objects(collection, mesh_only=True)
    exact = {}
    normalized = {}
    for obj in sorted(objects, key=source_choice_key):
        name = source_object_name(obj)
        exact.setdefault(name, obj)
        if ignore_suffix:
            normalized.setdefault(strip_numeric_suffix(name), []).append(obj)
    for candidates in normalized.values():
        candidates.sort(key=source_choice_key)
    return objects, exact, normalized


def resolve_source(name, exact, normalized, ignore_suffix):
    source = exact.get(name)
    if source is not None or not ignore_suffix:
        return source
    candidates = normalized.get(strip_numeric_suffix(name), ())
    return candidates[0] if candidates else None


def apply_csv_transform(obj, row, props):
    obj.location = row[1:4]
    obj.rotation_mode = 'XYZ'
    obj.rotation_euler = row[4:7]
    obj.scale = row[7:10]
    obj.delta_location = (0.0, 0.0, 0.0)
    if props.apply_fbx_correction:
        csv_rotation = obj.rotation_euler.to_quaternion()
        local_x = Quaternion((1.0, 0.0, 0.0), props.fbx_rotation_x)
        world_delta = csv_rotation @ local_x @ csv_rotation.conjugated()
        obj.delta_rotation_euler = world_delta.to_euler('XYZ')
        correction = props.fbx_unit_scale
        obj.delta_scale = (correction, correction, correction)
    else:
        obj.delta_rotation_euler = (0.0, 0.0, 0.0)
        obj.delta_scale = (1.0, 1.0, 1.0)


def tag_view3d_redraw(context=None):
    windows = bpy.context.window_manager.windows
    for window in windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def find_layer_collection(layer_collection, collection):
    if layer_collection.collection == collection:
        return layer_collection
    for child in layer_collection.children:
        found = find_layer_collection(child, collection)
        if found is not None:
            return found
    return None


def hide_source_collection(scene, collection):
    excluded = False
    for view_layer in scene.view_layers:
        layer = find_layer_collection(view_layer.layer_collection, collection)
        if layer is not None:
            layer.exclude = True
            excluded = True
    collection.hide_viewport = True
    collection.hide_render = True
    return excluded


def remove_collection_objects(collection):
    objects = collect_collection_objects(collection)
    if objects:
        bpy.data.batch_remove(objects)
    children = list(collection.children_recursive)
    for child in reversed(children):
        if child.name in bpy.data.collections:
            bpy.data.collections.remove(child)
    if collection.name in bpy.data.collections:
        bpy.data.collections.remove(collection)


def cleanup_previous_meshes():
    stale = [
        mesh
        for mesh in bpy.data.meshes
        if bool(mesh.get(FBX_PREVIOUS_MESH_KEY, False)) and mesh.users == 0
    ]
    for mesh in stale:
        if mesh.name in bpy.data.meshes and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    return len(stale)


def set_running(props, phase, can_cancel):
    props.busy = True
    props.phase = phase
    props.can_cancel = can_cancel
    props.cancel_requested = False
    props.progress = 0.0
    props.eta = "Estimating..."


def set_idle(props):
    props.busy = False
    props.can_cancel = False
    props.cancel_requested = False


class FbxImportTransaction:
    def __init__(self, old_collection):
        self.old_collection = old_collection
        self.snapshots = []
        self.snapshot_pointers = set()
        self.expected_objects = set()
        self.expected_meshes = {}
        self.prepared = False
        self.committed = False

    def snapshot(self, data_block, keys=()):
        pointer = data_block.as_pointer()
        if pointer in self.snapshot_pointers:
            return
        self.snapshot_pointers.add(pointer)
        properties = {
            key: (key in data_block, data_block.get(key))
            for key in keys
        }
        self.snapshots.append((data_block, data_block.name, properties))

    def prepare(self):
        if self.old_collection is None:
            self.prepared = True
            return
        keys = (
            FBX_MANAGED_KEY,
            FBX_PATH_KEY,
            FBX_CANONICAL_OBJECT_KEY,
            FBX_CANONICAL_MESH_KEY,
            FBX_PREVIOUS_MESH_KEY,
        )
        mesh_index = 0
        for object_index, obj in enumerate(collect_collection_objects(self.old_collection)):
            canonical_object = source_object_name(obj)
            self.expected_objects.add(canonical_object)
            self.snapshot(obj, keys)
            obj[FBX_CANONICAL_OBJECT_KEY] = canonical_object
            obj.name = f"__CSVMI_PREVIOUS_OBJECT__{object_index:06d}"
            if obj.type != 'MESH' or obj.data is None:
                continue
            mesh = obj.data
            canonical_mesh = mesh.get(FBX_CANONICAL_MESH_KEY, "") or mesh.name
            self.expected_meshes.setdefault(canonical_object, canonical_mesh)
            if mesh.as_pointer() in self.snapshot_pointers:
                continue
            self.snapshot(mesh, keys)
            mesh[FBX_CANONICAL_MESH_KEY] = canonical_mesh
            mesh[FBX_PREVIOUS_MESH_KEY] = True
            mesh.name = f"{canonical_mesh} [Previous FBX {mesh_index:04d}]"
            mesh_index += 1
        self.snapshot(self.old_collection, keys)
        self.old_collection.name = "__CSVMI_PREVIOUS_FBX_SOURCE__"
        self.prepared = True

    def normalize_new(self, new_objects):
        meshes = {}
        for obj in new_objects:
            canonical_object = obj.name
            if canonical_object not in self.expected_objects:
                base = strip_numeric_suffix(canonical_object)
                if base in self.expected_objects:
                    canonical_object = base
            obj[FBX_MANAGED_KEY] = True
            obj[FBX_CANONICAL_OBJECT_KEY] = canonical_object
            obj.name = canonical_object
            if obj.type != 'MESH' or obj.data is None:
                continue
            mesh = obj.data
            pointer = mesh.as_pointer()
            canonical_mesh = meshes.get(pointer)
            if canonical_mesh is None:
                canonical_mesh = self.expected_meshes.get(canonical_object, mesh.name)
                meshes[pointer] = canonical_mesh
                mesh[FBX_CANONICAL_MESH_KEY] = canonical_mesh
                if FBX_PREVIOUS_MESH_KEY in mesh:
                    del mesh[FBX_PREVIOUS_MESH_KEY]
                mesh.name = canonical_mesh

    def commit(self):
        self.committed = True

    def restore(self):
        if not self.prepared or self.committed:
            return
        token = str(time.time_ns())
        for index, (data_block, _name, _properties) in enumerate(self.snapshots):
            try:
                data_block.name = f"__CSVMI_ROLLBACK__{token}_{index:06d}"
            except (ReferenceError, RuntimeError):
                pass
        for data_block, name, properties in self.snapshots:
            try:
                data_block.name = name
                for key, (existed, value) in properties.items():
                    if existed:
                        data_block[key] = value
                    elif key in data_block:
                        del data_block[key]
            except (ReferenceError, RuntimeError):
                pass


def cleanup_imported_data(new_objects, new_collections, new_meshes, temp_collection):
    for obj in list(new_objects):
        if obj and obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    for collection in reversed(list(new_collections)):
        if collection and collection.name in bpy.data.collections:
            bpy.data.collections.remove(collection)
    if temp_collection and temp_collection.name in bpy.data.collections:
        bpy.data.collections.remove(temp_collection)
    for mesh in list(new_meshes):
        if mesh and mesh.name in bpy.data.meshes and mesh.users == 0:
            bpy.data.meshes.remove(mesh)


class PlacementTask:
    def __init__(self, scene, cache, source_collection, old_output):
        self.scene = scene
        self.props = scene.csvmi_props
        self.cache = cache
        self.source_collection = source_collection
        self.old_output = old_output
        self.source_objects, self.exact, self.normalized = build_source_index(
            source_collection,
            self.props.ignore_numeric_suffix,
        )
        self.replacing = old_output is not None
        self.staging = (
            old_output
            if self.replacing
            else bpy.data.collections.new("__CSVMI_BUILD_OUTPUT__")
        )
        self.staging[OUTPUT_MANAGED_KEY] = True
        self.staging[OUTPUT_VERSION_KEY] = OUTPUT_VERSION
        if not self.replacing:
            self.scene.collection.children.link(self.staging)
        hide_source_collection(self.scene, self.staging)
        self.created = []
        self.resolved = tuple(
            resolve_source(
                row[0], self.exact, self.normalized, self.props.ignore_numeric_suffix
            )
            for row in cache.rows
        )
        self.rows_index = 0
        self.old_objects = list(old_output.objects) if old_output is not None else []
        self.reuse_index = 0
        self.remove_index = len(self.old_objects)
        self.remove_chunk_size = 1024
        self.phase = 'GENERATE'
        self.started_at = time.perf_counter()
        self.last_ui_at = 0.0
        self.generated_count = 0
        self.missing_count = 0
        self.missing_names = set()
        self.completed_units = 0
        valid_count = sum(source is not None for source in self.resolved)
        removable_count = max(0, len(self.old_objects) - valid_count)
        self.total_units = max(
            1,
            len(cache.rows)
            + removable_count,
        )
        self.done = False
        self.cancelled = False

    def update_ui(self, force=False):
        now = time.perf_counter()
        if not force and now - self.last_ui_at < UI_UPDATE_SECONDS:
            return
        self.last_ui_at = now
        elapsed = max(0.000001, now - self.started_at)
        self.props.progress = min(0.999, self.completed_units / self.total_units)
        remaining = max(0, self.total_units - self.completed_units)
        if self.completed_units < 32:
            self.props.eta = "Estimating..."
        else:
            seconds = remaining / (self.completed_units / elapsed)
            if seconds < 60:
                self.props.eta = f"Remaining: ~{max(1, round(seconds))}s"
            else:
                self.props.eta = f"Remaining: ~{math.ceil(seconds / 60)}m"
        phase_labels = {
            'GENERATE': "Placing objects",
            'REMOVE': "Removing unused objects",
            'FINALIZE': "Finishing placement",
        }
        self.props.phase = phase_labels.get(self.phase, "Placement")
        tag_view3d_redraw()

    def generate_one(self):
        row = self.cache.rows[self.rows_index]
        source = self.resolved[self.rows_index]
        self.rows_index += 1
        if source is None:
            self.missing_count += 1
            if len(self.missing_names) < 20:
                self.missing_names.add(row[0])
        else:
            object_name = f"{row[10]:06d}_{row[0]}"
            if self.reuse_index < len(self.old_objects):
                obj = self.old_objects[self.reuse_index]
                self.reuse_index += 1
                if obj.name != object_name:
                    obj.name = object_name
                obj.data = source.data
            else:
                obj = bpy.data.objects.new(object_name, source.data)
                self.staging.objects.link(obj)
                self.created.append(obj)
            apply_csv_transform(obj, row, self.props)
            self.generated_count += 1
        self.completed_units += 1

    def remove_old_batch(self):
        end = min(len(self.old_objects), self.remove_index + self.remove_chunk_size)
        batch = self.old_objects[self.remove_index:end]
        started = time.perf_counter()
        if batch:
            bpy.data.batch_remove(batch)
        elapsed = max(0.000001, time.perf_counter() - started)
        self.remove_index = end
        self.completed_units += len(batch)
        scale = TARGET_TICK_SECONDS / elapsed
        self.remove_chunk_size = max(
            MIN_CHUNK_SIZE,
            min(MAX_CHUNK_SIZE, int(self.remove_chunk_size * max(0.25, min(4.0, scale)))),
        )

    def finalize(self):
        self.staging.name = self.props.output_collection_name.strip()
        self.staging.hide_viewport = True
        self.staging.hide_render = True
        cleanup_previous_meshes()
        elapsed = time.perf_counter() - self.started_at
        self.props.generated_count = self.generated_count
        self.props.missing_count = self.missing_count
        self.props.elapsed_seconds = elapsed
        self.props.progress = 1.0
        self.props.eta = ""
        self.props.phase = "Complete"
        self.props.status = (
            f"Placed {self.generated_count:,} objects / "
            f"missing {self.missing_count:,} / {elapsed:.2f}s"
        )
        if self.missing_names:
            self.props.status += " / " + ", ".join(sorted(self.missing_names))
        self.done = True
        self.update_ui(force=True)

    def abort(self):
        if self.replacing or self.phase != 'GENERATE':
            return
        if self.created:
            bpy.data.batch_remove(self.created)
        if self.staging.name in bpy.data.collections:
            bpy.data.collections.remove(self.staging)
        self.cancelled = True
        self.done = True
        self.props.phase = "Cancelled"
        self.props.eta = ""
        self.props.status = "Placement cancelled. The previous output was preserved."
        tag_view3d_redraw()

    def fail(self, message):
        if not self.replacing and self.phase == 'GENERATE':
            self.abort()
        else:
            self.done = True
        self.props.phase = "Placement error"
        self.props.eta = ""
        self.props.status = message
        tag_view3d_redraw()

    def step(self, time_budget=TARGET_TICK_SECONDS):
        if self.done:
            return True
        if not self.replacing and self.phase == 'GENERATE' and self.props.cancel_requested:
            self.abort()
            return True
        deadline = None if time_budget is None else time.perf_counter() + time_budget
        if self.phase == 'GENERATE':
            while self.rows_index < len(self.cache.rows):
                self.generate_one()
                if deadline is not None and time.perf_counter() >= deadline:
                    self.update_ui()
                    return False
            self.phase = 'REMOVE'
            self.props.can_cancel = False
            self.remove_index = self.reuse_index
            self.update_ui(force=True)
        if self.phase == 'REMOVE':
            while self.remove_index < len(self.old_objects):
                self.remove_old_batch()
                if deadline is not None and time.perf_counter() >= deadline:
                    self.update_ui()
                    return False
            self.phase = 'FINALIZE'
        if self.phase == 'FINALIZE':
            self.finalize()
        return self.done


class CSVMI_Props(PropertyGroup):
    csv_path: StringProperty(
        name="CSV File",
        subtype='FILE_PATH',
        default="",
        update=update_csv_path,
    )
    fbx_path: StringProperty(name="FBX File", subtype='FILE_PATH', default="")
    fbx_collection_name: StringProperty(name="Source Collection", default="CSVMI_FBX_Source")
    fbx_collection: PointerProperty(type=bpy.types.Collection)
    output_collection_name: StringProperty(name="Output Collection", default="CSV_Output")
    ignore_numeric_suffix: BoolProperty(name="Ignore .001 Suffixes", default=False)
    apply_fbx_correction: BoolProperty(name="Apply FBX Correction", default=True)
    fbx_unit_scale: FloatProperty(
        name="Unit Scale",
        default=0.01,
        min=0.000001,
        soft_max=1.0,
        precision=4,
    )
    fbx_rotation_x: FloatProperty(
        name="Local X Rotation",
        default=math.radians(90.0),
        subtype='ANGLE',
        unit='ROTATION',
    )
    use_multi_tick: BoolProperty(name="Split Across Multiple Ticks", default=True)
    busy: BoolProperty(default=False, options={'HIDDEN'})
    can_cancel: BoolProperty(default=False, options={'HIDDEN'})
    cancel_requested: BoolProperty(default=False, options={'HIDDEN'})
    progress: FloatProperty(default=0.0, min=0.0, max=1.0, subtype='FACTOR')
    eta: StringProperty(default="", options={'HIDDEN'})
    phase: StringProperty(default="Ready", options={'HIDDEN'})
    status: StringProperty(default="Ready", options={'HIDDEN'})
    csv_count: IntProperty(default=0, min=0, options={'HIDDEN'})
    csv_name_count: IntProperty(default=0, min=0, options={'HIDDEN'})
    fbx_mesh_count: IntProperty(default=0, min=0, options={'HIDDEN'})
    generated_count: IntProperty(default=0, min=0, options={'HIDDEN'})
    missing_count: IntProperty(default=0, min=0, options={'HIDDEN'})
    elapsed_seconds: FloatProperty(default=0.0, options={'HIDDEN'})


class CSVMI_OT_import_csv(Operator):
    bl_idname = "csvmi.import_csv"
    bl_label = "Import CSV"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        props = getattr(context.scene, "csvmi_props", None)
        return props is not None and not props.busy and bool(props.csv_path.strip())

    def execute(self, context):
        props = context.scene.csvmi_props
        path = absolute_path(props.csv_path)
        try:
            set_running(props, "Reading CSV", False)
            if not os.path.isfile(path):
                raise ValueError("CSV file not found.")
            data = parse_csv_file(path)
            _CSV_CACHE[scene_key(context.scene)] = data
            props.csv_count = len(data.rows)
            props.csv_name_count = len(data.unique_names)
            props.progress = 1.0
            props.phase = "CSV loaded"
            props.status = (
                f"CSV imported: {len(data.rows):,} rows / "
                f"{len(data.unique_names):,} object names"
            )
            self.report({'INFO'}, props.status)
            return {'FINISHED'}
        except Exception as exc:
            clear_csv_cache(context.scene)
            props.csv_count = 0
            props.csv_name_count = 0
            props.phase = "CSV error"
            props.status = str(exc)
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        finally:
            set_idle(props)


class CSVMI_OT_import_fbx(Operator):
    bl_idname = "csvmi.import_fbx"
    bl_label = "Import FBX"
    bl_options = {'REGISTER'}

    _timer = None

    @classmethod
    def poll(cls, context):
        props = getattr(context.scene, "csvmi_props", None)
        return props is not None and not props.busy and bool(props.fbx_path.strip())

    def execute(self, context):
        props = context.scene.csvmi_props
        self._path = absolute_path(props.fbx_path)
        self._desired_name = props.fbx_collection_name.strip()
        if not os.path.isfile(self._path):
            self.report({'ERROR'}, "FBX file not found.")
            return {'CANCELLED'}
        if not self._desired_name:
            self.report({'ERROR'}, "Source Collection name is empty.")
            return {'CANCELLED'}
        old = props.fbx_collection
        if old is not None and old.name not in bpy.data.collections:
            old = None
        existing = bpy.data.collections.get(self._desired_name)
        if existing is not None and existing != old:
            if bool(existing.get(FBX_MANAGED_KEY, False)):
                old = existing
            else:
                self.report({'ERROR'}, "A regular Collection already uses this source name.")
                return {'CANCELLED'}
        self._old_collection = old
        set_running(props, "Preparing FBX import", True)
        tag_view3d_redraw(context)
        if bpy.app.background or context.window is None:
            try:
                return self._import(context)
            finally:
                set_idle(props)
        self._timer = context.window_manager.event_timer_add(
            0.05, window=context.window
        )
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        props = context.scene.csvmi_props
        if event.type == 'ESC':
            props.cancel_requested = True
        if event.type != 'TIMER':
            return {'RUNNING_MODAL'}
        try:
            if props.cancel_requested:
                props.phase = "Cancelled"
                props.status = "FBX import cancelled before it started."
                return {'CANCELLED'}
            return self._import(context)
        finally:
            if self._timer is not None:
                context.window_manager.event_timer_remove(self._timer)
                self._timer = None
            set_idle(props)
            tag_view3d_redraw(context)

    def _import(self, context):
        scene = context.scene
        props = scene.csvmi_props
        before_objects = {obj.as_pointer() for obj in bpy.data.objects}
        before_collections = {collection.as_pointer() for collection in bpy.data.collections}
        before_meshes = {mesh.as_pointer() for mesh in bpy.data.meshes}
        temp = bpy.data.collections.new("__CSVMI_FBX_IMPORT__")
        scene.collection.children.link(temp)
        transaction = FbxImportTransaction(self._old_collection)
        try:
            transaction.prepare()
            props.phase = "Importing FBX"
            tag_view3d_redraw(context)
            result = bpy.ops.wm.fbx_import(
                filepath=self._path,
                use_anim=False,
                validate_meshes=True,
            )
            if 'FINISHED' not in result:
                raise RuntimeError("Blender did not complete the FBX import.")
            new_objects = [
                obj for obj in bpy.data.objects if obj.as_pointer() not in before_objects
            ]
            new_collections = [
                collection
                for collection in bpy.data.collections
                if collection.as_pointer() not in before_collections and collection != temp
            ]
            mesh_objects = [obj for obj in new_objects if obj.type == 'MESH']
            if not mesh_objects:
                raise RuntimeError("The FBX contains no Mesh objects.")
            for obj in new_objects:
                if temp not in obj.users_collection:
                    temp.objects.link(obj)
                for collection in list(obj.users_collection):
                    if collection != temp:
                        collection.objects.unlink(obj)
            for collection in reversed(new_collections):
                if collection.name in bpy.data.collections:
                    bpy.data.collections.remove(collection)
            transaction.normalize_new(new_objects)
            temp.name = self._desired_name
            temp[FBX_MANAGED_KEY] = True
            temp[FBX_PATH_KEY] = self._path
            if self._old_collection is not None:
                remove_collection_objects(self._old_collection)
            transaction.commit()
            cleanup_previous_meshes()
            hidden_by_layer = hide_source_collection(scene, temp)
            props.fbx_collection = temp
            props.fbx_mesh_count = len(mesh_objects)
            props.progress = 1.0
            props.phase = "FBX loaded"
            props.status = f"FBX imported: {len(mesh_objects):,} Mesh objects"
            props.status += (
                " / excluded from View Layers"
                if hidden_by_layer
                else " / source Collection hidden"
            )
            self.report({'INFO'}, props.status)
            return {'FINISHED'}
        except Exception as exc:
            traceback.print_exc()
            new_objects = [
                obj for obj in bpy.data.objects if obj.as_pointer() not in before_objects
            ]
            new_collections = [
                collection
                for collection in bpy.data.collections
                if collection.as_pointer() not in before_collections and collection != temp
            ]
            new_meshes = [
                mesh for mesh in bpy.data.meshes if mesh.as_pointer() not in before_meshes
            ]
            cleanup_imported_data(new_objects, new_collections, new_meshes, temp)
            transaction.restore()
            props.phase = "FBX error"
            props.status = f"FBX import failed: {exc}"
            self.report({'ERROR'}, props.status)
            return {'CANCELLED'}


class CSVMI_OT_place(Operator):
    bl_idname = "csvmi.place"
    bl_label = "Place / Replace Objects"
    bl_options = {'REGISTER'}

    _timer = None
    _task = None

    @classmethod
    def poll(cls, context):
        props = getattr(context.scene, "csvmi_props", None)
        return props is not None and not props.busy

    def execute(self, context):
        scene = context.scene
        props = scene.csvmi_props
        cache = get_csv_cache(scene)
        if cache is None:
            self.report({'ERROR'}, "Import a CSV file first.")
            return {'CANCELLED'}
        if csv_cache_is_stale(cache):
            self.report({'ERROR'}, "The CSV file changed. Import it again.")
            return {'CANCELLED'}
        source = props.fbx_collection
        if (
            source is None
            or source.name not in bpy.data.collections
            or not bool(source.get(FBX_MANAGED_KEY, False))
        ):
            self.report({'ERROR'}, "Import an FBX file first.")
            return {'CANCELLED'}
        output_name = props.output_collection_name.strip()
        if not output_name:
            self.report({'ERROR'}, "Output Collection name is empty.")
            return {'CANCELLED'}
        old_output = bpy.data.collections.get(output_name)
        if old_output is not None:
            if not bool(old_output.get(OUTPUT_MANAGED_KEY, False)):
                self.report({'ERROR'}, "A regular or older output Collection uses this name.")
                return {'CANCELLED'}
            if int(old_output.get(OUTPUT_VERSION_KEY, 0)) != OUTPUT_VERSION:
                self.report({'ERROR'}, "The existing output is not a v3 output. Remove it or use another name.")
                return {'CANCELLED'}
            if old_output.children:
                self.report({'ERROR'}, "The v3 output unexpectedly contains child Collections.")
                return {'CANCELLED'}
        source_objects, _exact, _normalized = build_source_index(
            source, props.ignore_numeric_suffix
        )
        if not source_objects:
            self.report({'ERROR'}, "The FBX source contains no Mesh objects.")
            return {'CANCELLED'}
        self._task = PlacementTask(scene, cache, source, old_output)
        _ACTIVE_TASKS[scene_key(scene)] = self._task
        set_running(props, "Placing objects", old_output is None)
        if not props.use_multi_tick or bpy.app.background or context.window is None:
            try:
                budget = TARGET_TICK_SECONDS if props.use_multi_tick else None
                while not self._task.step(budget):
                    pass
                return {'CANCELLED'} if self._task.cancelled else {'FINISHED'}
            except Exception as exc:
                traceback.print_exc()
                self._task.fail(str(exc))
                self.report({'ERROR'}, str(exc))
                return {'CANCELLED'}
            finally:
                _ACTIVE_TASKS.pop(scene_key(scene), None)
                set_idle(props)
        self._timer = context.window_manager.event_timer_add(
            TIMER_INTERVAL_SECONDS, window=context.window
        )
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        props = context.scene.csvmi_props
        if event.type == 'ESC' and props.can_cancel:
            props.cancel_requested = True
        if event.type != 'TIMER':
            return {'RUNNING_MODAL'}
        try:
            if not self._task.step(TARGET_TICK_SECONDS):
                return {'RUNNING_MODAL'}
            return {'CANCELLED'} if self._task.cancelled else {'FINISHED'}
        except Exception as exc:
            traceback.print_exc()
            self._task.fail(str(exc))
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        finally:
            if self._task.done:
                if self._timer is not None:
                    context.window_manager.event_timer_remove(self._timer)
                    self._timer = None
                _ACTIVE_TASKS.pop(scene_key(context.scene), None)
                set_idle(props)
                tag_view3d_redraw(context)


class CSVMI_OT_cancel(Operator):
    bl_idname = "csvmi.cancel"
    bl_label = "Cancel"

    @classmethod
    def poll(cls, context):
        props = getattr(context.scene, "csvmi_props", None)
        return props is not None and props.busy and props.can_cancel

    def execute(self, context):
        context.scene.csvmi_props.cancel_requested = True
        return {'FINISHED'}


class CSVMI_PT_panel(Panel):
    bl_label = "CSV Mesh Instancer"
    bl_idname = "CSVMI_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "CSV Instancer"

    def draw(self, context):
        layout = self.layout
        props = context.scene.csvmi_props
        if props.busy:
            box = layout.box()
            box.label(text=props.phase, icon='TIME')
            box.prop(props, "progress", text="Progress", slider=True)
            if props.eta:
                box.label(text=props.eta)
            if props.can_cancel:
                box.operator("csvmi.cancel", icon='CANCEL')
            return

        csv_box = layout.box()
        csv_box.label(text="1. CSV", icon='FILE_TEXT')
        csv_box.prop(props, "csv_path", text="")
        csv_box.operator("csvmi.import_csv", icon='IMPORT')
        cache = get_csv_cache(context.scene)
        if cache is not None:
            csv_box.label(
                text=f"{len(cache.rows):,} rows / {len(cache.unique_names):,} names",
                icon='CHECKMARK',
            )
            if csv_cache_is_stale(cache):
                csv_box.label(text="File changed. Import again.", icon='ERROR')

        fbx_box = layout.box()
        fbx_box.label(text="2. FBX", icon='MESH_DATA')
        fbx_box.prop(props, "fbx_path", text="")
        fbx_box.prop(props, "fbx_collection_name")
        fbx_box.operator("csvmi.import_fbx", icon='IMPORT')
        if props.fbx_collection is not None:
            fbx_box.label(
                text=f"{int(props.fbx_mesh_count):,} Mesh objects loaded",
                icon='CHECKMARK',
            )

        place_box = layout.box()
        place_box.label(text="3. Placement", icon='OUTLINER_COLLECTION')
        place_box.prop(props, "output_collection_name")
        place_box.prop(props, "ignore_numeric_suffix")
        place_box.prop(props, "apply_fbx_correction")
        if props.apply_fbx_correction:
            correction = place_box.column(align=True)
            correction.prop(props, "fbx_unit_scale")
            correction.prop(props, "fbx_rotation_x")
        place_box.prop(props, "use_multi_tick")
        place_box.operator("csvmi.place", icon='PLAY')

        if props.status and props.status != "Ready":
            status = layout.box()
            status.label(text=props.status, icon='INFO')
            if props.generated_count or props.missing_count:
                status.label(
                    text=(
                        f"Generated {int(props.generated_count):,} / "
                        f"Missing {int(props.missing_count):,} / "
                        f"{props.elapsed_seconds:.2f}s"
                    )
                )


CLASSES = (
    CSVMI_Props,
    CSVMI_OT_import_csv,
    CSVMI_OT_import_fbx,
    CSVMI_OT_place,
    CSVMI_OT_cancel,
    CSVMI_PT_panel,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.csvmi_props = PointerProperty(type=CSVMI_Props)


def unregister():
    for task in list(_ACTIVE_TASKS.values()):
        try:
            task.abort()
        except Exception:
            pass
    _ACTIVE_TASKS.clear()
    _CSV_CACHE.clear()
    if hasattr(bpy.types.Scene, "csvmi_props"):
        del bpy.types.Scene.csvmi_props
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
