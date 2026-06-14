bl_info = {
    "name": "Unreal Bridge Tools",
    "author": "Overnight Artelier",
    "version": (2, 2, 18),
    "blender": (4, 2, 0),
    "location": "3D Viewport > N Panel > Unreal Bridge Tools",
    "description": "Export transforms & collision tags from Blender to CSV for Unreal Engine PCG pipeline.",
    "warning": "",
    "doc_url": "https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/_Taiyo_Blender_Extensions_Repo/unreal_bridge_tools/Unreal_Bridge_Tools_%E4%BD%BF%E7%94%A8%E6%9B%B8.md",
    "category": "Import-Export",
}

DOCUMENTATION_URL = "https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/_Taiyo_Blender_Extensions_Repo/unreal_bridge_tools/Unreal_Bridge_Tools_%E4%BD%BF%E7%94%A8%E6%9B%B8.md"

import bpy, os, csv, re, tempfile, datetime, time
from bpy_extras.io_utils import ExportHelper, ImportHelper
from bpy.props import (
    StringProperty, PointerProperty, BoolProperty, EnumProperty,
    CollectionProperty, IntProperty
)
from bpy.types import Operator, Panel, AddonPreferences, PropertyGroup, UIList
from math import pi

try:
    from . import preset_utils
except ImportError:
    import preset_utils

# Regex for numeric suffix .001+
_NUM_SUFFIX_RE = re.compile(r"\.(\d{3,})$")
_COLL = "-coll"
EXPORT_TIMER_INTERVAL = 0.02
EXPORT_SECONDS_PER_TICK = 0.024
EXPORT_PROGRESS_INTERVAL = 0.18
EXPORT_INITIAL_ITEMS_PER_TICK = 256
EXPORT_MIN_ITEMS_PER_TICK = 4
EXPORT_MAX_ITEMS_PER_TICK = 32768
EXPORT_RATE_SMOOTHING = 0.45
_EXPORT_RUNNING = False
_EMPTY_PRESET_ENUM_ITEMS = [("__NONE__", "No Presets", "No presets are available")]
_PRESET_ENUM_CACHE = None
_PRESET_ENUM_RETIRED_ITEMS = []

# -----------------------------
# Preferences
# -----------------------------
class UBT_AddonPreferences(AddonPreferences):
    bl_idname = __package__ or __name__
    default_export_path: StringProperty(
        name="Default Export Path",
        subtype='FILE_PATH',
        default="//exports/TransformData.csv"
    )
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "default_export_path")
        layout.separator()
        layout.label(text="Documentation")
        op = layout.operator("wm.url_open", text="Open User Guide on GitHub", icon="URL")
        op.url = DOCUMENTATION_URL

# -----------------------------
# Helpers
# -----------------------------
def _iter_collection_objects(coll, recursive=True, seen=None):
    if seen is None:
        seen = set()
    for ob in coll.objects:
        if ob.name not in seen:
            seen.add(ob.name)
            yield ob
    if recursive:
        for child in coll.children:
            yield from _iter_collection_objects(child, recursive=recursive, seen=seen)

def _iter_all_scene_objects(context):
    seen = set()
    layer = context.view_layer.layer_collection
    def walk(lc):
        coll = lc.collection
        for ob in coll.objects:
            if ob.name not in seen:
                seen.add(ob.name)
                yield ob
        for ch in lc.children:
            yield from walk(ch)
    yield from walk(layer)

def ci_remove_all(text: str, sub: str) -> str:
    return re.sub(re.escape(sub), "", text, flags=re.IGNORECASE)

def contains_coll(name: str, case_sensitive=False) -> bool:
    return (_COLL if case_sensitive else _COLL.lower()) in (name if case_sensitive else name.lower())

def _contains(name, key, case_sensitive=False):
    if not key:
        return True
    if not case_sensitive:
        name = name.lower(); key = key.lower()
    return key in name

def name_filters_pass(name: str, items, case_sensitive=False) -> bool:
    return name_filters_pass_values(
        name,
        [(it.mode, it.text) for it in items],
        case_sensitive=case_sensitive,
    )

def name_filters_pass_values(name: str, items, case_sensitive=False) -> bool:
    includes, excludes = compile_name_filters(items, case_sensitive)
    return compiled_name_filters_pass(
        name,
        includes,
        excludes,
        case_sensitive=case_sensitive,
    )

def compile_name_filters(items, case_sensitive=False):
    includes = []
    excludes = []
    for mode, text in items:
        if not text:
            continue
        value = text if case_sensitive else text.lower()
        if mode == 'include':
            includes.append(value)
        elif mode == 'exclude':
            excludes.append(value)
    return includes, excludes

def compiled_name_filters_pass(name, includes, excludes, case_sensitive=False):
    if not case_sensitive:
        name = name.lower()
    for text in excludes:
        if text in name:
            return False
    if includes:
        for text in includes:
            if text in name:
                return True
        return False
    return True

def _count_collection_objects(coll, recursive=True):
    seen = set()
    stack = [coll]
    while stack:
        current = stack.pop()
        for ob in current.objects:
            if ob.name not in seen:
                seen.add(ob.name)
        if recursive:
            stack.extend(current.children)
    return len(seen)

def _estimate_object_count(context, scope, collection):
    if scope == 'all':
        return len(context.view_layer.objects)
    if collection is None:
        return 0
    if scope == 'direct':
        return len(collection.objects)
    return _count_collection_objects(collection, recursive=True)

def _set_status_text(context, text=None):
    workspace = getattr(context, "workspace", None)
    if workspace is None:
        return
    try:
        workspace.status_text_set(text)
    except Exception:
        pass

def _redraw_view3d(context):
    screen = getattr(context, "screen", None)
    if screen is None:
        return
    for area in screen.areas:
        if area.type == "VIEW_3D":
            area.tag_redraw()

def _clamp_int(value, minimum, maximum):
    return max(minimum, min(maximum, int(value)))

def _format_eta(seconds):
    if seconds is None:
        return "--"
    seconds = max(0, int(round(seconds)))
    if seconds >= 3600:
        hours, remainder = divmod(seconds, 3600)
        minutes = remainder // 60
        return f"{hours}h {minutes:02d}m"
    if seconds >= 60:
        minutes, seconds = divmod(seconds, 60)
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"

def _enforce_csv_ext(path: str) -> str:
    base, ext = os.path.splitext(path)
    return base + ".csv" if ext.lower() != ".csv" else path

def _safe_temp_csv_path() -> str:
    base = "UnrealBridge_Export_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".csv"
    tmp_dir = bpy.app.tempdir or tempfile.gettempdir()
    return os.path.join(tmp_dir, base)

def strip_numeric_suffix(name: str) -> str:
    return _NUM_SUFFIX_RE.sub("", name)

def preset_enum_items(_self, _context):
    global _PRESET_ENUM_CACHE
    try:
        presets = preset_utils.load_presets()
    except Exception:
        presets = []
    if not presets:
        return _EMPTY_PRESET_ENUM_ITEMS

    signature = tuple(preset["name"] for preset in presets)
    if (
        _PRESET_ENUM_CACHE is not None
        and _PRESET_ENUM_CACHE["signature"] == signature
    ):
        return _PRESET_ENUM_CACHE["items"]

    items = [
        (preset["name"], preset["name"], f"{len(preset['filters'])} filter(s)")
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
    selected = getattr(self, "selected_preset", "")
    self.preset_name = "" if selected == "__NONE__" else selected

# -----------------------------
# Name Filters
# -----------------------------
class UBT_FilterItem(PropertyGroup):
    text: StringProperty(name="Text", default="")
    mode: EnumProperty(
        name="Mode",
        items=[('include', "Include", ""), ('exclude', "Exclude", "")],
        default='include'
    )

class UBT_UL_Filters(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.prop(item, "text", text="", emboss=True)
        row.prop(item, "mode", text="")

# -----------------------------
# Properties
# -----------------------------
class UBT_Props(PropertyGroup):
    selected_preset: EnumProperty(
        name="Preset",
        items=preset_enum_items,
        update=selected_preset_updated,
    )
    preset_name: StringProperty(
        name="Preset Name",
        default=""
    )
    collection: PointerProperty(
        name="Target Collection",
        type=bpy.types.Collection
    )
    export_path: StringProperty(
        name="Export CSV",
        subtype='FILE_PATH',
        default=""
    )

    # --- NEW: name_mode (Keep Raw added, legacy Keep removed) ---
    name_mode: EnumProperty(
        name="Name Normalize",
        items=[
            ('keep_raw', "Keep Raw (No Change)", "Export name exactly, including .001 or anything."),
            ('numeric_suffix', "Remove Numeric Suffix (.001+)", "Remove trailing .###"),
            ('trim_after_dot', "Trim After Dot", "Remove everything after the last '.'"),
        ],
        default='keep_raw'
    )

    scope: EnumProperty(
        name="Scope",
        items=[
            ('direct', "Direct Only", ""),
            ('recursive', "Recursive", ""),
            ('all', "All Collections", ""),
        ],
        default='recursive'
    )

    select_visible_only: BoolProperty(
        name="Visible Only",
        default=True
    )
    case_sensitive: BoolProperty(
        name="Case Sensitive",
        default=False
    )

    filters: CollectionProperty(type=UBT_FilterItem)
    filters_index: IntProperty(default=0)

# -----------------------------
# Operators (filter add/remove)
# -----------------------------
class UBT_OT_FilterAdd(Operator):
    bl_idname = "ubt.filter_add"
    bl_label = "Add Filter"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        p = context.scene.ubt_props
        it = p.filters.add()
        it.text = ""
        it.mode = 'include'
        p.filters_index = len(p.filters)-1
        return {'FINISHED'}

class UBT_OT_FilterRemove(Operator):
    bl_idname = "ubt.filter_remove"
    bl_label = "Remove Filter"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        p = context.scene.ubt_props
        if p.filters and 0 <= p.filters_index < len(p.filters):
            p.filters.remove(p.filters_index)
            p.filters_index = max(0, p.filters_index-1)
        return {'FINISHED'}

# -----------------------------
# Presets
# -----------------------------
def _selected_preset(settings):
    name = settings.selected_preset
    if not name or name == "__NONE__":
        return None
    return preset_utils.find_preset(preset_utils.load_presets(), name)

def _load_preset_report(operator, context, preset):
    settings = context.scene.ubt_props
    missing_collection = preset_utils.load_preset_into_settings(settings, preset)
    settings.selected_preset = preset["name"]
    settings.preset_name = preset["name"]
    if missing_collection:
        operator.report(
            {'WARNING'},
            f"Loaded preset, but collection was not found: {missing_collection}",
        )
    else:
        operator.report({'INFO'}, f"Loaded preset '{preset['name']}'.")

class UBT_OT_LoadPreset(Operator):
    bl_idname = "ubt.load_preset"
    bl_label = "Load Preset"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.ubt_props
        try:
            preset = _selected_preset(settings)
        except Exception as exc:
            self.report({'ERROR'}, f"Preset load failed: {exc}")
            return {'CANCELLED'}
        if preset is None:
            self.report({'ERROR'}, "Preset not found.")
            return {'CANCELLED'}
        try:
            _load_preset_report(self, context, preset)
        except Exception as exc:
            self.report({'ERROR'}, f"Preset load failed: {exc}")
            return {'CANCELLED'}
        return {'FINISHED'}

class UBT_OT_SavePreset(Operator):
    bl_idname = "ubt.save_preset"
    bl_label = "Save Preset"
    bl_options = {'REGISTER'}

    def execute(self, context):
        settings = context.scene.ubt_props
        name = settings.selected_preset
        if not name or name == "__NONE__":
            self.report({'ERROR'}, "Select a preset or use Save As New.")
            return {'CANCELLED'}
        try:
            presets = preset_utils.load_presets()
            if preset_utils.find_preset(presets, name) is None:
                self.report({'ERROR'}, "Preset not found. Use Save As New.")
                return {'CANCELLED'}
            presets = preset_utils.upsert_preset(
                presets,
                preset_utils.settings_to_preset(settings, name),
            )
            preset_utils.save_presets(presets)
        except Exception as exc:
            self.report({'ERROR'}, f"Preset save failed: {exc}")
            return {'CANCELLED'}
        settings.selected_preset = name
        settings.preset_name = name
        self.report({'INFO'}, f"Saved preset '{name}'.")
        return {'FINISHED'}

class UBT_OT_SavePresetAs(Operator):
    bl_idname = "ubt.save_preset_as"
    bl_label = "Save As New"
    bl_options = {'REGISTER'}

    preset_name: StringProperty(name="Preset Name", default="")

    def invoke(self, context, event):
        settings = context.scene.ubt_props
        self.preset_name = (
            settings.preset_name
            if settings.preset_name
            else (settings.selected_preset if settings.selected_preset != "__NONE__" else "")
        )
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop(self, "preset_name")

    def execute(self, context):
        settings = context.scene.ubt_props
        name = self.preset_name.strip()
        if not name:
            self.report({'ERROR'}, "Preset name is empty.")
            return {'CANCELLED'}
        try:
            presets = preset_utils.load_presets()
            if preset_utils.find_preset(presets, name) is not None:
                self.report({'ERROR'}, "A preset with this name already exists. Use Save.")
                return {'CANCELLED'}
            presets = preset_utils.upsert_preset(
                presets,
                preset_utils.settings_to_preset(settings, name),
            )
            preset_utils.save_presets(presets)
        except Exception as exc:
            self.report({'ERROR'}, f"Preset save failed: {exc}")
            return {'CANCELLED'}
        settings.selected_preset = name
        settings.preset_name = name
        self.report({'INFO'}, f"Saved preset '{name}'.")
        return {'FINISHED'}

class UBT_OT_DeletePreset(Operator):
    bl_idname = "ubt.delete_preset"
    bl_label = "Delete Preset"
    bl_options = {'REGISTER'}

    def execute(self, context):
        settings = context.scene.ubt_props
        name = settings.selected_preset
        if not name or name == "__NONE__":
            self.report({'ERROR'}, "Preset not found.")
            return {'CANCELLED'}
        try:
            presets = preset_utils.load_presets()
            if preset_utils.find_preset(presets, name) is None:
                self.report({'ERROR'}, "Preset not found.")
                return {'CANCELLED'}
            remaining = preset_utils.delete_preset(presets, name)
            preset_utils.save_presets(remaining)
        except Exception as exc:
            self.report({'ERROR'}, f"Preset delete failed: {exc}")
            return {'CANCELLED'}
        settings.selected_preset = remaining[0]["name"] if remaining else "__NONE__"
        settings.preset_name = "" if not remaining else remaining[0]["name"]
        self.report({'INFO'}, f"Deleted preset '{name}'.")
        return {'FINISHED'}

class UBT_OT_ImportPresets(Operator, ImportHelper):
    bl_idname = "ubt.import_presets"
    bl_label = "Import Presets"
    bl_options = {'REGISTER'}

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={'HIDDEN'})

    def execute(self, context):
        try:
            imported = preset_utils.read_preset_file(self.filepath)
            merged = preset_utils.merge_presets(
                preset_utils.load_presets(),
                imported,
            )
            preset_utils.save_presets(merged)
        except Exception as exc:
            self.report({'ERROR'}, f"Preset import failed: {exc}")
            return {'CANCELLED'}
        if imported:
            context.scene.ubt_props.selected_preset = imported[0]["name"]
            context.scene.ubt_props.preset_name = imported[0]["name"]
        self.report({'INFO'}, f"Imported {len(imported)} preset(s).")
        return {'FINISHED'}

class UBT_OT_ExportPresets(Operator, ExportHelper):
    bl_idname = "ubt.export_presets"
    bl_label = "Export Presets"
    bl_options = {'REGISTER'}

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={'HIDDEN'})

    def invoke(self, context, event):
        if not self.filepath:
            self.filepath = "unreal_bridge_tools_presets.json"
        return super().invoke(context, event)

    def execute(self, context):
        try:
            preset_utils.write_preset_file(
                self.filepath,
                preset_utils.load_presets(),
            )
        except Exception as exc:
            self.report({'ERROR'}, f"Preset export failed: {exc}")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Exported presets to {self.filepath}.")
        return {'FINISHED'}

# -----------------------------
# Collision Tag Operations
# -----------------------------
class UBT_OT_AddColl(Operator):
    bl_idname = "ubt.add_coll"
    bl_label = "Add -coll"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        changed = 0
        for ob in context.selected_objects:
            clean = ci_remove_all(ob.name, _COLL)
            m = _NUM_SUFFIX_RE.search(clean)
            new = clean[:m.start()] + _COLL + clean[m.start():] if m else clean + _COLL
            if new != ob.name:
                ob.name = new; changed += 1
        self.report({'INFO'}, f"Adjusted {changed} object(s).")
        return {'FINISHED'}

class UBT_OT_RemoveColl(Operator):
    bl_idname = "ubt.remove_coll"
    bl_label = "Remove -coll"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        cnt = 0
        for ob in context.selected_objects:
            new = ci_remove_all(ob.name, _COLL)
            if new != ob.name:
                ob.name = new; cnt += 1
        self.report({'INFO'}, f"Removed -coll from {cnt} object(s).")
        return {'FINISHED'}

class UBT_OT_SelectWithColl(Operator):
    bl_idname = "ubt.select_with_coll"
    bl_label = "Select With -coll"
    bl_options = {'REGISTER', 'UNDO'}
    invert: BoolProperty(default=False)
    def execute(self, context):
        p = context.scene.ubt_props
        if p.scope == 'all':
            iterable = _iter_all_scene_objects(context)
        else:
            if p.collection is None:
                self.report({'ERROR'}, "Select a collection.")
                return {'CANCELLED'}
            iterable = _iter_collection_objects(p.collection, recursive=(p.scope=='recursive'))

        count = 0
        for ob in iterable:
            if p.select_visible_only and not ob.visible_get():
                continue
            if not name_filters_pass(ob.name, p.filters, p.case_sensitive):
                continue
            ok = contains_coll(ob.name, case_sensitive=p.case_sensitive)
            if self.invert:
                ok = not ok
            ob.select_set(ok)
            if ok: count += 1
        self.report({'INFO'}, f"Selected {count} object(s).")
        return {'FINISHED'}

# -----------------------------
# Test Write
# -----------------------------
class UBT_OT_TestWrite(Operator):
    bl_idname = "ubt.test_write"
    bl_label = "Test Write"
    bl_options = {'REGISTER'}
    def execute(self, context):
        p = context.scene.ubt_props
        path = bpy.path.abspath(_enforce_csv_ext(p.export_path or "//exports/TransformData.csv"))
        folder = os.path.dirname(path)
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception as e:
            self.report({'ERROR'}, f"Cannot create folder: {e}")
            return {'CANCELLED'}
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("test\n")
            os.remove(path)
            self.report({'INFO'}, f"Write OK: {path}")
        except Exception as e:
            self.report({'ERROR'}, f"Write failed: {e}")
            return {'CANCELLED'}
        return {'FINISHED'}

# -----------------------------
# Export CSV
# -----------------------------
class UBT_OT_ExportCSV(Operator):
    bl_idname = "ubt.export_csv"
    bl_label = "Export CSV"
    bl_options = {'REGISTER'}

    _timer = None
    _file = None
    _writer = None
    _iterator = None

    def invoke(self, context, event):
        if context.window is None:
            return self._run_blocking(context)
        return self._start_modal(context)

    def execute(self, context):
        return self._run_blocking(context)

    def modal(self, context, event):
        if event.type == 'ESC':
            return self._finish(context, cancelled=True)
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        try:
            has_more = self._process_tick(context)
        except Exception as exc:
            if self._try_restart_to_temp(context, exc):
                return {'PASS_THROUGH'}
            return self._finish(context, error_message=str(exc))

        self._update_progress(context)
        _redraw_view3d(context)
        if not has_more:
            return self._finish(context)
        return {'PASS_THROUGH'}

    def _start_modal(self, context):
        result = self._initialize(context)
        if result is not None:
            return result

        self._timer = context.window_manager.event_timer_add(
            EXPORT_TIMER_INTERVAL,
            window=context.window,
        )
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _run_blocking(self, context):
        result = self._initialize(context)
        if result is not None:
            return result

        try:
            while self._process_tick(context):
                self._update_progress(context)
        except Exception as exc:
            if self._try_restart_to_temp(context, exc):
                try:
                    while self._process_tick(context):
                        self._update_progress(context)
                except Exception as fallback_exc:
                    return self._finish(context, error_message=str(fallback_exc))
            else:
                return self._finish(context, error_message=str(exc))
        return self._finish(context)

    def _initialize(self, context):
        global _EXPORT_RUNNING
        if _EXPORT_RUNNING:
            self.report({'WARNING'}, "Export CSV is already running.")
            return {'CANCELLED'}

        p = context.scene.ubt_props
        addon_key = __package__ or __name__
        addon = context.preferences.addons.get(addon_key)
        prefs = addon.preferences if addon else None
        if not p.export_path and prefs is not None:
            p.export_path = prefs.default_export_path

        if p.scope == 'all':
            collection = None
        else:
            if p.collection is None:
                self.report({'ERROR'}, "Select a collection.")
                return {'CANCELLED'}
            collection = p.collection

        self._scope = p.scope
        self._collection = collection
        self._select_visible_only = p.select_visible_only
        self._case_sensitive = p.case_sensitive
        self._filter_includes, self._filter_excludes = compile_name_filters(
            [(it.mode, it.text) for it in p.filters if it.text],
            self._case_sensitive,
        )
        self._name_mode = p.name_mode
        self._total = max(1, _estimate_object_count(context, self._scope, self._collection))
        self._processed = 0
        self._exported = 0
        self._row_id = 1
        self._last_progress_time = 0.0
        self._started_time = time.perf_counter()
        self._items_per_tick = EXPORT_INITIAL_ITEMS_PER_TICK
        self._items_per_second = 0.0
        self._last_tick_seconds = 0.0
        self._using_temp = False
        self._original_error = ""
        self._iterator = self._make_iterator(context)

        export_path = bpy.path.abspath(_enforce_csv_ext(p.export_path or "//exports/TransformData.csv"))
        folder = os.path.dirname(export_path)
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception as exc:
            export_path = _safe_temp_csv_path()
            self._using_temp = True
            self._original_error = str(exc)

        try:
            self._open_export_file(export_path)
        except Exception as exc:
            fallback = _safe_temp_csv_path()
            try:
                self._using_temp = True
                self._original_error = str(exc)
                self._open_export_file(fallback)
            except Exception as fallback_exc:
                self._close_export_file()
                self.report({'ERROR'}, f"Failed: {fallback_exc}")
                return {'CANCELLED'}

        _EXPORT_RUNNING = True
        context.window_manager.progress_begin(0, self._total)
        self._update_progress(context, force=True)
        return None

    def _make_iterator(self, context):
        if self._scope == 'all':
            return _iter_all_scene_objects(context)
        return _iter_collection_objects(
            self._collection,
            recursive=(self._scope == 'recursive'),
        )

    def _open_export_file(self, path):
        self._close_export_file()
        self._export_path = path
        self._file = open(path, "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        self._writer.writerow([
            "id", "tx", "ty", "tz", "rx", "ry", "rz",
            "sx", "sy", "sz", "objname", "colname",
        ])

    def _close_export_file(self):
        file = getattr(self, "_file", None)
        self._writer = None
        self._file = None
        if file is not None:
            file.close()

    def _process_tick(self, context):
        started = time.perf_counter()
        processed_this_tick = 0
        max_items = self._items_per_tick
        while processed_this_tick < max_items:
            if not self._process_one(context):
                self._adjust_items_per_tick(processed_this_tick, started)
                return False
            processed_this_tick += 1
        self._adjust_items_per_tick(processed_this_tick, started)
        return True

    def _process_one(self, context):
        try:
            ob = next(self._iterator)
        except StopIteration:
            return False

        self._processed += 1
        if self._select_visible_only:
            try:
                if not ob.visible_get():
                    return True
            except RuntimeError:
                return True
        if not compiled_name_filters_pass(
            ob.name,
            self._filter_includes,
            self._filter_excludes,
            case_sensitive=self._case_sensitive,
        ):
            return True

        m = ob.matrix_world
        loc = m.to_translation()
        rot = m.to_euler('XYZ')
        scl = m.to_scale()
        objname = self._resolve_name(ob.name)
        colname = ob.users_collection[0].name if ob.users_collection else ""
        self._writer.writerow([
            self._row_id,
            round(loc.x, 6), round(loc.y, 6), round(loc.z, 6),
            round(rot.x * 180 / pi, 6),
            round(rot.y * 180 / pi, 6),
            round(rot.z * 180 / pi, 6),
            round(scl.x, 6), round(scl.y, 6), round(scl.z, 6),
            objname,
            colname,
        ])
        self._row_id += 1
        self._exported += 1
        return True

    def _resolve_name(self, name):
        if self._name_mode == 'numeric_suffix':
            return strip_numeric_suffix(name)
        if self._name_mode == 'trim_after_dot':
            return name.split(".", 1)[0] if "." in name else name
        return name

    def _adjust_items_per_tick(self, processed_this_tick, started):
        elapsed = max(time.perf_counter() - started, 0.000001)
        self._last_tick_seconds = elapsed
        if processed_this_tick <= 0:
            return

        instant_rate = processed_this_tick / elapsed
        if self._items_per_second > 0.0:
            self._items_per_second = (
                self._items_per_second * (1.0 - EXPORT_RATE_SMOOTHING)
                + instant_rate * EXPORT_RATE_SMOOTHING
            )
        else:
            self._items_per_second = instant_rate

        proposed = processed_this_tick * EXPORT_SECONDS_PER_TICK / elapsed
        current = max(1, self._items_per_tick)
        if elapsed < EXPORT_SECONDS_PER_TICK * 0.50:
            proposed = max(proposed, current * 2.5)
        elif elapsed < EXPORT_SECONDS_PER_TICK * 0.85:
            proposed = max(proposed, current * 1.5)
        elif elapsed > EXPORT_SECONDS_PER_TICK * 1.35:
            proposed = min(proposed, current * 0.75)

        if proposed > current:
            proposed = min(proposed, current * 3.0)
        else:
            proposed = max(proposed, current * 0.5)

        self._items_per_tick = _clamp_int(
            round(proposed),
            EXPORT_MIN_ITEMS_PER_TICK,
            EXPORT_MAX_ITEMS_PER_TICK,
        )

    def _progress_percent(self, done=False):
        if done:
            return 100.0
        return min(100.0, self._processed / max(1, self._total) * 100.0)

    def _eta_seconds(self, done=False):
        if done or self._processed >= self._total:
            return 0
        rate = self._items_per_second
        if rate <= 0.0 and self._processed:
            elapsed = max(time.perf_counter() - self._started_time, 0.000001)
            rate = self._processed / elapsed
        if rate <= 0.0:
            return None
        return max(0, self._total - self._processed) / rate

    def _update_progress(self, context, force=False, done=False):
        now = time.perf_counter()
        if not force and not done and now - self._last_progress_time < EXPORT_PROGRESS_INTERVAL:
            return
        self._last_progress_time = now
        value = self._total if done else min(self._processed, self._total)
        percent = self._progress_percent(done=done)
        eta = _format_eta(self._eta_seconds(done=done))
        context.window_manager.progress_update(value)
        _set_status_text(
            context,
            (
                f"Unreal Bridge Export: {percent:.1f}% | ETA {eta} | "
                f"{self._processed}/{self._total} scanned, {self._exported} exported | "
                f"{self._items_per_tick}/tick | ESC cancels"
            ),
        )

    def _try_restart_to_temp(self, context, exc):
        if self._using_temp or not isinstance(exc, OSError):
            return False
        self._using_temp = True
        self._original_error = str(exc)
        self._iterator = self._make_iterator(context)
        self._processed = 0
        self._exported = 0
        self._row_id = 1
        self._last_progress_time = 0.0
        self._started_time = time.perf_counter()
        self._items_per_tick = EXPORT_INITIAL_ITEMS_PER_TICK
        self._items_per_second = 0.0
        self._last_tick_seconds = 0.0
        try:
            self._open_export_file(_safe_temp_csv_path())
        except Exception:
            return False
        self._update_progress(context, force=True)
        return True

    def _finish(self, context, cancelled=False, error_message=""):
        global _EXPORT_RUNNING
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None

        if not error_message:
            try:
                self._close_export_file()
            except Exception as exc:
                error_message = str(exc)
        else:
            try:
                self._close_export_file()
            except Exception:
                pass

        try:
            self._update_progress(
                context,
                force=True,
                done=not cancelled and not error_message,
            )
            context.window_manager.progress_end()
        except RuntimeError:
            pass
        _set_status_text(context, None)
        _EXPORT_RUNNING = False

        if error_message:
            self.report({'ERROR'}, f"Failed: {error_message}")
            return {'CANCELLED'}
        if cancelled:
            self.report(
                {'WARNING'},
                f"Canceled after scanning {self._processed} object(s); partial CSV: {self._export_path}",
            )
            return {'CANCELLED'}
        if self._using_temp:
            self.report(
                {'WARNING'},
                f"Exported {self._exported} objects to temp: {self._export_path}",
            )
        else:
            self.report({'INFO'}, f"Exported {self._exported} objects -> {self._export_path}")
        return {'FINISHED'}

# -----------------------------
# UI
# -----------------------------
class UBT_PT_Main(Panel):
    bl_label = "Unreal Bridge Tools"
    bl_idname = "UBT_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Unreal Bridge Tools"

    def draw(self, context):
        layout = self.layout
        p = context.scene.ubt_props

        box = layout.box()
        box.label(text="Presets", icon="PRESET")
        box.prop(p, "selected_preset")
        row = box.row(align=True)
        row.enabled = not _EXPORT_RUNNING
        row.operator("ubt.load_preset", text="Load", icon="IMPORT")
        row.operator("ubt.save_preset", text="Save", icon="FILE_TICK")
        row.operator("ubt.save_preset_as", text="Save As New", icon="ADD")
        row = box.row(align=True)
        row.enabled = not _EXPORT_RUNNING
        row.operator("ubt.delete_preset", text="Delete", icon="TRASH")
        row.operator("ubt.import_presets", text="Import", icon="IMPORT")
        row.operator("ubt.export_presets", text="Export", icon="EXPORT")

        box = layout.box()
        box.label(text="Scope & Export")
        row = box.row(align=True)
        row.prop(p, "scope", expand=True)
        if p.scope != 'all':
            box.prop(p, "collection")
        box.prop(p, "export_path")
        box.operator("ubt.test_write", icon="FILE_TICK")

        box = layout.box()
        box.label(text="Filters")
        row = box.row()
        row.template_list("UBT_UL_Filters", "", p, "filters", p, "filters_index")
        col = row.column(align=True)
        col.operator("ubt.filter_add", icon="ADD", text="")
        col.operator("ubt.filter_remove", icon="REMOVE", text="")
        row = box.row(align=True)
        row.prop(p, "case_sensitive")
        row.prop(p, "select_visible_only")

        box = layout.box()
        box.label(text="Collision Tag")
        row = box.row(align=True)
        row.operator("ubt.add_coll", text="Add -coll", icon="ADD")
        row.operator("ubt.remove_coll", text="Remove -coll", icon="REMOVE")
        row = box.row(align=True)
        row.operator("ubt.select_with_coll", text="Select With -coll").invert = False
        row.operator("ubt.select_with_coll", text="Select Without -coll").invert = True

        box = layout.box()
        box.label(text="Name Normalization")
        box.prop(p, "name_mode")

        previous_operator_context = layout.operator_context
        layout.operator_context = 'INVOKE_DEFAULT'
        row = layout.row()
        row.enabled = not _EXPORT_RUNNING
        row.operator("ubt.export_csv", icon="EXPORT")
        layout.operator_context = previous_operator_context

# -----------------------------
# Registration
# -----------------------------
classes = (
    UBT_AddonPreferences,
    UBT_FilterItem,
    UBT_UL_Filters,
    UBT_Props,
    UBT_OT_FilterAdd,
    UBT_OT_FilterRemove,
    UBT_OT_LoadPreset,
    UBT_OT_SavePreset,
    UBT_OT_SavePresetAs,
    UBT_OT_DeletePreset,
    UBT_OT_ImportPresets,
    UBT_OT_ExportPresets,
    UBT_OT_AddColl,
    UBT_OT_RemoveColl,
    UBT_OT_SelectWithColl,
    UBT_OT_TestWrite,
    UBT_OT_ExportCSV,
    UBT_PT_Main,
)

def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.ubt_props = PointerProperty(type=UBT_Props)

def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
    del bpy.types.Scene.ubt_props
