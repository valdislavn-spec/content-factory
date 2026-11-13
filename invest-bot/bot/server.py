from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

log = logging.getLogger(__name__)


class StatusHandler(BaseHTTPRequestHandler):
    engine = None
    token = ""

    def _authorized(self) -> bool:
        if not self.token:
            return True
        header = self.headers.get("X-Api-Token", "")
        query = parse_qs(urlparse(self.path).query).get("token", [""])[0]
        return header == self.token or query == self.token

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/health", "/healthz"}:
            self._json(200, {"ok": True})
            return
        if not self._authorized():
            self._json(401, {"ok": False, "error": "unauthorized"})
            return
        if path == "/status":
            self._json(200, {"ok": True, "data": self.engine.status()})
            return
        if path == "/trades":
            q = parse_qs(urlparse(self.path).query)
            limit = int(q.get("limit", ["50"])[0])
            self._json(200, {"ok": True, "data": self.engine.broker.trades(limit=limit)})
            return
        if path in {"/", "/index.html"}:
            body = (
                "<html><body><h2>Content Factory invest bot</h2>"
                "<p>Paper-trading intraday bot for MOEX stocks.</p>"
                "<ul><li><a href='/status'>/status</a></li>"
                "<li><a href='/trades'>/trades</a></li>"
                "<li><a href='/health'>/health</a></li></ul></body></html>"
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._json(404, {"ok": False, "error": "not found"})

    def log_message(self, fmt: str, *args) -> None:
        log.debug("%s - %s", self.address_string(), fmt % args)


def start_server(engine, port: int, token: str = "") -> ThreadingHTTPServer:
    handler = type("Handler", (StatusHandler,), {"engine": engine, "token": token})
    server = ThreadingHTTPServer(("0.0.0.0", port), handler)
    thread = threading.Thread(target=server.serve_forever, name="status-server", daemon=True)
    thread.start()
    log.info("status server listening on :%s", port)
    return server
