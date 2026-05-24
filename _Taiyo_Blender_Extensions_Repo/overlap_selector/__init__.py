bl_info = {
    "name":        "Overlap Object Selector",
    "author":      "Taiyo",
    "version":     (1, 2, 2),
    "blender":     (4, 2, 0),
    "location":    "View3D > N-Panel > Overlap",
    "description": "Detect, filter, review, select, and optionally delete overlapping objects",
    "category":    "Object",
}

DOCUMENTATION_URL = "https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/_Taiyo_Blender_Extensions_Repo/overlap_selector/Overlap_Selector_User_Guide_v1_2_1.md"

import bpy
import time
from collections import defaultdict

# ── Performance tuning ─────────────────────────────────────────────
TARGET_MS  = 16.0      # target milliseconds per modal tick (~60 fps)
CHUNK_MIN  = 10
CHUNK_MAX  = 100_000
CHUNK_INIT = 500


# ───────────────────────────────────────────────────────────────────
# Key builders  (world-space, handles parenting & instances)
# ───────────────────────────────────────────────────────────────────

def _loc_key(obj):
    t = obj.matrix_world.translation
    return (t.x, t.y, t.z)


def _scale_key(obj):
    s = obj.matrix_world.to_scale()
    return (round(s.x, 6), round(s.y, 6), round(s.z, 6))


def _rot_key(obj):
    e = obj.matrix_world.to_euler()
    return (round(e.x, 6), round(e.y, 6), round(e.z, 6))


def _build_key(obj, use_scale, use_rot):
    k = _loc_key(obj)
    if use_scale:
        k += _scale_key(obj)
    if use_rot:
        k += _rot_key(obj)
    return k


# ───────────────────────────────────────────────────────────────────
# Status bar / UI refresh helpers
# ───────────────────────────────────────────────────────────────────

def _bar(pct, w=20):
    f = int(w * pct / 100)
    return "X" * f + "." * (w - f)


def _update_status(context, done, total, elapsed):
    if total == 0:
        return
    pct = int(done / total * 100)
    if elapsed < 0.15 or done == 0:
        eta = "---"
    else:
        sec = int((total - done) / (done / elapsed))
        eta = f"{sec}s" if sec < 60 else f"{sec // 60}:{sec % 60:02d}"
    context.workspace.status_text_set(
        f"Overlap Detect  {_bar(pct)}  {pct}%   {done}/{total} objects   ETA {eta}"
    )


def _tag_view3d_redraw(context):
    screen = getattr(context, "screen", None)
    if not screen:
        return
    for area in screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


def _reset_overlap_state(context, clear_results=True, request_cancel=False, invalidate_run=False):
    """Reset Scene-side state so stale modal flags cannot lock the UI."""
    scene = context.scene

    if invalidate_run:
        scene.overlap_run_id += 1

    scene.overlap_cancel_requested = request_cancel
    scene.overlap_is_running = False
    scene.overlap_progress = 0.0

    if clear_results:
        scene.overlap_groups.clear()

    workspace = getattr(context, "workspace", None)
    if workspace:
        workspace.status_text_set(None)

    _tag_view3d_redraw(context)


# ───────────────────────────────────────────────────────────────────
# View Layer safe selection helpers
# ───────────────────────────────────────────────────────────────────

def _view_layer_object(context, obj_name):
    """Return the object only if it exists in the current View Layer."""
    view_layer = getattr(context, "view_layer", None)
    if not view_layer:
        return None
    try:
        return view_layer.objects.get(obj_name)
    except Exception:
        return None


def _deselect_view_layer_objects(context):
    """Deselect objects safely without using bpy.ops."""
    view_layer = getattr(context, "view_layer", None)
    if not view_layer:
        return
    for obj in view_layer.objects:
        try:
            obj.select_set(False)
        except RuntimeError:
            pass


def _select_object_safe(context, scene_obj, make_active=False):
    """
    Select an object only when it exists in the current View Layer.
    Returns: (success: bool, reason: str)
    """
    if scene_obj is None:
        return False, "missing"

    obj = _view_layer_object(context, scene_obj.name)
    if obj is None:
        return False, "not_in_view_layer"

    try:
        obj.select_set(True)
        if make_active:
            context.view_layer.objects.active = obj
        return True, ""
    except RuntimeError as exc:
        return False, str(exc)


def _format_selection_report(selected, skipped_view_layer, missing, failed):
    parts = [f"Selected {selected} object(s)"]
    if skipped_view_layer:
        parts.append(f"skipped {skipped_view_layer} not in current View Layer")
    if missing:
        parts.append(f"missing {missing}")
    if failed:
        parts.append(f"failed {failed}")
    return "; ".join(parts) + "."


def _select_group_by_index(context, group_index):
    """Select all selectable Blender objects in a stored overlap group."""
    scene = context.scene
    groups = scene.overlap_groups
    if group_index < 0 or group_index >= len(groups):
        return 0

    _deselect_view_layer_objects(context)
    selected = 0
    made_active = False
    for item in groups[group_index].objects:
        scene_obj = scene.objects.get(item.obj_name)
        ok, _reason = _select_object_safe(context, scene_obj, make_active=not made_active)
        if ok:
            selected += 1
            made_active = True
    return selected


def _select_object_entry_by_index(context, group_index, object_index):
    """Select one Blender object from the stored overlap result list."""
    scene = context.scene
    groups = scene.overlap_groups
    if group_index < 0 or group_index >= len(groups):
        return False

    grp = groups[group_index]
    if object_index < 0 or object_index >= len(grp.objects):
        return False

    scene_obj = scene.objects.get(grp.objects[object_index].obj_name)
    _deselect_view_layer_objects(context)
    ok, _reason = _select_object_safe(context, scene_obj, make_active=True)
    return ok


def _cleanup_single_object_groups(scene):
    """Remove result groups that no longer contain at least two entries."""
    removed = 0
    for i in reversed(range(len(scene.overlap_groups))):
        if len(scene.overlap_groups[i].objects) < 2:
            scene.overlap_groups.remove(i)
            removed += 1

    if len(scene.overlap_groups) == 0:
        scene.overlap_active_group_index = 0
        scene.overlap_active_object_index = 0
    else:
        scene.overlap_active_group_index = max(0, min(scene.overlap_active_group_index, len(scene.overlap_groups) - 1))
        active_group = scene.overlap_groups[scene.overlap_active_group_index]
        scene.overlap_active_object_index = max(0, min(scene.overlap_active_object_index, len(active_group.objects) - 1))
    return removed


def _remove_object_entry_and_cleanup(scene, group_index, object_index):
    """Remove one result-list entry, then hide/remove the group if it has one or zero entries."""
    groups = scene.overlap_groups
    if group_index < 0 or group_index >= len(groups):
        return False, False
    grp = groups[group_index]
    if object_index < 0 or object_index >= len(grp.objects):
        return False, False

    grp.objects.remove(object_index)
    removed_group = False
    if len(grp.objects) < 2:
        groups.remove(group_index)
        removed_group = True

    if len(groups) == 0:
        scene.overlap_active_group_index = 0
        scene.overlap_active_object_index = 0
    else:
        scene.overlap_active_group_index = max(0, min(scene.overlap_active_group_index, len(groups) - 1))
        active_group = groups[scene.overlap_active_group_index]
        scene.overlap_active_object_index = max(0, min(scene.overlap_active_object_index, len(active_group.objects) - 1))
    return True, removed_group


def _on_active_group_index_update(scene, context):
    """When a group row is clicked, select that group in the Blender View Layer."""
    if getattr(scene, "overlap_is_running", False):
        return
    if len(scene.overlap_groups) == 0:
        return
    idx = max(0, min(scene.overlap_active_group_index, len(scene.overlap_groups) - 1))
    if idx != scene.overlap_active_group_index:
        scene.overlap_active_group_index = idx
        return
    _select_group_by_index(context, idx)


def _on_active_object_index_update(scene, context):
    """When an object row is clicked, select that object in the Blender View Layer."""
    if getattr(scene, "overlap_is_running", False):
        return
    if len(scene.overlap_groups) == 0:
        return
    g_idx = max(0, min(scene.overlap_active_group_index, len(scene.overlap_groups) - 1))
    grp = scene.overlap_groups[g_idx]
    if len(grp.objects) == 0:
        return
    o_idx = max(0, min(scene.overlap_active_object_index, len(grp.objects) - 1))
    if o_idx != scene.overlap_active_object_index:
        scene.overlap_active_object_index = o_idx
        return
    _select_object_entry_by_index(context, g_idx, o_idx)


# ───────────────────────────────────────────────────────────────────
# Property groups
# ───────────────────────────────────────────────────────────────────

class OverlapObjectItem(bpy.types.PropertyGroup):
    obj_name: bpy.props.StringProperty()
    selected: bpy.props.BoolProperty(
        name="Checked",
        description="Use this object for Select Checked / Remove Checked operations",
        default=False,
    )


class OverlapGroupItem(bpy.types.PropertyGroup):
    objects: bpy.props.CollectionProperty(type=OverlapObjectItem)
    loc_x:   bpy.props.FloatProperty()
    loc_y:   bpy.props.FloatProperty()
    loc_z:   bpy.props.FloatProperty()
    expanded: bpy.props.BoolProperty(
        name="Expanded",
        description="Show or hide the object list for this overlap group",
        default=False,
    )


# ───────────────────────────────────────────────────────────────────
# Operators
# ───────────────────────────────────────────────────────────────────

class OBJECT_OT_detect_overlaps(bpy.types.Operator):
    bl_idname      = "object.detect_overlaps"
    bl_label       = "Detect Overlaps"
    bl_description = "Find objects at identical world-space positions  (ESC = cancel)"

    def invoke(self, context, event):
        scene = context.scene

        # Always start from a clean Scene-side state.
        # This prevents stale flags from a previous modal run from blocking execution.
        scene.overlap_run_id += 1
        scene.overlap_cancel_requested = False
        scene.overlap_groups.clear()
        scene.overlap_is_running = True
        scene.overlap_progress   = 0.0

        self._run_id = scene.overlap_run_id
        self._timer = None

        include_hidden = scene.overlap_include_hidden
        self._objs = [
            o for o in scene.objects
            if include_hidden or not o.hide_viewport
        ]
        self._n       = len(self._objs)
        self._idx     = 0
        self._chunk   = CHUNK_INIT
        self._buckets = defaultdict(list)
        self._t0      = time.perf_counter()

        if self._n == 0:
            self.report({'WARNING'}, "No objects found.")
            _reset_overlap_state(context, clear_results=True, request_cancel=False)
            return {'FINISHED'}

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.01, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        scene = context.scene

        # If another run/reset has happened after this modal started, this operator is stale.
        # Remove only its own timer and do not touch the newer Scene state.
        if getattr(self, "_run_id", None) != scene.overlap_run_id:
            self._cleanup_modal(context, reset_scene=False)
            return {'CANCELLED'}

        if event.type == 'ESC' or scene.overlap_cancel_requested:
            self._cleanup_modal(context, reset_scene=True)
            self.report({'INFO'}, "Overlap detection cancelled.")
            return {'CANCELLED'}

        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        use_scale = scene.overlap_use_scale_filter
        use_rot   = scene.overlap_use_rot_filter
        elapsed   = time.perf_counter() - self._t0
        tick_s    = time.perf_counter()

        end = min(self._idx + self._chunk, self._n)
        for i in range(self._idx, end):
            obj = self._objs[i]
            key = _build_key(obj, use_scale, use_rot)
            self._buckets[key].append(obj.name)

        self._idx = end

        tick_ms     = (time.perf_counter() - tick_s) * 1000
        ratio       = TARGET_MS / max(tick_ms, 0.1)
        self._chunk = max(CHUNK_MIN, min(CHUNK_MAX, int(self._chunk * ratio)))

        scene.overlap_progress = self._idx / self._n
        _update_status(context, self._idx, self._n, elapsed)
        self._redraw(context)

        if self._idx >= self._n:
            self._finalize(context)
            return {'FINISHED'}

        return {'PASS_THROUGH'}

    def _finalize(self, context):
        scene = context.scene
        wm    = context.window_manager

        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None

        context.workspace.status_text_set(None)

        for key, names in self._buckets.items():
            if len(names) < 2:
                continue
            grp       = scene.overlap_groups.add()
            grp.loc_x = key[0]
            grp.loc_y = key[1]
            grp.loc_z = key[2]
            grp.expanded = False
            for name in sorted(names):
                it          = grp.objects.add()
                it.obj_name = name
                it.selected = False

        scene.overlap_cancel_requested = False
        scene.overlap_is_running = False
        scene.overlap_progress   = 1.0

        scene.overlap_active_group_index = 0
        scene.overlap_active_object_index = 0

        n_g = len(scene.overlap_groups)
        n_o = sum(len(g.objects) for g in scene.overlap_groups)
        self.report({'INFO'}, f"Done — {n_g} overlap group(s), {n_o} objects.")
        self._redraw(context)

    def _cleanup_modal(self, context, reset_scene=True):
        wm = context.window_manager
        if getattr(self, "_timer", None):
            wm.event_timer_remove(self._timer)
            self._timer = None
        if reset_scene:
            _reset_overlap_state(context, clear_results=False, request_cancel=False)

    @staticmethod
    def _redraw(context):
        _tag_view3d_redraw(context)


class OBJECT_OT_cancel_overlap_detection(bpy.types.Operator):
    bl_idname      = "object.cancel_overlap_detection"
    bl_label       = "Cancel"
    bl_description = "Cancel the current detection and unlock the panel"

    def execute(self, context):
        # Invalidate the current run so even an already-running modal operator cannot
        # write old results back into the panel after Cancel is pressed.
        _reset_overlap_state(
            context,
            clear_results=False,
            request_cancel=True,
            invalidate_run=True,
        )
        self.report({'INFO'}, "Overlap detection cancellation requested.")
        return {'FINISHED'}


class OBJECT_OT_reset_overlap_selector(bpy.types.Operator):
    bl_idname      = "object.reset_overlap_selector"
    bl_label       = "Reset"
    bl_description = "Cancel any active detection and clear all stored overlap results"

    def execute(self, context):
        # Invalidate the current run and clear all visible/stored results.
        _reset_overlap_state(
            context,
            clear_results=True,
            request_cancel=True,
            invalidate_run=True,
        )
        self.report({'INFO'}, "Overlap selector state reset.")
        return {'FINISHED'}


class OBJECT_OT_clear_overlap_results(bpy.types.Operator):
    bl_idname      = "object.clear_overlap_results"
    bl_label       = "Clear Results"
    bl_description = "Clear all overlap detection results"

    def execute(self, context):
        _reset_overlap_state(context, clear_results=True, request_cancel=False)
        return {'FINISHED'}


class OBJECT_OT_select_overlap_checked(bpy.types.Operator):
    bl_idname      = "object.select_overlap_checked"
    bl_label       = "Select Checked"
    bl_description = "Select every checked object in the current View Layer"

    def execute(self, context):
        _deselect_view_layer_objects(context)
        selected = skipped_view_layer = missing = failed = 0
        made_active = False

        for grp in context.scene.overlap_groups:
            for item in grp.objects:
                if not item.selected:
                    continue
                scene_obj = context.scene.objects.get(item.obj_name)
                ok, reason = _select_object_safe(context, scene_obj, make_active=not made_active)
                if ok:
                    selected += 1
                    made_active = True
                elif reason == "missing":
                    missing += 1
                elif reason == "not_in_view_layer":
                    skipped_view_layer += 1
                else:
                    failed += 1

        msg = _format_selection_report(selected, skipped_view_layer, missing, failed)
        self.report({'INFO'} if selected else {'WARNING'}, msg)
        return {'FINISHED'}


class OBJECT_OT_select_overlap_group(bpy.types.Operator):
    bl_idname      = "object.select_overlap_group"
    bl_label       = "Select Group"
    bl_description = "Select all objects in this group that exist in the current View Layer"

    group_index: bpy.props.IntProperty()

    def execute(self, context):
        groups = context.scene.overlap_groups
        if self.group_index < 0 or self.group_index >= len(groups):
            self.report({'WARNING'}, "Group no longer exists.")
            return {'CANCELLED'}

        _deselect_view_layer_objects(context)
        grp = groups[self.group_index]
        selected = skipped_view_layer = missing = failed = 0
        made_active = False

        for item in grp.objects:
            scene_obj = context.scene.objects.get(item.obj_name)
            ok, reason = _select_object_safe(context, scene_obj, make_active=not made_active)
            if ok:
                selected += 1
                made_active = True
            elif reason == "missing":
                missing += 1
            elif reason == "not_in_view_layer":
                skipped_view_layer += 1
            else:
                failed += 1

        msg = _format_selection_report(selected, skipped_view_layer, missing, failed)
        self.report({'INFO'} if selected else {'WARNING'}, msg)
        return {'FINISHED'}


class OBJECT_OT_select_overlap_object(bpy.types.Operator):
    bl_idname      = "object.select_overlap_object"
    bl_label       = "Select Object"
    bl_description = "Select only this object if it exists in the current View Layer"

    group_index: bpy.props.IntProperty()
    object_index: bpy.props.IntProperty()

    def execute(self, context):
        groups = context.scene.overlap_groups
        if self.group_index < 0 or self.group_index >= len(groups):
            self.report({'WARNING'}, "Group no longer exists.")
            return {'CANCELLED'}

        grp = groups[self.group_index]
        if self.object_index < 0 or self.object_index >= len(grp.objects):
            self.report({'WARNING'}, "Object entry no longer exists.")
            return {'CANCELLED'}

        item = grp.objects[self.object_index]
        scene_obj = context.scene.objects.get(item.obj_name)
        _deselect_view_layer_objects(context)
        ok, reason = _select_object_safe(context, scene_obj, make_active=True)

        if ok:
            self.report({'INFO'}, f"Selected '{item.obj_name}'.")
            return {'FINISHED'}
        if reason == "not_in_view_layer":
            self.report({'WARNING'}, f"'{item.obj_name}' is not in the current View Layer, so it cannot be selected here.")
        elif reason == "missing":
            self.report({'WARNING'}, f"'{item.obj_name}' no longer exists.")
        else:
            self.report({'WARNING'}, f"Could not select '{item.obj_name}': {reason}")
        return {'CANCELLED'}


class OBJECT_OT_toggle_overlap_checks(bpy.types.Operator):
    bl_idname     = "object.toggle_overlap_checks"
    bl_label      = "Toggle All Checkboxes"
    bl_description = "Check or uncheck every object in every result group"

    select_state: bpy.props.BoolProperty(default=True)

    def execute(self, context):
        for grp in context.scene.overlap_groups:
            for item in grp.objects:
                item.selected = self.select_state
        return {'FINISHED'}


class OBJECT_OT_toggle_overlap_group_checks(bpy.types.Operator):
    bl_idname      = "object.toggle_overlap_group_checks"
    bl_label       = "Toggle Group Checkboxes"
    bl_description = "Check or uncheck every object in this group"

    group_index: bpy.props.IntProperty()
    select_state: bpy.props.BoolProperty(default=True)

    def execute(self, context):
        groups = context.scene.overlap_groups
        if self.group_index < 0 or self.group_index >= len(groups):
            self.report({'WARNING'}, "Group no longer exists.")
            return {'CANCELLED'}
        for item in groups[self.group_index].objects:
            item.selected = self.select_state
        return {'FINISHED'}


class OBJECT_OT_toggle_overlap_group_expanded(bpy.types.Operator):
    bl_idname      = "object.toggle_overlap_group_expanded"
    bl_label       = "Expand / Collapse Group"
    bl_description = "Show or hide the object list for this group"

    group_index: bpy.props.IntProperty()

    def execute(self, context):
        groups = context.scene.overlap_groups
        if self.group_index < 0 or self.group_index >= len(groups):
            self.report({'WARNING'}, "Group no longer exists.")
            return {'CANCELLED'}
        groups[self.group_index].expanded = not groups[self.group_index].expanded
        return {'FINISHED'}


class OBJECT_OT_set_overlap_groups_expanded(bpy.types.Operator):
    bl_idname      = "object.set_overlap_groups_expanded"
    bl_label       = "Expand / Collapse All Groups"
    bl_description = "Show or hide object lists for all groups"

    expanded: bpy.props.BoolProperty(default=True)

    def execute(self, context):
        for grp in context.scene.overlap_groups:
            grp.expanded = self.expanded
        return {'FINISHED'}


class OBJECT_OT_remove_overlap_checked_from_group(bpy.types.Operator):
    bl_idname      = "object.remove_overlap_checked_from_group"
    bl_label       = "Remove Checked"
    bl_description = "Remove checked object entries from this result group only. This does not delete Blender objects."

    group_index: bpy.props.IntProperty()

    def execute(self, context):
        groups = context.scene.overlap_groups
        if self.group_index < 0 or self.group_index >= len(groups):
            self.report({'WARNING'}, "Group no longer exists.")
            return {'CANCELLED'}

        grp = groups[self.group_index]
        remove_indices = [i for i, item in enumerate(grp.objects) if item.selected]
        if not remove_indices:
            self.report({'WARNING'}, "No checked entries in this group.")
            return {'CANCELLED'}

        removed = len(remove_indices)
        for i in reversed(remove_indices):
            grp.objects.remove(i)

        # If fewer than 2 entries remain, it is no longer an overlap group.
        if len(grp.objects) < 2:
            groups.remove(self.group_index)
            self.report({'INFO'}, f"Removed {removed} checked entrie(s). The group was removed because fewer than 2 objects remained.")
        else:
            self.report({'INFO'}, f"Removed {removed} checked entrie(s) from the result list.")
        return {'FINISHED'}


class OBJECT_OT_remove_overlap_object_entry(bpy.types.Operator):
    bl_idname      = "object.remove_overlap_object_entry"
    bl_label       = "Remove Entry"
    bl_description = "Remove this object entry from the result list only. This does not delete the Blender object."

    group_index: bpy.props.IntProperty()
    object_index: bpy.props.IntProperty()

    def execute(self, context):
        groups = context.scene.overlap_groups
        if self.group_index < 0 or self.group_index >= len(groups):
            self.report({'WARNING'}, "Group no longer exists.")
            return {'CANCELLED'}

        grp = groups[self.group_index]
        if self.object_index < 0 or self.object_index >= len(grp.objects):
            self.report({'WARNING'}, "Object entry no longer exists.")
            return {'CANCELLED'}

        name = grp.objects[self.object_index].obj_name
        grp.objects.remove(self.object_index)

        if len(grp.objects) < 2:
            groups.remove(self.group_index)
            self.report({'INFO'}, f"Removed '{name}'. The group was removed because fewer than 2 objects remained.")
        else:
            self.report({'INFO'}, f"Removed '{name}' from the result list.")
        return {'FINISHED'}



class OBJECT_OT_delete_overlap_object(bpy.types.Operator):
    bl_idname      = "object.delete_overlap_object"
    bl_label       = "Delete Object"
    bl_description = "Delete this Blender object from the scene, then remove its entry from the overlap result list"
    bl_options     = {'REGISTER', 'UNDO'}

    group_index: bpy.props.IntProperty()
    object_index: bpy.props.IntProperty()

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        scene = context.scene
        groups = scene.overlap_groups
        if self.group_index < 0 or self.group_index >= len(groups):
            self.report({'WARNING'}, "Group no longer exists.")
            return {'CANCELLED'}

        grp = groups[self.group_index]
        if self.object_index < 0 or self.object_index >= len(grp.objects):
            self.report({'WARNING'}, "Object entry no longer exists.")
            return {'CANCELLED'}

        name = grp.objects[self.object_index].obj_name
        obj = bpy.data.objects.get(name)
        if obj is None:
            _remove_object_entry_and_cleanup(scene, self.group_index, self.object_index)
            self.report({'WARNING'}, f"'{name}' was already missing. Removed the stale entry from the result list.")
            return {'FINISHED'}

        try:
            bpy.data.objects.remove(obj, do_unlink=True)
        except Exception as exc:
            self.report({'ERROR'}, f"Could not delete '{name}': {exc}")
            return {'CANCELLED'}

        _removed, removed_group = _remove_object_entry_and_cleanup(scene, self.group_index, self.object_index)
        if removed_group:
            self.report({'INFO'}, f"Deleted '{name}'. The group was hidden because only one or zero entries remained.")
        else:
            self.report({'INFO'}, f"Deleted '{name}' and removed it from the result list.")
        return {'FINISHED'}


class OBJECT_OT_select_overlap_by_collection(bpy.types.Operator):
    bl_idname      = "object.select_overlap_by_collection"
    bl_label       = "Select Collection Matches"
    bl_description = "Select detected result objects that belong to the typed collection name"

    def execute(self, context):
        scene = context.scene
        text = scene.overlap_collection_filter.strip()
        if not text:
            self.report({'WARNING'}, "Type a collection name first.")
            return {'CANCELLED'}

        exact = scene.overlap_collection_filter_exact
        case_sensitive = scene.overlap_collection_filter_case_sensitive

        _deselect_view_layer_objects(context)
        selected = skipped_view_layer = missing = failed = matched = 0
        made_active = False

        for grp in scene.overlap_groups:
            for item in grp.objects:
                scene_obj = scene.objects.get(item.obj_name)
                if scene_obj is None:
                    continue
                if not _matches_collection_filter(scene_obj, text, exact=exact, case_sensitive=case_sensitive):
                    continue

                matched += 1
                ok, reason = _select_object_safe(context, scene_obj, make_active=not made_active)
                if ok:
                    selected += 1
                    made_active = True
                elif reason == "missing":
                    missing += 1
                elif reason == "not_in_view_layer":
                    skipped_view_layer += 1
                else:
                    failed += 1

        if matched == 0:
            self.report({'WARNING'}, f"No detected result objects matched collection filter '{text}'.")
            return {'CANCELLED'}

        msg = _format_selection_report(selected, skipped_view_layer, missing, failed)
        msg += f" Filter matched {matched} result entrie(s)."
        self.report({'INFO'} if selected else {'WARNING'}, msg)
        return {'FINISHED'}


class OBJECT_OT_check_overlap_by_collection(bpy.types.Operator):
    bl_idname      = "object.check_overlap_by_collection"
    bl_label       = "Check Collection Matches"
    bl_description = "Check detected result entries that belong to the typed collection name"

    clear_existing: bpy.props.BoolProperty(default=True)

    def execute(self, context):
        scene = context.scene
        text = scene.overlap_collection_filter.strip()
        if not text:
            self.report({'WARNING'}, "Type a collection name first.")
            return {'CANCELLED'}

        exact = scene.overlap_collection_filter_exact
        case_sensitive = scene.overlap_collection_filter_case_sensitive

        if self.clear_existing:
            for grp in scene.overlap_groups:
                for item in grp.objects:
                    item.selected = False

        count = 0
        first_group = None
        for g_idx, grp in enumerate(scene.overlap_groups):
            for item in grp.objects:
                scene_obj = scene.objects.get(item.obj_name)
                if scene_obj is None:
                    continue
                if _matches_collection_filter(scene_obj, text, exact=exact, case_sensitive=case_sensitive):
                    item.selected = True
                    count += 1
                    if first_group is None:
                        first_group = g_idx

        if count == 0:
            self.report({'WARNING'}, f"No detected result entries matched collection filter '{text}'.")
            return {'CANCELLED'}

        if first_group is not None:
            scene.overlap_active_group_index = first_group
            scene.overlap_active_object_index = 0

        self.report({'INFO'}, f"Checked {count} result entrie(s) matching collection filter '{text}'.")
        return {'FINISHED'}


# ───────────────────────────────────────────────────────────────────
# Panel
# ───────────────────────────────────────────────────────────────────

_TYPE_ICON = {
    'MESH':        'MESH_DATA',
    'CURVE':       'CURVE_DATA',
    'SURFACE':     'SURFACE_DATA',
    'META':        'META_DATA',
    'FONT':        'FONT_DATA',
    'GPENCIL':     'GREASEPENCIL',
    'ARMATURE':    'ARMATURE_DATA',
    'LATTICE':     'LATTICE_DATA',
    'EMPTY':       'EMPTY_DATA',
    'LIGHT':       'LIGHT_DATA',
    'CAMERA':      'CAMERA_DATA',
    'SPEAKER':     'SPEAKER',
    'LIGHT_PROBE': 'LIGHTPROBE_CUBEMAP',
}


def _preview_group_names(grp, max_names=3, max_chars=90):
    names = [grp.objects[i].obj_name for i in range(min(len(grp.objects), max_names))]
    text = ", ".join(names)
    if len(grp.objects) > max_names:
        text += f", ... +{len(grp.objects) - max_names} more"
    if len(text) > max_chars:
        text = text[:max_chars - 3] + "..."
    return text


def _format_collection_names(obj, max_names=4, max_chars=110):
    """Return direct collection memberships for an object as a compact UI string."""
    if obj is None:
        return "[object missing]"

    collections = getattr(obj, "users_collection", None)
    if not collections:
        return "[no direct collection]"

    names = sorted({coll.name for coll in collections if coll is not None})
    if not names:
        return "[no direct collection]"

    shown = names[:max_names]
    text = ", ".join(shown)
    if len(names) > max_names:
        text += f", ... +{len(names) - max_names} more"
    if len(text) > max_chars:
        text = text[:max_chars - 3] + "..."
    return text


def _collection_names_for_object(obj):
    """Return direct collection names for matching/filter operations."""
    if obj is None:
        return []
    collections = getattr(obj, "users_collection", None)
    if not collections:
        return []
    return sorted({coll.name for coll in collections if coll is not None})


def _matches_collection_filter(obj, filter_text, exact=True, case_sensitive=False):
    """Check whether an object belongs to a collection matching the current filter."""
    needle = (filter_text or "").strip()
    if not needle:
        return False

    names = _collection_names_for_object(obj)
    if not case_sensitive:
        needle = needle.lower()
        names = [name.lower() for name in names]

    if exact:
        return any(name == needle for name in names)
    return any(needle in name for name in names)


def _count_collection_filter_matches(scene):
    """Count detected result entries whose object belongs to the typed collection."""
    text = getattr(scene, "overlap_collection_filter", "").strip()
    if not text:
        return 0
    exact = getattr(scene, "overlap_collection_filter_exact", True)
    case_sensitive = getattr(scene, "overlap_collection_filter_case_sensitive", False)

    count = 0
    for grp in scene.overlap_groups:
        for item in grp.objects:
            obj = scene.objects.get(item.obj_name)
            if _matches_collection_filter(obj, text, exact=exact, case_sensitive=case_sensitive):
                count += 1
    return count


def _active_group(context):
    """Return (index, group) for the active group list row."""
    scene = context.scene
    groups = scene.overlap_groups
    if len(groups) == 0:
        return -1, None
    idx = max(0, min(scene.overlap_active_group_index, len(groups) - 1))
    if scene.overlap_active_group_index != idx:
        scene.overlap_active_group_index = idx
    return idx, groups[idx]


def _active_object_item(context, grp):
    """Return (index, item) for the active object list row inside a group."""
    scene = context.scene
    if grp is None or len(grp.objects) == 0:
        return -1, None
    idx = max(0, min(scene.overlap_active_object_index, len(grp.objects) - 1))
    if scene.overlap_active_object_index != idx:
        scene.overlap_active_object_index = idx
    return idx, grp.objects[idx]


class OVERLAP_UL_group_list(bpy.types.UIList):
    """Compact, clickable list of overlap groups."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.label(
                text=f"Group {index + 1}   {len(item.objects)} objects",
                icon='OUTLINER_OB_GROUP_INSTANCE',
            )
            row.label(text=f"XYZ {item.loc_x:.2f}, {item.loc_y:.2f}, {item.loc_z:.2f}")
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text=str(index + 1), icon='OUTLINER_OB_GROUP_INSTANCE')


class OVERLAP_UL_object_list(bpy.types.UIList):
    """Compact, clickable object list for the active overlap group."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        scene = context.scene
        obj = scene.objects.get(item.obj_name)
        in_view_layer = _view_layer_object(context, item.obj_name) is not None

        if obj is None:
            obj_icon = 'GHOST_DISABLED'
        else:
            obj_icon = _TYPE_ICON.get(obj.type, 'OBJECT_DATA')

        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.prop(item, "selected", text="")
            label = item.obj_name if in_view_layer else f"{item.obj_name}  [not in View Layer]"
            row.label(text=label, icon=obj_icon)
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text="", icon=obj_icon)


class VIEW3D_PT_overlap_selector(bpy.types.Panel):
    bl_label       = "Overlap Selector"
    bl_idname      = "VIEW3D_PT_overlap_selector"
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = "Overlap"

    def draw(self, context):
        layout  = self.layout
        scene   = context.scene
        running = scene.overlap_is_running
        groups  = scene.overlap_groups

        # Settings
        box = layout.box()
        box.label(text="Detect Settings", icon='PREFERENCES')
        box.prop(scene, "overlap_include_hidden",   text="Include Hidden Objects")
        box.prop(scene, "overlap_use_scale_filter", text="Match Scale")
        box.prop(scene, "overlap_use_rot_filter",   text="Match Rotation")
        box.prop(scene, "overlap_show_collections", text="Show Collection Names")

        layout.separator(factor=0.5)

        # Detect / Running
        if running:
            pct = int(scene.overlap_progress * 100)

            col = layout.column()
            col.enabled = False
            col.operator("object.detect_overlaps", text=f"Detecting...  {pct}%", icon='TIME')

            row = layout.row(align=True)
            row.scale_y = 1.2
            row.operator("object.cancel_overlap_detection", text="Cancel", icon='CANCEL')
            row.operator("object.reset_overlap_selector", text="Reset", icon='FILE_REFRESH')

            layout.label(text="ESC also cancels detection", icon='INFO')
        else:
            row = layout.row(align=True)
            row.scale_y = 1.3
            label = "Re-detect" if len(groups) > 0 else "Detect Overlaps"
            row.operator("object.detect_overlaps", text=label, icon='ZOOM_ALL')

            row2 = layout.row(align=True)
            if len(groups) > 0:
                row2.operator("object.clear_overlap_results", text="Clear Results", icon='X')
            row2.operator("object.reset_overlap_selector", text="Reset", icon='FILE_REFRESH')

        layout.separator(factor=0.5)

        # Results
        if len(groups) == 0 and not running:
            layout.label(text="No results yet.", icon='MATPLANE')
            return

        if len(groups) == 0:
            return

        total_objs = sum(len(g.objects) for g in groups)
        layout.label(
            text=f"Found: {len(groups)} group(s)  x  {total_objs} objects",
            icon='OUTLINER_OB_GROUP_INSTANCE',
        )
        layout.label(text="Selection only works for objects in the current View Layer.", icon='INFO')

        # Collection filter / bulk selection
        filter_box = layout.box()
        filter_box.label(text="Collection Filter / Bulk Select", icon='FILTER')
        filter_box.prop(scene, "overlap_collection_filter", text="Collection")

        opt = filter_box.row(align=True)
        opt.prop(scene, "overlap_collection_filter_exact", text="Exact")
        opt.prop(scene, "overlap_collection_filter_case_sensitive", text="Case")

        match_count = _count_collection_filter_matches(scene)
        if scene.overlap_collection_filter.strip():
            filter_box.label(text=f"Matches in results: {match_count} object(s)", icon='VIEWZOOM')

        frow = filter_box.row(align=True)
        frow.scale_y = 1.15
        frow.operator("object.select_overlap_by_collection", text="Select Matches", icon='RESTRICT_SELECT_OFF')
        op_check = frow.operator("object.check_overlap_by_collection", text="Check Matches", icon='CHECKBOX_HLT')
        op_check.clear_existing = True

        filter_box.label(text="Select Matches selects Blender objects; it does not delete them.", icon='INFO')

        layout.separator(factor=0.5)

        # Global check/select tools
        tool = layout.row(align=True)
        tool.operator("object.select_overlap_checked", text="Select Checked", icon='CHECKMARK')
        op_all = tool.operator("object.toggle_overlap_checks", text="Check All", icon='CHECKBOX_HLT')
        op_all.select_state = True
        op_none = tool.operator("object.toggle_overlap_checks", text="None", icon='CHECKBOX_DEHLT')
        op_none.select_state = False

        # Group list selector
        list_box = layout.box()
        list_box.label(text="Overlap Groups", icon='PRESET')
        list_box.label(text="Click a group row to select its objects in Blender.", icon='RESTRICT_SELECT_OFF')
        list_box.template_list(
            "OVERLAP_UL_group_list",
            "",
            scene,
            "overlap_groups",
            scene,
            "overlap_active_group_index",
            rows=6,
        )

        g_idx, grp = _active_group(context)
        if grp is None:
            return

        # Active group detail
        detail = layout.box()
        detail.label(text=f"Selected Group: {g_idx + 1} / {len(groups)}", icon='OUTLINER_OB_GROUP_INSTANCE')
        detail.label(
            text=f"XYZ  {grp.loc_x:.4f}   {grp.loc_y:.4f}   {grp.loc_z:.4f}",
            icon='ORIENTATION_GLOBAL',
        )
        preview = _preview_group_names(grp, max_names=5)
        if preview:
            detail.label(text=preview, icon='TEXT')

        grow = detail.row(align=True)
        op_select = grow.operator("object.select_overlap_group", text="Select Group", icon='RESTRICT_SELECT_OFF')
        op_select.group_index = g_idx
        op_g_all = grow.operator("object.toggle_overlap_group_checks", text="Check Group", icon='CHECKBOX_HLT')
        op_g_all.group_index = g_idx
        op_g_all.select_state = True
        op_g_none = grow.operator("object.toggle_overlap_group_checks", text="None", icon='CHECKBOX_DEHLT')
        op_g_none.group_index = g_idx
        op_g_none.select_state = False

        remove_row = detail.row(align=True)
        op_remove = remove_row.operator("object.remove_overlap_checked_from_group", text="Remove Checked From List", icon='X')
        op_remove.group_index = g_idx

        detail.separator(factor=0.5)
        detail.label(text="Objects in Selected Group", icon='OBJECT_DATA')
        detail.label(text="Click an object row to select it in Blender.", icon='RESTRICT_SELECT_OFF')
        detail.template_list(
            "OVERLAP_UL_object_list",
            "",
            grp,
            "objects",
            scene,
            "overlap_active_object_index",
            rows=8,
        )

        o_idx, item = _active_object_item(context, grp)
        if item is None:
            return

        obj = scene.objects.get(item.obj_name)
        in_view_layer = _view_layer_object(context, item.obj_name) is not None

        object_box = detail.box()
        object_box.label(text="Selected Object Entry", icon='RNA')
        icon = 'GHOST_DISABLED' if obj is None else _TYPE_ICON.get(obj.type, 'OBJECT_DATA')
        object_box.label(text=item.obj_name, icon=icon)
        object_box.label(
            text="View Layer: selectable" if in_view_layer else "View Layer: not in current View Layer",
            icon='CHECKMARK' if in_view_layer else 'ERROR',
        )
        if scene.overlap_show_collections:
            object_box.label(text=f"Collection: {_format_collection_names(obj)}", icon='OUTLINER_COLLECTION')

        orow = object_box.row(align=True)
        op_one = orow.operator("object.select_overlap_object", text="Select This Object", icon='RESTRICT_SELECT_OFF')
        op_one.group_index = g_idx
        op_one.object_index = o_idx

        op_rm_one = orow.operator("object.remove_overlap_object_entry", text="Remove Entry From List", icon='X')
        op_rm_one.group_index = g_idx
        op_rm_one.object_index = o_idx

        delete_row = object_box.row(align=True)
        delete_row.alert = True
        op_del_one = delete_row.operator("object.delete_overlap_object", text="Delete This Blender Object", icon='TRASH')
        op_del_one.group_index = g_idx
        op_del_one.object_index = o_idx


# ───────────────────────────────────────────────────────────────────
# Register / Unregister
# ───────────────────────────────────────────────────────────────────

class OVERLAP_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__ or __name__

    def draw(self, context):
        layout = self.layout
        layout.label(text="Documentation")
        op = layout.operator("wm.url_open", text="Open User Guide on GitHub", icon="URL")
        op.url = DOCUMENTATION_URL


classes = (
    OVERLAP_AddonPreferences,
    OverlapObjectItem,
    OverlapGroupItem,
    OBJECT_OT_detect_overlaps,
    OBJECT_OT_cancel_overlap_detection,
    OBJECT_OT_reset_overlap_selector,
    OBJECT_OT_clear_overlap_results,
    OBJECT_OT_select_overlap_checked,
    OBJECT_OT_select_overlap_group,
    OBJECT_OT_select_overlap_object,
    OBJECT_OT_toggle_overlap_checks,
    OBJECT_OT_toggle_overlap_group_checks,
    OBJECT_OT_toggle_overlap_group_expanded,
    OBJECT_OT_set_overlap_groups_expanded,
    OBJECT_OT_remove_overlap_checked_from_group,
    OBJECT_OT_remove_overlap_object_entry,
    OBJECT_OT_delete_overlap_object,
    OBJECT_OT_select_overlap_by_collection,
    OBJECT_OT_check_overlap_by_collection,
    OVERLAP_UL_group_list,
    OVERLAP_UL_object_list,
    VIEW3D_PT_overlap_selector,
)

_SCENE_PROPS = (
    ("overlap_groups",           bpy.props.CollectionProperty(type=OverlapGroupItem)),
    ("overlap_include_hidden",   bpy.props.BoolProperty(
        name="Include Hidden",
        description="Include viewport-hidden objects in detection",
        default=False,
    )),
    ("overlap_use_scale_filter", bpy.props.BoolProperty(
        name="Match Scale",
        description="Only group objects that also share the same world-space scale",
        default=False,
    )),
    ("overlap_use_rot_filter",   bpy.props.BoolProperty(
        name="Match Rotation",
        description="Only group objects that also share the same world-space rotation",
        default=False,
    )),
    ("overlap_show_collections", bpy.props.BoolProperty(
        name="Show Collection Names",
        description="Show direct collection memberships under each object entry",
        default=True,
    )),
    ("overlap_collection_filter", bpy.props.StringProperty(
        name="Collection Filter",
        description="Collection name used by Select Matches / Check Matches",
        default="",
    )),
    ("overlap_collection_filter_exact", bpy.props.BoolProperty(
        name="Exact",
        description="Match the collection name exactly. Disable this to allow partial name search",
        default=True,
    )),
    ("overlap_collection_filter_case_sensitive", bpy.props.BoolProperty(
        name="Case Sensitive",
        description="Use case-sensitive collection matching",
        default=False,
    )),
    ("overlap_active_group_index", bpy.props.IntProperty(default=0, min=0, update=_on_active_group_index_update)),
    ("overlap_active_object_index", bpy.props.IntProperty(default=0, min=0, update=_on_active_object_index_update)),
    ("overlap_is_running",       bpy.props.BoolProperty(default=False)),
    ("overlap_cancel_requested", bpy.props.BoolProperty(default=False)),
    ("overlap_run_id",           bpy.props.IntProperty(default=0)),
    ("overlap_progress",         bpy.props.FloatProperty(default=0.0, min=0.0, max=1.0)),
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    for name, prop in _SCENE_PROPS:
        setattr(bpy.types.Scene, name, prop)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    for name, _ in _SCENE_PROPS:
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)


if __name__ == "__main__":
    register()
