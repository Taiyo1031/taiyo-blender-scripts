bl_info = {
    "name": "Object Preview Sequencer",
    "author": "Taiyo",
    "version": (1, 0, 0),
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

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)


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


def _create_temp_visibility_action(obj, frames, visible_frame):
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

    for frame in frames:
        hidden = visible_frame is None or frame != visible_frame
        obj.hide_viewport = hidden
        obj.hide_render = hidden
        obj.keyframe_insert(data_path="hide_viewport", frame=frame)
        obj.keyframe_insert(data_path="hide_render", frame=frame)

    for fcurve in action.fcurves:
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


def _restore_selection(context, items, active_object):
    for obj in context.view_layer.objects:
        try:
            obj.select_set(False)
        except Exception:
            pass

    for item in items:
        obj = item.object
        if not _is_valid_object(obj) or not item.was_selected:
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
    temp_action_names = [item.temp_action_name for item in settings.restore_items if item.temp_action_name]
    restore_items = list(settings.restore_items)
    active_object = settings.saved_active_object

    for item in restore_items:
        obj = item.object
        if not _is_valid_object(obj):
            continue

        if item.had_animation_data:
            obj.animation_data_create()
            obj.animation_data.action = item.original_action if _is_valid_action(item.original_action) else None
        elif obj.animation_data:
            obj.animation_data_clear()

    for action_name in temp_action_names:
        action = bpy.data.actions.get(action_name)
        if action is not None and action.get(TEMP_ACTION_MARKER):
            bpy.data.actions.remove(action)

    if settings.saved_frame_start <= settings.saved_frame_end:
        scene.frame_start = settings.saved_frame_start
        scene.frame_end = settings.saved_frame_end
    scene.frame_set(settings.saved_frame_current)

    for item in restore_items:
        obj = item.object
        if not _is_valid_object(obj):
            continue
        obj.hide_viewport = item.original_hide_viewport
        obj.hide_render = item.original_hide_render
        try:
            obj.hide_set(item.original_hidden)
        except Exception:
            pass

    _restore_selection(context, restore_items, active_object)
    _clear_collection(settings.restore_items)
    settings.sequence_active = False
    settings.sequence_start = 0
    settings.sequence_end = 0
    settings.status_message = "Restored original state."


def _build_sequence(context, settings):
    scene = context.scene
    targets = _registered_targets(settings)
    if not targets:
        return 0, 0

    all_objects = _ordered_view_layer_objects(context)
    frames = list(range(scene.frame_current, scene.frame_current + len(targets)))
    target_frames = {_object_key(obj): frames[index] for index, obj in enumerate(targets)}

    _store_restore_state(settings, context)

    built_count = 0
    for obj in all_objects:
        try:
            item = settings.restore_items.add()
            item.object = obj
            item.had_animation_data = obj.animation_data is not None
            item.original_action = obj.animation_data.action if obj.animation_data else None
            item.original_hide_viewport = obj.hide_viewport
            item.original_hide_render = obj.hide_render
            item.original_hidden = obj.hide_get()
            item.was_selected = obj.select_get()

            action = _create_temp_visibility_action(obj, frames, target_frames.get(_object_key(obj)))
            item.temp_action_name = action.name
            obj.hide_set(False)
            built_count += 1
        except Exception:
            continue

    if built_count == 0:
        _clear_collection(settings.restore_items)
        return 0, 0

    scene.frame_start = frames[0]
    scene.frame_end = frames[-1]
    scene.frame_set(frames[0])
    context.view_layer.update()

    settings.sequence_active = True
    settings.sequence_start = frames[0]
    settings.sequence_end = frames[-1]
    settings.status_message = (
        f"Built {len(targets)} frame(s) from {frames[0]} to {frames[-1]}."
    )
    return len(targets), built_count


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
        if settings.sequence_active:
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

    def execute(self, context):
        settings = context.scene.opseq_settings
        if settings.sequence_active:
            restore_sequence(context, settings)

        target_count, object_count = _build_sequence(context, settings)
        if target_count == 0:
            settings.status_message = "No valid registered objects."
            self.report({"WARNING"}, settings.status_message)
            return {"CANCELLED"}
        if object_count == 0:
            settings.status_message = "Could not build temporary actions."
            self.report({"ERROR"}, settings.status_message)
            return {"CANCELLED"}

        self.report({"INFO"}, settings.status_message)
        return {"FINISHED"}


class OPSEQ_OT_restore_sequence(bpy.types.Operator):
    bl_idname = "opseq.restore_sequence"
    bl_label = "Restore / End Mode"
    bl_description = "Remove temporary preview actions and restore the original state"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.opseq_settings
        if not settings.sequence_active:
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
        if settings.sequence_active:
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
        if settings.sequence_active:
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


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.opseq_settings = PointerProperty(type=OPSEQ_Settings)


def unregister():
    if hasattr(bpy.types.Scene, "opseq_settings"):
        settings = getattr(bpy.context.scene, "opseq_settings", None)
        if settings is not None and settings.sequence_active:
            try:
                restore_sequence(bpy.context, settings)
            except Exception:
                pass
        del bpy.types.Scene.opseq_settings

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
