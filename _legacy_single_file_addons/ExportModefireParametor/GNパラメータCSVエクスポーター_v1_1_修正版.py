bl_info = {
    "name": "GN Parameter CSV Exporter",
    "author": "ChatGPT",
    "version": (1, 1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar (N) > GN CSV Export",
    "description": "Export selected objects' Geometry Nodes modifier input parameters to CSV",
    "category": "3D View",
}

import bpy
import csv
from bpy.types import Panel, Operator, PropertyGroup
from bpy.props import (
    StringProperty,
    CollectionProperty,
    BoolProperty,
    IntProperty,
    PointerProperty,
)
from bpy_extras.io_utils import ExportHelper


# -----------------------------
# Helpers
# -----------------------------
def _get_active_obj(context):
    return context.view_layer.objects.active


def _first_gn_modifier(obj):
    if not obj:
        return None
    try:
        for mod in obj.modifiers:
            if getattr(mod, "type", None) == 'NODES':
                return mod
    except Exception:
        return None
    return None


def _find_modifier(obj, mod_name: str):
    """Find target modifier by exact name, case-insensitive name, or first GN modifier when blank."""
    if not obj:
        return None

    name = (mod_name or "").strip()
    if not name:
        return _first_gn_modifier(obj)

    try:
        mod = obj.modifiers.get(name)
        if mod:
            return mod
    except Exception:
        pass

    # Case-insensitive fallback
    try:
        lower_name = name.lower()
        for mod in obj.modifiers:
            if getattr(mod, "name", "").lower() == lower_name:
                return mod
    except Exception:
        pass

    return None


def _get_gn_node_group(mod):
    """Geometry Nodes modifiers usually expose the node tree as node_group."""
    if not mod:
        return None
    return getattr(mod, "node_group", None)


def _iter_gn_input_sockets(node_group):
    """Enumerate Geometry Nodes group input interface sockets across Blender versions."""
    if not node_group:
        return []

    # Blender 4.x+ interface API
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

    # Older/fallback API
    try:
        return list(getattr(node_group, "inputs", []))
    except Exception:
        return []


def _resolve_identifier(node_group, key: str):
    """
    Resolve a visible GN input socket name to its internal identifier.
    Users may enter either the UI name or the internal identifier.
    """
    if not node_group or not key:
        return None

    sockets = _iter_gn_input_sockets(node_group)
    for socket in sockets:
        socket_name = getattr(socket, "name", "")
        socket_identifier = getattr(socket, "identifier", None)

        if key == socket_name or (socket_identifier and key == socket_identifier):
            return socket_identifier if socket_identifier else socket_name

    return None


def _get_param_value(obj, mod, param_key: str):
    """
    Get a Geometry Nodes modifier input value by:
    1) direct modifier ID property key,
    2) visible GN socket name -> internal identifier,
    3) case-insensitive modifier key match.
    """
    if not obj or not mod or not param_key:
        return None

    # Direct key / identifier
    try:
        if param_key in mod.keys():
            return mod.get(param_key)
    except Exception:
        pass

    # Resolve from visible input name
    node_group = _get_gn_node_group(mod)
    identifier = _resolve_identifier(node_group, param_key)
    if identifier:
        try:
            if identifier in mod.keys():
                return mod.get(identifier)
        except Exception:
            pass

    # Case-insensitive fallback
    try:
        lower_key = param_key.lower()
        for key in mod.keys():
            if str(key).lower() == lower_key:
                return mod.get(key)
    except Exception:
        pass

    return None


def _value_to_csv_cell(value):
    """Convert Blender values to CSV-friendly text."""
    if value is None:
        return ""

    # Blender datablocks such as Object, Collection, Material, etc.
    if hasattr(value, "name") and isinstance(getattr(value, "name", None), str):
        return value.name

    # Tuples/lists
    if isinstance(value, (tuple, list)):
        return ";".join(str(x) for x in value)

    # mathutils.Vector / Color and other iterable value types
    try:
        if hasattr(value, "__len__") and hasattr(value, "__iter__") and not isinstance(value, (str, bytes)):
            return ";".join(str(x) for x in list(value))
    except Exception:
        pass

    return str(value)


def _collect_export_objects(context, export_selected_objects: bool):
    """Return objects to export according to the panel setting."""
    if export_selected_objects:
        objects = list(context.selected_objects)
        if objects:
            return objects

    active_obj = _get_active_obj(context)
    return [active_obj] if active_obj else []


# -----------------------------
# Properties
# -----------------------------
class GNCSV_ParamItem(PropertyGroup):
    param_name: StringProperty(
        name="Param",
        description="Geometry Nodes modifier input name as shown in the UI, or internal identifier",
        default="",
    )


class GNCSV_Settings(PropertyGroup):
    modifier_name: StringProperty(
        name="Modifier Name",
        description="Target Geometry Nodes modifier name. Leave blank to use the first GN modifier on each object.",
        default="GeometryNodes",
    )
    params: CollectionProperty(type=GNCSV_ParamItem)
    include_header: BoolProperty(
        name="Include Header",
        description="Write the first CSV row as column names: Object + parameters",
        default=True,
    )
    export_selected_objects: BoolProperty(
        name="Export All Selected Objects",
        description="ON: export every selected object as one row. OFF: export only the active object.",
        default=True,
    )


# -----------------------------
# Operators
# -----------------------------
class GNCSV_OT_add_param(Operator):
    bl_idname = "gncsv.add_param"
    bl_label = "Add Param"
    bl_description = "Add one parameter row"

    def execute(self, context):
        settings = context.scene.gncsv_settings
        settings.params.add()
        return {'FINISHED'}


class GNCSV_OT_remove_param(Operator):
    bl_idname = "gncsv.remove_param"
    bl_label = "Remove Param"
    bl_description = "Remove this parameter row"

    index: IntProperty(default=-1)

    def execute(self, context):
        settings = context.scene.gncsv_settings
        if 0 <= self.index < len(settings.params):
            settings.params.remove(self.index)
            return {'FINISHED'}

        self.report({'WARNING'}, "Parameter row not found.")
        return {'CANCELLED'}


class GNCSV_OT_clear_params(Operator):
    bl_idname = "gncsv.clear_params"
    bl_label = "Clear"
    bl_description = "Clear all parameter rows"

    def execute(self, context):
        settings = context.scene.gncsv_settings
        settings.params.clear()
        return {'FINISHED'}


class GNCSV_OT_populate_from_modifier(Operator):
    bl_idname = "gncsv.populate_from_modifier"
    bl_label = "Populate from GN Inputs"
    bl_description = "Auto-fill parameter rows from the active object's Geometry Nodes group inputs"

    def execute(self, context):
        settings = context.scene.gncsv_settings
        obj = _get_active_obj(context)
        mod = _find_modifier(obj, settings.modifier_name)

        if not obj:
            self.report({'WARNING'}, "No active object.")
            return {'CANCELLED'}

        if not mod:
            self.report({'WARNING'}, "Target modifier not found on active object.")
            return {'CANCELLED'}

        node_group = _get_gn_node_group(mod)
        if not node_group:
            self.report({'WARNING'}, "Modifier has no node_group. This may not be a Geometry Nodes modifier.")
            return {'CANCELLED'}

        sockets = _iter_gn_input_sockets(node_group)
        if not sockets:
            self.report({'WARNING'}, "No GN input sockets found in the node group interface.")
            return {'CANCELLED'}

        settings.params.clear()
        for socket in sockets:
            item = settings.params.add()
            item.param_name = getattr(socket, "name", "")

        self.report({'INFO'}, f"Loaded {len(settings.params)} GN input parameter(s).")
        return {'FINISHED'}


class GNCSV_OT_set_modifier_from_active(Operator):
    bl_idname = "gncsv.set_modifier_from_active"
    bl_label = "Use Active GN Modifier"
    bl_description = "Set Modifier Name to the first Geometry Nodes modifier on the active object"

    def execute(self, context):
        settings = context.scene.gncsv_settings
        obj = _get_active_obj(context)

        if not obj:
            self.report({'WARNING'}, "No active object.")
            return {'CANCELLED'}

        mod = _first_gn_modifier(obj)
        if mod:
            settings.modifier_name = mod.name
            self.report({'INFO'}, f"Modifier set to: {mod.name}")
            return {'FINISHED'}

        self.report({'WARNING'}, "No Geometry Nodes modifier found on the active object.")
        return {'CANCELLED'}


class GNCSV_OT_export_csv(Operator, ExportHelper):
    bl_idname = "gncsv.export_csv"
    bl_label = "Export CSV"
    bl_description = "Export specified Geometry Nodes modifier parameters to CSV"

    filename_ext = ".csv"
    filter_glob: StringProperty(default="*.csv", options={'HIDDEN'})

    def execute(self, context):
        settings = context.scene.gncsv_settings

        objects = _collect_export_objects(context, settings.export_selected_objects)
        if not objects:
            self.report({'ERROR'}, "No objects to export.")
            return {'CANCELLED'}

        param_names = [p.param_name.strip() for p in settings.params if p.param_name.strip()]
        if not param_names:
            self.report({'ERROR'}, "No parameters specified.")
            return {'CANCELLED'}

        try:
            with open(self.filepath, "w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)

                if settings.include_header:
                    writer.writerow(["Object"] + param_names)

                for obj in objects:
                    mod = _find_modifier(obj, settings.modifier_name)
                    row = [obj.name]

                    if mod:
                        for key in param_names:
                            value = _get_param_value(obj, mod, key)
                            row.append(_value_to_csv_cell(value))
                    else:
                        row.extend(["" for _ in param_names])

                    writer.writerow(row)

        except Exception as error:
            self.report({'ERROR'}, f"Failed to export CSV: {error}")
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
        settings = context.scene.gncsv_settings
        obj = _get_active_obj(context)

        col = layout.column(align=True)
        col.label(text="Target Modifier (Geometry Nodes):")
        row = col.row(align=True)
        row.prop(settings, "modifier_name", text="")
        row.operator("gncsv.set_modifier_from_active", text="", icon='EYEDROPPER')

        col.separator()

        box = layout.box()
        box.label(text="Parameters (CSV columns after Object):")
        row = box.row(align=True)
        row.operator("gncsv.add_param", icon='ADD', text="Add Param")
        row.operator("gncsv.clear_params", icon='TRASH', text="Clear")
        box.operator("gncsv.populate_from_modifier", icon='NODETREE', text="Populate from GN Inputs (active object)")

        if not obj:
            box.label(text="No active object.", icon='ERROR')
        else:
            mod = _find_modifier(obj, settings.modifier_name)
            if not mod:
                box.label(text=f"Modifier '{settings.modifier_name}' not found on active object.", icon='ERROR')
            else:
                for index, param in enumerate(settings.params):
                    row = box.row(align=True)
                    row.prop(param, "param_name", text="")
                    value = _get_param_value(obj, mod, param.param_name.strip())
                    row.label(text=_value_to_csv_cell(value))
                    remove_op = row.operator("gncsv.remove_param", text="", icon='X')
                    remove_op.index = index

        layout.separator()
        layout.prop(settings, "export_selected_objects")
        layout.prop(settings, "include_header")
        layout.operator("gncsv.export_csv", icon='EXPORT')


# -----------------------------
# Register
# -----------------------------
classes = (
    GNCSV_ParamItem,
    GNCSV_Settings,
    GNCSV_OT_add_param,
    GNCSV_OT_remove_param,
    GNCSV_OT_clear_params,
    GNCSV_OT_populate_from_modifier,
    GNCSV_OT_set_modifier_from_active,
    GNCSV_OT_export_csv,
    VIEW3D_PT_gncsv_export_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.gncsv_settings = PointerProperty(type=GNCSV_Settings)


def unregister():
    if hasattr(bpy.types.Scene, "gncsv_settings"):
        del bpy.types.Scene.gncsv_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
