import time

from bpy.types import Operator

from ..utils.async_processing import (
    TIMER_INTERVAL,
    begin_operation,
    cancel_operation,
    finish_operation,
    redraw_view3d,
    time_budget_exceeded,
    update_operation,
)
from ..utils.collections import (
    iter_collection_objects,
    iter_collection_tree,
    iter_layer_collection_tree,
)


def _target_collection(context):
    collection = context.scene.maplink_settings.helper_collection
    if collection is None:
        return None
    return collection


def _layer_collections_for_targets(context, target_collections):
    target_set = set(target_collections)
    return [
        layer_collection for layer_collection in iter_layer_collection_tree(context)
        if layer_collection.collection in target_set
    ]


class _HelperModalBase:
    _operation_label = "Helper Operation"
    _include_unhide = False
    _include_selectable = False

    def invoke(self, context, event):
        return self._start(context)

    def execute(self, context):
        return self._start(context)

    def _start(self, context):
        settings = context.scene.maplink_settings
        if settings.is_running:
            self.report({"WARNING"}, "Another Map Link Tools operation is running.")
            return {"CANCELLED"}

        collection = _target_collection(context)
        if collection is None:
            self.report({"WARNING"}, "Set a Helper Collection.")
            return {"CANCELLED"}

        self._collections = list(iter_collection_tree(collection))
        self._layer_collections = _layer_collections_for_targets(context, self._collections)
        self._object_iter = iter_collection_objects(collection)
        self._phase = "COLLECTIONS"
        self._index = 0
        self._processed = 0
        self._object_count = 0
        self._finished = False
        self._timer = context.window_manager.event_timer_add(TIMER_INTERVAL, window=context.window)
        total = len(self._collections) + len(self._layer_collections)
        begin_operation(settings, self._operation_label, total=total, message="Processing collections...")
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        settings = context.scene.maplink_settings
        if event.type == "ESC" or settings.cancel_requested:
            return self._cancel(context)
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        start = time.perf_counter()
        while not time_budget_exceeded(start):
            if self._phase == "COLLECTIONS":
                if self._process_collections(settings):
                    continue
                break
            if self._phase == "LAYERS":
                if self._process_layers(settings):
                    continue
                break
            if self._phase == "OBJECTS":
                if self._process_objects(settings):
                    continue
                break

        if self._finished:
            return self._finish(context)

        redraw_view3d(context)
        return {"PASS_THROUGH"}

    def _process_collections(self, settings):
        if self._index >= len(self._collections):
            self._phase = "LAYERS"
            self._index = 0
            update_operation(settings, self._processed, message="Processing layer collections...")
            return True

        collection = self._collections[self._index]
        if self._include_unhide:
            collection.hide_viewport = False
        if self._include_selectable and hasattr(collection, "hide_select"):
            collection.hide_select = False
        self._index += 1
        self._processed += 1
        update_operation(settings, self._processed)
        return True

    def _process_layers(self, settings):
        if self._index >= len(self._layer_collections):
            self._phase = "OBJECTS"
            self._index = 0
            update_operation(settings, self._processed, message="Processing objects...")
            return True

        layer_collection = self._layer_collections[self._index]
        if self._include_unhide:
            layer_collection.exclude = False
            layer_collection.hide_viewport = False
        self._index += 1
        self._processed += 1
        update_operation(settings, self._processed)
        return True

    def _process_objects(self, settings):
        try:
            obj = next(self._object_iter)
        except StopIteration:
            self._finished = True
            return False

        if self._include_unhide:
            obj.hide_viewport = False
            try:
                obj.hide_set(False)
            except RuntimeError:
                pass
        if self._include_selectable:
            obj.hide_select = False
        self._object_count += 1
        self._processed += 1
        update_operation(settings, self._processed, total=self._processed + 1)
        return True

    def _finish(self, context):
        raise NotImplementedError

    def _cancel(self, context):
        context.window_manager.event_timer_remove(self._timer)
        settings = context.scene.maplink_settings
        message = f"Canceled {self._operation_label} after {self._processed} item(s)."
        cancel_operation(settings, message)
        self.report({"WARNING"}, message)
        redraw_view3d(context)
        return {"CANCELLED"}

    def _finalize(self, context, settings, message):
        context.window_manager.event_timer_remove(self._timer)
        finish_operation(settings, message)
        self.report({"INFO"}, message)
        redraw_view3d(context)
        return {"FINISHED"}


class MAPLINK_OT_unhide_helper_collection(_HelperModalBase, Operator):
    bl_idname = "maplink.unhide_helper_collection"
    bl_label = "Unhide Collection + Objects"
    bl_description = "Unhide the selected collection tree and all objects inside it"
    bl_options = {"REGISTER", "UNDO"}

    _operation_label = "Unhide Collection + Objects"
    _include_unhide = True

    def _start(self, context):
        self._include_selectable = context.scene.maplink_settings.helper_make_selectable
        return super()._start(context)

    def _finish(self, context):
        settings = context.scene.maplink_settings
        message = (
            f"Unhid {len(self._collections)} collection(s), {self._object_count} object(s), "
            f"{len(self._layer_collections)} layer collection(s)."
        )
        if self._include_selectable:
            message += " Made selectable."
        settings.helper_result_message = message
        update_operation(settings, self._processed, total=self._processed, message=message)
        return self._finalize(context, settings, message)


class MAPLINK_OT_make_helper_collection_selectable(_HelperModalBase, Operator):
    bl_idname = "maplink.make_helper_collection_selectable"
    bl_label = "Make Collection + Objects Selectable"
    bl_description = "Make the selected collection tree and all objects inside it selectable"
    bl_options = {"REGISTER", "UNDO"}

    _operation_label = "Make Collection + Objects Selectable"
    _include_unhide = False
    _include_selectable = True

    def _finish(self, context):
        settings = context.scene.maplink_settings
        message = f"Made selectable: {len(self._collections)} collection(s), {self._object_count} object(s)."
        settings.helper_result_message = message
        update_operation(settings, self._processed, total=self._processed, message=message)
        return self._finalize(context, settings, message)
