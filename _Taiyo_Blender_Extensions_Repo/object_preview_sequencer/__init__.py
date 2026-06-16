bl_info = {
    "name": "Object Preview Sequencer",
    "author": "Taiyo",
    "version": (1, 0, 2),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar (N) > Object Preview",
    "description": "Build a temporary one-frame-per-object visibility preview sequence.",
    "category": "Object",
}

DOCUMENTATION_URL = (
    "https://github.com/Taiyo1031/taiyo-blender-scripts/blob/main/"
    "_Taiyo_Blender_Extensions_Repo/object_preview_sequencer/README.md"
)

TEMP_ACTION_PREFIX = "OPSEQ_TEMP_"
TEMP_ACTION_MARKER = "object_preview_sequencer_temp"
RESTORE_STATE_KEY = "object_preview_sequencer_restore_state"
BUILD_OBJECTS_PER_TICK = 50

import json
import bpy
from bpy.app.handlers import persistent
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)


_BUILD_IN_PROGRESS = False


def _is_valid_object(obj):
    try:
        return obj is not None and obj.name in bpy.data.objects
    except ReferenceError:
        return False


def _is_valid_action(action):
    try:
        return action is not None and action.name in bpy.data.actions
    except ReferenceError:
        return False


def _object_key(obj):
    try:
        return obj.as_pointer()
    except ReferenceError:
        return 0


def _clear_collection(collection):
    while collection:
        collection.remove(len(collection) - 1)


def _add_unique(result, seen, obj):
    if not _is_valid_object(obj):
        return
    key = _object_key(obj)
    if key in seen:
        return
    seen.add(key)
    result.append(obj)


def _walk_collection(collection, result, seen, allowed):
    for obj in collection.objects:
        if _object_key(obj) in allowed:
            _add_unique(result, seen, obj)
    for child in collection.children:
        _walk_collection(child, result, seen, allowed)


def _ordered_view_layer_objects(context):
    allowed = {_object_key(obj) for obj in context.view_layer.objects}
    result = []
    seen = set()

    _walk_collection(context.scene.collection, result, seen, allowed)

    for obj in context.view_layer.objects:
        _add_unique(result, seen, obj)

    return result


def _ordered_selected_objects(context):
    selected = {_object_key(obj) for obj in context.selected_objects}
    return [obj for obj in _ordered_view_layer_objects(context) if _object_key(obj) in selected]


def _registered_targets(settings):
    result = []
    seen = set()
    for item in settings.registered_objects:
        obj = item.object
        if not _is_valid_object(obj):
            continue
        _add_unique(result, seen, obj)
    return result


def _temp_action_name(obj):
    return bpy.data.actions.new(name=f"{TEMP_ACTION_PREFIX}{obj.name}").name


def _iter_action_fcurves(action):
    for fcurve in getattr(action, "fcurves", []):
        yield fcurve
    for layer in getattr(action, "layers", []):
        for strip in getattr(layer, "strips", []):
            for channelbag in getattr(strip, "channelbags", []):
                for fcurve in channelbag.fcurves:
                    yield fcurve


def _insert_visibility_key(obj, frame, hidden):
    obj.hide_viewport = hidden
    obj.hide_render = hidden
    obj.keyframe_insert(data_path="hide_viewport", frame=frame)
    obj.keyframe_insert(data_path="hide_render", frame=frame)


def _create_temp_visibility_action(obj, start_frame, end_frame, visible_frame):
    action_name = _temp_action_name(obj)
    action = bpy.data.actions[action_name]
    action[TEMP_ACTION_MARKER] = True
    action["object_name"] = obj.name
    try:
        action.id_root = "OBJECT"
    except Exception:
        pass

    obj.animation_data_create()
    obj.animation_data.action = action

    if visible_frame is None:
        _insert_visibility_key(obj, start_frame, True)
    else:
        if visible_frame > start_frame:
            _insert_visibility_key(obj, start_frame, True)
        _insert_visibility_key(obj, visible_frame, False)
        _insert_visibility_key(obj, visible_frame + 1, True)

    for fcurve in _iter_action_fcurves(action):
        for point in fcurve.keyframe_points:
            point.interpolation = "CONSTANT"
        fcurve.update()

    return action


def _store_restore_state(settings, context):
    scene = context.scene
    settings.saved_frame_current = scene.frame_current
    settings.saved_frame_start = scene.frame_start
    settings.saved_frame_end = scene.frame_end
    settings.saved_active_object = context.view_layer.objects.active
    _clear_collection(settings.restore_items)


def _restore_item_to_dict(item):
    obj = item.object
    original_action = item.original_action
    return {
        "object_name": obj.name if _is_valid_object(obj) else "",
        "original_action_name": original_action.name if _is_valid_action(original_action) else "",
        "temp_action_name": item.temp_action_name,
        "had_animation_data": bool(item.had_animation_data),
        "original_hide_viewport": bool(item.original_hide_viewport),
        "original_hide_render": bool(item.original_hide_render),
        "original_hidden": bool(item.original_hidden),
        "was_selected": bool(item.was_selected),
    }


def _persistent_restore_payload(settings):
    active_object = settings.saved_active_object
    return {
        "schema_version": 1,
        "saved_frame_current": int(settings.saved_frame_current),
        "saved_frame_start": int(settings.saved_frame_start),
        "saved_frame_end": int(settings.saved_frame_end),
        "sequence_start": int(settings.sequence_start),
        "sequence_end": int(settings.sequence_end),
        "saved_active_object_name": active_object.name if _is_valid_object(active_object) else "",
        "items": [_restore_item_to_dict(item) for item in settings.restore_items],
    }


def _save_persistent_restore_state(scene, settings):
    scene[RESTORE_STATE_KEY] = json.dumps(_persistent_restore_payload(settings), sort_keys=True)


def _load_persistent_restore_state(scene):
    raw = scene.get(RESTORE_STATE_KEY)
    if not raw:
        return None
    if not isinstance(raw, str):
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("items"):
        return None
    return data


def _has_persistent_restore_state(scene):
    return _load_persistent_restore_state(scene) is not None


def _clear_persistent_restore_state(scene):
    if RESTORE_STATE_KEY in scene:
        del scene[RESTORE_STATE_KEY]


def _sync_scene_from_persistent_state(scene):
    if not hasattr(scene, "opseq_settings"):
        return
    settings = scene.opseq_settings
    data = _load_persistent_restore_state(scene)
    if not data:
        return
    settings.sequence_active = True
    settings.sequence_start = int(data.get("sequence_start", 0))
    settings.sequence_end = int(data.get("sequence_end", 0))
    settings.status_message = "Saved preview sequence can be restored."


def _sync_all_scenes_from_persistent_state():
    for scene in bpy.data.scenes:
        _sync_scene_from_persistent_state(scene)


def _restore_entries(settings, scene):
    if settings.restore_items:
        entries = []
        for item in settings.restore_items:
            entries.append({
                "object": item.object,
                "object_name": item.object.name if _is_valid_object(item.object) else "",
                "original_action": item.original_action,
                "original_action_name": item.original_action.name if _is_valid_action(item.original_action) else "",
                "temp_action_name": item.temp_action_name,
                "had_animation_data": bool(item.had_animation_data),
                "original_hide_viewport": bool(item.original_hide_viewport),
                "original_hide_render": bool(item.original_hide_render),
                "original_hidden": bool(item.original_hidden),
                "was_selected": bool(item.was_selected),
            })
        return entries, settings.saved_active_object, {
            "saved_frame_current": settings.saved_frame_current,
            "saved_frame_start": settings.saved_frame_start,
            "saved_frame_end": settings.saved_frame_end,
        }

    data = _load_persistent_restore_state(scene)
    if not data:
        return [], None, {}

    entries = []
    for item in data.get("items", []):
        obj = bpy.data.objects.get(item.get("object_name", ""))
        original_action = bpy.data.actions.get(item.get("original_action_name", ""))
        entries.append({
            "object": obj,
            "object_name": item.get("object_name", ""),
            "original_action": original_action,
            "original_action_name": item.get("original_action_name", ""),
            "temp_action_name": item.get("temp_action_name", ""),
            "had_animation_data": bool(item.get("had_animation_data", False)),
            "original_hide_viewport": bool(item.get("original_hide_viewport", False)),
            "original_hide_render": bool(item.get("original_hide_render", False)),
            "original_hidden": bool(item.get("original_hidden", False)),
            "was_selected": bool(item.get("was_selected", False)),
        })

    active_object = bpy.data.objects.get(data.get("saved_active_object_name", ""))
    frames = {
        "saved_frame_current": int(data.get("saved_frame_current", scene.frame_current)),
        "saved_frame_start": int(data.get("saved_frame_start", scene.frame_start)),
        "saved_frame_end": int(data.get("saved_frame_end", scene.frame_end)),
    }
    return entries, active_object, frames


def _restore_selection(context, items, active_object):
    for obj in context.view_layer.objects:
        try:
            obj.select_set(False)
        except Exception:
            pass

    for item in items:
        obj = item.get("object") if isinstance(item, dict) else item.object
        was_selected = item.get("was_selected", False) if isinstance(item, dict) else item.was_selected
        if not _is_valid_object(obj) or not was_selected:
            continue
        try:
            obj.select_set(True)
        except Exception:
            pass

    if _is_valid_object(active_object):
        try:
            context.view_layer.objects.active = active_object
        except Exception:
            pass


def restore_sequence(context, settings):
    scene = context.scene
    restore_items, active_object, frame_state = _restore_entries(settings, scene)
    temp_action_names = [item["temp_action_name"] for item in restore_items if item.get("temp_action_name")]

    for item in restore_items:
        obj = item.get("object")
        if not _is_valid_object(obj):
            continue

        if item.get("had_animation_data"):
            obj.animation_data_create()
            original_action = item.get("original_action")
            obj.animation_data.action = original_action if _is_valid_action(original_action) else None
        elif obj.animation_data:
            obj.animation_data_clear()

    for action_name in temp_action_names:
        action = bpy.data.actions.get(action_name)
        if action is not None and action.get(TEMP_ACTION_MARKER):
            bpy.data.actions.remove(action)

    saved_frame_start = int(frame_state.get("saved_frame_start", settings.saved_frame_start))
    saved_frame_end = int(frame_state.get("saved_frame_end", settings.saved_frame_end))
    saved_frame_current = int(frame_state.get("saved_frame_current", settings.saved_frame_current))
    if saved_frame_start <= saved_frame_end:
        scene.frame_start = saved_frame_start
        scene.frame_end = saved_frame_end
    scene.frame_set(saved_frame_current)

    for item in restore_items:
        obj = item.get("object")
        if not _is_valid_object(obj):
            continue
        obj.hide_viewport = bool(item.get("original_hide_viewport", False))
        obj.hide_render = bool(item.get("original_hide_render", False))
        try:
            obj.hide_set(bool(item.get("original_hidden", False)))
        except Exception:
            pass

    _restore_selection(context, restore_items, active_object)
    _clear_collection(settings.restore_items)
    _clear_persistent_restore_state(scene)
    settings.sequence_active = False
    settings.sequence_start = 0
    settings.sequence_end = 0
    settings.status_message = "Restored original state."


def _prepare_build_sequence(context, settings):
    scene = context.scene
    targets = _registered_targets(settings)
    if not targets:
        return None

    all_objects = _ordered_view_layer_objects(context)
    start_frame = max(1, scene.frame_current)
    frames = list(range(start_frame, start_frame + len(targets)))
    target_frames = {_object_key(obj): frames[index] for index, obj in enumerate(targets)}

    _store_restore_state(settings, context)

    return {
        "all_objects": all_objects,
        "target_count": len(targets),
        "target_frames": target_frames,
        "start_frame": frames[0],
        "end_frame": frames[-1],
        "index": 0,
        "built_count": 0,
        "action_count": 0,
    }


def _process_build_state(context, settings, state, object_limit=None):
    processed = 0
    all_objects = state["all_objects"]

    while state["index"] < len(all_objects):
        if object_limit is not None and processed >= object_limit:
            break

        obj = all_objects[state["index"]]
        state["index"] += 1
        processed += 1

        try:
            item = settings.restore_items.add()
            item.object = obj
            item.had_animation_data = obj.animation_data is not None
            item.original_action = obj.animation_data.action if obj.animation_data else None
            item.original_hide_viewport = obj.hide_viewport
            item.original_hide_render = obj.hide_render
            item.original_hidden = obj.hide_get()
            item.was_selected = obj.select_get()

            visible_frame = state["target_frames"].get(_object_key(obj))
            if visible_frame is None:
                obj.hide_viewport = True
                obj.hide_render = True
                try:
                    obj.hide_set(True)
                except Exception:
                    pass
            else:
                action = _create_temp_visibility_action(
                    obj,
                    state["start_frame"],
                    state["end_frame"],
                    visible_frame,
                )
                item.temp_action_name = action.name
                obj.hide_set(False)
                state["action_count"] += 1
            state["built_count"] += 1
        except Exception:
            continue

    return state["index"] >= len(all_objects)


def _finish_build_sequence(context, settings, state):
    scene = context.scene
    if state["built_count"] == 0 or state["action_count"] == 0:
        if settings.restore_items:
            restore_sequence(context, settings)
        else:
            _clear_collection(settings.restore_items)
        return False

    scene.frame_start = state["start_frame"]
    scene.frame_end = state["end_frame"]
    scene.frame_set(state["start_frame"])
    context.view_layer.update()

    settings.sequence_active = True
    settings.sequence_start = state["start_frame"]
    settings.sequence_end = state["end_frame"]
    settings.status_message = (
        f"Built {state['target_count']} frame(s) from {state['start_frame']} to {state['end_frame']}."
    )
    _save_persistent_restore_state(scene, settings)
    return True


def _build_sequence(context, settings):
    state = _prepare_build_sequence(context, settings)
    if state is None:
        return 0, 0

    _process_build_state(context, settings, state)
    if not _finish_build_sequence(context, settings, state):
        return 0, 0
    return state["target_count"], state["built_count"]


class OPSEQ_ObjectItem(bpy.types.PropertyGroup):
    object: PointerProperty(type=bpy.types.Object)


class OPSEQ_RestoreItem(bpy.types.PropertyGroup):
    object: PointerProperty(type=bpy.types.Object)
    original_action: PointerProperty(type=bpy.types.Action)
    temp_action_name: StringProperty(default="")
    had_animation_data: BoolProperty(default=False)
    original_hide_viewport: BoolProperty(default=False)
    original_hide_render: BoolProperty(default=False)
    original_hidden: BoolProperty(default=False)
    was_selected: BoolProperty(default=False)


class OPSEQ_Settings(bpy.types.PropertyGroup):
    registered_objects: CollectionProperty(type=OPSEQ_ObjectItem)
    restore_items: CollectionProperty(type=OPSEQ_RestoreItem)
    saved_active_object: PointerProperty(type=bpy.types.Object)
    saved_frame_current: IntProperty(default=1)
    saved_frame_start: IntProperty(default=1)
    saved_frame_end: IntProperty(default=250)
    sequence_start: IntProperty(default=0)
    sequence_end: IntProperty(default=0)
    sequence_active: BoolProperty(default=False)
    status_message: StringProperty(default="Register selected objects to build a preview sequence.")


class OPSEQ_OT_register_selected(bpy.types.Operator):
    bl_idname = "opseq.register_selected"
    bl_label = "Register Selected"
    bl_description = "Register selected objects in Outliner order"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.opseq_settings
        if settings.sequence_active or _has_persistent_restore_state(context.scene):
            self.report({"WARNING"}, "End the active preview sequence before registering objects.")
            return {"CANCELLED"}

        selected = _ordered_selected_objects(context)
        if not selected:
            self.report({"WARNING"}, "No objects selected.")
            return {"CANCELLED"}

        _clear_collection(settings.registered_objects)
        for obj in selected:
            item = settings.registered_objects.add()
            item.object = obj

        settings.status_message = f"Registered {len(selected)} object(s)."
        self.report({"INFO"}, settings.status_message)
        return {"FINISHED"}


class OPSEQ_OT_build_sequence(bpy.types.Operator):
    bl_idname = "opseq.build_sequence"
    bl_label = "Build Sequence"
    bl_description = "Build a temporary one-frame-per-object visibility sequence"
    bl_options = {"REGISTER", "UNDO"}

    _timer = None
    _state = None

    def _finish_modal(self, context):
        global _BUILD_IN_PROGRESS
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        _BUILD_IN_PROGRESS = False

    def modal(self, context, event):
        if event.type == "ESC":
            restore_sequence(context, context.scene.opseq_settings)
            self._finish_modal(context)
            self.report({"WARNING"}, "Cancelled preview sequence build.")
            return {"CANCELLED"}

        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        settings = context.scene.opseq_settings
        done = _process_build_state(context, settings, self._state, BUILD_OBJECTS_PER_TICK)
        settings.status_message = (
            f"Building preview sequence... {self._state['index']} / {len(self._state['all_objects'])}"
        )

        if not done:
            return {"RUNNING_MODAL"}

        self._finish_modal(context)
        if not _finish_build_sequence(context, settings, self._state):
            settings.status_message = "Could not build temporary actions."
            self.report({"ERROR"}, settings.status_message)
            return {"CANCELLED"}

        self.report({"INFO"}, settings.status_message)
        return {"FINISHED"}

    def execute(self, context):
        global _BUILD_IN_PROGRESS
        settings = context.scene.opseq_settings
        if _BUILD_IN_PROGRESS:
            self.report({"WARNING"}, "A preview sequence is already building.")
            return {"CANCELLED"}

        if settings.sequence_active or _has_persistent_restore_state(context.scene):
            restore_sequence(context, settings)

        state = _prepare_build_sequence(context, settings)
        if state is None:
            settings.status_message = "No valid registered objects."
            self.report({"WARNING"}, settings.status_message)
            return {"CANCELLED"}

        if bpy.app.background or context.window is None:
            _process_build_state(context, settings, state)
            if not _finish_build_sequence(context, settings, state):
                settings.status_message = "Could not build temporary actions."
                self.report({"ERROR"}, settings.status_message)
                return {"CANCELLED"}
            self.report({"INFO"}, settings.status_message)
            return {"FINISHED"}

        self._state = state
        self._timer = context.window_manager.event_timer_add(0.01, window=context.window)
        context.window_manager.modal_handler_add(self)
        _BUILD_IN_PROGRESS = True
        settings.status_message = "Building preview sequence..."
        self.report({"INFO"}, settings.status_message)
        return {"RUNNING_MODAL"}


class OPSEQ_OT_restore_sequence(bpy.types.Operator):
    bl_idname = "opseq.restore_sequence"
    bl_label = "Restore / End Mode"
    bl_description = "Remove temporary preview actions and restore the original state"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.opseq_settings
        if not settings.sequence_active and not _has_persistent_restore_state(context.scene):
            settings.status_message = "No active preview sequence."
            self.report({"INFO"}, settings.status_message)
            return {"CANCELLED"}

        restore_sequence(context, settings)
        self.report({"INFO"}, settings.status_message)
        return {"FINISHED"}


class OPSEQ_OT_clear_registered(bpy.types.Operator):
    bl_idname = "opseq.clear_registered"
    bl_label = "Clear"
    bl_description = "Clear the registered object list"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.opseq_settings
        if settings.sequence_active or _has_persistent_restore_state(context.scene):
            restore_sequence(context, settings)

        _clear_collection(settings.registered_objects)
        settings.status_message = "Cleared registered objects."
        self.report({"INFO"}, settings.status_message)
        return {"FINISHED"}


class OPSEQ_PT_object_preview(bpy.types.Panel):
    bl_label = "Object Preview"
    bl_idname = "OPSEQ_PT_object_preview"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Object Preview"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.opseq_settings

        box = layout.box()
        box.label(text="Objects", icon="OUTLINER_OB_GROUP_INSTANCE")
        row = box.row(align=True)
        row.operator("opseq.register_selected", icon="RESTRICT_SELECT_OFF")
        row.operator("opseq.clear_registered", icon="X")

        registered = _registered_targets(settings)
        if registered:
            box.label(text=f"{len(registered)} registered")
            for index, obj in enumerate(registered[:12], start=1):
                box.label(text=f"{index}. {obj.name}", icon="OBJECT_DATA")
            if len(registered) > 12:
                box.label(text=f"... {len(registered) - 12} more")
        else:
            box.label(text="No registered objects", icon="INFO")

        box = layout.box()
        box.label(text="Sequence", icon="TIME")
        if settings.sequence_active or _has_persistent_restore_state(context.scene):
            box.label(text=f"Frames: {settings.sequence_start} - {settings.sequence_end}")
            box.operator("opseq.restore_sequence", text="Restore / End Mode", icon="LOOP_BACK")
        else:
            box.operator("opseq.build_sequence", icon="PLAY")
        if settings.status_message:
            box.label(text=settings.status_message, icon="INFO")


class OPSEQ_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__ or __name__

    def draw(self, context):
        layout = self.layout
        layout.label(text="Documentation")
        op = layout.operator("wm.url_open", text="Open User Guide on GitHub", icon="URL")
        op.url = DOCUMENTATION_URL


classes = (
    OPSEQ_AddonPreferences,
    OPSEQ_ObjectItem,
    OPSEQ_RestoreItem,
    OPSEQ_Settings,
    OPSEQ_OT_register_selected,
    OPSEQ_OT_build_sequence,
    OPSEQ_OT_restore_sequence,
    OPSEQ_OT_clear_registered,
    OPSEQ_PT_object_preview,
)


@persistent
def _opseq_load_post(_dummy):
    _sync_all_scenes_from_persistent_state()


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.opseq_settings = PointerProperty(type=OPSEQ_Settings)
    _sync_all_scenes_from_persistent_state()
    if _opseq_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_opseq_load_post)


def unregister():
    if _opseq_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_opseq_load_post)
    if hasattr(bpy.types.Scene, "opseq_settings"):
        del bpy.types.Scene.opseq_settings

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
