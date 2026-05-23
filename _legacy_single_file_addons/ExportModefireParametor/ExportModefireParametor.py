bl_info = {
    "name": "GN Modifier Param CSV Export (N-Panel)",
    "author": "ChatGPT",
    "version": (1, 0, 0),
    "blender": (5, 0, 1),
    "location": "View3D > Sidebar (N) > GN CSV Export",
    "description": "Export selected objects' Geometry Nodes modifier parameters to CSV",
    "category": "3D View",
}

import bpy
import csv
from bpy.types import Panel, Operator, PropertyGroup
from bpy.props import (
    StringProperty,
    CollectionProperty,
    BoolProperty,
    PointerProperty,
)
from bpy_extras.io_utils import ExportHelper


# -----------------------------
# Helpers
# -----------------------------
def _get_active_obj(context):
    return context.view_layer.objects.active


def _find_modifier(obj, mod_name: str):
    if not obj:
        return None
    if not mod_name:
        return None
    return obj.modifiers.get(mod_name)


def _get_gn_node_group(mod):
    # Geometry Nodes modifier usually has node_group
    if not mod:
        return None
    return getattr(mod, "node_group", None)


def _iter_gn_input_sockets(node_group):
    """Try to enumerate Geometry Nodes group input interface sockets robustly across versions."""
    if not node_group:
        return []

    # Newer interface API
    try:
        iface = getattr(node_group, "interface", None)
        items_tree = getattr(iface, "items_tree", None) if iface else None
        if items_tree:
            sockets = []
            for item in items_tree:
                if getattr(item, "item_type", None) == 'SOCKET' and getattr(item, "in_out", None) == 'INPUT':
                    sockets.append(item)
            return sockets
    except Exception:
        pass

    # Fallback: older API (may or may not exist)
    try:
        # node_group.inputs exists in some versions
        return list(getattr(node_group, "inputs", []))
    except Exception:
        return []


def _resolve_identifier(node_group, key: str):
    """
    If user types the visible name, try to resolve to an internal identifier.
    Returns identifier string or None.
    """
    if not node_group or not key:
        return None

    sockets = _iter_gn_input_sockets(node_group)
    for s in sockets:
        s_name = getattr(s, "name", "")
        s_ident = getattr(s, "identifier", None)  # interface item sockets often have identifier
        # Some socket objects might not have identifier; fallback to name
        if key == s_name or (s_ident and key == s_ident):
            return s_ident if s_ident else s_name

    return None


def _get_param_value(obj, mod, param_key: str):
    """
    Try to get Geometry Nodes modifier param value by:
    1) direct modifier idprop key (identifier)
    2) resolve by GN interface socket name -> identifier
    3) case-insensitive key match in modifier keys
    """
    if not obj or not mod or not param_key:
        return None

    # Direct key
    try:
        if param_key in mod.keys():
            return mod.get(param_key)
    except Exception:
        pass

    ng = _get_gn_node_group(mod)
    ident = _resolve_identifier(ng, param_key)
    if ident:
        try:
            if ident in mod.keys():
                return mod.get(ident)
        except Exception:
            pass

    # Case-insensitive fallback
    try:
        lower = param_key.lower()
        for k in mod.keys():
            if str(k).lower() == lower:
                return mod.get(k)
    except Exception:
        pass

    return None


def _value_to_csv_cell(v):
    """Convert Blender values to something CSV-friendly."""
    if v is None:
        return ""
    # ID datablock (Object, Collection, Material, etc.)
    if hasattr(v, "name") and isinstance(getattr(v, "name", None), str):
        # But avoid strings that just happen to have name attr? Typically datablocks do.
        # This is okay for CSV.
        return v.name

    # mathutils types or sequences
    if isinstance(v, (tuple, list)):
        return ";".join(str(x) for x in v)

    # Some Blender properties return mathutils.Vector/Color which behave like sequences
    try:
        # Vector/Color has __len__ and is iterable
        if hasattr(v, "__len__") and hasattr(v, "__iter__") and not isinstance(v, (str, bytes)):
            # Avoid iterating over things like matrices? still ok; will be flattened.
            return ";".join(str(x) for x in list(v))
    except Exception:
        pass

    return str(v)


# -----------------------------
# Properties
# -----------------------------
class GNCSV_ParamItem(PropertyGroup):
    param_name: StringProperty(
        name="Param",
        description="Geometry Nodes modifier input name (as shown in UI) or identifier",
        default="",
    )


class GNCSV_Settings(PropertyGroup):
    modifier_name: StringProperty(
        name="Modifier Name",
        description="Target modifier name (usually a Geometry Nodes modifier)",
        default="GeometryNodes",
    )
    params: CollectionProperty(type=GNCSV_ParamItem)
    include_header: BoolProperty(
        name="Include Header",
        default=True,
    )
    export_selected_objects: BoolProperty(
        name="Export All Selected Objects",
        description="If ON, export all selected objects (rows). If OFF, export only active object.",
        default=True,
    )


# -----------------------------
# Operators
# -----------------------------
class GNCSV_OT_add_param(Operator):
    bl_idname = "gncsv.add_param"
    bl_label = "Add Param"
    bl_description = "Add a parameter row"

    def execute(self, context):
        s = context.scene.gncsv_settings
        s.params.add()
        return {'FINISHED'}


class GNCSV_OT_clear_params(Operator):
    bl_idname = "gncsv.clear_params"
    bl_label = "Clear"
    bl_description = "Clear all parameters"

    def execute(self, context):
        s = context.scene.gncsv_settings
        s.params.clear()
        return {'FINISHED'}


class GNCSV_OT_populate_from_modifier(Operator):
    bl_idname = "gncsv.populate_from_modifier"
    bl_label = "Populate from GN Inputs"
    bl_description = "Auto-fill parameter list from the Geometry Nodes group interface inputs"

    def execute(self, context):
        s = context.scene.gncsv_settings
        obj = _get_active_obj(context)
        mod = _find_modifier(obj, s.modifier_name)
        if not obj or not mod:
            self.report({'WARNING'}, "Active object or modifier not found.")
            return {'CANCELLED'}

        ng = _get_gn_node_group(mod)
        if not ng:
            self.report({'WARNING'}, "Modifier has no node_group (not a Geometry Nodes modifier?)")
            return {'CANCELLED'}

        sockets = _iter_gn_input_sockets(ng)
        if not sockets:
            self.report({'WARNING'}, "No GN input sockets found in node group interface.")
            return {'CANCELLED'}

        s.params.clear()
        for sock in sockets:
            item = s.params.add()
            # Use visible name (user-friendly)
            item.param_name = getattr(sock, "name", "")
        return {'FINISHED'}


class GNCSV_OT_set_modifier_from_active(Operator):
    bl_idname = "gncsv.set_modifier_from_active"
    bl_label = "Use Active GN Modifier"
    bl_description = "Set Modifier Name to the first Geometry Nodes modifier on the active object"

    def execute(self, context):
        s = context.scene.gncsv_settings
        obj = _get_active_obj(context)
        if not obj:
            self.report({'WARNING'}, "No active object.")
            return {'CANCELLED'}

        for m in obj.modifiers:
            if m.type == 'NODES':
                s.modifier_name = m.name
                return {'FINISHED'}

        self.report({'WARNING'}, "No Geometry Nodes modifier (type NODES) found on active object.")
        return {'CANCELLED'}


class GNCSV_OT_export_csv(Operator, ExportHelper):
    bl_idname = "gncsv.export_csv"
    bl_label = "Export CSV"
    bl_description = "Export specified modifier parameters to CSV"

    filename_ext = ".csv"
    filter_glob: StringProperty(default="*.csv", options={'HIDDEN'})

    def execute(self, context):
        s = context.scene.gncsv_settings

        # Decide objects to export
        if s.export_selected_objects:
            objects = [o for o in context.selected_objects if o.type != 'EMPTY' or True]
            # If nothing selected, fallback to active
            if not objects:
                obj = _get_active_obj(context)
                objects = [obj] if obj else []
        else:
            obj = _get_active_obj(context)
            objects = [obj] if obj else []

        if not objects:
            self.report({'ERROR'}, "No objects to export.")
            return {'CANCELLED'}

        # Collect param names (as user typed)
        param_names = [p.param_name.strip() for p in s.params if p.param_name.strip()]
        if not param_names:
            self.report({'ERROR'}, "No parameters specified.")
            return {'CANCELLED'}

        # Write CSV (UTF-8 with BOM for Excel compatibility)
        try:
            with open(self.filepath, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)

                if s.include_header:
                    writer.writerow(["Object"] + param_names)

                for obj in objects:
                    mod = _find_modifier(obj, s.modifier_name)
                    if not mod:
                        # Still write row with empty values
                        row = [obj.name] + ["" for _ in param_names]
                        writer.writerow(row)
                        continue

                    row = [obj.name]
                    for key in param_names:
                        v = _get_param_value(obj, mod, key)
                        row.append(_value_to_csv_cell(v))
                    writer.writerow(row)

        except Exception as e:
            self.report({'ERROR'}, f"Failed to export CSV: {e}")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Exported CSV: {self.filepath}")
        return {'FINISHED'}


# -----------------------------
# UI Panel
# -----------------------------
class VIEW3D_PT_gncsv_export_panel(Panel):
    bl_label = "GN CSV Export"
    bl_idname = "VIEW3D_PT_gncsv_export_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "GN CSV Export"

    def draw(self, context):
        layout = self.layout
        s = context.scene.gncsv_settings
        obj = _get_active_obj(context)

        col = layout.column(align=True)
        col.label(text="Target Modifier (Geometry Nodes):")
        row = col.row(align=True)
        row.prop(s, "modifier_name", text="")
        row.operator("gncsv.set_modifier_from_active", text="", icon='EYEDROPPER')

        col.separator()

        box = layout.box()
        box.label(text="Parameters (CSV columns after Object):")
        row = box.row(align=True)
        row.operator("gncsv.add_param", icon='ADD', text="Add Param")
        row.operator("gncsv.clear_params", icon='TRASH', text="Clear")
        box.operator("gncsv.populate_from_modifier", icon='NODETREE', text="Populate from GN Inputs (active object)")

        # Show current values in N-panel
        if not obj:
            box.label(text="No active object.", icon='ERROR')
            return

        mod = _find_modifier(obj, s.modifier_name)
        if not mod:
            box.label(text=f"Modifier '{s.modifier_name}' not found on active object.", icon='ERROR')
        else:
            # Parameter rows
            for i, p in enumerate(s.params):
                row = box.row(align=True)
                row.prop(p, "param_name", text="")

                v = _get_param_value(obj, mod, p.param_name.strip())
                row.label(text=_value_to_csv_cell(v))

        layout.separator()
        layout.prop(s, "export_selected_objects")
        layout.prop(s, "include_header")
        layout.operator("gncsv.export_csv", icon='EXPORT')


# -----------------------------
# Register
# -----------------------------
classes = (
    GNCSV_ParamItem,
    GNCSV_Settings,
    GNCSV_OT_add_param,
    GNCSV_OT_clear_params,
    GNCSV_OT_populate_from_modifier,
    GNCSV_OT_set_modifier_from_active,
    GNCSV_OT_export_csv,
    VIEW3D_PT_gncsv_export_panel,
)

def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.gncsv_settings = PointerProperty(type=GNCSV_Settings)

def unregister():
    if hasattr(bpy.types.Scene, "gncsv_settings"):
        del bpy.types.Scene.gncsv_settings
    for c in reversed(classes):
        bpy.utils.unregister_class(c)

if __name__ == "__main__":
    register()
