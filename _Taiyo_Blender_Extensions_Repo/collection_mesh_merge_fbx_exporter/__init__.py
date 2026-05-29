bl_info = {
    "name": "Collection Mesh Merge FBX Exporter",
    "author": "Taiyo",
    "version": (0, 3, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > CMFE",
    "description": "Export target collections as merged FBX, USD, or Alembic files, non-destructively.",
    "category": "Import-Export",
}

DOCUMENTATION_URL = "https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/_Taiyo_Blender_Extensions_Repo/collection_mesh_merge_fbx_exporter/Collection_Mesh_Merge_FBX_Exporter_%E4%BD%BF%E7%94%A8%E6%9B%B8.md"

import bpy
import bmesh
import os
import re
import traceback
from mathutils import Matrix
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import AddonPreferences, Operator, Panel, PropertyGroup


# -----------------------------------------------------------------------------
# Utility
# -----------------------------------------------------------------------------

INVALID_FILENAME_CHARS = r'[\\/:*?"<>|]'
TEMP_COLLECTION_NAME = "__CMFE_TEMP_EXPORT__"
DEFAULT_COMBINED_FILE_NAME = "CMFE_Combined_Export"

EXPORT_EXTENSIONS = {
    "FBX": ".fbx",
    "USD": ".usd",
    "ABC": ".abc",
}

EXPORT_FORMAT_LABELS = {
    "FBX": "FBX",
    "USD": "USD",
    "ABC": "Alembic",
}


def sanitize_filename(name: str) -> str:
    """Make a collection name safe for use as a file name."""
    safe = re.sub(INVALID_FILENAME_CHARS, "_", name).strip()
    safe = safe.rstrip(". ")
    return safe or "Unnamed_Collection"


def ensure_export_folder(path: str) -> str:
    if not path:
        return ""
    abs_path = bpy.path.abspath(path)
    os.makedirs(abs_path, exist_ok=True)
    return abs_path


def export_extension(export_format: str) -> str:
    return EXPORT_EXTENSIONS.get(export_format, ".fbx")


def export_format_label(export_format: str) -> str:
    return EXPORT_FORMAT_LABELS.get(export_format, "FBX")


def output_filename_for_collection(collection: bpy.types.Collection, props) -> str:
    return sanitize_filename(collection.name) + export_extension(props.export_format)


def combined_output_filename(props) -> str:
    base_name = sanitize_filename(props.combined_file_name or DEFAULT_COMBINED_FILE_NAME)
    return base_name + export_extension(props.export_format)


def is_collection_asset(collection: bpy.types.Collection) -> bool:
    """True if this collection is marked as an Asset Browser asset."""
    return getattr(collection, "asset_data", None) is not None


def is_object_hidden(obj: bpy.types.Object) -> bool:
    # obj.hide_get() checks current view-layer hide state.
    # hide_viewport/hide_render are persistent object-level flags.
    try:
        hidden_get = obj.hide_get()
    except Exception:
        hidden_get = False
    return bool(hidden_get or obj.hide_viewport or obj.hide_render)


def name_filter_match(name: str, text: str, rule: str, case_sensitive: bool) -> bool:
    if not text:
        return True
    a = name if case_sensitive else name.lower()
    b = text if case_sensitive else text.lower()

    if rule == "CONTAINS":
        return b in a
    if rule == "STARTS_WITH":
        return a.startswith(b)
    if rule == "ENDS_WITH":
        return a.endswith(b)
    if rule == "EXACT":
        return a == b
    return b in a


def collection_passes_filter(collection: bpy.types.Collection, props) -> bool:
    asset_ok = is_collection_asset(collection)
    name_ok = name_filter_match(
        collection.name,
        props.name_filter,
        props.name_match_rule,
        props.name_case_sensitive,
    )

    mode = props.filter_mode
    if mode == "ASSET":
        return asset_ok
    if mode == "NAME":
        return name_ok
    if mode == "ASSET_AND_NAME":
        return asset_ok and name_ok
    if mode == "ASSET_OR_NAME":
        return asset_ok or name_ok
    return False


def iter_collection_tree(root: bpy.types.Collection, include_root: bool = True):
    if root is None:
        return
    if include_root:
        yield root
    for child in root.children:
        yield child
        yield from iter_collection_tree(child, include_root=False)


def child_collections_recursive(collection: bpy.types.Collection):
    for child in collection.children:
        yield child
        yield from child_collections_recursive(child)


def target_collections(root: bpy.types.Collection, props):
    """Return target collections based on the current filter mode and nested target rule."""
    if root is None:
        return []

    rule = props.nested_target_rule
    targets = []

    if rule == "PARENT_IGNORES_CHILDREN":
        def walk(coll):
            if collection_passes_filter(coll, props):
                targets.append(coll)
                return
            for ch in coll.children:
                walk(ch)

        if props.include_root_collection:
            walk(root)
        else:
            for ch in root.children:
                walk(ch)
        return targets

    all_candidates = [
        c for c in iter_collection_tree(root, include_root=props.include_root_collection)
        if collection_passes_filter(c, props)
    ]

    if rule == "LEAF_TARGETS":
        candidate_set = set(all_candidates)
        for coll in all_candidates:
            has_target_descendant = any(desc in candidate_set for desc in child_collections_recursive(coll))
            if not has_target_descendant:
                targets.append(coll)
        return targets

    # ALL_TARGETS
    return all_candidates


def object_materials(obj: bpy.types.Object):
    return [slot.material for slot in obj.material_slots]


def object_modifier_count(obj: bpy.types.Object) -> int:
    try:
        return len(obj.modifiers)
    except Exception:
        return 0


def object_allowed_by_visibility(obj: bpy.types.Object, include_hidden: bool) -> bool:
    if include_hidden:
        return True
    return not is_object_hidden(obj)


def collect_mesh_sources_from_collection(collection: bpy.types.Collection, props):
    """
    Collect mesh sources from a collection.

    Each source is a dict:
        {
            "object": bpy.types.Object,
            "matrix": Matrix,
            "is_instance": bool,
        }
    """
    sources = []
    seen_normal_objects = set()

    if props.include_nested_meshes:
        objects = list(collection.all_objects)
    else:
        objects = list(collection.objects)

    for obj in objects:
        if not object_allowed_by_visibility(obj, props.include_hidden_objects):
            continue

        if obj.type == "MESH":
            if obj.name in seen_normal_objects:
                continue
            seen_normal_objects.add(obj.name)
            sources.append({
                "object": obj,
                "matrix": obj.matrix_world.copy(),
                "is_instance": False,
            })
            continue

        if props.include_collection_instances and obj.instance_type == "COLLECTION" and obj.instance_collection:
            sources.extend(collect_mesh_sources_from_instance(obj, props, depth=0))

    return sources


def collect_mesh_sources_from_instance(instancer: bpy.types.Object, props, depth=0):
    """Experimental support for collection instances."""
    if depth > 8:
        return []
    instanced_collection = instancer.instance_collection
    if instanced_collection is None:
        return []

    # Blender collection instances use collection.instance_offset. This approximation is
    # good for common asset-library workflows where collection contents are authored around origin.
    instance_matrix = instancer.matrix_world @ Matrix.Translation(-instanced_collection.instance_offset)

    sources = []
    for child in instanced_collection.all_objects:
        if not object_allowed_by_visibility(child, props.include_hidden_objects):
            continue
        if child.type == "MESH":
            sources.append({
                "object": child,
                "matrix": instance_matrix @ child.matrix_world,
                "is_instance": True,
            })
        elif props.include_collection_instances and child.instance_type == "COLLECTION" and child.instance_collection:
            # Nested instances are uncommon but supported with a safety depth limit.
            sources.extend(collect_mesh_sources_from_instance(child, props, depth=depth + 1))
    return sources


def count_modifiers_in_sources(sources) -> int:
    return sum(object_modifier_count(src["object"]) for src in sources)


def get_or_create_temp_collection(scene: bpy.types.Scene) -> bpy.types.Collection:
    coll = bpy.data.collections.get(TEMP_COLLECTION_NAME)
    if coll is None:
        coll = bpy.data.collections.new(TEMP_COLLECTION_NAME)
        scene.collection.children.link(coll)
    return coll


def cleanup_temp_collection_if_empty():
    coll = bpy.data.collections.get(TEMP_COLLECTION_NAME)
    if coll and len(coll.objects) == 0 and len(coll.children) == 0:
        # Keep it hidden during a session? For now remove to keep file clean.
        try:
            bpy.data.collections.remove(coll)
        except Exception:
            pass


def deselect_all(context):
    for obj in context.view_layer.objects:
        obj.select_set(False)


def export_fbx_selected(filepath: str, context):
    """FBX export wrapper. Uses UE-friendly static mesh defaults."""
    # Blender's FBX operator keyword set has changed slightly over versions.
    # Try the modern signature first, then fallback to a smaller argument set.
    kwargs = dict(
        filepath=filepath,
        check_existing=False,
        use_selection=True,
        use_visible=False,
        use_active_collection=False,
        global_scale=1.0,
        apply_unit_scale=True,
        apply_scale_options='FBX_SCALE_ALL',
        use_space_transform=True,
        bake_space_transform=False,
        object_types={'MESH'},
        use_mesh_modifiers=False,
        use_mesh_modifiers_render=False,
        mesh_smooth_type='OFF',
        colors_type='SRGB',
        use_subsurf=False,
        use_mesh_edges=False,
        use_tspace=False,
        use_triangles=False,
        use_custom_props=False,
        add_leaf_bones=False,
        bake_anim=False,
        path_mode='AUTO',
        embed_textures=False,
        batch_mode='OFF',
        use_batch_own_dir=True,
        use_metadata=True,
        axis_forward='-Z',
        axis_up='Y',
    )
    try:
        return bpy.ops.export_scene.fbx(**kwargs)
    except TypeError:
        fallback = dict(
            filepath=filepath,
            check_existing=False,
            use_selection=True,
            object_types={'MESH'},
            use_mesh_modifiers=False,
            bake_anim=False,
            axis_forward='-Z',
            axis_up='Y',
        )
        return bpy.ops.export_scene.fbx(**fallback)


def export_usd_selected(filepath: str, context):
    """USD export wrapper for selected temporary merged meshes."""
    if not hasattr(bpy.ops.wm, "usd_export"):
        raise RuntimeError("USD export operator is not available in this Blender build.")

    kwargs = dict(
        filepath=filepath,
        check_existing=False,
        selected_objects_only=True,
        visible_objects_only=False,
        export_animation=False,
        export_meshes=True,
        export_materials=True,
        export_textures=False,
    )
    try:
        return bpy.ops.wm.usd_export(**kwargs)
    except TypeError:
        fallback = dict(
            filepath=filepath,
            selected_objects_only=True,
        )
        return bpy.ops.wm.usd_export(**fallback)


def export_alembic_selected(filepath: str, context):
    """Alembic export wrapper for selected temporary merged meshes."""
    if not hasattr(bpy.ops.wm, "alembic_export"):
        raise RuntimeError("Alembic export operator is not available in this Blender build.")

    frame = context.scene.frame_current
    kwargs = dict(
        filepath=filepath,
        check_existing=False,
        selected=True,
        visible_objects_only=False,
        start=frame,
        end=frame,
        xsamples=1,
        gsamples=1,
        global_scale=1.0,
        flatten=False,
        uvs=True,
        normals=True,
        vcolors=True,
        face_sets=False,
    )
    try:
        return bpy.ops.wm.alembic_export(**kwargs)
    except TypeError:
        fallback = dict(
            filepath=filepath,
            selected=True,
        )
        return bpy.ops.wm.alembic_export(**fallback)


def export_selected_objects(filepath: str, context, export_format: str):
    if export_format == "USD":
        return export_usd_selected(filepath, context)
    if export_format == "ABC":
        return export_alembic_selected(filepath, context)
    return export_fbx_selected(filepath, context)


def select_only_objects(context, objects):
    deselect_all(context)
    first_obj = None
    for obj in objects:
        if obj is None:
            continue
        obj.select_set(True)
        if first_obj is None:
            first_obj = obj
    if first_obj is not None:
        context.view_layer.objects.active = first_obj


def append_source_to_bmesh(bm, material_slots, source, depsgraph, apply_modifiers: bool, keep_material_slots: bool):
    obj = source["object"]
    matrix = source["matrix"]

    temp_mesh = None
    source_mesh = None

    if apply_modifiers:
        eval_obj = obj.evaluated_get(depsgraph)
        temp_mesh = bpy.data.meshes.new_from_object(
            eval_obj,
            depsgraph=depsgraph,
            preserve_all_data_layers=True,
        )
        source_mesh = temp_mesh
    else:
        source_mesh = obj.data

    if source_mesh is None:
        return

    mat_base = len(material_slots)
    if keep_material_slots:
        mats = object_materials(obj)
        material_slots.extend(mats)

    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    old_vert_count = len(bm.verts)
    old_face_count = len(bm.faces)

    bm.from_mesh(source_mesh)

    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    for i in range(old_vert_count, len(bm.verts)):
        bm.verts[i].co = matrix @ bm.verts[i].co

    for i in range(old_face_count, len(bm.faces)):
        if keep_material_slots:
            bm.faces[i].material_index += mat_base
        else:
            bm.faces[i].material_index = 0

    if temp_mesh is not None:
        try:
            bpy.data.meshes.remove(temp_mesh)
        except Exception:
            pass


def make_merged_object_from_bmesh(collection_name: str, bm, material_slots, scene):
    mesh_name = f"{collection_name}_CMFE_Mesh"
    object_name = collection_name

    mesh = bpy.data.meshes.new(mesh_name)
    bm.to_mesh(mesh)
    mesh.update(calc_edges=True)

    if material_slots:
        for mat in material_slots:
            mesh.materials.append(mat)

    obj = bpy.data.objects.new(object_name, mesh)
    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)

    temp_coll = get_or_create_temp_collection(scene)
    temp_coll.objects.link(obj)
    return obj


def remove_object_and_mesh(obj):
    if obj is None:
        return
    mesh = obj.data if hasattr(obj, "data") else None
    try:
        bpy.data.objects.remove(obj, do_unlink=True)
    except Exception:
        pass
    if mesh and mesh.users == 0:
        try:
            bpy.data.meshes.remove(mesh)
        except Exception:
            pass


# -----------------------------------------------------------------------------
# Properties
# -----------------------------------------------------------------------------

class CMFE_PreviewItem(PropertyGroup):
    collection_name: StringProperty(name="Collection")
    mesh_count: IntProperty(name="Meshes", default=0)
    modifier_count: IntProperty(name="Modifiers", default=0)
    asset_registered: BoolProperty(name="Asset", default=False)
    name_match: BoolProperty(name="Name Match", default=False)
    output_file: StringProperty(name="Output File")
    status: StringProperty(name="Status")
    reason: StringProperty(name="Reason")


class CMFE_Properties(PropertyGroup):
    export_folder: StringProperty(
        name="Export Folder",
        subtype='DIR_PATH',
        description="Folder where export files will be written",
    )
    root_collection: PointerProperty(
        name="Search Root Collection",
        type=bpy.types.Collection,
        description="Search this collection and its children for export targets",
    )

    filter_mode: EnumProperty(
        name="Filter Mode",
        default="ASSET",
        items=[
            ("ASSET", "Asset Browser Registered", "Export collections marked as Asset Browser assets"),
            ("NAME", "Name Contains Filter", "Export collections matching the name filter"),
            ("ASSET_AND_NAME", "Asset AND Name", "Export collections that are assets and also match the name filter"),
            ("ASSET_OR_NAME", "Asset OR Name", "Export collections that are assets or match the name filter"),
        ],
    )
    name_filter: StringProperty(
        name="Name Filter",
        default="SM_",
        description="Used by name filter modes",
    )
    name_match_rule: EnumProperty(
        name="Name Match Rule",
        default="CONTAINS",
        items=[
            ("CONTAINS", "Contains", "Name contains the filter text"),
            ("STARTS_WITH", "Starts With", "Name starts with the filter text"),
            ("ENDS_WITH", "Ends With", "Name ends with the filter text"),
            ("EXACT", "Exact Match", "Name exactly matches the filter text"),
        ],
    )
    name_case_sensitive: BoolProperty(
        name="Case Sensitive",
        default=False,
    )

    nested_target_rule: EnumProperty(
        name="Nested Target Rule",
        default="ALL_TARGETS",
        items=[
            ("ALL_TARGETS", "Export All Matching Collections", "Export every collection that matches the filter, even if parent and child both match"),
            ("LEAF_TARGETS", "Export Only Leaf Matching Collections", "If parent and child both match, export only child/leaf targets"),
            ("PARENT_IGNORES_CHILDREN", "Parent Ignores Children", "If a parent matches, export it and do not scan its children as separate targets"),
        ],
    )

    include_root_collection: BoolProperty(
        name="Include Root Collection as Target",
        default=True,
        description="The selected root collection itself can also be exported if it matches the filter",
    )
    include_nested_meshes: BoolProperty(
        name="Include Nested Meshes in Each Target",
        default=True,
        description="When exporting a target collection, also include meshes inside its child collections",
    )
    include_hidden_objects: BoolProperty(
        name="Include Hidden Objects",
        default=True,
        description="If enabled, hidden viewport/render objects are included. If disabled, hidden objects are skipped",
    )
    include_collection_instances: BoolProperty(
        name="Include Collection Instances",
        default=False,
        description="Experimental: include meshes from collection instance empties",
    )
    apply_modifiers: BoolProperty(
        name="Apply Modifiers Before Export",
        default=True,
        description="Use evaluated mesh results for modifiers while keeping original objects unchanged",
    )
    keep_material_slots: BoolProperty(
        name="Keep Material Slots",
        default=True,
        description="Copy source material slots to the merged mesh. If disabled, exported mesh has no material slots",
    )
    export_format: EnumProperty(
        name="Export Format",
        default="FBX",
        items=[
            ("FBX", "FBX (.fbx)", "Export selected merged mesh objects as FBX"),
            ("USD", "USD (.usd)", "Export selected merged mesh objects as USD"),
            ("ABC", "Alembic (.abc)", "Export selected merged mesh objects as Alembic"),
        ],
    )
    export_output_mode: EnumProperty(
        name="Output Mode",
        default="INDIVIDUAL",
        items=[
            ("INDIVIDUAL", "Individual Files", "Export one file per target collection"),
            ("COMBINED", "Single Combined File", "Export all target collections into one file"),
        ],
    )
    combined_file_name: StringProperty(
        name="Combined File Name",
        default=DEFAULT_COMBINED_FILE_NAME,
        description="File name used when Output Mode is Single Combined File",
    )
    overwrite_existing: BoolProperty(
        name="Overwrite Existing Files",
        default=True,
        description="Overwrite export files with the same name",
    )
    skip_empty_collections: BoolProperty(
        name="Skip Empty Collections",
        default=True,
    )
    objects_per_tick: IntProperty(
        name="Objects per Tick",
        default=20,
        min=1,
        max=500,
        description="Number of mesh objects processed per timer tick. Lower values keep UI more responsive",
    )
    preview_sample_limit: IntProperty(
        name="Preview Sample Count",
        default=8,
        min=1,
        max=50,
        description="Only show this many target rows in the compact preview list",
    )

    # Foldout states
    show_export_target: BoolProperty(name="Show Export Target", default=True)
    show_filter: BoolProperty(name="Show Filter", default=True)
    show_processing: BoolProperty(name="Show Processing", default=True)
    show_preview: BoolProperty(name="Show Preview", default=True)
    show_advanced: BoolProperty(name="Show Advanced", default=False)


# -----------------------------------------------------------------------------
# Operators
# -----------------------------------------------------------------------------

class CMFE_OT_refresh_preview(Operator):
    bl_idname = "cmfe.refresh_preview"
    bl_label = "Refresh Preview"
    bl_description = "Scan target collections and show a compact export preview"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = context.scene
        props = scene.cmfe_props
        scene.cmfe_preview_items.clear()

        if props.root_collection is None:
            self.report({'ERROR'}, "Search Root Collection is not set.")
            return {'CANCELLED'}

        if not props.export_folder:
            self.report({'WARNING'}, "Export Folder is not set yet. Preview can still be generated.")

        targets = target_collections(props.root_collection, props)

        folder = bpy.path.abspath(props.export_folder) if props.export_folder else ""
        filename_counts = {}
        rows = []
        total_meshes = 0
        total_modifiers = 0
        ready_count = 0
        skipped_count = 0
        combined_file = combined_output_filename(props)
        combined_output_path = os.path.join(folder, combined_file) if folder else combined_file
        combined_file_blocked = (
            props.export_output_mode == "COMBINED"
            and folder
            and os.path.exists(combined_output_path)
            and not props.overwrite_existing
        )

        for coll in targets:
            sources = collect_mesh_sources_from_collection(coll, props)
            mesh_count = len(sources)
            modifier_count = count_modifiers_in_sources(sources)
            asset_ok = is_collection_asset(coll)
            name_ok = name_filter_match(coll.name, props.name_filter, props.name_match_rule, props.name_case_sensitive)
            out_file = (
                output_filename_for_collection(coll, props)
                if props.export_output_mode == "INDIVIDUAL"
                else combined_file
            )
            output_path = os.path.join(folder, out_file) if folder else out_file

            status = "Ready"
            reason = ""

            if mesh_count == 0 and props.skip_empty_collections:
                status = "Skipped"
                reason = "No mesh objects found"
            elif props.export_output_mode == "COMBINED" and combined_file_blocked:
                status = "Skipped"
                reason = "Combined output file already exists"
            elif (
                props.export_output_mode == "INDIVIDUAL"
                and folder
                and os.path.exists(output_path)
                and not props.overwrite_existing
            ):
                status = "Skipped"
                reason = "Output file already exists"

            filename_counts[out_file] = filename_counts.get(out_file, 0) + 1
            rows.append((coll, mesh_count, modifier_count, asset_ok, name_ok, out_file, status, reason))

            if status == "Ready":
                ready_count += 1
                total_meshes += mesh_count
                total_modifiers += modifier_count
            else:
                skipped_count += 1

        # Mark duplicate names as warnings/skips only in preview. Export will still overwrite by file name if allowed.
        for coll, mesh_count, modifier_count, asset_ok, name_ok, out_file, status, reason in rows:
            item = scene.cmfe_preview_items.add()
            item.collection_name = coll.name
            item.mesh_count = mesh_count
            item.modifier_count = modifier_count
            item.asset_registered = asset_ok
            item.name_match = name_ok
            item.output_file = out_file
            if props.export_output_mode == "INDIVIDUAL" and filename_counts.get(out_file, 0) > 1:
                item.status = "Warning"
                item.reason = "Duplicate export filename"
            else:
                item.status = status
                item.reason = reason

        scene.cmfe_total_collections = ready_count
        scene.cmfe_total_objects = total_meshes
        scene.cmfe_remaining_objects = total_meshes
        scene.cmfe_exported_count = 0
        scene.cmfe_skipped_count = skipped_count
        scene.cmfe_current_collection = ""
        mode_label = "individual files" if props.export_output_mode == "INDIVIDUAL" else f"single file: {combined_file}"
        scene.cmfe_status = (
            f"Preview: {ready_count} collections, {total_meshes} mesh objects, "
            f"{total_modifiers} modifiers, {export_format_label(props.export_format)} / {mode_label}"
        )
        scene.cmfe_progress = 0.0

        self.report({'INFO'}, scene.cmfe_status)
        return {'FINISHED'}


class CMFE_OT_cancel_export(Operator):
    bl_idname = "cmfe.cancel_export"
    bl_label = "Cancel Export"
    bl_description = "Request cancellation of the running export"

    def execute(self, context):
        context.scene.cmfe_cancel_requested = True
        self.report({'INFO'}, "Cancel requested. The current tick will finish first.")
        return {'FINISHED'}


class CMFE_OT_export_modal(Operator):
    bl_idname = "cmfe.export_modal"
    bl_label = "Export Files"
    bl_description = "Export target collections as merged files using a modal, chunked process"
    bl_options = {'REGISTER'}

    _timer = None
    _jobs = None
    _job_index = 0
    _source_index = 0
    _bm = None
    _materials = None
    _depsgraph = None
    _processed_sources = 0
    _total_sources = 0
    _export_folder = ""
    _export_format = "FBX"
    _export_output_mode = "INDIVIDUAL"
    _combined_filepath = ""
    _created_objects = None
    _original_active = None
    _original_selected_names = None
    _errors = None

    def invoke(self, context, event):
        scene = context.scene
        props = scene.cmfe_props

        if scene.cmfe_running:
            self.report({'ERROR'}, "Export is already running.")
            return {'CANCELLED'}

        if props.root_collection is None:
            self.report({'ERROR'}, "Search Root Collection is not set.")
            return {'CANCELLED'}

        if not props.export_folder:
            self.report({'ERROR'}, "Export Folder is not set.")
            return {'CANCELLED'}

        self._export_folder = ensure_export_folder(props.export_folder)
        if not self._export_folder:
            self.report({'ERROR'}, "Invalid Export Folder.")
            return {'CANCELLED'}

        targets = target_collections(props.root_collection, props)
        jobs = []
        self._export_format = props.export_format
        self._export_output_mode = props.export_output_mode
        self._combined_filepath = ""
        self._created_objects = []

        if props.export_output_mode == "COMBINED":
            self._combined_filepath = os.path.join(self._export_folder, combined_output_filename(props))
            if os.path.exists(self._combined_filepath) and not props.overwrite_existing:
                self.report({'ERROR'}, "Combined output file already exists.")
                return {'CANCELLED'}

        for coll in targets:
            sources = collect_mesh_sources_from_collection(coll, props)
            if len(sources) == 0 and props.skip_empty_collections:
                continue
            if props.export_output_mode == "INDIVIDUAL":
                filepath = os.path.join(self._export_folder, output_filename_for_collection(coll, props))
            else:
                filepath = self._combined_filepath
            if (
                props.export_output_mode == "INDIVIDUAL"
                and os.path.exists(filepath)
                and not props.overwrite_existing
            ):
                continue
            jobs.append({
                "collection": coll,
                "name": coll.name,
                "sources": sources,
                "filepath": filepath,
            })

        if not jobs:
            self.report({'ERROR'}, "No exportable collections found.")
            return {'CANCELLED'}

        self._jobs = jobs
        self._job_index = 0
        self._source_index = 0
        self._bm = None
        self._materials = None
        self._depsgraph = context.evaluated_depsgraph_get()
        self._processed_sources = 0
        self._total_sources = sum(len(job["sources"]) for job in jobs)
        self._errors = []

        self._original_active = context.view_layer.objects.active.name if context.view_layer.objects.active else None
        self._original_selected_names = [obj.name for obj in context.selected_objects]

        scene.cmfe_running = True
        scene.cmfe_cancel_requested = False
        scene.cmfe_progress = 0.0
        scene.cmfe_total_collections = len(jobs)
        scene.cmfe_total_objects = self._total_sources
        scene.cmfe_remaining_objects = self._total_sources
        scene.cmfe_exported_count = 0
        scene.cmfe_skipped_count = 0
        scene.cmfe_current_collection = jobs[0]["name"]
        scene.cmfe_status = f"Export started: {export_format_label(self._export_format)}"

        context.window_manager.progress_begin(0, max(1, self._total_sources))
        self._timer = context.window_manager.event_timer_add(0.05, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        scene = context.scene
        props = scene.cmfe_props

        if scene.cmfe_cancel_requested:
            self._finish(context, cancelled=True)
            return {'CANCELLED'}

        try:
            self._process_tick(context, props)
        except Exception as exc:
            self._errors.append(str(exc))
            traceback.print_exc()
            self._finish(context, cancelled=True)
            self.report({'ERROR'}, f"Export failed: {exc}")
            return {'CANCELLED'}

        if self._job_index >= len(self._jobs):
            self._finish(context, cancelled=False)
            return {'FINISHED'}

        return {'RUNNING_MODAL'}

    def _start_job_if_needed(self):
        if self._bm is None:
            self._bm = bmesh.new()
            self._materials = []
            self._source_index = 0

    def _process_tick(self, context, props):
        scene = context.scene
        if self._job_index >= len(self._jobs):
            return

        job = self._jobs[self._job_index]
        sources = job["sources"]
        scene.cmfe_current_collection = job["name"]

        self._start_job_if_needed()

        # Process source meshes in chunks.
        processed_this_tick = 0
        while self._source_index < len(sources) and processed_this_tick < props.objects_per_tick:
            source = sources[self._source_index]
            append_source_to_bmesh(
                self._bm,
                self._materials,
                source,
                self._depsgraph,
                props.apply_modifiers,
                props.keep_material_slots,
            )
            self._source_index += 1
            self._processed_sources += 1
            processed_this_tick += 1

            scene.cmfe_remaining_objects = max(0, self._total_sources - self._processed_sources)
            scene.cmfe_progress = self._processed_sources / max(1, self._total_sources)
            context.window_manager.progress_update(self._processed_sources)

        scene.cmfe_status = (
            f"Processing {job['name']} | "
            f"Remaining objects: {scene.cmfe_remaining_objects}"
        )

        # If this collection is done, create one merged object and export it now
        # or keep it selected later for a single combined file.
        if self._source_index >= len(sources):
            self._finish_current_job(context, job)
            self._job_index += 1
            self._bm = None
            self._materials = None
            self._source_index = 0

            if self._job_index < len(self._jobs):
                scene.cmfe_current_collection = self._jobs[self._job_index]["name"]
            elif self._export_output_mode == "COMBINED":
                self._export_combined_jobs(context)

    def _finish_current_job(self, context, job):
        scene = context.scene
        obj = None
        try:
            obj = make_merged_object_from_bmesh(job["name"], self._bm, self._materials, scene)
            self._bm.free()
            self._bm = None

            if self._export_output_mode == "COMBINED":
                self._created_objects.append(obj)
                scene.cmfe_status = f"Prepared {job['name']} for combined export"
                return

            select_only_objects(context, [obj])
            export_selected_objects(job["filepath"], context, self._export_format)
            scene.cmfe_exported_count += 1
        finally:
            if self._export_output_mode == "INDIVIDUAL":
                remove_object_and_mesh(obj)
                cleanup_temp_collection_if_empty()

    def _export_combined_jobs(self, context):
        if not self._created_objects:
            return
        scene = context.scene
        scene.cmfe_status = f"Writing combined {export_format_label(self._export_format)} file"
        select_only_objects(context, self._created_objects)
        export_selected_objects(self._combined_filepath, context, self._export_format)
        scene.cmfe_exported_count = 1

    def _restore_selection(self, context):
        try:
            deselect_all(context)
            for name in self._original_selected_names or []:
                obj = bpy.data.objects.get(name)
                if obj:
                    obj.select_set(True)
            if self._original_active:
                active = bpy.data.objects.get(self._original_active)
                if active:
                    context.view_layer.objects.active = active
        except Exception:
            pass

    def _finish(self, context, cancelled=False):
        scene = context.scene

        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None

        try:
            context.window_manager.progress_end()
        except Exception:
            pass

        if self._bm is not None:
            try:
                self._bm.free()
            except Exception:
                pass
            self._bm = None

        for obj in self._created_objects or []:
            remove_object_and_mesh(obj)
        self._created_objects = []

        self._restore_selection(context)
        cleanup_temp_collection_if_empty()

        scene.cmfe_running = False
        scene.cmfe_cancel_requested = False
        scene.cmfe_remaining_objects = max(0, self._total_sources - self._processed_sources)
        scene.cmfe_progress = 1.0 if not cancelled else scene.cmfe_progress

        if cancelled:
            scene.cmfe_status = "Export cancelled"
            self.report({'WARNING'}, "Export cancelled.")
        else:
            format_label = export_format_label(self._export_format)
            scene.cmfe_status = f"Export completed: {scene.cmfe_exported_count} {format_label} file(s)"
            self.report({'INFO'}, scene.cmfe_status)


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------

class CMFE_PT_panel(Panel):
    bl_label = "Collection Mesh Exporter"
    bl_idname = "CMFE_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "CMFE"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = scene.cmfe_props

        self.draw_foldout(layout, props, "show_export_target", "1. Export Target")
        if props.show_export_target:
            box = layout.box()
            box.prop(props, "export_folder")
            box.prop(props, "root_collection")
            box.prop(props, "include_root_collection")
            box.separator()
            box.prop(props, "export_format")
            box.prop(props, "export_output_mode")
            if props.export_output_mode == "COMBINED":
                box.prop(props, "combined_file_name")

        self.draw_foldout(layout, props, "show_filter", "2. Filter")
        if props.show_filter:
            box = layout.box()
            box.prop(props, "filter_mode")
            if props.filter_mode in {'NAME', 'ASSET_AND_NAME', 'ASSET_OR_NAME'}:
                box.prop(props, "name_filter")
                box.prop(props, "name_match_rule")
                box.prop(props, "name_case_sensitive")
            box.prop(props, "nested_target_rule")

        self.draw_foldout(layout, props, "show_processing", "3. Mesh Processing")
        if props.show_processing:
            box = layout.box()
            box.prop(props, "include_nested_meshes")
            box.prop(props, "include_hidden_objects")
            box.prop(props, "include_collection_instances")
            box.separator()
            box.prop(props, "apply_modifiers")
            box.prop(props, "keep_material_slots")
            box.label(text="Origin Mode: World 0,0,0", icon='ORIENTATION_GLOBAL')
            box.label(text="Transforms: baked into vertices", icon='OBJECT_ORIGIN')

        self.draw_foldout(layout, props, "show_advanced", "4. Export / Performance")
        if props.show_advanced:
            box = layout.box()
            box.prop(props, "overwrite_existing")
            box.prop(props, "skip_empty_collections")
            box.prop(props, "objects_per_tick")
            box.prop(props, "preview_sample_limit")
            box.label(text="Auto Save: OFF", icon='FILE_TICK')
            if props.export_format == "FBX":
                box.label(text="FBX Axis: -Z Forward / Y Up", icon='EXPORT')
            else:
                box.label(text=f"Format: {export_format_label(props.export_format)}", icon='EXPORT')

        # Main actions are intentionally outside any foldout so the export button
        # is always visible, even when preview/settings sections are collapsed.
        layout.separator()
        action_box = layout.box()
        action_box.label(text="Main Actions", icon='PLAY')
        row = action_box.row(align=True)
        row.operator("cmfe.refresh_preview", icon='VIEWZOOM')
        if scene.cmfe_running:
            row.operator("cmfe.cancel_export", icon='CANCEL')
        else:
            row.operator("cmfe.export_modal", text=f"Export {props.export_format}", icon='EXPORT')

        action_box.label(text=scene.cmfe_status or "Ready. Set Export Folder and Search Root Collection.")
        if scene.cmfe_running:
            action_box.label(text=f"Remaining Objects: {scene.cmfe_remaining_objects}")
            if scene.cmfe_current_collection:
                action_box.label(text=f"Current: {scene.cmfe_current_collection}")
            if hasattr(action_box, "progress"):
                action_box.progress(
                    factor=scene.cmfe_progress,
                    type='BAR',
                    text=f"{int(scene.cmfe_progress * 100)}%",
                )
            else:
                action_box.label(text=f"Progress: {int(scene.cmfe_progress * 100)}%")

        self.draw_foldout(layout, props, "show_preview", "5. Preview")
        if props.show_preview:
            box = layout.box()
            box.label(text=scene.cmfe_status or "No preview yet")
            box.label(text=f"Export Collections: {scene.cmfe_total_collections}")
            box.label(text=f"Total Mesh Objects: {scene.cmfe_total_objects}")
            box.label(text=f"Remaining Objects: {scene.cmfe_remaining_objects}")
            if scene.cmfe_current_collection:
                box.label(text=f"Current: {scene.cmfe_current_collection}")

            if len(scene.cmfe_preview_items) > 0:
                box.separator()
                box.label(text="Compact Preview")
                max_rows = min(len(scene.cmfe_preview_items), props.preview_sample_limit)
                for i in range(max_rows):
                    item = scene.cmfe_preview_items[i]
                    row = box.row(align=True)
                    icon = 'CHECKMARK' if item.status == "Ready" else 'ERROR' if item.status == "Skipped" else 'INFO'
                    row.label(text=item.collection_name, icon=icon)
                    row.label(text=f"Meshes: {item.mesh_count}")
                    row.label(text=f"Mods: {item.modifier_count}")

                    if item.reason:
                        box.label(text=f"  {item.status}: {item.reason}")

                remaining = len(scene.cmfe_preview_items) - max_rows
                if remaining > 0:
                    box.label(text=f"...and {remaining} more rows")

    @staticmethod
    def draw_foldout(layout, props, prop_name, text):
        row = layout.row(align=True)
        icon = 'TRIA_DOWN' if getattr(props, prop_name) else 'TRIA_RIGHT'
        row.prop(props, prop_name, text=text, icon=icon, emboss=False)


# -----------------------------------------------------------------------------
# Register
# -----------------------------------------------------------------------------

class CMFE_AddonPreferences(AddonPreferences):
    bl_idname = __package__ or __name__

    def draw(self, context):
        layout = self.layout
        layout.label(text="Documentation")
        op = layout.operator("wm.url_open", text="Open User Guide on GitHub", icon="URL")
        op.url = DOCUMENTATION_URL


classes = (
    CMFE_AddonPreferences,
    CMFE_PreviewItem,
    CMFE_Properties,
    CMFE_OT_refresh_preview,
    CMFE_OT_cancel_export,
    CMFE_OT_export_modal,
    CMFE_PT_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.cmfe_props = PointerProperty(type=CMFE_Properties)
    bpy.types.Scene.cmfe_preview_items = CollectionProperty(type=CMFE_PreviewItem)

    bpy.types.Scene.cmfe_progress = FloatProperty(name="CMFE Progress", default=0.0, min=0.0, max=1.0)
    bpy.types.Scene.cmfe_status = StringProperty(name="CMFE Status", default="")
    bpy.types.Scene.cmfe_total_objects = IntProperty(name="CMFE Total Objects", default=0)
    bpy.types.Scene.cmfe_remaining_objects = IntProperty(name="CMFE Remaining Objects", default=0)
    bpy.types.Scene.cmfe_total_collections = IntProperty(name="CMFE Total Collections", default=0)
    bpy.types.Scene.cmfe_exported_count = IntProperty(name="CMFE Exported Count", default=0)
    bpy.types.Scene.cmfe_skipped_count = IntProperty(name="CMFE Skipped Count", default=0)
    bpy.types.Scene.cmfe_current_collection = StringProperty(name="CMFE Current Collection", default="")
    bpy.types.Scene.cmfe_running = BoolProperty(name="CMFE Running", default=False)
    bpy.types.Scene.cmfe_cancel_requested = BoolProperty(name="CMFE Cancel Requested", default=False)


def unregister():
    cleanup_temp_collection_if_empty()

    del bpy.types.Scene.cmfe_props
    del bpy.types.Scene.cmfe_preview_items
    del bpy.types.Scene.cmfe_progress
    del bpy.types.Scene.cmfe_status
    del bpy.types.Scene.cmfe_total_objects
    del bpy.types.Scene.cmfe_remaining_objects
    del bpy.types.Scene.cmfe_total_collections
    del bpy.types.Scene.cmfe_exported_count
    del bpy.types.Scene.cmfe_skipped_count
    del bpy.types.Scene.cmfe_current_collection
    del bpy.types.Scene.cmfe_running
    del bpy.types.Scene.cmfe_cancel_requested

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
