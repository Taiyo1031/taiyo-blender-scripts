from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest import mock

sys.dont_write_bytecode = True
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "_Taiyo_Blender_Extensions_Repo"))
import blend_reference_graph as addon
from blend_reference_graph import operators
from blend_reference_graph.live import controller
from blend_reference_graph.version import VERSION


class Client:
    def __init__(self, server, pool):
        self.server = server
        self.pool = pool

    def _http(self, method, route, body=None, headers=None, raw=None, path=None):
        assert threading.current_thread() is not threading.main_thread()
        connection = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=5)
        data = raw if raw is not None else json.dumps(body).encode() if body is not None else None
        request_headers = {"Content-Type": "application/json"}
        request_headers.update(headers or {})
        try:
            connection.request(method, path or f"/{self.server.token}/{route}", data, request_headers)
            response = connection.getresponse()
            result = response.status, response.read(), dict(response.getheaders())
            assert result[2]["Cache-Control"] == "no-store"
            return result
        finally:
            connection.close()

    def http(self, method, route, body=None, **kwargs):
        return self.pool.submit(self._http, method, route, body, **kwargs).result(timeout=10)

    def json(self, method, route, body=None, expected=200, **kwargs):
        status, raw, headers = self.http(method, route, body, **kwargs)
        assert status == expected, (status, raw)
        assert headers["Content-Type"] == "application/json"
        return json.loads(raw)

    def rescan(self, scope="NODE", node_id="Object:LiveObject", **kwargs):
        return self.json("POST", "api/rescan", dict(scope=scope, node_id=node_id,
                         mode="BOTH", depth=2), expected=202, **kwargs)["request_id"]

    def wait(self, expected="done"):
        def poll():
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                code, raw, _ = self._http("GET", "api/status")
                assert code == 200
                state = json.loads(raw)
                assert 0 <= state["progress"] <= 1
                if state["state"] in {"done", "error", "cancelled"}:
                    assert state["state"] == expected, state
                    return state
                time.sleep(0.005)
            raise AssertionError("HTTP status timeout")

        future = self.pool.submit(poll)
        deadline = time.monotonic() + 25
        while not future.done() and time.monotonic() < deadline:
            assert controller.pump() == 0.1
            time.sleep(0.001)
        return future.result(timeout=1)


def fixture():
    mesh = bpy.data.meshes.new("LiveMesh")
    material = bpy.data.materials.new("LiveMaterial")
    mesh.materials.append(material)
    obj = bpy.data.objects.new("LiveObject", mesh)
    bpy.context.scene.collection.objects.link(obj)
    assert obj.name == "LiveObject" and material.name == "LiveMaterial"
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)


def security(client, folder):
    state = client.json("GET", "api/status")
    assert state == dict(state="idle", progress=0.0, message="Ready", request_id=0,
                         error=None, version=VERSION)
    assert client.server.httpd.socket.getsockname() == ("127.0.0.1", client.server.port)
    assert client.server.thread.daemon and client.server.httpd.daemon_threads
    client.json("GET", "api/status", path="/wrong/api/status", expected=403)
    client.json("GET", "api/status", headers={"Host": "attacker.test"}, expected=421)
    for origin in ("https://attacker.test", "null", "http://127.0.0.1:1"):
        client.json("POST", "api/rescan", {}, headers={"Origin": origin}, expected=403)
    client.json("GET", "api/status", headers={"Host": f"localhost:{client.server.port}"})
    for route in ("private.txt", "../viewer.html", "%2e%2e/viewer.html", "x/../viewer.html",
                  "viewer.html/", "", "api/unknown"):
        client.json("GET", route, expected=404)
    (folder / "private.txt").write_text("secret")
    for filename in ("viewer.html", "viewer.css", "viewer.js"):
        status, body, _ = client.http("GET", filename)
        assert status == 200 and body == (folder / filename).read_bytes()
    client.json("POST", "api/rescan", raw=b"x" * (16 * 1024 + 1), expected=413)
    for raw in (b"{", b"null", b"[]", b"false", b"\xff"):
        error = client.json("POST", "api/rescan", raw=raw, expected=400)
        assert error["error"]
    for body in ({}, {"scope": "BAD"}, {"scope": []}, {"scope": "NODE"},
                 {"scope": "NODE", "node_id": 123}, {"scope": "WHOLE_FILE", "depth": True},
                 {"scope": "WHOLE_FILE", "depth": 0}, {"scope": "WHOLE_FILE", "depth": 6},
                 {"scope": "WHOLE_FILE", "depth": 1.5}, {"scope": "WHOLE_FILE", "mode": []},
                 {"scope": "WHOLE_FILE", "other": 1}):
        assert client.json("POST", "api/rescan", body, expected=400)["error"]
    client.json("POST", "api/rescan", {}, headers={"Content-Type": "text/plain"}, expected=400)
    client.json("POST", "api/rescan", {}, headers={"Content-Length": "-1"}, expected=400)
    client.json("POST", "api/rescan", {}, headers={"Transfer-Encoding": "chunked"}, expected=400)
    assert client.json("GET", "api/status")["request_id"] == 0
    print("PASS: loopback binding, static allowlist and HTTP validation")


def scans(client, folder):
    last_id = 0
    for scope, node_id in (("NODE", "Object:LiveObject"), ("NODE", "Material:LiveMaterial"),
                           ("WHOLE_FILE", "")):
        request_id = client.rescan(scope, node_id,
                                  headers={"Origin": f"http://localhost:{client.server.port}"})
        assert request_id == last_id + 1
        last_id = request_id
        assert client.json("GET", "api/status")["state"] == "queued"
        client.json("POST", "api/rescan", {"scope": "WHOLE_FILE"}, expected=409)
        state = client.wait()
        assert state["request_id"] == request_id and state["progress"] == 1 and state["error"] is None
        code, raw, _ = client.http("GET", "graph_data.js")
        assert code == 200 and len(raw.splitlines()) == 1
        payload = json.loads(raw.decode().removeprefix("window.BRG_GRAPH_DATA = ").removesuffix(";\n"))
        assert payload == client.json("GET", "graph_data.json")
        assert payload["meta"]["scope"] == scope and payload["meta"]["target_id"] == node_id
        assert payload["meta"]["version"] == VERSION
        assert payload["meta"]["scan_seconds"] >= 0
        ids = {node["id"] for node in payload["nodes"]}
        assert (node_id in ids) if node_id else ("Object:LiveObject" in ids)
        assert bpy.context.scene.brg_settings.node_count == len(ids)
    before = (folder / "graph_data.js").read_bytes()
    client.rescan(node_id="Object:MissingLiveObject")
    state = client.wait("error")
    assert state["error"] == state["message"] == "Node not found: Object:MissingLiveObject"
    assert (folder / "graph_data.js").read_bytes() == before
    with mock.patch.object(controller, "export_graph_data", side_effect=OSError("Test write failure")):
        client.rescan()
        state = client.wait("error")
        assert state["error"] == "Test write failure"
    client.rescan()
    client.wait()
    print("PASS: Object, Material, Whole File, errors and recovery")


def cancellation(client, folder):
    before = {name: (folder / name).read_bytes() for name in ("graph_data.js", "graph_data.json")}
    client.rescan()
    client.json("POST", "api/cancel")
    client.wait("cancelled")
    assert controller._iterator is None
    closed = []

    def slow_scan(*args):
        try:
            while True:
                time.sleep(0.035)
                yield 0.25, "Test running scan"
        finally:
            closed.append(True)

    with mock.patch.object(controller, "iter_build_node_graph", side_effect=slow_scan):
        client.rescan()
        controller.pump()
        assert client.json("GET", "api/status")["state"] == "running"
        client.json("POST", "api/rescan", {"scope": "WHOLE_FILE"}, expected=409)
        client.json("POST", "api/cancel", {})
        client.wait("cancelled")
    assert closed == [True] and controller._iterator is None
    for name, raw in before.items():
        assert (folder / name).read_bytes() == raw
    client.rescan()
    client.wait()
    print("PASS: queued/running conflicts, cancellation and preserved exports")


def assert_closed(server):
    assert not server.thread.is_alive()
    try:
        with socket.create_connection(("127.0.0.1", server.port), timeout=1):
            raise AssertionError("Stopped server still accepts connections")
    except OSError:
        pass
    assert not controller.is_running() and controller.url() == ""
    assert not bpy.app.timers.is_registered(controller.pump)
    assert controller._load_pre not in bpy.app.handlers.load_pre
    assert controller.pump() is None


def lifecycle(folder, pool):
    previous = controller._server
    assert controller.start(bpy.context) == previous.url
    assert controller._server is previous
    assert bpy.app.timers.is_registered(controller.pump)
    assert bpy.app.handlers.load_pre.count(controller._load_pre) == 1
    assert bpy.ops.brg.stop_live_viewer() == {"FINISHED"}
    assert_closed(previous)
    # Reserve the old port so the OS cannot immediately reassign it.
    with socket.socket() as reservation:
        reservation.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        reservation.bind(("127.0.0.1", previous.port))
        reservation.listen()
        controller.start(bpy.context)
    current = controller._server
    assert current.port != previous.port and current.token != previous.token
    Client(current, pool).json("GET", "api/status", path=f"/{previous.token}/api/status", expected=403)
    controller._load_pre(None)
    assert_closed(current)
    with mock.patch.object(operators.webbrowser, "open") as browser, \
            mock.patch.object(operators, "resolve_output_folder", return_value=folder):
        assert bpy.ops.brg.open_viewer() == {"FINISHED"}
        browser.assert_called_with(controller.url())
        assert bpy.ops.brg.update_and_open_viewer() == {"FINISHED"}
        browser.assert_called_with(controller.url())
        with mock.patch.object(controller, "enabled", return_value=False):
            assert bpy.ops.brg.open_viewer() == {"FINISHED"}
            browser.assert_called_with((folder / "viewer.html").resolve().as_uri())
            assert not controller.is_running()
    controller.start(bpy.context)
    server = controller._server
    addon.unregister()
    assert_closed(server)
    addon.register()
    assert not controller.is_running()
    print("PASS: operators, file URL fallback, restart, load_pre and unregister")


def main():
    addon.register()
    try:
        fixture()
        with tempfile.TemporaryDirectory() as temporary, ThreadPoolExecutor(max_workers=2) as pool:
            folder = Path(temporary)
            with mock.patch.object(controller, "resolve_output_folder", return_value=folder):
                try:
                    assert controller.enabled(bpy.context)
                    controller.start(bpy.context)
                    client = Client(controller._server, pool)
                    security(client, folder)
                    scans(client, folder)
                    cancellation(client, folder)
                    lifecycle(folder, pool)
                finally:
                    controller.stop()
        print("Blend Reference Graph Live Server integration tests passed")
    finally:
        addon.unregister()


main()
