import queue
import time

import bpy
from bpy.app.handlers import persistent

from ..graph import GraphData, export_graph_data, iter_build_node_graph, resolve_output_folder
from ..graph.graph_exporter import get_addon_preferences
from ..scanner.whole_file_scanner import ScanOptions, iter_scan
from ..version import VERSION
from .server import LiveServer


_server = None
_iterator = None
_scene = None
_request = None
_started = 0.0


def enabled(context):
    return getattr(get_addon_preferences(context), "live_viewer", True)


def is_running():
    return _server is not None and _server.thread.is_alive()


def url():
    return _server.url if is_running() else ""


def start(context):
    global _server, _scene
    from ..operators import _copy_viewer_files

    folder = resolve_output_folder(context)
    if is_running() and _server.output_folder == folder.resolve() and _scene == context.scene:
        return url()
    stop()
    _copy_viewer_files(folder)
    try:
        _server = LiveServer(folder)
        _scene = context.scene
        bpy.app.timers.register(pump, first_interval=0.1, persistent=True)
        if _load_pre not in bpy.app.handlers.load_pre:
            bpy.app.handlers.load_pre.append(_load_pre)
    except Exception:
        stop()
        raise
    return url()


def _clear_scan():
    global _iterator, _request
    iterator, _iterator = _iterator, None
    _request = None
    if iterator is not None:
        iterator.close()


def stop():
    global _server, _scene
    server, _server = _server, None
    try:
        if bpy.app.timers.is_registered(pump):
            bpy.app.timers.unregister(pump)
        if _load_pre in bpy.app.handlers.load_pre:
            bpy.app.handlers.load_pre.remove(_load_pre)
        _clear_scan()
    finally:
        _scene = None
        if server is not None:
            server.close()


@persistent
def _load_pre(_dummy):
    stop()


def _redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _cancelled(server, settings):
    with server.lock:
        if not server.cancel_requested:
            return False
        _clear_scan()
        server.state.update(state="cancelled", message="Cancelled", error=None)
        settings.status_message = "Cancelled"
        return True


def _finish(server, graph, settings):
    generated_at = time.strftime("%Y-%m-%d %H:%M:%S")
    meta = {
        "addon_name": "Blend Reference Graph", "version": VERSION,
        "generated_at": generated_at,
        "blend_file": bpy.path.basename(bpy.data.filepath) if bpy.data.filepath else "Unsaved",
        "scope": _request["scope"],
        "target_id": _request["node_id"] if _request["scope"] == "NODE" else "",
        "mode": _request["mode"], "depth": _request["depth"],
        "scan_seconds": time.perf_counter() - _started,
    }
    # Serialize publication with HTTP reads and cancellation acceptance.
    with server.lock:
        if _cancelled(server, settings):
            return
        _, payload = export_graph_data(graph, meta, server.output_folder, compact=True)
        settings.last_update = generated_at
        settings.node_count = payload["meta"]["node_count"]
        settings.edge_count = payload["meta"]["edge_count"]
        settings.scan_seconds = payload["meta"]["scan_seconds"]
        settings.scan_progress = 100.0
        settings.resolved_output_path = str(server.output_folder)
        settings.status_message = "Live scan complete"
        _clear_scan()
        server.state.update(state="done", progress=1.0, message="Scan complete", error=None)


def pump():
    global _iterator, _request, _started
    server = _server
    if server is None:
        return None
    try:
        settings = _scene.brg_settings
        if _iterator is None:
            try:
                _, _request = server.requests.get_nowait()
            except queue.Empty:
                return 0.1
            if _cancelled(server, settings):
                _redraw()
                return 0.1
            _started = time.perf_counter()
            options = ScanOptions(include_internals=settings.include_internals,
                                  include_bones=settings.include_bones, max_bones=settings.max_bones)
            if _request["scope"] == "WHOLE_FILE":
                _iterator = iter_scan(GraphData(), options)
            else:
                _iterator = iter_build_node_graph(bpy.context, _request["node_id"],
                                                 _request["mode"], _request["depth"], options)
            server.update(state="running", message="Scanning")
        deadline = time.perf_counter() + 0.03
        while time.perf_counter() < deadline:
            if _cancelled(server, settings):
                break
            try:
                progress, message = next(_iterator)
            except StopIteration as result:
                _finish(server, result.value, settings)
                break
            server.update(progress=progress, message=message)
            settings.scan_progress = progress * 100
            settings.status_message = message
        _redraw()
    except Exception as exc:
        try:
            _clear_scan()
        finally:
            message = str(exc) or type(exc).__name__
            server.update(state="error", message=message, error=message)
            if _scene is not None:
                _scene.brg_settings.status_message = message
            _redraw()
    return 0.1
