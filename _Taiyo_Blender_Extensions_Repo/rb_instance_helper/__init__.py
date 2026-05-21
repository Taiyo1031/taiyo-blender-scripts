
bl_info = {
    "name": "RB Instance Helper",
    "author": "Taiyo Parent + ChatGPT",
    "version": (1, 3, 1),
    "blender": (5, 1, 0),
    "location": "View3D > N-panel > RB Helper",
    "description": "Rigid Body workflow helper for linked Collection Instances using stable generated proxy meshes",
    "category": "Object",
}

import uuid
import bpy
from mathutils import Matrix, Vector
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import (
    BoolProperty,
    EnumProperty,
    IntProperty,
    PointerProperty,
)


# ──────────────────────────────────────────────────────────────────────────────
# Constants / Custom Properties
# ──────────────────────────────────────────────────────────────────────────────

ADDON_VERSION_STR = "1.3.1"
RB_PROXIES_COLLECTION_NAME = "RB_Proxies"

PROP_PAIR_ID = "rbih_pair_id"
PROP_ROLE = "rbih_role"
PROP_VERSION = "rbih_version"
PROP_SOURCE_INSTANCE_NAME = "rbih_source_instance_name"
PROP_PROXY_ROOT_NAME = "rbih_proxy_root_name"
PROP_SOURCE_COLLECTION_NAME = "rbih_source_collection_name"
PROP_IS_GENERATED_PROXY = "rbih_is_generated_proxy"
PROP_INSTANCE_OFFSET_MATRIX = "rbih_instance_offset_matrix"
PROP_PROXY_ORIGIN_OFFSET_LOCAL = "rbih_proxy_origin_offset_local"

ROLE_INSTANCE = "INSTANCE"
ROLE_PROXY_ROOT = "PROXY_ROOT"

# Legacy properties kept for compatibility with v1.1 tools/files.
LEGACY_PROP_PROXY_SOURCE = "rb_proxy_source"
LEGACY_PROP_PROXY_REF = "rb_proxy_ref"


RB_COPY_PROPS = (
    "type",
    "mass",
    "friction",
    "restitution",
    "collision_shape",
    "mesh_source",
    "use_margin",
    "collision_margin",
    "linear_damping",
    "angular_damping",
)


# ──────────────────────────────────────────────────────────────────────────────
# Scene Properties
# ──────────────────────────────────────────────────────────────────────────────

class RBIH_Props(PropertyGroup):
    target_mode: EnumProperty(
        name="Target",
        items=[
            ("SELECTED",   "Selected Objects", "Use currently selected linked Collection Instance objects"),
            ("COLLECTION", "Collection",        "Use all linked Collection Instance objects in specified collection"),
        ],
        default="SELECTED",
    )

    target_collection: PointerProperty(
        name="Collection",
        type=bpy.types.Collection,
    )

    hide_proxy_render: BoolProperty(
        name="Hide Proxy from Render",
        default=True,
        description="Hide generated proxy mesh from render. The original linked instance remains renderable",
    )

    move_to_rb_collection: BoolProperty(
        name='Put Proxies in "RB_Proxies"',
        default=True,
        description='Put generated proxy meshes into the "RB_Proxies" collection. The original linked instance is not moved',
    )

    auto_add_rigid_body: BoolProperty(
        name="Auto Add Rigid Body",
        default=True,
        description="Automatically add an Active Rigid Body to each generated proxy",
    )

    center_proxy_origin: BoolProperty(
        name="Center Proxy Origin",
        default=True,
        description="Move generated proxy origin to the combined mesh bounds center for more stable Rigid Body simulation. The visual instance offset is preserved",
    )

    default_collision_shape: EnumProperty(
        name="Collision Shape",
        items=[
            ("CONVEX_HULL", "Convex Hull", "Stable default for moving rigid bodies"),
            ("MESH",        "Mesh",        "Use exact proxy mesh shape. Useful but heavier and less stable for complex active bodies"),
            ("BOX",         "Box",         "Fast simple box collision"),
            ("SPHERE",      "Sphere",      "Fast simple sphere collision"),
            ("CAPSULE",     "Capsule",     "Capsule collision"),
            ("CYLINDER",    "Cylinder",    "Cylinder collision"),
            ("CONE",        "Cone",        "Cone collision"),
        ],
        default="CONVEX_HULL",
        description="Default collision shape assigned when Auto Add Rigid Body is enabled",
    )

    frame_range_mode: EnumProperty(
        name="Range",
        items=[
            ("SCENE",  "Scene",  "Use scene frame range"),
            ("CUSTOM", "Custom", "Use custom frame range"),
        ],
        default="SCENE",
    )

    frame_start_custom: IntProperty(name="Start", default=1, min=0)
    frame_end_custom:   IntProperty(name="End",   default=250, min=1)

    delete_proxy_after_transfer: BoolProperty(
        name="Delete Proxy after Transfer",
        default=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# General Utilities
# ──────────────────────────────────────────────────────────────────────────────

def _safe_name(name):
    """Object names can contain most characters, but keep generated data readable."""
    return "".join(c if c not in "\\/:*?\"<>|" else "_" for c in name)


def _new_pair_id():
    return uuid.uuid4().hex


def _ensure_object_mode(context):
    obj = context.active_object
    if obj and obj.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


def _ensure_rb_world(context):
    if context.scene.rigidbody_world is None:
        bpy.ops.rigidbody.world_add()


def _get_or_create_rb_proxies_col(context):
    col = bpy.data.collections.get(RB_PROXIES_COLLECTION_NAME)
    if col is None:
        col = bpy.data.collections.new(RB_PROXIES_COLLECTION_NAME)
        context.scene.collection.children.link(col)

    # Blender color tags are theme-dependent, but COLOR_03 is usually close to brown/orange.
    try:
        col.color_tag = "COLOR_03"
    except Exception:
        pass

    return col


def _link_object_to_collection(obj, col):
    if obj.name not in col.objects:
        col.objects.link(obj)


def _unlink_object_from_all_collections(obj):
    for col in list(obj.users_collection):
        try:
            col.objects.unlink(obj)
        except RuntimeError:
            pass


def _put_object_in_collection(obj, col, exclusive=True):
    if exclusive:
        _unlink_object_from_all_collections(obj)
    if obj.name not in col.objects:
        col.objects.link(obj)


def _store_selection(context):
    return list(context.selected_objects), context.view_layer.objects.active


def _restore_selection(context, selected, active):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in selected:
        if obj and obj.name in bpy.data.objects:
            obj.select_set(True)
    if active and active.name in bpy.data.objects:
        context.view_layer.objects.active = active


def _select_only(context, objects, active=None):
    bpy.ops.object.select_all(action="DESELECT")
    alive = [o for o in objects if o and o.name in bpy.data.objects]
    for obj in alive:
        obj.select_set(True)
    if active is None and alive:
        active = alive[0]
    if active and active.name in bpy.data.objects:
        context.view_layer.objects.active = active


def _has_pair(obj):
    return obj is not None and PROP_PAIR_ID in obj


def _get_pair_id(obj):
    if not obj:
        return ""
    return obj.get(PROP_PAIR_ID, "")


def _role(obj):
    if not obj:
        return ""
    return obj.get(PROP_ROLE, "")


def _objects_with_pair(pair_id):
    if not pair_id:
        return []
    return [o for o in bpy.data.objects if o.get(PROP_PAIR_ID, "") == pair_id]


def _find_instance_by_pair(pair_id):
    for obj in _objects_with_pair(pair_id):
        if obj.get(PROP_ROLE, "") == ROLE_INSTANCE:
            return obj
    return None


def _find_proxy_by_pair(pair_id):
    for obj in _objects_with_pair(pair_id):
        if obj.get(PROP_ROLE, "") == ROLE_PROXY_ROOT:
            return obj
    return None


def _find_pair_id_from_legacy(obj):
    """Best-effort migration support for v1.1 files."""
    if not obj:
        return ""

    if obj.get(LEGACY_PROP_PROXY_REF):
        proxy = bpy.data.objects.get(obj.get(LEGACY_PROP_PROXY_REF))
        if proxy and proxy.get(PROP_PAIR_ID):
            return proxy.get(PROP_PAIR_ID)

    if obj.get(LEGACY_PROP_PROXY_SOURCE):
        inst = bpy.data.objects.get(obj.get(LEGACY_PROP_PROXY_SOURCE))
        if inst and inst.get(PROP_PAIR_ID):
            return inst.get(PROP_PAIR_ID)

    return ""


def _pair_ids_from_objects(objects):
    ids = []
    for obj in objects:
        pair_id = _get_pair_id(obj) or _find_pair_id_from_legacy(obj)
        if pair_id and pair_id not in ids:
            ids.append(pair_id)
    return ids


def _get_frame_range(props, scene):
    if props.frame_range_mode == "SCENE":
        return scene.frame_start, scene.frame_end
    return props.frame_start_custom, props.frame_end_custom


def _copy_custom_id_properties(src, dst, skip_rbih=True):
    """Copy user custom properties except internal RBIH link properties."""
    if not src or not dst:
        return

    internal_keys = {
        PROP_PAIR_ID,
        PROP_ROLE,
        PROP_VERSION,
        PROP_SOURCE_INSTANCE_NAME,
        PROP_PROXY_ROOT_NAME,
        PROP_SOURCE_COLLECTION_NAME,
        PROP_IS_GENERATED_PROXY,
        PROP_INSTANCE_OFFSET_MATRIX,
        PROP_PROXY_ORIGIN_OFFSET_LOCAL,
        LEGACY_PROP_PROXY_SOURCE,
        LEGACY_PROP_PROXY_REF,
    }

    for key in src.keys():
        if skip_rbih and key in internal_keys:
            continue
        try:
            dst[key] = src[key]
        except Exception:
            pass


def _matrix_to_list(mat):
    return [float(mat[r][c]) for r in range(4) for c in range(4)]


def _matrix_from_list(values, fallback=None):
    try:
        vals = list(values)
        if len(vals) != 16:
            raise ValueError("matrix list must contain 16 values")
        return Matrix((
            vals[0:4],
            vals[4:8],
            vals[8:12],
            vals[12:16],
        ))
    except Exception:
        return fallback.copy() if fallback is not None else Matrix.Identity(4)


def _vector_to_list(vec):
    return [float(vec.x), float(vec.y), float(vec.z)]


# ──────────────────────────────────────────────────────────────────────────────
# Target Collection Instances
# ──────────────────────────────────────────────────────────────────────────────

def _is_collection_instance(obj):
    return obj is not None and obj.instance_collection is not None


def _get_target_instances(context):
    props = context.scene.rbih

    if props.target_mode == "SELECTED":
        return [o for o in context.selected_objects if _is_collection_instance(o)]

    if props.target_mode == "COLLECTION":
        if not props.target_collection:
            return []
        return [o for o in props.target_collection.all_objects if _is_collection_instance(o)]

    return []


# ──────────────────────────────────────────────────────────────────────────────
# Mesh Proxy Generation
# ──────────────────────────────────────────────────────────────────────────────

def _iter_mesh_source_objects(source_collection):
    if not source_collection:
        return []
    return [o for o in source_collection.all_objects if o.type == "MESH" and o.data is not None]


def _mesh_data_for_object(context, src_obj):
    """
    Returns evaluated mesh data when possible, otherwise base mesh data.
    Caller must call to_mesh_clear() on eval_obj when eval_obj is not None.
    """
    depsgraph = context.evaluated_depsgraph_get()

    try:
        eval_obj = src_obj.evaluated_get(depsgraph)
        mesh = eval_obj.to_mesh(preserve_all_data_layers=False, depsgraph=depsgraph)
        if mesh:
            return mesh, eval_obj
    except Exception:
        pass

    return src_obj.data, None


def _build_combined_proxy_mesh(context, instance_obj, center_origin=True):
    """
    Build a single generated mesh for a linked Collection Instance.

    Source vertices are first generated in the Collection Instance's local space.
    When center_origin=True, the generated mesh vertices are shifted so the
    proxy object's origin sits at the combined bounds center. This makes the
    proxy origin usable as the Rigid Body center of mass while preserving the
    visual instance through a stored offset matrix.

    Returns (mesh, origin_offset_local, error).
    """
    source_col = instance_obj.instance_collection
    mesh_sources = _iter_mesh_source_objects(source_col)

    if not mesh_sources:
        return None, Vector((0.0, 0.0, 0.0)), "No mesh objects found in source collection"

    raw_verts = []
    faces = []
    source_names = []

    for src_obj in mesh_sources:
        src_mesh, eval_obj = _mesh_data_for_object(context, src_obj)

        if not src_mesh or len(src_mesh.vertices) == 0:
            if eval_obj:
                try:
                    eval_obj.to_mesh_clear()
                except Exception:
                    pass
            continue

        # In Collection Instance drawing, source object transforms are applied under the instance transform.
        # Therefore vertices are first placed into the Collection Instance's local space.
        mat = src_obj.matrix_world.copy()
        base_index = len(raw_verts)

        for v in src_mesh.vertices:
            raw_verts.append(mat @ v.co)

        for poly in src_mesh.polygons:
            if len(poly.vertices) >= 3:
                faces.append(tuple(base_index + i for i in poly.vertices))

        source_names.append(src_obj.name)

        if eval_obj:
            try:
                eval_obj.to_mesh_clear()
            except Exception:
                pass

    if not raw_verts or not faces:
        return None, Vector((0.0, 0.0, 0.0)), "Source collection contains meshes, but no valid faces were generated"

    origin_offset_local = Vector((0.0, 0.0, 0.0))

    if center_origin:
        min_v = Vector((
            min(v.x for v in raw_verts),
            min(v.y for v in raw_verts),
            min(v.z for v in raw_verts),
        ))
        max_v = Vector((
            max(v.x for v in raw_verts),
            max(v.y for v in raw_verts),
            max(v.z for v in raw_verts),
        ))
        origin_offset_local = (min_v + max_v) * 0.5

    verts = [v - origin_offset_local for v in raw_verts]

    mesh_name = f"RBProxyMesh_{_safe_name(instance_obj.name)}"
    mesh = bpy.data.meshes.new(mesh_name)
    mesh.from_pydata(verts, [], faces)
    mesh.validate(clean_customdata=True)
    mesh.update()

    # Store metadata on Mesh datablock too; useful if object is renamed.
    mesh["rbih_generated_from_collection"] = source_col.name if source_col else ""
    mesh["rbih_source_object_count"] = len(source_names)
    mesh["rbih_source_objects"] = ", ".join(source_names[:32])
    mesh[PROP_PROXY_ORIGIN_OFFSET_LOCAL] = _vector_to_list(origin_offset_local)

    return mesh, origin_offset_local, None


def _assign_pair_properties(instance_obj, proxy_obj, pair_id):
    source_col_name = instance_obj.instance_collection.name if instance_obj.instance_collection else ""

    instance_obj[PROP_PAIR_ID] = pair_id
    instance_obj[PROP_ROLE] = ROLE_INSTANCE
    instance_obj[PROP_VERSION] = ADDON_VERSION_STR
    instance_obj[PROP_PROXY_ROOT_NAME] = proxy_obj.name
    instance_obj[PROP_SOURCE_COLLECTION_NAME] = source_col_name

    proxy_obj[PROP_PAIR_ID] = pair_id
    proxy_obj[PROP_ROLE] = ROLE_PROXY_ROOT
    proxy_obj[PROP_VERSION] = ADDON_VERSION_STR
    proxy_obj[PROP_SOURCE_INSTANCE_NAME] = instance_obj.name
    proxy_obj[PROP_SOURCE_COLLECTION_NAME] = source_col_name
    proxy_obj[PROP_IS_GENERATED_PROXY] = True

    # Legacy v1.1 compatible properties.
    proxy_obj[LEGACY_PROP_PROXY_SOURCE] = instance_obj.name
    instance_obj[LEGACY_PROP_PROXY_REF] = proxy_obj.name


def _store_instance_proxy_offset(instance_obj, proxy_obj):
    if not instance_obj or not proxy_obj:
        return Matrix.Identity(4)

    try:
        offset = proxy_obj.matrix_world.inverted() @ instance_obj.matrix_world
    except Exception:
        offset = Matrix.Identity(4)

    values = _matrix_to_list(offset)
    try:
        instance_obj[PROP_INSTANCE_OFFSET_MATRIX] = values
    except Exception:
        pass
    try:
        proxy_obj[PROP_INSTANCE_OFFSET_MATRIX] = values
    except Exception:
        pass
    return offset


def _get_instance_proxy_offset(instance_obj, proxy_obj):
    fallback = None
    if instance_obj and proxy_obj:
        try:
            fallback = proxy_obj.matrix_world.inverted() @ instance_obj.matrix_world
        except Exception:
            fallback = Matrix.Identity(4)
    else:
        fallback = Matrix.Identity(4)

    for obj in (instance_obj, proxy_obj):
        if obj and PROP_INSTANCE_OFFSET_MATRIX in obj:
            return _matrix_from_list(obj.get(PROP_INSTANCE_OFFSET_MATRIX), fallback=fallback)

    return fallback


def _parent_instance_to_proxy_keep_world(instance_obj, proxy_obj):
    world = instance_obj.matrix_world.copy()
    _store_instance_proxy_offset(instance_obj, proxy_obj)
    instance_obj.parent = proxy_obj
    try:
        instance_obj.matrix_parent_inverse = proxy_obj.matrix_world.inverted()
    except Exception:
        instance_obj.matrix_parent_inverse = Matrix.Identity(4)
    instance_obj.matrix_world = world


def _unparent_instance_keep_world(instance_obj):
    if not instance_obj:
        return
    world = instance_obj.matrix_world.copy()
    instance_obj.parent = None
    instance_obj.matrix_world = world


def _apply_default_proxy_display(proxy_obj):
    proxy_obj.show_name = True
    proxy_obj.show_in_front = False
    proxy_obj.display_type = "WIRE"
    proxy_obj.color = (0.55, 0.32, 0.16, 1.0)


def _ensure_rigid_body_on_proxy(context, proxy_obj, props):
    _ensure_rb_world(context)

    prev_selected, prev_active = _store_selection(context)

    try:
        _ensure_object_mode(context)
        _select_only(context, [proxy_obj], active=proxy_obj)

        if proxy_obj.rigid_body is None:
            bpy.ops.rigidbody.object_add(type="ACTIVE")

        rb = proxy_obj.rigid_body
        if rb:
            rb.type = "ACTIVE"
            try:
                rb.collision_shape = props.default_collision_shape
            except Exception:
                rb.collision_shape = "CONVEX_HULL"

            # A safe default for generated proxies. Users can still edit or copy settings later.
            rb.mass = max(rb.mass, 1.0)

    finally:
        _restore_selection(context, prev_selected, prev_active)


def _create_proxy_for_instance(context, instance_obj, pair_id=None, rb_cache=None, fc_cache=None, matrix_cache=None):
    props = context.scene.rbih

    if not _is_collection_instance(instance_obj):
        return None, f"'{instance_obj.name}' is not a linked Collection Instance"

    if pair_id is None:
        pair_id = _new_pair_id()

    mesh, origin_offset_local, err = _build_combined_proxy_mesh(
        context,
        instance_obj,
        center_origin=bool(props.center_proxy_origin),
    )
    if err:
        return None, f"{instance_obj.name}: {err}"

    proxy_name = f"RBProxy_{_safe_name(instance_obj.name)}"
    proxy_obj = bpy.data.objects.new(proxy_name, mesh)

    if matrix_cache:
        proxy_obj.matrix_world = matrix_cache.copy()
    else:
        # Move the proxy object origin to the generated mesh center.
        # Mesh vertices are shifted by -origin_offset_local, so the final visible
        # proxy geometry remains exactly aligned with the original Collection Instance.
        proxy_obj.matrix_world = instance_obj.matrix_world.copy() @ Matrix.Translation(origin_offset_local)

    proxy_obj[PROP_PROXY_ORIGIN_OFFSET_LOCAL] = _vector_to_list(origin_offset_local)

    target_col = _get_or_create_rb_proxies_col(context) if props.move_to_rb_collection else context.scene.collection
    target_col.objects.link(proxy_obj)

    proxy_obj.hide_render = bool(props.hide_proxy_render)
    _apply_default_proxy_display(proxy_obj)
    _assign_pair_properties(instance_obj, proxy_obj, pair_id)

    if props.auto_add_rigid_body:
        _ensure_rigid_body_on_proxy(context, proxy_obj, props)

    if rb_cache:
        _apply_rb_cache(context, proxy_obj, rb_cache)

    if fc_cache:
        _restore_fcurves(proxy_obj, fc_cache)

    _parent_instance_to_proxy_keep_world(instance_obj, proxy_obj)

    return proxy_obj, None


# ──────────────────────────────────────────────────────────────────────────────
# Rigid Body / Animation Cache
# ──────────────────────────────────────────────────────────────────────────────

def _cache_rb(obj):
    rb = obj.rigid_body if obj else None
    if not rb:
        return None

    result = {}
    for prop_name in RB_COPY_PROPS:
        if hasattr(rb, prop_name):
            try:
                result[prop_name] = getattr(rb, prop_name)
            except Exception:
                pass
    return result


def _apply_rb_cache(context, obj, cache):
    if not obj or not cache:
        return

    prev_selected, prev_active = _store_selection(context)

    try:
        _ensure_rb_world(context)
        _ensure_object_mode(context)
        _select_only(context, [obj], active=obj)

        if obj.rigid_body is None:
            bpy.ops.rigidbody.object_add(type="ACTIVE")

        rb = obj.rigid_body
        if not rb:
            return

        for k, v in cache.items():
            if hasattr(rb, k):
                try:
                    setattr(rb, k, v)
                except Exception:
                    pass

    finally:
        _restore_selection(context, prev_selected, prev_active)


def _cache_fcurves(obj):
    if not obj or not obj.animation_data or not obj.animation_data.action:
        return []

    result = []
    action = obj.animation_data.action

    for fc in action.fcurves:
        pts = []
        for kp in fc.keyframe_points:
            left = tuple(kp.handle_left)
            right = tuple(kp.handle_right)
            co = tuple(kp.co)
            pts.append({
                "co": co,
                "handle_left": left,
                "handle_right": right,
                "interpolation": kp.interpolation,
                "easing": kp.easing,
            })
        result.append({
            "data_path": fc.data_path,
            "array_index": fc.array_index,
            "points": pts,
        })

    return result


def _restore_fcurves(obj, cache):
    if not obj or not cache:
        return

    obj.animation_data_create()

    # Replace action to avoid accumulating old curves.
    old_action = obj.animation_data.action
    action = bpy.data.actions.new(name=f"{obj.name}_Action")
    obj.animation_data.action = action

    # Do not delete old_action; it may be used elsewhere or intentionally kept by Blender.

    for item in cache:
        try:
            fc = action.fcurves.new(data_path=item["data_path"], index=item["array_index"])
        except Exception:
            continue

        pts = item.get("points", [])
        if not pts:
            continue

        fc.keyframe_points.add(len(pts))

        for i, data in enumerate(pts):
            kp = fc.keyframe_points[i]
            kp.co = data["co"]
            kp.handle_left = data["handle_left"]
            kp.handle_right = data["handle_right"]
            kp.interpolation = data["interpolation"]
            kp.easing = data["easing"]

        fc.update()


def _cache_proxy_state(proxy_obj):
    if not proxy_obj:
        return {
            "matrix": None,
            "rb": None,
            "fcurves": [],
            "custom_props": {},
        }

    custom_props = {}
    internal = {
        PROP_PAIR_ID,
        PROP_ROLE,
        PROP_VERSION,
        PROP_SOURCE_INSTANCE_NAME,
        PROP_PROXY_ROOT_NAME,
        PROP_SOURCE_COLLECTION_NAME,
        PROP_IS_GENERATED_PROXY,
        PROP_INSTANCE_OFFSET_MATRIX,
        PROP_PROXY_ORIGIN_OFFSET_LOCAL,
        LEGACY_PROP_PROXY_SOURCE,
        LEGACY_PROP_PROXY_REF,
    }

    for key in proxy_obj.keys():
        if key not in internal:
            try:
                custom_props[key] = proxy_obj[key]
            except Exception:
                pass

    return {
        "matrix": proxy_obj.matrix_world.copy(),
        "rb": _cache_rb(proxy_obj),
        "fcurves": _cache_fcurves(proxy_obj),
        "custom_props": custom_props,
    }


def _apply_proxy_state(context, proxy_obj, state):
    if not proxy_obj or not state:
        return

    if state.get("matrix") is not None:
        proxy_obj.matrix_world = state["matrix"]

    for k, v in state.get("custom_props", {}).items():
        try:
            proxy_obj[k] = v
        except Exception:
            pass

    if state.get("rb"):
        _apply_rb_cache(context, proxy_obj, state["rb"])

    if state.get("fcurves"):
        _restore_fcurves(proxy_obj, state["fcurves"])


# ──────────────────────────────────────────────────────────────────────────────
# Pair Delete / Rebuild
# ──────────────────────────────────────────────────────────────────────────────

def _remove_proxy_object(obj):
    if not obj or obj.name not in bpy.data.objects:
        return

    mesh = obj.data if obj.type == "MESH" else None
    bpy.data.objects.remove(obj, do_unlink=True)

    if mesh and mesh.users == 0:
        try:
            bpy.data.meshes.remove(mesh)
        except Exception:
            pass


def _delete_proxy_objects_for_pair(pair_id):
    for obj in list(_objects_with_pair(pair_id)):
        if obj.get(PROP_ROLE, "") == ROLE_PROXY_ROOT or obj.get(PROP_IS_GENERATED_PROXY, False):
            _remove_proxy_object(obj)


def _cleanup_instance_pair_props(instance_obj):
    if not instance_obj:
        return

    for key in (
        PROP_PAIR_ID,
        PROP_ROLE,
        PROP_VERSION,
        PROP_PROXY_ROOT_NAME,
        PROP_SOURCE_COLLECTION_NAME,
        PROP_INSTANCE_OFFSET_MATRIX,
        PROP_PROXY_ORIGIN_OFFSET_LOCAL,
        LEGACY_PROP_PROXY_REF,
    ):
        if key in instance_obj:
            try:
                del instance_obj[key]
            except Exception:
                pass


def _cleanup_proxy_pair_props(proxy_obj):
    if not proxy_obj:
        return

    for key in (
        PROP_PAIR_ID,
        PROP_ROLE,
        PROP_VERSION,
        PROP_SOURCE_INSTANCE_NAME,
        PROP_SOURCE_COLLECTION_NAME,
        PROP_IS_GENERATED_PROXY,
        PROP_INSTANCE_OFFSET_MATRIX,
        PROP_PROXY_ORIGIN_OFFSET_LOCAL,
        LEGACY_PROP_PROXY_SOURCE,
    ):
        if key in proxy_obj:
            try:
                del proxy_obj[key]
            except Exception:
                pass


def _rebuild_pair(context, pair_id, op=None):
    instance_obj = _find_instance_by_pair(pair_id)
    proxy_obj = _find_proxy_by_pair(pair_id)

    if not instance_obj:
        if op:
            op.report({"WARNING"}, f"Pair {pair_id}: source instance not found")
        return None, False

    state = _cache_proxy_state(proxy_obj)
    instance_world = instance_obj.matrix_world.copy()

    # Keep the visible instance exactly where it is, then delete all old generated proxy objects for this pair.
    _unparent_instance_keep_world(instance_obj)
    instance_obj.matrix_world = instance_world

    _delete_proxy_objects_for_pair(pair_id)

    new_proxy, err = _create_proxy_for_instance(
        context,
        instance_obj,
        pair_id=pair_id,
        rb_cache=state.get("rb"),
        fc_cache=state.get("fcurves"),
        matrix_cache=state.get("matrix") or instance_world,
    )

    if err:
        if op:
            op.report({"WARNING"}, err)
        return None, False

    # Re-apply custom props after generated link props are assigned.
    for k, v in state.get("custom_props", {}).items():
        try:
            new_proxy[k] = v
        except Exception:
            pass

    return new_proxy, True


def _setup_or_rebuild_instance(context, instance_obj, op=None):
    pair_id = instance_obj.get(PROP_PAIR_ID, "")

    # If this instance already has a proxy pair, Realize & Parent becomes safe rebuild/update.
    if pair_id and _find_proxy_by_pair(pair_id):
        return _rebuild_pair(context, pair_id, op=op)

    # If legacy data exists, avoid blindly creating duplicates. Create a new v1.2 pair only if no valid proxy is found.
    legacy_proxy_name = instance_obj.get(LEGACY_PROP_PROXY_REF, "")
    legacy_proxy = bpy.data.objects.get(legacy_proxy_name) if legacy_proxy_name else None
    if legacy_proxy and legacy_proxy.get(PROP_PAIR_ID):
        return _rebuild_pair(context, legacy_proxy.get(PROP_PAIR_ID), op=op)

    proxy, err = _create_proxy_for_instance(context, instance_obj)
    if err:
        if op:
            op.report({"WARNING"}, err)
        return None, False

    return proxy, True


# ──────────────────────────────────────────────────────────────────────────────
# Operators — SETUP
# ──────────────────────────────────────────────────────────────────────────────

class RBIH_OT_RealizeAndParent(Operator):
    bl_idname = "rbih.realize_and_parent"
    bl_label = "Realize & Parent"
    bl_description = "Create or update a stable generated Rigid Body proxy mesh for linked Collection Instance objects"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        _ensure_object_mode(context)
        props = context.scene.rbih

        if props.target_mode == "COLLECTION" and not props.target_collection:
            self.report({"WARNING"}, "Collection mode is enabled, but no collection is specified")
            return {"CANCELLED"}

        targets = _get_target_instances(context)

        if not targets:
            self.report({"WARNING"}, "No linked Collection Instance objects found")
            return {"CANCELLED"}

        if props.move_to_rb_collection:
            _get_or_create_rb_proxies_col(context)

        ok = 0
        fail = 0
        created_or_updated = []

        for inst in targets:
            proxy, success = _setup_or_rebuild_instance(context, inst, op=self)
            if success:
                ok += 1
                if proxy:
                    created_or_updated.append(proxy)
            else:
                fail += 1

        if created_or_updated:
            _select_only(context, created_or_updated, active=created_or_updated[-1])

        self.report({"INFO"}, f"Done: {ok} proxy pair(s) created/updated, {fail} skipped")
        return {"FINISHED"}


# ──────────────────────────────────────────────────────────────────────────────
# Operators — UPDATE
# ──────────────────────────────────────────────────────────────────────────────

class RBIH_OT_UpdateSelected(Operator):
    bl_idname = "rbih.update_selected"
    bl_label = "Update Selected Proxy"
    bl_description = "Update selected proxy pair(s) without accumulating old meshes or empties"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        _ensure_object_mode(context)

        pair_ids = _pair_ids_from_objects(context.selected_objects)

        if not pair_ids:
            self.report({"WARNING"}, "No RB Instance Helper pair selected")
            return {"CANCELLED"}

        updated = []
        failed = 0

        for pair_id in pair_ids:
            proxy, success = _rebuild_pair(context, pair_id, op=self)
            if success and proxy:
                updated.append(proxy)
            else:
                failed += 1

        if updated:
            _select_only(context, updated, active=updated[-1])

        self.report({"INFO"}, f"Updated {len(updated)} pair(s), {failed} failed")
        return {"FINISHED"}


class RBIH_OT_UpdateAll(Operator):
    bl_idname = "rbih.update_all"
    bl_label = "Update All Proxies"
    bl_description = "Update all RB Instance Helper proxy pairs in the scene"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        _ensure_object_mode(context)

        pair_ids = []
        for obj in bpy.data.objects:
            pair_id = obj.get(PROP_PAIR_ID, "")
            if pair_id and pair_id not in pair_ids:
                if _find_instance_by_pair(pair_id) and _find_proxy_by_pair(pair_id):
                    pair_ids.append(pair_id)

        if not pair_ids:
            self.report({"WARNING"}, "No valid RB Instance Helper proxy pairs found")
            return {"CANCELLED"}

        updated = []
        failed = 0

        for pair_id in pair_ids:
            proxy, success = _rebuild_pair(context, pair_id, op=self)
            if success and proxy:
                updated.append(proxy)
            else:
                failed += 1

        if updated:
            _select_only(context, updated, active=updated[-1])

        self.report({"INFO"}, f"Updated {len(updated)} pair(s), {failed} failed")
        return {"FINISHED"}


# ──────────────────────────────────────────────────────────────────────────────
# Transfer Utilities
# ──────────────────────────────────────────────────────────────────────────────

def _insert_transform_keyframes(obj, frame):
    obj.keyframe_insert(data_path="location", frame=frame)

    if obj.rotation_mode == "QUATERNION":
        obj.keyframe_insert(data_path="rotation_quaternion", frame=frame)
    elif obj.rotation_mode == "AXIS_ANGLE":
        obj.keyframe_insert(data_path="rotation_axis_angle", frame=frame)
    else:
        obj.keyframe_insert(data_path="rotation_euler", frame=frame)

    obj.keyframe_insert(data_path="scale", frame=frame)


def _create_clean_transfer_action(obj):
    obj.animation_data_create()
    action = bpy.data.actions.new(name=f"{obj.name}_RB_Transfer")
    obj.animation_data.action = action
    return action


def _transfer_proxy_animation_to_instance(context, instance_obj, proxy_obj, frame_start, frame_end):
    """
    Transfer proxy animation to the linked Collection Instance by evaluating each frame.

    Unlike bpy.ops.nla.bake() on the child instance, this explicitly evaluates:
        desired_instance_world = proxy_world @ stored_instance_offset

    This preserves the visual offset created when the proxy origin is centered for
    Rigid Body simulation. It also avoids losing animation when the proxy origin
    and visual instance origin are different.
    """
    scene = context.scene
    current_frame = scene.frame_current
    offset = _get_instance_proxy_offset(instance_obj, proxy_obj)

    # Clear parent before inserting final world-space keys.
    try:
        instance_obj.parent = None
        instance_obj.matrix_parent_inverse = Matrix.Identity(4)
    except Exception:
        pass

    _create_clean_transfer_action(instance_obj)

    for frame in range(frame_start, frame_end + 1):
        scene.frame_set(frame)
        desired_world = proxy_obj.matrix_world.copy() @ offset
        instance_obj.matrix_world = desired_world
        _insert_transform_keyframes(instance_obj, frame)

    scene.frame_set(current_frame)
    # Force the instance to evaluate correctly at the restored frame.
    desired_world = proxy_obj.matrix_world.copy() @ offset if proxy_obj.name in bpy.data.objects else instance_obj.matrix_world.copy()
    instance_obj.matrix_world = desired_world


# ──────────────────────────────────────────────────────────────────────────────
# Operators — BAKE & TRANSFER
# ──────────────────────────────────────────────────────────────────────────────

class RBIH_OT_BakeRB(Operator):
    bl_idname = "rbih.bake_rb"
    bl_label = "Bake RB to Keyframes"
    bl_description = "Bake selected RB proxy pair(s) using Blender's built-in Rigid Body bake to keyframes"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        _ensure_object_mode(context)

        props = context.scene.rbih
        scene = context.scene

        fs, fe = _get_frame_range(props, scene)
        if fs >= fe:
            self.report({"ERROR"}, "Frame Start must be less than Frame End")
            return {"CANCELLED"}

        pair_ids = _pair_ids_from_objects(context.selected_objects)
        proxies = []

        if pair_ids:
            for pair_id in pair_ids:
                proxy = _find_proxy_by_pair(pair_id)
                if proxy and proxy.rigid_body:
                    proxies.append(proxy)
        else:
            # Fallback: allow direct selected rigid bodies, but prefer managed pairs.
            proxies = [o for o in context.selected_objects if o.rigid_body is not None]

        if not proxies:
            self.report({"WARNING"}, "No selected proxy with Rigid Body found")
            return {"CANCELLED"}

        prev_selected, prev_active = _store_selection(context)

        try:
            _select_only(context, proxies, active=proxies[-1])
            bpy.ops.rigidbody.bake_to_keyframes(frame_start=fs, frame_end=fe, step=1)
        except Exception as exc:
            self.report({"ERROR"}, f"Rigid Body bake failed: {exc}")
            _restore_selection(context, prev_selected, prev_active)
            return {"CANCELLED"}

        self.report({"INFO"}, f"Baked {len(proxies)} proxy object(s), frames {fs}–{fe}")
        return {"FINISHED"}


class RBIH_OT_TransferAndRemove(Operator):
    bl_idname = "rbih.transfer_and_remove"
    bl_label = "Transfer & Remove Parent"
    bl_description = "Copy proxy animation to linked instance with preserved offset, then clear parent and optionally delete proxy"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        _ensure_object_mode(context)

        props = context.scene.rbih
        scene = context.scene

        fs, fe = _get_frame_range(props, scene)
        if fs >= fe:
            self.report({"ERROR"}, "Frame Start must be less than Frame End")
            return {"CANCELLED"}

        pair_ids = _pair_ids_from_objects(context.selected_objects)
        if not pair_ids:
            self.report({"WARNING"}, "No RB Instance Helper pair selected")
            return {"CANCELLED"}

        prev_selected, prev_active = _store_selection(context)
        done = 0
        failed = 0
        transferred_instances = []

        for pair_id in pair_ids:
            instance_obj = _find_instance_by_pair(pair_id)
            proxy_obj = _find_proxy_by_pair(pair_id)

            if not instance_obj or not proxy_obj:
                self.report({"WARNING"}, f"Pair {pair_id}: instance or proxy not found")
                failed += 1
                continue

            try:
                _transfer_proxy_animation_to_instance(context, instance_obj, proxy_obj, fs, fe)
            except Exception as exc:
                self.report({"WARNING"}, f"{instance_obj.name}: transfer failed: {exc}")
                failed += 1
                continue

            _cleanup_instance_pair_props(instance_obj)
            transferred_instances.append(instance_obj)

            if props.delete_proxy_after_transfer:
                _delete_proxy_objects_for_pair(pair_id)
            else:
                _cleanup_proxy_pair_props(proxy_obj)

            done += 1

        if transferred_instances:
            _select_only(context, transferred_instances, active=transferred_instances[-1])
        else:
            _restore_selection(context, prev_selected, prev_active)

        self.report({"INFO"}, f"Transfer complete: {done} done, {failed} failed")
        return {"FINISHED"}


# ──────────────────────────────────────────────────────────────────────────────
# Operators — SELECT & COPY
# ──────────────────────────────────────────────────────────────────────────────

def _all_rbih_instances():
    """All visual linked Collection Instances currently managed by RB Instance Helper."""
    return [
        obj for obj in bpy.data.objects
        if obj.get(PROP_ROLE, "") == ROLE_INSTANCE
        and obj.get(PROP_PAIR_ID, "")
        and obj.name in bpy.data.objects
    ]


def _all_rbih_proxies():
    """All generated Rigid Body proxy roots currently managed by RB Instance Helper."""
    return [
        obj for obj in bpy.data.objects
        if obj.get(PROP_ROLE, "") == ROLE_PROXY_ROOT
        and obj.get(PROP_PAIR_ID, "")
        and obj.name in bpy.data.objects
    ]


def _dedupe_objects(objects):
    result = []
    seen = set()
    for obj in objects:
        if not obj or obj.name in seen or obj.name not in bpy.data.objects:
            continue
        seen.add(obj.name)
        result.append(obj)
    return result


class RBIH_OT_SelectInstance(Operator):
    bl_idname = "rbih.select_instance"
    bl_label = "Instances"
    bl_description = "Select all linked Collection Instances managed by RB Instance Helper in the scene"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        instances = _all_rbih_instances()
        if not instances:
            self.report({"WARNING"}, "No RB Instance Helper instances found in the scene")
            return {"CANCELLED"}

        _select_only(context, instances, active=instances[-1])
        self.report({"INFO"}, f"Selected all RB Instance Helper instances: {len(instances)}")
        return {"FINISHED"}


class RBIH_OT_SelectProxy(Operator):
    bl_idname = "rbih.select_proxy"
    bl_label = "Proxies"
    bl_description = "Select all generated Rigid Body proxies managed by RB Instance Helper in the scene"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        proxies = _all_rbih_proxies()
        if not proxies:
            self.report({"WARNING"}, "No RB Instance Helper proxies found in the scene")
            return {"CANCELLED"}

        _select_only(context, proxies, active=proxies[-1])
        self.report({"INFO"}, f"Selected all RB Instance Helper proxies: {len(proxies)}")
        return {"FINISHED"}


class RBIH_OT_SelectBoth(Operator):
    bl_idname = "rbih.select_both"
    bl_label = "Both"
    bl_description = "Select all RB Instance Helper linked instances and generated proxies in the scene"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        objects = _dedupe_objects(_all_rbih_instances() + _all_rbih_proxies())
        if not objects:
            self.report({"WARNING"}, "No RB Instance Helper instances or proxies found in the scene")
            return {"CANCELLED"}

        _select_only(context, objects, active=objects[-1])
        self.report({"INFO"}, f"Selected all RB Instance Helper objects: {len(objects)}")
        return {"FINISHED"}


class RBIH_OT_CopyRBSettings(Operator):
    bl_idname = "rbih.copy_rb_settings"
    bl_label = "Copy RB Settings to Selected"
    bl_description = "Copy Rigid Body settings from Active object to selected objects"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        _ensure_object_mode(context)

        active = context.active_object
        if not active or not active.rigid_body:
            self.report({"ERROR"}, "Active object has no Rigid Body component")
            return {"CANCELLED"}

        targets = [o for o in context.selected_objects if o != active]
        if not targets:
            self.report({"WARNING"}, "No other objects selected")
            return {"CANCELLED"}

        _ensure_rb_world(context)
        src = active.rigid_body
        copied = 0

        prev_selected, prev_active = _store_selection(context)

        try:
            for obj in targets:
                if obj.rigid_body is None:
                    _select_only(context, [obj], active=obj)
                    bpy.ops.rigidbody.object_add(type="ACTIVE")

                rb = obj.rigid_body
                if not rb:
                    continue

                for prop_name in RB_COPY_PROPS:
                    if hasattr(src, prop_name) and hasattr(rb, prop_name):
                        try:
                            setattr(rb, prop_name, getattr(src, prop_name))
                        except Exception:
                            pass

                copied += 1

        finally:
            _restore_selection(context, prev_selected, prev_active)

        self.report({"INFO"}, f"RB settings copied to {copied} object(s)")
        return {"FINISHED"}


# ──────────────────────────────────────────────────────────────────────────────
# Panels
# ──────────────────────────────────────────────────────────────────────────────

class RBIH_PT_Main(Panel):
    bl_label = "RB Instance Helper"
    bl_idname = "RBIH_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "RB Helper"

    def draw(self, context):
        layout = self.layout
        layout.label(text=f"Version {ADDON_VERSION_STR}")


class RBIH_PT_Setup(Panel):
    bl_label = "1 · SETUP"
    bl_idname = "RBIH_PT_setup"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "RB Helper"
    bl_parent_id = "RBIH_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        props = context.scene.rbih

        row = layout.row(align=True)
        row.prop(props, "target_mode", expand=True)

        if props.target_mode == "COLLECTION":
            layout.prop(props, "target_collection", text="Collection")

        layout.separator(factor=0.8)

        col = layout.column(align=True)
        col.prop(props, "hide_proxy_render")
        col.prop(props, "move_to_rb_collection")
        col.prop(props, "auto_add_rigid_body")
        col.prop(props, "center_proxy_origin")

        if props.auto_add_rigid_body:
            col.prop(props, "default_collision_shape")

        layout.separator(factor=0.8)
        layout.operator("rbih.realize_and_parent", icon="OUTLINER_OB_MESH")


class RBIH_PT_Update(Panel):
    bl_label = "2 · UPDATE"
    bl_idname = "RBIH_PT_update"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "RB Helper"
    bl_parent_id = "RBIH_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.operator("rbih.update_selected", icon="FILE_REFRESH")
        col.operator("rbih.update_all", icon="WORLD")


class RBIH_PT_Bake(Panel):
    bl_label = "3 · BAKE & TRANSFER"
    bl_idname = "RBIH_PT_bake"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "RB Helper"
    bl_parent_id = "RBIH_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        props = context.scene.rbih

        row = layout.row(align=True)
        row.prop(props, "frame_range_mode", expand=True)

        if props.frame_range_mode == "CUSTOM":
            row2 = layout.row(align=True)
            row2.prop(props, "frame_start_custom")
            row2.prop(props, "frame_end_custom")

        layout.separator(factor=0.8)
        layout.operator("rbih.bake_rb", icon="RENDER_ANIMATION")

        layout.separator()
        layout.prop(props, "delete_proxy_after_transfer")
        layout.operator("rbih.transfer_and_remove", icon="FORWARD")


class RBIH_PT_SelectCopy(Panel):
    bl_label = "4 · SELECT & COPY"
    bl_idname = "RBIH_PT_select_copy"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "RB Helper"
    bl_parent_id = "RBIH_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout

        layout.label(text="Select Related:", icon="RESTRICT_SELECT_OFF")
        row = layout.row(align=True)
        row.operator("rbih.select_instance", icon="LINKED")
        row.operator("rbih.select_proxy", icon="OUTLINER_OB_MESH")
        row.operator("rbih.select_both", icon="SELECT_EXTEND")

        layout.separator()
        layout.label(text="Rigid Body:", icon="RIGID_BODY")
        layout.operator("rbih.copy_rb_settings", icon="COPYDOWN")


# ──────────────────────────────────────────────────────────────────────────────
# Registration
# ──────────────────────────────────────────────────────────────────────────────

classes = (
    RBIH_Props,

    RBIH_OT_RealizeAndParent,
    RBIH_OT_UpdateSelected,
    RBIH_OT_UpdateAll,
    RBIH_OT_BakeRB,
    RBIH_OT_TransferAndRemove,
    RBIH_OT_SelectInstance,
    RBIH_OT_SelectProxy,
    RBIH_OT_SelectBoth,
    RBIH_OT_CopyRBSettings,

    RBIH_PT_Main,
    RBIH_PT_Setup,
    RBIH_PT_Update,
    RBIH_PT_Bake,
    RBIH_PT_SelectCopy,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.rbih = PointerProperty(type=RBIH_Props)


def unregister():
    if hasattr(bpy.types.Scene, "rbih"):
        del bpy.types.Scene.rbih

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
