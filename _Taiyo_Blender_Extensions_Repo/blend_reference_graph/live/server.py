import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import queue
import secrets
import threading

from ..version import VERSION


STATIC_FILES = {
    "viewer.html": "text/html; charset=utf-8",
    "viewer.css": "text/css; charset=utf-8",
    "viewer.js": "text/javascript; charset=utf-8",
    "graph_data.js": "text/javascript; charset=utf-8",
    "graph_data.json": "application/json",
}
MAX_BODY = 16 * 1024


def validate_request(body):
    if not isinstance(body, dict):
        raise ValueError("Body must be a JSON object")
    if set(body) - {"scope", "node_id", "mode", "depth"}:
        raise ValueError("Unknown request fields")
    if body.get("scope") not in ("NODE", "WHOLE_FILE"):
        raise ValueError("scope must be NODE or WHOLE_FILE")
    node_id = body.get("node_id", "")
    if not isinstance(node_id, str) or (body["scope"] == "NODE" and not node_id.strip()):
        raise ValueError("node_id must be a nonempty string for NODE")
    mode = body.get("mode", "BOTH")
    if mode not in ("USES", "USED_BY", "BOTH"):
        raise ValueError("mode must be USES, USED_BY or BOTH")
    depth = body.get("depth", 1)
    if type(depth) is not int or not 1 <= depth <= 5:
        raise ValueError("depth must be an integer from 1 to 5")
    return dict(scope=body["scope"], node_id=node_id, mode=mode, depth=depth)


class LiveServer:
    def __init__(self, output_folder):
        self.output_folder = Path(output_folder).resolve()
        self.token = secrets.token_urlsafe(24)
        self.requests = queue.Queue()
        self.lock = threading.RLock()
        self.cancel_requested = False
        self.state = dict(state="idle", progress=0.0, message="Ready", request_id=0,
                          error=None, version=VERSION)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.httpd.daemon_threads = True
        self.httpd.live = self
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       kwargs={"poll_interval": 0.1}, daemon=True)
        try:
            self.thread.start()
        except Exception:
            self.httpd.server_close()
            raise

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}/{self.token}/viewer.html"

    def status(self):
        with self.lock:
            return dict(self.state)

    def update(self, **values):
        with self.lock:
            self.state.update(values)

    def submit(self, request):
        with self.lock:
            if self.state["state"] in {"queued", "running"}:
                return None
            request_id = self.state["request_id"] + 1
            self.cancel_requested = False
            self.state.update(state="queued", progress=0.0, message="Queued",
                              request_id=request_id, error=None)
            self.requests.put((request_id, request))
            return request_id

    def cancel(self):
        with self.lock:
            if self.state["state"] in {"queued", "running"}:
                self.cancel_requested = True
            return dict(self.state)

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join()


class _Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, format, *args):
        pass

    def _send(self, code, data, content_type="application/json"):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _route(self):
        live = self.server.live
        hosts = (f"127.0.0.1:{live.port}", f"localhost:{live.port}")
        if self.headers.get_all("Host", []) not in ([hosts[0]], [hosts[1]]):
            self._send(421, {"error": "Invalid Host"})
            return None
        if self.command == "POST":
            origins = self.headers.get_all("Origin", [])
            if origins not in ([], ["http://" + hosts[0]], ["http://" + hosts[1]]):
                self._send(403, {"error": "Invalid Origin"})
                return None
        prefix = f"/{live.token}/"
        # Require origin-form paths and exact filenames; never normalize traversal.
        path = self.path.split("?", 1)[0]
        if not path.startswith(prefix):
            self._send(403, {"error": "Invalid token"})
            return None
        return path[len(prefix):]

    def do_GET(self):
        route = self._route()
        if route is None:
            return
        live = self.server.live
        if route == "api/status":
            self._send(200, live.status())
        elif route in STATIC_FILES:
            try:
                with live.lock:
                    path = live.output_folder / route
                    if path.is_symlink() or path.resolve().parent != live.output_folder:
                        raise FileNotFoundError(route)
                    data = path.read_bytes()
            except OSError:
                self._send(404, {"error": "File not found"})
                return
            self._send(200, data, STATIC_FILES[route])
        else:
            self._send(404, {"error": "Not found"})

    def _body(self, allow_empty=False):
        lengths = self.headers.get_all("Content-Length", [])
        if allow_empty and not self.headers.get("Transfer-Encoding") and lengths in ([], ["0"]):
            return {}
        if self.headers.get("Transfer-Encoding") or len(lengths) != 1:
            self._send(400, {"error": "One Content-Length is required"})
            return None
        try:
            length = int(lengths[0])
            if length < 0:
                raise ValueError
        except ValueError:
            self._send(400, {"error": "Invalid Content-Length"})
            return None
        if length > MAX_BODY:
            self._send(413, {"error": "Body exceeds 16KB"})
            return None
        if self.headers.get_content_type() != "application/json":
            self._send(400, {"error": "Content-Type must be application/json"})
            return None
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError("Incomplete body")
            body = json.loads(raw)
            if body is None:
                raise ValueError("Body must be a JSON object")
            return body
        except (ValueError, UnicodeError, RecursionError, OSError):
            self._send(400, {"error": "Invalid JSON body"})
            return None

    def do_POST(self):
        route = self._route()
        if route is None:
            return
        if route not in {"api/rescan", "api/cancel"}:
            self._send(404, {"error": "Not found"})
            return
        body = self._body(allow_empty=route == "api/cancel")
        if body is None:
            return
        live = self.server.live
        if route == "api/cancel":
            if not isinstance(body, dict) or body:
                self._send(400, {"error": "Cancel body must be an empty object"})
                return
            self._send(200, live.cancel())
            return
        try:
            request = validate_request(body)
        except ValueError as exc:
            self._send(400, {"error": str(exc)})
            return
        request_id = live.submit(request)
        if request_id is None:
            self._send(409, {"error": "Scan already queued or running"})
        else:
            self._send(202, {"request_id": request_id})
