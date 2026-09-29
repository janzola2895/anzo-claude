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

import datetime
import json
import mimetypes
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import brain

PORT = int(os.environ.get("ANZO_PORT", "8730"))
HOST = "127.0.0.1"
TOKEN = secrets.token_urlsafe(24)
UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
ALLOWED_ORIGIN = f"http://{HOST}:{PORT}"

BROWSER_MCP_PORT = int(os.environ.get("ANZO_BROWSER_MCP_PORT", "8931"))
CHROME_DEBUG_PORT = int(os.environ.get("ANZO_CHROME_DEBUG_PORT", "9223"))
PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".browser-profile")

# Bitacora: a running log of what's been said, summarized -- not transcribed
# raw -- so it stays short and doesn't multiply claude -p calls against the
# weekly usage limit. See record_exchange()/_summary_loop() below.
BITACORA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Anzo", "Bitacora")
IDLE_SUMMARY_GAP_S = int(os.environ.get("ANZO_IDLE_SUMMARY_GAP", "600"))
SUMMARY_CHECK_INTERVAL_S = 120

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def _find_chrome():
    found = shutil.which("chrome") or shutil.which("google-chrome")
    if found:
        return found
    for p in CHROME_PATHS:
        if os.path.isfile(p):
            return p
    return None


def start_chrome():
    """Launch Chrome ourselves, as our own long-lived process, instead of
    letting Playwright MCP launch (and therefore own) it.

    Playwright MCP's maintainer confirmed the browser's lifetime is tied to
    the MCP client CONNECTION's lifetime by design ("we rely on the
    connection-is-a-lifetime model" -- microsoft/playwright-mcp#1302): the
    browser closes whenever the connected client goes away, with no opt-out.
    Since every claude -p turn is its own short-lived client that connects
    and then disconnects when the turn ends, that meant the browser closed
    at the end of every single turn -- confirmed live, repeatedly.

    Fix: launch Chrome ourselves with a devtools port open, and have
    Playwright MCP attach to it over CDP (start_browser_mcp) instead of
    spawning its own. It doesn't own this process, so a client disconnecting
    just ends Playwright MCP's control of it, not the browser itself."""
    chrome = _find_chrome()
    if not chrome:
        print("WARNING: Chrome not found in the usual install locations — "
              "browser control will not be available. Continuing with voice-only.")
        return None
    cmd = [chrome,
           f"--remote-debugging-port={CHROME_DEBUG_PORT}",
           f"--user-data-dir={PROFILE_DIR}",
           "--no-first-run", "--no-default-browser-check"]
    proc = subprocess.Popen(cmd)
    print(f"Starting Chrome with a devtools port on {CHROME_DEBUG_PORT} "
          f"(profile: {PROFILE_DIR})")
    return proc


def start_browser_mcp():
    """Launch the Playwright MCP server as its own long-lived process, attached
    to the Chrome instance from start_chrome() via CDP rather than launching
    (and owning) its own browser."""
    npx = shutil.which("npx")
    if not npx:
        print("WARNING: npx not found — browser control will not be available "
              "(install Node.js). Continuing with voice-only.")
        return None
    cmd = [npx, "@playwright/mcp@latest",
           "--port", str(BROWSER_MCP_PORT),
           "--cdp-endpoint", f"http://localhost:{CHROME_DEBUG_PORT}"]
    # No stdout=PIPE here: nothing was reading that pipe, so its output
    # buffer would eventually fill and silently block the process (and any
    # startup error would be invisible instead of just failing loudly).
    # Inheriting the parent's console is simpler and correct for a
    # single-user local tool.
    kwargs = {}
    if sys.platform == "win32":
        kwargs["shell"] = True  # same npx.cmd-shim reason as brain.py
    proc = subprocess.Popen(cmd, **kwargs)
    print(f"Starting browser MCP server on port {BROWSER_MCP_PORT}, "
          f"attaching to Chrome via CDP — first launch downloads the package, give it a moment.")
    return proc


_exchange_lock = threading.Lock()
_pending_exchanges = []  # [(user_text, anzo_text), ...] since the last summary
_last_activity = time.monotonic()


def record_exchange(user_text: str, anzo_text: str):
    """Called once a turn completes successfully (see _handle_stream) --
    skipped for errored/interrupted turns so the summary reflects what
    actually got said, not aborted attempts."""
    global _last_activity
    anzo_text = anzo_text.strip()
    if not anzo_text:
        return
    with _exchange_lock:
        _pending_exchanges.append((user_text, anzo_text))
        _last_activity = time.monotonic()


def _write_summary(exchanges):
    summary = brain.summarize(exchanges)
    if not summary:
        return  # best-effort: a failed/empty summarize() just skips this round
    os.makedirs(BITACORA_DIR, exist_ok=True)
    today = datetime.date.today().isoformat()
    path = os.path.join(BITACORA_DIR, f"{today}.md")
    is_new = not os.path.exists(path)
    stamp = datetime.datetime.now().strftime("%H:%M")
    with open(path, "a", encoding="utf-8") as f:
        if is_new:
            f.write(f"# {today}\n\n")
        f.write(f"## {stamp}\n\n{summary}\n\n")


def _maybe_flush_summary(force=False):
    with _exchange_lock:
        if not _pending_exchanges:
            return
        if not force and (time.monotonic() - _last_activity) < IDLE_SUMMARY_GAP_S:
            return
        exchanges = list(_pending_exchanges)
        _pending_exchanges.clear()
    _write_summary(exchanges)


def _summary_loop():
    while True:
        time.sleep(SUMMARY_CHECK_INTERVAL_S)
        _maybe_flush_summary()


class Server(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        # A browser tab closing or navigating away mid-request (an SSE
        # stream in particular) aborts the connection from the client side
        # -- normal and frequent, not a bug. socketserver's default
        # handle_error prints a full traceback for it; only do that for
        # exceptions that aren't just "the other side hung up".
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


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

        reply_parts = []
        try:
            for ev in brain.run(message, session_id):
                line = f"data: {json.dumps(ev)}\n\n".encode("utf-8")
                self.wfile.write(line)
                self.wfile.flush()
                if ev.get("t") == "delta":
                    reply_parts.append(ev.get("text") or "")
                elif ev.get("t") == "complete":
                    record_exchange(message, "".join(reply_parts))
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


def _stop(proc, name):
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _wait_for_port(port, timeout_s, label):
    """Poll until something accepts a TCP connection on this port, or give
    up after timeout_s. Replaces a fixed time.sleep(2) that assumed
    Chrome's devtools port (and, worse, Playwright MCP -- launched via
    `npx @playwright/mcp@latest`, which can take much longer than 2s if it
    needs to check for or download the package) would always be ready by
    then. Confirmed live: it wasn't always, and the browser tool reported
    "not connected" on the very first command after startup.

    Tries both 127.0.0.1 and localhost, not just HOST (127.0.0.1): also
    confirmed live, Playwright MCP's own startup banner ("Listening on
    http://localhost:8931") had already printed while a 127.0.0.1-only
    check here kept failing to connect, so this sat out the full
    timeout every time before falling through and continuing anyway --
    it worked, but only after needlessly waiting the whole budget. On
    this machine plain 127.0.0.1 and localhost apparently don't resolve
    to the same thing for a fresh Node listener; trying both is cheap
    and avoids needing to know which one will actually work."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for h in ("127.0.0.1", "localhost"):
            try:
                with socket.create_connection((h, port), timeout=1):
                    return True
            except OSError:
                continue
        time.sleep(0.3)
    print(f"WARNING: {label} (port {port}) didn't respond within {timeout_s}s -- "
          f"continuing anyway, but the browser tool may not work yet.")
    return False


def main():
    chrome_proc = start_chrome()
    if chrome_proc:
        print("Esperando a que el puerto de depuracion de Chrome responda...")
        _wait_for_port(CHROME_DEBUG_PORT, 20, "Chrome devtools")
    browser_mcp_proc = start_browser_mcp() if chrome_proc else None
    if browser_mcp_proc:
        print("Esperando a que el servidor de Playwright MCP responda "
              "(la primera vez puede tardar mientras npx descarga el paquete)...")
        _wait_for_port(BROWSER_MCP_PORT, 60, "Playwright MCP")
    threading.Thread(target=_summary_loop, daemon=True).start()

    # ThreadingHTTPServer's constructor already binds and listens, so the
    # page is reachable immediately even though serve_forever() hasn't
    # started accepting connections yet.
    server = Server((HOST, PORT), Handler)
    print(f"ANZO listening on http://{HOST}:{PORT}")
    print(f"(token is embedded in the served page automatically)")

    # Opens in the OS's default browser -- NOT the dedicated automation
    # Chrome instance from start_chrome(), which is a separate profile/
    # process reserved for Playwright to drive Power Apps/Automate in.
    # Loading this page in that same automation window was the actual
    # cause of "it stopped listening after I said open PowerApps": Claude
    # navigated the only tab that instance had open, which happened to be
    # this one, out from under its own running voice UI.
    webbrowser.open(f"http://{HOST}:{PORT}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        _stop(browser_mcp_proc, "browser MCP")
        _stop(chrome_proc, "Chrome")
        _maybe_flush_summary(force=True)


if __name__ == "__main__":
    main()
