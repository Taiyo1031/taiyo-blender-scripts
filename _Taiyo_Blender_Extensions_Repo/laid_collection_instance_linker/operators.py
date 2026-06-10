import time
import traceback

import bpy
from bpy.props import StringProperty

from . import core


REALIZE_TIMER_INTERVAL = 0.02
REALIZE_SECONDS_PER_TICK = 0.012


def _redraw_view3d(context):
    screen = getattr(context, "screen", None)
    if screen is None:
        return
    for area in screen.areas:
        if area.type == "VIEW_3D":
            area.tag_redraw()


def _realize_operation_running(operator, settings):
    if not settings.realize_is_running:
        return False
    operator.report({"WARNING"}, "Realize Generated Instances is already running")
    return True


def _validate_source_collections(operator, settings):
    if settings.laid_map_collection is None:
        operator.report({"ERROR"}, "Laid_MAP collection is not valid")
        return False
    if settings.individual_root is None:
        operator.report(
            {"ERROR"},
            "Laid_Individual root collection is not valid",
        )
        return False
    return True


def _fill_preview_item(item, result):
    item.status = result["status"]
    item.object_name = result["object_name"]
    item.match_key = result["match_key"]
    item.source_name_field = result["source_name_field"]
    item.target_collection = result["target_collection"]
    item.target_path = result["target_path"]
    item.color_tag = result["color_tag"]
    item.detail = result["detail"]


class LCIL_OT_preview_link(bpy.types.Operator):
    bl_idname = "lcil.preview_link"
    bl_label = "Preview / Link"
    bl_description = "Match Laid_MAP objects to target collections and store link properties"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.lcil_settings
        if _realize_operation_running(self, settings):
            return {"CANCELLED"}
        if not _validate_source_collections(self, settings):
            return {"CANCELLED"}

        target_index, _path_map, targets = core.build_target_index(
            settings.individual_root,
            settings.ignore_numeric_suffix,
        )
        if not targets:
            self.report(
                {"ERROR"},
                "No target collections found. Target collections must directly contain mesh objects.",
            )
            return {"CANCELLED"}

        settings.preview_items.clear()
        counts = {
            "LINKED": 0,
            "MISSING": 0,
            "DUPLICATE": 0,
            "SKIPPED": 0,
        }
        for obj in core.walk_objects(settings.laid_map_collection):
            result = core.match_object(obj, settings, target_index)
            core.store_match_properties(obj, result)
            item = settings.preview_items.add()
            _fill_preview_item(item, result)
            counts[result["status"]] += 1

        settings.preview_linked = counts["LINKED"]
        settings.preview_missing = counts["MISSING"]
        settings.preview_duplicate = counts["DUPLICATE"]
        settings.preview_skipped = counts["SKIPPED"]
        settings.preview_index = 0

        self.report(
            {"INFO"},
            (
                f"Linked {counts['LINKED']}, Missing {counts['MISSING']}, "
                f"Duplicate {counts['DUPLICATE']}, Skipped {counts['SKIPPED']}"
            ),
        )
        return {"FINISHED"}


def _select_objects(context, objects):
    for obj in context.view_layer.objects:
        obj.select_set(False)

    selected = []
    for obj in objects:
        obj.hide_viewport = False
        try:
            obj.hide_set(False)
            obj.select_set(True)
        except RuntimeError:
            continue
        selected.append(obj)

    if selected:
        context.view_layer.objects.active = selected[-1]
    return selected


class LCIL_OT_select_object(bpy.types.Operator):
    bl_idname = "lcil.select_object"
    bl_label = "Select Object"
    bl_description = "Select the source object for this preview row"

    object_name: StringProperty()

    def execute(self, context):
        obj = bpy.data.objects.get(self.object_name)
        if obj is None:
            self.report({"WARNING"}, f"Object not found: {self.object_name}")
            return {"CANCELLED"}
        selected = _select_objects(context, [obj])
        if not selected:
            self.report(
                {"WARNING"},
                "Object is not available in the current view layer",
            )
            return {"CANCELLED"}
        return {"FINISHED"}


class LCIL_OT_select_issue_objects(bpy.types.Operator):
    bl_idname = "lcil.select_issue_objects"
    bl_label = "Select All Issue Objects"
    bl_description = "Select all missing and duplicate source objects"

    def execute(self, context):
        settings = context.scene.lcil_settings
        issue_objects = []
        for item in settings.preview_items:
            if item.status not in {"MISSING", "DUPLICATE"}:
                continue
            obj = bpy.data.objects.get(item.object_name)
            if obj is not None:
                issue_objects.append(obj)

        selected = _select_objects(context, issue_objects)
        if not selected:
            self.report({"WARNING"}, "No issue objects are selectable")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Selected {len(selected)} issue object(s)")
        return {"FINISHED"}


class LCIL_OT_generate_instances(bpy.types.Operator):
    bl_idname = "lcil.generate_instances"
    bl_label = "Generate Collection Instances"
    bl_description = "Generate collection instances from saved link properties"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.lcil_settings
        if _realize_operation_running(self, settings):
            return {"CANCELLED"}
        if not _validate_source_collections(self, settings):
            return {"CANCELLED"}

        output_name = settings.output_collection_name.strip()
        if not output_name:
            self.report({"ERROR"}, "Output collection name is empty")
            return {"CANCELLED"}

        _target_index, path_map, targets = core.build_target_index(
            settings.individual_root,
            settings.ignore_numeric_suffix,
        )
        if not targets:
            self.report(
                {"ERROR"},
                "No target collections found. Target collections must directly contain mesh objects.",
            )
            return {"CANCELLED"}

        linked_sources = [
            obj
            for obj in core.walk_objects(settings.laid_map_collection)
            if obj.get("LCIL_link_status") == "LINKED"
        ]
        if not linked_sources:
            self.report(
                {"ERROR"},
                "No linked objects found. Run Preview / Link first.",
            )
            return {"CANCELLED"}

        output = core.get_or_create_output_collection(context.scene, output_name)
        core.remove_generated_content(output)

        generated = 0
        skipped = 0
        for source_obj in linked_sources:
            target_path = source_obj.get("LCIL_link_collection_path", "")
            target_collection = path_map.get(target_path)
            if target_collection is None:
                skipped += 1
                continue

            destination = output
            if settings.group_by_target:
                destination = core.get_or_create_group(output, target_collection)
            core.create_collection_instance(
                source_obj,
                target_collection,
                target_path,
                destination,
                settings.instance_prefix,
            )
            generated += 1

        if not generated:
            self.report(
                {"ERROR"},
                "No valid linked target collections were found",
            )
            return {"CANCELLED"}

        message = f"Generated {generated} collection instance(s)"
        if skipped:
            message += f"; skipped {skipped} stale link(s)"
        self.report({"INFO"}, message)
        return {"FINISHED"}


def _get_output(operator, context):
    settings = context.scene.lcil_settings
    output_name = settings.output_collection_name.strip()
    if not output_name:
        operator.report({"ERROR"}, "Output collection name is empty")
        return None
    output = bpy.data.collections.get(output_name)
    if output is None:
        operator.report({"WARNING"}, f"Output collection not found: {output_name}")
        return None
    return output


class LCIL_OT_realize_instances(bpy.types.Operator):
    bl_idname = "lcil.realize_instances"
    bl_label = "Realize Generated Instances"
    bl_description = "Duplicate instance contents as real objects and remove generated empties"
    bl_options = {"REGISTER", "UNDO"}

    _timer = None
    _queue = None

    def invoke(self, context, event):
        if context.window is None:
            return self.execute(context)
        result = self._initialize(context)
        if result is not None:
            return result

        self._timer = context.window_manager.event_timer_add(
            REALIZE_TIMER_INTERVAL,
            window=context.window,
        )
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        result = self._initialize(context)
        if result is not None:
            return result

        try:
            while not self._queue.done:
                self._queue.process_one()
                self._update_progress(context)
        except Exception as exc:
            traceback.print_exc()
            self._queue.cancel_current()
            return self._finish(
                context,
                cancelled=True,
                error_message=str(exc),
            )
        return self._finish(context)

    def modal(self, context, event):
        settings = context.scene.lcil_settings
        if event.type == "ESC" or settings.realize_cancel_requested:
            self._queue.cancel_current()
            return self._finish(context, cancelled=True)
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        started = time.perf_counter()
        processed_this_tick = 0
        try:
            while not self._queue.done:
                self._queue.process_one()
                processed_this_tick += 1
                if (
                    processed_this_tick > 0
                    and time.perf_counter() - started >= REALIZE_SECONDS_PER_TICK
                ):
                    break
        except Exception as exc:
            traceback.print_exc()
            self._queue.cancel_current()
            return self._finish(
                context,
                cancelled=True,
                error_message=str(exc),
            )

        self._update_progress(context)
        _redraw_view3d(context)
        if self._queue.done:
            return self._finish(context)
        return {"PASS_THROUGH"}

    def _initialize(self, context):
        settings = context.scene.lcil_settings
        if _realize_operation_running(self, settings):
            return {"CANCELLED"}

        output = _get_output(self, context)
        if output is None:
            return {"CANCELLED"}

        self._queue = core.RealizeQueue(output)
        if not self._queue.jobs:
            self.report(
                {"WARNING"},
                "No generated collection instance empties found",
            )
            return {"CANCELLED"}

        settings.realize_is_running = True
        settings.realize_cancel_requested = False
        settings.realize_progress = 0.0
        settings.realize_processed = 0
        settings.realize_total = self._queue.total_steps
        settings.realize_completed_instances = 0
        settings.realize_current_instance = self._queue.current_instance_name
        settings.realize_status = (
            f"Starting {len(self._queue.jobs)} generated instance(s)..."
        )
        context.window_manager.progress_begin(
            0,
            max(1, self._queue.total_steps),
        )
        return None

    def _update_progress(self, context):
        settings = context.scene.lcil_settings
        settings.realize_processed = self._queue.processed_steps
        settings.realize_completed_instances = self._queue.completed_instances
        settings.realize_current_instance = self._queue.current_instance_name
        settings.realize_progress = (
            self._queue.processed_steps / max(1, self._queue.total_steps)
        )
        context.window_manager.progress_update(self._queue.processed_steps)
        settings.realize_status = (
            f"Realized {self._queue.completed_instances} / "
            f"{len(self._queue.jobs)} instance(s), "
            f"{self._queue.realized_objects} object(s)"
        )

    def _finish(self, context, cancelled=False, error_message=""):
        settings = context.scene.lcil_settings
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None

        self._update_progress(context)
        try:
            context.window_manager.progress_end()
        except RuntimeError:
            pass

        settings.realize_is_running = False
        settings.realize_cancel_requested = False
        settings.realize_current_instance = ""

        if error_message:
            settings.realize_status = f"Realize failed: {error_message}"
            self.report({"ERROR"}, settings.realize_status)
            _redraw_view3d(context)
            return {"CANCELLED"}

        if cancelled:
            settings.realize_status = (
                f"Canceled after {self._queue.completed_instances} / "
                f"{len(self._queue.jobs)} instance(s). Run again to continue."
            )
            self.report({"WARNING"}, settings.realize_status)
            _redraw_view3d(context)
            return {"CANCELLED"}

        settings.realize_progress = 1.0
        settings.realize_processed = self._queue.total_steps
        settings.realize_status = (
            f"Realized {self._queue.completed_instances} instance(s) as "
            f"{self._queue.realized_objects} object(s)"
        )
        self.report({"INFO"}, settings.realize_status)
        _redraw_view3d(context)
        return {"FINISHED"}


class LCIL_OT_cancel_realize(bpy.types.Operator):
    bl_idname = "lcil.cancel_realize"
    bl_label = "Cancel Realize"
    bl_description = "Cancel after the current object copy finishes"

    def execute(self, context):
        settings = context.scene.lcil_settings
        if not settings.realize_is_running:
            self.report({"WARNING"}, "Realize is not running")
            return {"CANCELLED"}
        settings.realize_cancel_requested = True
        self.report({"INFO"}, "Cancel requested")
        return {"FINISHED"}


class LCIL_OT_delete_generated_empties(bpy.types.Operator):
    bl_idname = "lcil.delete_generated_empties"
    bl_label = "Delete Generated Empty Instances"
    bl_description = "Delete only generated collection instance empties"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.lcil_settings
        if _realize_operation_running(self, settings):
            return {"CANCELLED"}
        output = _get_output(self, context)
        if output is None:
            return {"CANCELLED"}

        empties = core.generated_instance_empties(output)
        if not empties:
            self.report(
                {"WARNING"},
                "No generated collection instance empties found",
            )
            return {"CANCELLED"}

        for empty in empties:
            bpy.data.objects.remove(empty, do_unlink=True)
        self.report({"INFO"}, f"Deleted {len(empties)} generated empty instance(s)")
        return {"FINISHED"}
