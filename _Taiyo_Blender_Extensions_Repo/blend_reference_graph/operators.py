import os
import shutil
import time
import webbrowser
from pathlib import Path

import bpy
from bpy.types import Operator

from .graph import build_graph, export_graph_data, resolve_output_folder


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


def _set_active_target(context, settings):
    obj = context.object
    if obj and context.mode == "POSE" and context.active_pose_bone:
        bone = context.active_pose_bone
        settings.target_type = "BONE"
        settings.target_name = f"{obj.name} / {bone.name}"
        settings.target_id = f"Bone:{obj.name}:{bone.name}"
        return True
    if obj:
        settings.target_type = "OBJECT"
        settings.target_name = obj.name
        settings.target_id = f"Object:{obj.name}"
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
                "version": "0.1.2",
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
        except (OSError, ValueError) as exc:
            settings.status_message = str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        webbrowser.open(Path(viewer_path).resolve().as_uri())
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
