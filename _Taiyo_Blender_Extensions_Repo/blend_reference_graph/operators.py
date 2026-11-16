import os
import shutil
import time
import webbrowser
from pathlib import Path

import bpy
from bpy.types import Operator

from .graph import GraphData, build_graph, export_graph_data, resolve_output_folder
from .scanner.object_scanner import bone_id, object_id
from .scanner.whole_file_scanner import ScanOptions, iter_scan
from .version import VERSION
from .live import controller


def _addon_dir():
    return os.path.dirname(os.path.abspath(__file__))


def _copy_viewer_files(output_folder):
    os.makedirs(output_folder, exist_ok=True)
    source_dir = os.path.join(_addon_dir(), "html")
    for filename in ("viewer.html", "viewer.css", "viewer.js"):
        source = os.path.join(source_dir, filename)
        target = os.path.join(output_folder, filename)
        shutil.copyfile(source, target)
    return os.path.join(output_folder, "viewer.html")


def _open_viewer(context, viewer_path):
    if controller.enabled(context):
        destination = controller.start(context)
    else:
        controller.stop()
        destination = Path(viewer_path).resolve().as_uri()
    webbrowser.open(destination)


def _set_active_target(context, settings):
    obj = context.object
    if obj and context.mode == "POSE" and context.active_pose_bone:
        bone = context.active_pose_bone
        settings.target_type = "BONE"
        settings.target_name = f"{obj.name} / {bone.name}"
        settings.target_id = bone_id(obj, bone.name)
        return True
    if obj:
        settings.target_type = "OBJECT"
        settings.target_name = obj.name
        settings.target_id = object_id(obj)
        return True
    return False


class BRG_OT_use_selected(Operator):
    bl_idname = "brg.use_selected"
    bl_label = "Use Selected"
    bl_description = "Use the active object or pose bone as the graph target"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.brg_settings
        if not _set_active_target(context, settings):
            self.report({"WARNING"}, "Select an object or pose bone first.")
            return {"CANCELLED"}
        settings.status_message = f"Target set: {settings.target_name}"
        return {"FINISHED"}


class BRG_OT_update_graph_data(Operator):
    bl_idname = "brg.update_graph_data"
    bl_label = "Update Graph Data"
    bl_description = "Scan Blender references and write graph_data.js"
    bl_options = {"REGISTER"}

    def execute(self, context):
        settings = context.scene.brg_settings
        if not settings.target_name:
            _set_active_target(context, settings)

        try:
            output_folder = resolve_output_folder(context)
            graph = build_graph(context, settings)
            generated_at = time.strftime("%Y-%m-%d %H:%M:%S")
            meta = {
                "addon_name": "Blend Reference Graph",
                "version": VERSION,
                "scope": "TARGET",
                "generated_at": generated_at,
                "blend_file": bpy.path.basename(bpy.data.filepath) if bpy.data.filepath else "Unsaved",
                "target_id": settings.target_id,
                "target_name": settings.target_name,
                "mode": settings.scan_mode,
                "depth": settings.depth,
            }
            output_path, payload = export_graph_data(graph, meta, output_folder)
            viewer_path = _copy_viewer_files(os.path.dirname(output_path))
        except (OSError, ValueError) as exc:
            settings.status_message = str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        settings.last_update = generated_at
        settings.node_count = payload["meta"]["node_count"]
        settings.edge_count = payload["meta"]["edge_count"]
        settings.resolved_output_path = str(output_folder)
        settings.status_message = f"Wrote {os.path.basename(output_path)}"
        self.report({"INFO"}, f"Graph data updated: {viewer_path}")
        return {"FINISHED"}


class BRG_OT_open_viewer(Operator):
    bl_idname = "brg.open_viewer"
    bl_label = "Open Viewer"
    bl_description = "Open the HTML graph viewer in the system browser"
    bl_options = {"REGISTER"}

    def execute(self, context):
        settings = context.scene.brg_settings
        try:
            output_folder = resolve_output_folder(context)
            viewer_path = os.path.join(output_folder, "viewer.html")
            if not os.path.exists(viewer_path):
                _copy_viewer_files(output_folder)
            _open_viewer(context, viewer_path)
        except (OSError, ValueError) as exc:
            settings.status_message = str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        settings.resolved_output_path = str(output_folder)
        settings.status_message = "Opened viewer."
        return {"FINISHED"}


class BRG_OT_update_and_open_viewer(Operator):
    bl_idname = "brg.update_and_open_viewer"
    bl_label = "Update + Open Viewer"
    bl_description = "Update graph data and open the HTML viewer"
    bl_options = {"REGISTER"}

    def execute(self, context):
        result = bpy.ops.brg.update_graph_data()
        if "FINISHED" not in result:
            return result
        return bpy.ops.brg.open_viewer()


class BRG_OT_scan_whole_file(Operator):
    bl_idname = "brg.scan_whole_file"
    bl_label = "Scan Whole File"
    bl_description = "Scan all data blocks and references in the open blend file"
    bl_options = {"REGISTER"}

    def invoke(self, context, event):
        self._timer = None
        self._iterator = None
        self._progress_started = False
        settings = context.scene.brg_settings
        try:
            self._graph = GraphData()
            self._iterator = iter_scan(self._graph, ScanOptions(
                include_internals=settings.include_internals,
                include_bones=settings.include_bones,
                max_bones=settings.max_bones,
            ))
            self._timer = context.window_manager.event_timer_add(0.05, window=context.window)
            context.window_manager.progress_begin(0, 100)
            self._progress_started = True
            settings.scan_progress = 0.0
            settings.status_message = "Scanning Whole File"
            context.window_manager.modal_handler_add(self)
        except Exception as exc:
            try:
                settings.status_message = str(exc)
                self.report({"ERROR"}, str(exc))
            finally:
                self._cleanup(context)
            return {"CANCELLED"}
        return {"RUNNING_MODAL"}

    def _cleanup(self, context):
        try:
            if self._iterator is not None:
                self._iterator.close()
                self._iterator = None
        finally:
            try:
                if self._timer is not None:
                    context.window_manager.event_timer_remove(self._timer)
                    self._timer = None
            finally:
                if self._progress_started:
                    context.window_manager.progress_end()
                    self._progress_started = False

    def cancel(self, context):
        try:
            context.scene.brg_settings.status_message = "Cancelled"
        finally:
            self._cleanup(context)

    def modal(self, context, event):
        if event.type in {"ESC", "RIGHTMOUSE"}:
            self.cancel(context)
            return {"CANCELLED"}
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        settings = context.scene.brg_settings
        finished = False
        try:
            deadline = time.perf_counter() + 0.03
            while time.perf_counter() < deadline:
                try:
                    progress, message = next(self._iterator)
                except StopIteration:
                    self._finish(context)
                    finished = True
                    return {"FINISHED"}
                settings.scan_progress = progress * 100
                settings.status_message = message
                context.window_manager.progress_update(progress * 100)
            if context.area:
                context.area.tag_redraw()
            return {"RUNNING_MODAL"}
        except Exception as exc:
            finished = True
            settings.status_message = str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        finally:
            if finished:
                self._cleanup(context)
                if context.area:
                    context.area.tag_redraw()

    def _finish(self, context):
        settings = context.scene.brg_settings
        output_folder = resolve_output_folder(context)
        generated_at = time.strftime("%Y-%m-%d %H:%M:%S")
        meta = {
            "addon_name": "Blend Reference Graph", "version": VERSION,
            "scope": "WHOLE_FILE", "generated_at": generated_at,
            "blend_file": bpy.path.basename(bpy.data.filepath) if bpy.data.filepath else "Unsaved",
        }
        output_path, payload = export_graph_data(self._graph, meta, output_folder, compact=True)
        viewer_path = _copy_viewer_files(output_folder)
        settings.last_update = generated_at
        settings.node_count = payload["meta"]["node_count"]
        settings.edge_count = payload["meta"]["edge_count"]
        settings.scan_seconds = payload["meta"]["scan_seconds"]
        settings.scan_progress = 100.0
        settings.resolved_output_path = str(output_folder)
        settings.status_message = f"Wrote {os.path.basename(output_path)}"
        if settings.open_viewer_after_scan:
            _open_viewer(context, viewer_path)


class BRG_OT_stop_live_viewer(Operator):
    bl_idname = "brg.stop_live_viewer"
    bl_label = "Stop Live Viewer"
    bl_description = "Stop the local server and cancel any live scan"
    bl_options = {"REGISTER"}

    def execute(self, context):
        controller.stop()
        context.scene.brg_settings.status_message = "Live Viewer stopped"
        return {"FINISHED"}
