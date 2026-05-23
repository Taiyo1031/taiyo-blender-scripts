bl_info = {
    "name": "Attribute CSV Exporter (Domain) - Transposed (Evaluated)",
    "author": "Taiyo Parent",
    "version": (1, 8, 1),
    "blender": (5, 1, 0),
    "location": "View3D > Sidebar (N) > Attr CSV",
    "description": (
        "Export selected mesh attributes to CSV (TRANSPOSED). Rows=index, Columns=attribute names. "
        "Supports evaluated mesh (Geometry Nodes/modifiers). Ignore internal '.' attributes. "
        "Export per-object or merged. Auto-updating preview."
    ),
    "category": "Import-Export",
}

import bpy
import csv
import os
from bpy.app.handlers import persistent
from bpy.props import (
    StringProperty,
    EnumProperty,
    BoolProperty,
    CollectionProperty,
    IntProperty,
)
from bpy.types import Operator, Panel, PropertyGroup, UIList


# ----------------------------
# UI enums
# ----------------------------

DOMAIN_ITEMS = [
    ("POINT", "Vertex (POINT)", "Vertex domain (POINT)"),
    ("EDGE", "Edge (EDGE)", "Edge domain (EDGE)"),
    ("FACE", "Face (FACE)", "Face domain (FACE)"),
    ("CORNER", "Corner (CORNER)", "Face corner domain (CORNER / loop)"),
]

VEC_MODE_ITEMS = [
    ("KEEP", "A: Keep as (x,y,z)", "Keep vectors as a single '(x,y,z)' cell"),
    ("SPLIT", "B: Split to _x/_y/_z", "Split vectors into multiple columns (default)"),
]

ATTRIBUTE_SOURCE_ITEMS = [
    ("SELECTED_UNION", "Selected Union", "Build the attribute list from all selected mesh objects"),
    ("ACTIVE", "Active Object", "Build the attribute list from the active mesh object only"),
]

COMP_SUFFIX = {
    2: ("_x", "_y"),
    3: ("_x", "_y", "_z"),
    4: ("_x", "_y", "_z", "_w"),
}

BUILTIN_ATTRIBUTE_ORDER = ("position", "normal")
BUILTIN_EXPORT_COLUMNS = ("object", "index")


# ----------------------------
# Helpers
# ----------------------------

def sanitize_filename(name: str) -> str:
    bad = '<>:"/\\|?*'
    for c in bad:
        name = name.replace(c, "_")
    return name.strip()


def float_str(x: float) -> str:
    return f"{x:.6g}"


def format_scalar(v) -> str:
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return float_str(v)
    return str(v)


def format_vector(vec) -> str:
    try:
        return "(" + ",".join(float_str(float(x)) for x in vec) + ")"
    except Exception:
        return str(vec)


def is_vector_like(value) -> bool:
    return hasattr(value, "__len__") and not isinstance(value, (str, bytes))


def domain_element_count(mesh: bpy.types.Mesh, domain: str) -> int:
    if domain == "POINT":
        return len(mesh.vertices)
    if domain == "EDGE":
        return len(mesh.edges)
    if domain == "FACE":
        return len(mesh.polygons)
    if domain == "CORNER":
        return len(mesh.loops)
    return 0


def value_to_components(value):
    """Normalize attribute element wrappers into scalar or iterable."""
    for prop in ("vector", "color", "value"):
        if hasattr(value, prop):
            v = getattr(value, prop)
            if prop == "value" and not hasattr(v, "__len__"):
                return v
            return v
    try:
        return list(value)
    except Exception:
        return value


def detect_component_count(value) -> int:
    if not is_vector_like(value):
        return 0
    try:
        return len(list(value))
    except Exception:
        return 0


def build_output_columns(attribute_name: str, component_count: int, vec_mode: str):
    if vec_mode == "SPLIT" and component_count in COMP_SUFFIX:
        return [attribute_name + suffix for suffix in COMP_SUFFIX[component_count]]
    return [attribute_name]


def make_item_key(item_kind: str, item_name: str) -> str:
    return f"{item_kind}:{item_name}"


def is_internal_attribute_name(name: str) -> bool:
    return bool(name) and name.startswith(".")


def get_object_label(obj: bpy.types.Object) -> str:
    return getattr(obj, "name_full", None) or obj.name


def get_active_mesh_object(context):
    obj = context.active_object
    if not obj or obj.type != "MESH":
        return None
    return obj


def get_selected_mesh_objects(context):
    return [obj for obj in context.selected_objects if obj and obj.type == "MESH"]


def get_attribute_source_objects(context, source_mode: str):
    if source_mode == "ACTIVE":
        obj = get_active_mesh_object(context)
        return [obj] if obj else []
    return get_selected_mesh_objects(context)


def get_source_mesh(context, obj: bpy.types.Object, use_evaluated: bool):
    """Return (mesh, cleanup_fn). If evaluated: includes GN/modifiers."""
    if not use_evaluated:
        return obj.data, (lambda: None)

    depsgraph = context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(depsgraph)
    mesh_eval = obj_eval.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)

    def cleanup():
        try:
            obj_eval.to_mesh_clear()
        except Exception:
            pass

    return mesh_eval, cleanup


def collect_export_attributes(
    mesh: bpy.types.Mesh,
    domain: str,
    include_builtin=True,
    allowed_names=None,
):
    """
    Collect exportable attributes in the requested domain.

    Internal '.' attributes are ignored. Attributes with mismatched lengths are
    skipped so preview and export share the same validity rules.
    """
    attrs = []
    seen = set()
    allowed = set(allowed_names) if allowed_names is not None else None
    count = domain_element_count(mesh, domain)
    if count <= 0:
        return count, attrs

    def maybe_add(attr):
        if not attr or attr.name in seen:
            return
        if attr.domain != domain:
            return
        if allowed is not None and attr.name not in allowed:
            return
        if is_internal_attribute_name(attr.name):
            return
        if len(attr.data) != count:
            return
        attrs.append(attr)
        seen.add(attr.name)

    if include_builtin:
        for name in BUILTIN_ATTRIBUTE_ORDER:
            maybe_add(mesh.attributes.get(name))

    for attr in mesh.attributes:
        maybe_add(attr)

    return count, attrs


def describe_attribute(attr) -> dict:
    raw = value_to_components(attr.data[0]) if len(attr.data) else None
    component_count = detect_component_count(raw) if raw is not None else 0
    return {
        "name": attr.name,
        "component_count": component_count,
    }


def sort_attribute_names(info_by_name):
    builtins = [name for name in BUILTIN_ATTRIBUTE_ORDER if name in info_by_name]
    others = sorted(name for name in info_by_name if name not in BUILTIN_ATTRIBUTE_ORDER)
    return builtins + others


def collect_source_attribute_infos(context, source_mode: str, domain: str, use_evaluated: bool):
    info_by_name = {}
    row_count = 0

    for obj in get_attribute_source_objects(context, source_mode):
        mesh, cleanup = get_source_mesh(context, obj, use_evaluated)
        try:
            count, attrs = collect_export_attributes(mesh, domain, include_builtin=True)
            row_count += count
            for attr in attrs:
                info = describe_attribute(attr)
                existing = info_by_name.get(info["name"])
                if existing is None:
                    info_by_name[info["name"]] = info
                else:
                    existing["component_count"] = max(existing["component_count"], info["component_count"])
        finally:
            cleanup()

    ordered_names = sort_attribute_names(info_by_name)
    return row_count, [info_by_name[name] for name in ordered_names]


def build_columns_and_cache(mesh: bpy.types.Mesh, domain: str, vec_mode: str, allowed_names=None):
    count, attrs = collect_export_attributes(mesh, domain, include_builtin=True, allowed_names=allowed_names)
    if count <= 0:
        raise RuntimeError(f"No elements in domain {domain} (count=0).")

    columns = []
    cache = {}
    attribute_columns = {}

    for attr in attrs:
        data = attr.data
        first_raw = value_to_components(data[0])
        component_count = detect_component_count(first_raw)
        column_names = build_output_columns(attr.name, component_count, vec_mode)
        attribute_columns[attr.name] = list(column_names)

        if component_count == 0 or column_names == [attr.name]:
            values = []
            for index in range(count):
                value = value_to_components(data[index])
                if is_vector_like(value):
                    values.append(format_vector(value))
                else:
                    values.append(format_scalar(value))
            columns.extend(column_names)
            cache[attr.name] = values
            continue

        all_values = []
        for index in range(count):
            value = value_to_components(data[index])
            try:
                all_values.append(list(value))
            except Exception:
                all_values.append([value])

        for component_index, column_name in enumerate(column_names):
            values = []
            for row_values in all_values:
                if component_index < len(row_values):
                    component = row_values[component_index]
                    values.append(format_scalar(component) if isinstance(component, (int, float, bool)) else str(component))
                else:
                    values.append("")
            columns.append(column_name)
            cache[column_name] = values

    return count, columns, cache, attribute_columns


def build_payload(obj_name: str, mesh: bpy.types.Mesh, domain: str, vec_mode: str, allowed_names):
    count, columns, cache, attribute_columns = build_columns_and_cache(
        mesh,
        domain,
        vec_mode,
        allowed_names=allowed_names,
    )
    return {
        "object_name": obj_name,
        "N": count,
        "columns": columns,
        "cache": cache,
        "attribute_columns": attribute_columns,
    }


def get_checked_attribute_specs(props):
    return [
        {
            "kind": item.item_kind,
            "name": item.attr_name,
            "component_count": item.component_count,
        }
        for item in props.attribute_items
        if item.enabled
    ]


def build_schema_entries(selected_specs, payloads, vec_mode: str):
    schema = []
    seen = set()

    for spec in selected_specs:
        if spec["kind"] == "builtin":
            entry = {
                "kind": "builtin",
                "name": spec["name"],
                "column_name": spec["name"],
            }
            entry_key = (entry["kind"], entry["name"], entry["column_name"])
            if entry_key not in seen:
                schema.append(entry)
                seen.add(entry_key)
            continue

        actual_columns = []
        for payload in payloads:
            for column_name in payload["attribute_columns"].get(spec["name"], []):
                if column_name not in actual_columns:
                    actual_columns.append(column_name)

        if not actual_columns:
            actual_columns = build_output_columns(spec["name"], spec["component_count"], vec_mode)

        for column_name in actual_columns:
            entry = {
                "kind": "mesh",
                "name": spec["name"],
                "column_name": column_name,
            }
            entry_key = (entry["kind"], entry["name"], entry["column_name"])
            if entry_key in seen:
                continue
            schema.append(entry)
            seen.add(entry_key)

    return schema


def estimate_selected_column_count(props) -> int:
    specs = get_checked_attribute_specs(props)
    count = 0
    seen = set()
    for spec in specs:
        if spec["kind"] == "builtin":
            column_names = [spec["name"]]
        else:
            column_names = build_output_columns(spec["name"], spec["component_count"], props.vec_mode)

        for column_name in column_names:
            entry_key = (spec["kind"], spec["name"], column_name)
            if entry_key in seen:
                continue
            seen.add(entry_key)
            count += 1
    return count


def get_schema_value(payload, schema_entry, index: int) -> str:
    if schema_entry["kind"] == "builtin":
        if schema_entry["name"] == "object":
            return payload["object_name"]
        if schema_entry["name"] == "index":
            return str(index)
        return ""

    column_name = schema_entry["column_name"]
    values = payload["cache"].get(column_name)
    if values is None:
        return ""
    return values[index]


def write_single_payload(filepath: str, payload, schema_entries):
    header = [entry["column_name"] for entry in schema_entries]
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    with open(filepath, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for index in range(payload["N"]):
            row = []
            for schema_entry in schema_entries:
                row.append(get_schema_value(payload, schema_entry, index))
            writer.writerow(row)


def export_csv_transposed_merged(per_object_payloads, filepath: str, schema_entries):
    header = [entry["column_name"] for entry in schema_entries]

    total_rows = 0
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)

        for payload in per_object_payloads:
            for index in range(payload["N"]):
                row = []
                for schema_entry in schema_entries:
                    row.append(get_schema_value(payload, schema_entry, index))
                writer.writerow(row)
                total_rows += 1

    return total_rows


# ----------------------------
# Preview list UI
# ----------------------------

# Blender 5.x note:
# You cannot write to ID data-block properties (Scene, Object, etc.) during Panel.draw().
# So preview refresh is scheduled via a timer and executed outside the draw context.
PREVIEW_SCHEDULED = set()


def mark_preview_dirty(_self, context):
    if context and context.scene and hasattr(context.scene, "attrcsv_props"):
        context.scene.attrcsv_props.preview_state_dirty = True


class AttrCSVAttributeItem(PropertyGroup):
    item_kind: StringProperty(name="Item Kind", default="mesh")
    attr_name: StringProperty(name="Attribute Name", default="")
    label: StringProperty(name="Label", default="")
    component_count: IntProperty(name="Component Count", default=0)
    enabled: BoolProperty(name="Enabled", default=False, update=mark_preview_dirty)


class ATTRCSV_UL_attribute_list(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.prop(item, "enabled", text="")
        row.label(text=item.label or item.attr_name, icon="DOT")


def make_preview_key(context) -> str:
    props = context.scene.attrcsv_props
    objects = get_attribute_source_objects(context, props.attribute_source)
    object_key = ",".join(sorted(get_object_label(obj) for obj in objects)) or "None"
    return (
        f"{props.attribute_source}|{object_key}|{props.domain}|{props.vec_mode}|"
        f"{'E' if props.use_evaluated else 'O'}"
    )


def refresh_preview(context):
    props = context.scene.attrcsv_props
    checked_by_key = {
        make_item_key(item.item_kind, item.attr_name): item.enabled
        for item in props.attribute_items
    }

    props.attribute_items.clear()
    props.preview_rows = 0

    try:
        row_count, attribute_infos = collect_source_attribute_infos(
            context,
            props.attribute_source,
            props.domain,
            props.use_evaluated,
        )
        props.preview_rows = row_count

        for name in BUILTIN_EXPORT_COLUMNS:
            item = props.attribute_items.add()
            item.item_kind = "builtin"
            item.attr_name = name
            item.label = name
            item.component_count = 0
            item.enabled = checked_by_key.get(make_item_key("builtin", name), False)

        for info in attribute_infos:
            item = props.attribute_items.add()
            item.item_kind = "mesh"
            item.attr_name = info["name"]
            item.label = info["name"]
            item.component_count = info["component_count"]
            item.enabled = checked_by_key.get(make_item_key("mesh", info["name"]), False)
    finally:
        props.preview_state_key = make_preview_key(context)
        props.preview_state_dirty = False


def schedule_preview_refresh(scene: bpy.types.Scene):
    """Schedule preview refresh outside UI draw context."""
    scene_key = scene.as_pointer()
    if scene_key in PREVIEW_SCHEDULED:
        return

    PREVIEW_SCHEDULED.add(scene_key)

    def _timer():
        try:
            context = bpy.context
            if context and context.scene == scene and hasattr(scene, "attrcsv_props"):
                refresh_preview(context)
        finally:
            PREVIEW_SCHEDULED.discard(scene_key)
        return None

    bpy.app.timers.register(_timer, first_interval=0.0)


def ensure_preview_up_to_date(context):
    """May be called from Panel.draw(); must NOT write to ID properties."""
    props = context.scene.attrcsv_props
    try:
        key = make_preview_key(context)
        if props.preview_state_dirty or props.preview_state_key != key:
            schedule_preview_refresh(context.scene)
    except Exception:
        schedule_preview_refresh(context.scene)
@persistent
def depsgraph_dirty_handler(scene, depsgraph):
    del depsgraph
    if scene and hasattr(scene, "attrcsv_props"):
        scene.attrcsv_props.preview_state_dirty = True


# ----------------------------
# Properties / UI
# ----------------------------

class AttrCSVProps(PropertyGroup):
    export_dir: StringProperty(
        name="Export Folder",
        subtype="DIR_PATH",
        default="//",
        description="Folder to export CSV into (supports // relative path)",
    )

    export_individual: BoolProperty(
        name="Export Individually (Selected)",
        default=True,
        description="If ON, export each selected mesh to its own CSV. If OFF, merge selected meshes into one CSV.",
    )

    file_name: StringProperty(
        name="Merged File Name",
        default="",
        description="Used only when Export Individually is OFF. Base file name without extension. If empty, uses Selected.",
    )

    prefix: StringProperty(name="Prefix", default="", description="File name prefix (optional).")
    suffix: StringProperty(name="Suffix", default="", description="File name suffix (optional).")

    domain: EnumProperty(
        name="Domain",
        items=DOMAIN_ITEMS,
        default="POINT",
        description="Which attribute domain to export",
        update=mark_preview_dirty,
    )

    vec_mode: EnumProperty(
        name="Vector Mode",
        items=VEC_MODE_ITEMS,
        default="SPLIT",
        description="How to export vector-like attributes",
        update=mark_preview_dirty,
    )

    attribute_source: EnumProperty(
        name="Attribute Source",
        items=ATTRIBUTE_SOURCE_ITEMS,
        default="SELECTED_UNION",
        description="Which objects are used to build the selectable attribute list",
        update=mark_preview_dirty,
    )

    use_evaluated: BoolProperty(
        name="Use Evaluated Mesh (GN/Modifiers)",
        default=True,
        description="Export from evaluated mesh so Geometry Nodes / modifiers-generated attributes are included",
        update=mark_preview_dirty,
    )

    attribute_items: CollectionProperty(type=AttrCSVAttributeItem)
    attribute_index: IntProperty(default=0)
    preview_rows: IntProperty(name="Preview Rows", default=0)

    preview_state_key: StringProperty(default="")
    preview_state_dirty: BoolProperty(default=True)


class ATTRCSV_OT_export(Operator):
    bl_idname = "attrcsv.export"
    bl_label = "Export CSV"
    bl_options = {"REGISTER"}

    def execute(self, context):
        props = context.scene.attrcsv_props
        export_dir = bpy.path.abspath(props.export_dir)
        if not export_dir:
            self.report({"ERROR"}, "Export folder is empty.")
            return {"CANCELLED"}

        selected_meshes = get_selected_mesh_objects(context)
        if not selected_meshes:
            self.report({"ERROR"}, "No mesh objects selected.")
            return {"CANCELLED"}

        selected_specs = get_checked_attribute_specs(props)
        if not selected_specs:
            self.report({"ERROR"}, "No attributes selected.")
            return {"CANCELLED"}

        selected_names = {spec["name"] for spec in selected_specs if spec["kind"] == "mesh"}
        payloads = []

        for obj in selected_meshes:
            mesh, cleanup = get_source_mesh(context, obj, props.use_evaluated)
            try:
                payloads.append(
                    build_payload(
                        obj.name,
                        mesh,
                        props.domain,
                        props.vec_mode,
                        selected_names,
                    )
                )
            except Exception as exc:
                self.report({"ERROR"}, f"Build failed for '{obj.name}': {exc}")
                return {"CANCELLED"}
            finally:
                cleanup()

        schema_entries = build_schema_entries(selected_specs, payloads, props.vec_mode)
        if not schema_entries:
            self.report({"ERROR"}, "Selected attributes did not produce any export columns.")
            return {"CANCELLED"}

        if props.export_individual:
            total_rows = 0
            for obj, payload in zip(selected_meshes, payloads):
                base = sanitize_filename(f"{props.prefix}{obj.name}{props.suffix}")
                filepath = os.path.join(export_dir, base + ".csv")
                try:
                    write_single_payload(filepath, payload, schema_entries)
                except Exception as exc:
                    self.report({"ERROR"}, f"Export failed for '{obj.name}': {exc}")
                    return {"CANCELLED"}
                total_rows += payload["N"]

            self.report({"INFO"}, f"Exported {len(payloads)} object(s), total rows: {total_rows}")
            return {"FINISHED"}

        base = props.file_name.strip() or "Selected"
        base = sanitize_filename(f"{props.prefix}{base}{props.suffix}")
        filepath = os.path.join(export_dir, base + ".csv")

        try:
            written_rows = export_csv_transposed_merged(payloads, filepath, schema_entries)
        except Exception as exc:
            self.report({"ERROR"}, f"Merged export failed: {exc}")
            return {"CANCELLED"}

        self.report({"INFO"}, f"Exported {len(payloads)} object(s) merged, total rows: {written_rows}")
        return {"FINISHED"}


class ATTRCSV_PT_panel(Panel):
    bl_label = "Attr CSV"
    bl_idname = "ATTRCSV_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Attr CSV"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Attr CSV (loaded)")

        try:
            ensure_preview_up_to_date(context)

            props = context.scene.attrcsv_props
            available_count = len(props.attribute_items)
            selected_count = sum(1 for item in props.attribute_items if item.enabled)
            estimated_columns = estimate_selected_column_count(props)

            col = layout.column(align=True)
            col.label(text="Target: Selected Mesh Objects")
            col.prop(props, "export_dir")
            col.prop(props, "domain")
            col.prop(props, "vec_mode")
            col.prop(props, "attribute_source")
            col.prop(props, "use_evaluated")

            col.separator()
            select_box = col.box()
            select_box.label(text="Attribute Selection")
            select_box.label(
                text=(
                    f"Available: {available_count}  |  Selected: {selected_count}  |  "
                    f"Output Columns: {estimated_columns}"
                )
            )
            select_box.label(text=f"Rows(N): {props.preview_rows}")
            select_box.template_list(
                "ATTRCSV_UL_attribute_list",
                "",
                props,
                "attribute_items",
                props,
                "attribute_index",
                rows=8,
            )

            col.separator()
            file_box = col.box()
            file_box.label(text="File Naming")
            file_box.prop(props, "export_individual")

            row = file_box.row(align=True)
            row.prop(props, "prefix")
            row.prop(props, "suffix")

            if not props.export_individual:
                file_box.prop(props, "file_name")

            col.separator()
            col.operator("attrcsv.export", icon="EXPORT")
        except Exception as exc:
            box = layout.box()
            box.label(text="UI Error occurred:")
            box.label(text=str(exc))


# ----------------------------
# Register
# ----------------------------

classes = (
    AttrCSVAttributeItem,
    ATTRCSV_UL_attribute_list,
    AttrCSVProps,
    ATTRCSV_OT_export,
    ATTRCSV_PT_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.attrcsv_props = bpy.props.PointerProperty(type=AttrCSVProps)

    if depsgraph_dirty_handler not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(depsgraph_dirty_handler)


def unregister():
    if depsgraph_dirty_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(depsgraph_dirty_handler)

    del bpy.types.Scene.attrcsv_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
