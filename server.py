"""
ANZO's local server: bridges the browser UI to brain.py.

Stdlib only, on purpose — no pip installs to keep in sync between this
machine and any other one this runs on. Binds to 127.0.0.1 only.

Endpoints:
  GET  /                          -> ui/index.html (token injected)
  GET  /app.js, /style.css        -> static files
  GET  /api/stream?token&message&session_id   -> Server-Sent Events,
        one line per brain.run() event, closes on "complete"/"error"/"interrupted"
  POST /api/interrupt  (header X-Anzo-Token)  -> brain.cancel_active()

A random per-launch token gates every request (EventSource can't send
custom headers, so the stream endpoint takes it as a query param instead;
POST /api/interrupt uses a header since fetch() supports one). Combined
with the 127.0.0.1 bind, this keeps it usable only from this machine's
own browser tab.
"""
from __future__ import annotations

import json
import mimetypes
import os
import secrets
import shutil
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import brain

PORT = int(os.environ.get("ANZO_PORT", "8730"))
HOST = "127.0.0.1"
TOKEN = secrets.token_urlsafe(24)
UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
ALLOWED_ORIGIN = f"http://{HOST}:{PORT}"

BROWSER_MCP_PORT = int(os.environ.get("ANZO_BROWSER_MCP_PORT", "8931"))
PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".browser-profile")


def start_browser_mcp():
    """Launch the Playwright MCP server as its own long-lived process, separate
    from any single `claude -p` turn. Each turn is a short-lived client that
    connects to this over HTTP (see mcp-config.json's "url") and disconnects
    when the turn ends — the browser and its login session live as long as
    THIS process does, not as long as the turn that happened to use it.
    Without this, the browser window closes the instant each turn's `claude -p`
    process exits, since it would otherwise be spawned as that process's own
    stdio child."""
    npx = shutil.which("npx")
    if not npx:
        print("WARNING: npx not found — browser control will not be available "
              "(install Node.js). Continuing with voice-only.")
        return None
    cmd = [npx, "@playwright/mcp@latest",
           "--port", str(BROWSER_MCP_PORT),
           "--user-data-dir", PROFILE_DIR,
           "--browser", "chrome"]
    kwargs = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if sys.platform == "win32":
        kwargs["shell"] = True  # same npx.cmd-shim reason as brain.py
    proc = subprocess.Popen(cmd, **kwargs)
    print(f"Starting browser MCP server on port {BROWSER_MCP_PORT} "
          f"(profile: {PROFILE_DIR}) — first launch downloads the package, give it a moment.")
    return proc


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("[server] " + (fmt % args) + "\n")

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        # No Origin header at all means a same-machine, non-browser caller
        # (curl, our own tooling) rather than a forged browser request.
        return origin is None or origin == ALLOWED_ORIGIN

    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: str, content_type: str):
        if not os.path.isfile(path):
            self._send_json(404, {"error": "not found"})
            return
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            index_path = os.path.join(UI_DIR, "index.html")
            if not os.path.isfile(index_path):
                self._send_json(404, {"error": "ui/index.html missing"})
                return
            with open(index_path, "r", encoding="utf-8") as f:
                html = f.read().replace("__ANZO_TOKEN__", TOKEN)
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/stream":
            self._handle_stream(parsed)
            return

        # Static files under ui/ (app.js, style.css, ...).
        safe_name = os.path.basename(parsed.path)
        static_path = os.path.join(UI_DIR, safe_name)
        if os.path.commonpath([os.path.abspath(static_path), UI_DIR]) == UI_DIR and safe_name:
            ctype, _ = mimetypes.guess_type(static_path)
            self._send_file(static_path, ctype or "application/octet-stream")
            return

        self._send_json(404, {"error": "not found"})

    def _handle_stream(self, parsed):
        qs = parse_qs(parsed.query)
        if not self._origin_ok() or qs.get("token", [""])[0] != TOKEN:
            self._send_json(403, {"error": "forbidden"})
            return
        message = qs.get("message", [""])[0]
        session_id = qs.get("session_id", [""])[0] or None
        if not message.strip():
            self._send_json(400, {"error": "empty message"})
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        try:
            for ev in brain.run(message, session_id):
                line = f"data: {json.dumps(ev)}\n\n".encode("utf-8")
                self.wfile.write(line)
                self.wfile.flush()
                if ev.get("t") in ("complete", "error", "interrupted"):
                    break
        except (BrokenPipeError, ConnectionAbortedError):
            # Browser navigated away / closed the tab mid-stream. Not our problem;
            # brain.run()'s own generator cleanup already terminates the subprocess.
            pass

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/interrupt":
            self._send_json(404, {"error": "not found"})
            return
        if not self._origin_ok() or self.headers.get("X-Anzo-Token") != TOKEN:
            self._send_json(403, {"error": "forbidden"})
            return
        cancelled = brain.cancel_active()
        self._send_json(200, {"cancelled": cancelled})


def main():
    browser_proc = start_browser_mcp()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"ANZO listening on http://{HOST}:{PORT}")
    print(f"(token is embedded in the served page automatically)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if browser_proc and browser_proc.poll() is None:
            browser_proc.terminate()
            try:
                browser_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                browser_proc.kill()


if __name__ == "__main__":
    main()
