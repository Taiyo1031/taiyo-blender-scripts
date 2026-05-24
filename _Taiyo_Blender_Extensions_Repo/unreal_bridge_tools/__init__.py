bl_info = {
    "name": "Unreal Bridge Tools",
    "author": "Overnight Artelier",
    "version": (2, 2, 15),
    "blender": (4, 2, 0),
    "location": "3D Viewport > N Panel > Unreal Bridge Tools",
    "description": "Export transforms & collision tags from Blender to CSV for Unreal Engine PCG pipeline.",
    "warning": "",
    "doc_url": "https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/_Taiyo_Blender_Extensions_Repo/unreal_bridge_tools/Unreal_Bridge_Tools_%E4%BD%BF%E7%94%A8%E6%9B%B8.md",
    "category": "Import-Export",
}

DOCUMENTATION_URL = "https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/_Taiyo_Blender_Extensions_Repo/unreal_bridge_tools/Unreal_Bridge_Tools_%E4%BD%BF%E7%94%A8%E6%9B%B8.md"

import bpy, os, csv, re, tempfile, datetime
from bpy.props import (
    StringProperty, PointerProperty, BoolProperty, EnumProperty,
    CollectionProperty, IntProperty
)
from bpy.types import Operator, Panel, AddonPreferences, PropertyGroup, UIList
from math import pi

# Regex for numeric suffix .001+
_NUM_SUFFIX_RE = re.compile(r"\.(\d{3,})$")
_COLL = "-coll"

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
    includes = [it for it in items if it.mode == 'include' and it.text]
    excludes = [it for it in items if it.mode == 'exclude' and it.text]
    for it in excludes:
        if _contains(name, it.text, case_sensitive=case_sensitive):
            return False
    if includes:
        for it in includes:
            if _contains(name, it.text, case_sensitive=case_sensitive):
                return True
        return False
    return True

def _enforce_csv_ext(path: str) -> str:
    base, ext = os.path.splitext(path)
    return base + ".csv" if ext.lower() != ".csv" else path

def _safe_temp_csv_path() -> str:
    base = "UnrealBridge_Export_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".csv"
    tmp_dir = bpy.app.tempdir or tempfile.gettempdir()
    return os.path.join(tmp_dir, base)

def strip_numeric_suffix(name: str) -> str:
    return _NUM_SUFFIX_RE.sub("", name)

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

    def invoke(self, context, event):
        prefs = context.preferences.addons[__package__].preferences
        p = context.scene.ubt_props
        if not p.export_path:
            p.export_path = prefs.default_export_path
        return self.execute(context)

    def execute(self, context):
        p = context.scene.ubt_props

        # Objects to export
        if p.scope == 'all':
            objs_iter = _iter_all_scene_objects(context)
        else:
            if p.collection is None:
                self.report({'ERROR'}, "Select a collection.")
                return {'CANCELLED'}
            objs_iter = _iter_collection_objects(p.collection, recursive=(p.scope=='recursive'))

        export_path = bpy.path.abspath(_enforce_csv_ext(p.export_path or "//exports/TransformData.csv"))
        folder = os.path.dirname(export_path)
        try:
            os.makedirs(folder, exist_ok=True)
        except:
            export_path = _safe_temp_csv_path()

        # Collect
        objs = []
        for ob in objs_iter:
            if p.select_visible_only and not ob.visible_get():
                continue
            if not name_filters_pass(ob.name, p.filters, p.case_sensitive):
                continue
            objs.append(ob)

        # Name mode helpers
        def resolve_name(ob):
            name = ob.name
            if p.name_mode == 'keep_raw':
                return name
            elif p.name_mode == 'numeric_suffix':
                return strip_numeric_suffix(name)
            elif p.name_mode == 'trim_after_dot':
                return name.split(".",1)[0] if "." in name else name
            return name

        # Write CSV
        def _write(path):
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["id","tx","ty","tz","rx","ry","rz","sx","sy","sz","objname","colname"])
                for i, ob in enumerate(objs, start=1):
                    m = ob.matrix_world
                    loc = m.to_translation()
                    rot = m.to_euler('XYZ')
                    scl = m.to_scale()
                    objname = resolve_name(ob)
                    colname = ob.users_collection[0].name if ob.users_collection else ""
                    w.writerow([
                        i,
                        round(loc.x,6), round(loc.y,6), round(loc.z,6),
                        round(rot.x*180/pi,6), round(rot.y*180/pi,6), round(rot.z*180/pi,6),
                        round(scl.x,6), round(scl.y,6), round(scl.z,6),
                        objname,
                        colname
                    ])

        try:
            _write(export_path)
            self.report({'INFO'}, f"Exported {len(objs)} objects → {export_path}")
        except:
            fallback = _safe_temp_csv_path()
            try:
                _write(fallback)
                self.report({'WARNING'}, f"Export failed. Exported to temp: {fallback}")
            except Exception as e:
                self.report({'ERROR'}, f"Failed: {e}")
                return {'CANCELLED'}

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

        layout.operator("ubt.export_csv", icon="EXPORT")

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
