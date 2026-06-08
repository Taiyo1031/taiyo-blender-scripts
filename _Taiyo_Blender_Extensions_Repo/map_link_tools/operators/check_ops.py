import time

from bpy.props import EnumProperty
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
from ..utils.collections import iter_collection_objects


def _collections_from_settings(context):
    settings = context.scene.maplink_settings
    return settings.collection_a, settings.collection_b


class MAPLINK_OT_check_collection_mesh_links(Operator):
    bl_idname = "maplink.check_collection_mesh_links"
    bl_label = "Check Mesh Links"
    bl_description = "Check whether Collection A and B contain objects sharing the same mesh data"
    bl_options = {"REGISTER"}

    def invoke(self, context, event):
        return self._start(context)

    def execute(self, context):
        return self._start(context)

    def _start(self, context):
        settings = context.scene.maplink_settings
        if settings.is_running:
            self.report({"WARNING"}, "Another Map Link Tools operation is running.")
            return {"CANCELLED"}

        collection_a, collection_b = _collections_from_settings(context)
        if collection_a is None or collection_b is None:
            self.report({"WARNING"}, "Set Collection A and Collection B.")
            return {"CANCELLED"}

        self._collection_a = collection_a
        self._collection_b = collection_b
        self._phase = "A"
        self._iterator = iter_collection_objects(collection_a)
        self._a_mesh_counts = {}
        self._shared_meshes = set()
        self._linked_b_count = 0
        self._processed = 0
        self._timer = context.window_manager.event_timer_add(TIMER_INTERVAL, window=context.window)

        begin_operation(settings, "Check Mesh Links", message="Scanning Collection A...")
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
            try:
                obj = next(self._iterator)
            except StopIteration:
                if self._phase == "A":
                    self._phase = "B"
                    self._iterator = iter_collection_objects(self._collection_b)
                    update_operation(settings, self._processed, message="Scanning Collection B...")
                    continue
                return self._finish(context)

            if obj.type == "MESH" and obj.data is not None:
                if self._phase == "A":
                    self._a_mesh_counts[obj.data] = self._a_mesh_counts.get(obj.data, 0) + 1
                elif obj.data in self._a_mesh_counts:
                    self._shared_meshes.add(obj.data)
                    self._linked_b_count += 1
            self._processed += 1

        update_operation(settings, self._processed, message=f"Scanning Collection {self._phase}...")
        redraw_view3d(context)
        return {"PASS_THROUGH"}

    def _finish(self, context):
        context.window_manager.event_timer_remove(self._timer)
        settings = context.scene.maplink_settings
        linked_a_count = sum(self._a_mesh_counts[mesh] for mesh in self._shared_meshes)
        message = (
            f"Shared mesh data: {len(self._shared_meshes)}. "
            f"A linked objects: {linked_a_count}, B linked objects: {self._linked_b_count}."
        )
        settings.check_result_message = message
        finish_operation(settings, message)
        self.report({"INFO"}, message)
        redraw_view3d(context)
        return {"FINISHED"}

    def _cancel(self, context):
        context.window_manager.event_timer_remove(self._timer)
        settings = context.scene.maplink_settings
        message = f"Canceled Check Mesh Links after {self._processed} object(s)."
        cancel_operation(settings, message)
        self.report({"WARNING"}, message)
        redraw_view3d(context)
        return {"CANCELLED"}


class MAPLINK_OT_select_unlinked_in_collection(Operator):
    bl_idname = "maplink.select_unlinked_in_collection"
    bl_label = "Select Unlinked"
    bl_description = "Select mesh objects in this collection that do not share mesh data with the other collection"
    bl_options = {"REGISTER", "UNDO"}

    side: EnumProperty(
        items=(
            ("A", "Collection A", "Use Collection A as the selection target"),
            ("B", "Collection B", "Use Collection B as the selection target"),
        ),
        default="A",
    )

    def invoke(self, context, event):
        return self._start(context)

    def execute(self, context):
        return self._start(context)

    def _start(self, context):
        settings = context.scene.maplink_settings
        if settings.is_running:
            self.report({"WARNING"}, "Another Map Link Tools operation is running.")
            return {"CANCELLED"}

        collection_a, collection_b = _collections_from_settings(context)
        if collection_a is None or collection_b is None:
            self.report({"WARNING"}, "Set Collection A and Collection B.")
            return {"CANCELLED"}

        self._target_collection = collection_a if self.side == "A" else collection_b
        self._other_collection = collection_b if self.side == "A" else collection_a
        self._phase = "OTHER"
        self._iterator = iter_collection_objects(self._other_collection)
        self._other_meshes = set()
        self._selected = 0
        self._skipped = 0
        self._processed = 0
        self._made_active = False
        self._finished = False
        self._timer = context.window_manager.event_timer_add(TIMER_INTERVAL, window=context.window)

        begin_operation(settings, f"Select Unlinked {self.side}", message="Scanning other collection...")
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
            if self._phase == "OTHER":
                if self._process_other(settings):
                    continue
                break
            if self._phase == "DESELECT":
                if self._process_deselect(context, settings):
                    continue
                break
            if self._phase == "TARGET":
                if self._process_target(context, settings):
                    continue
                break

        if self._finished:
            return self._finish(context)

        update_operation(settings, self._processed)
        redraw_view3d(context)
        return {"PASS_THROUGH"}

    def _process_other(self, settings):
        try:
            obj = next(self._iterator)
        except StopIteration:
            self._phase = "DESELECT"
            self._iterator = None
            update_operation(settings, self._processed, message="Clearing current selection...")
            return True

        if obj.type == "MESH" and obj.data is not None:
            self._other_meshes.add(obj.data)
        self._processed += 1
        return True

    def _process_deselect(self, context, settings):
        if self._iterator is None:
            self._iterator = iter(context.view_layer.objects)
        try:
            obj = next(self._iterator)
        except StopIteration:
            self._phase = "TARGET"
            self._iterator = iter_collection_objects(self._target_collection)
            update_operation(settings, self._processed, message="Selecting unlinked objects...")
            return True

        try:
            obj.select_set(False)
        except RuntimeError:
            self._skipped += 1
        self._processed += 1
        return True

    def _process_target(self, context, settings):
        try:
            obj = next(self._iterator)
        except StopIteration:
            self._finished = True
            return False

        if obj.type == "MESH" and obj.data is not None and obj.data not in self._other_meshes:
            try:
                obj.select_set(True)
                if not self._made_active:
                    context.view_layer.objects.active = obj
                    self._made_active = True
                self._selected += 1
            except RuntimeError:
                self._skipped += 1
        self._processed += 1
        return True

    def _finish(self, context):
        context.window_manager.event_timer_remove(self._timer)
        settings = context.scene.maplink_settings
        message = f"Selected {self._selected} unlinked object(s) from Collection {self.side}; skipped {self._skipped}."
        finish_operation(settings, message)
        self.report({"INFO"}, message)
        redraw_view3d(context)
        return {"FINISHED"}

    def _cancel(self, context):
        context.window_manager.event_timer_remove(self._timer)
        settings = context.scene.maplink_settings
        message = f"Canceled Select Unlinked after {self._processed} item(s)."
        cancel_operation(settings, message)
        self.report({"WARNING"}, message)
        redraw_view3d(context)
        return {"CANCELLED"}
