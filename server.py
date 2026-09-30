"""
ANZO + Claude's local server: bridges the browser UI to brain.py.

Stdlib only, on purpose -- no pip installs to keep in sync between this
machine and any other one this runs on. Binds to 127.0.0.1 only.

Endpoints:
  GET  /                          -> ui/index.html (token injected)
  GET  /app.js, /style.css        -> static files
  GET  /api/stream?token&message&session_id   -> Server-Sent Events,
        one line per brain.run() event, closes on "complete"/"error"/"interrupted"
  GET  /api/ready?token           -> startup progress for the window
  GET  /api/model?token           -> which Claude model answered the last turn
  POST /api/interrupt  (header X-Anzo-Token)  -> brain.cancel_active()

A random per-launch token gates every request (EventSource can't send
custom headers, so the stream endpoint takes it as a query param instead;
POST /api/interrupt uses a header since fetch() supports one). Combined
with the 127.0.0.1 bind, this keeps it usable only from this machine's
own browser tab.

Unlike the original ANZO (C:\\dev\\anzo), this version starts no browser
automation of its own: Claude drives the user's everyday Chrome through the
Claude in Chrome extension, and there is no router. The server only makes sure
that Chrome is running, because the extension lives in it.
"""
from __future__ import annotations

import datetime
import json
import mimetypes
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


def _load_dotenv(path):
    """Minimal KEY=VALUE loader (stdlib only). Real environment variables win
    over the file, so a value set in a terminal still overrides it. Needed
    because a double-clicked launcher doesn't inherit variables that were only
    ever `set` in some terminal session."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


# Must run before `import brain`: brain reads ANZO_* at import time.
_load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

import brain

# Not 8730: that's the original ANZO's port. Both can be installed side by
# side, and a busy port makes main() open a window onto whatever is running
# there -- it must never be the other version.
PORT = int(os.environ.get("ANZO_PORT", "8740"))
HOST = "127.0.0.1"
TOKEN = secrets.token_urlsafe(24)
UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
ALLOWED_ORIGIN = f"http://{HOST}:{PORT}"

# Separate Chrome profile for ANZO's own app window (mic permission, etc.), so
# the voice UI never lives inside the user's everyday Chrome, where Claude works.
UI_PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".ui-profile")
# app (default): Chrome --app window, no tabs/address bar. browser: default
# browser tab. none: don't open anything.
UI_MODE = os.environ.get("ANZO_UI", "app").strip().lower()

# The user's everyday Chrome, where the Claude in Chrome extension is installed
# (profile "Default" on this machine).
CHROME_USER_DATA = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data")
CHROME_PROFILE = os.environ.get("ANZO_CHROME_PROFILE", "Default").strip() or "Default"

# Shared with the UI through /api/ready so the window can open immediately and
# show startup progress.
_boot_state = {"ready": False, "step": "Iniciando…"}

# Bitacora: a running log of what's been said, summarized -- not transcribed
# raw -- so it stays short and doesn't multiply claude -p calls against the
# membership's limits. See record_exchange()/_summary_loop() below.
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


def user_chrome_running() -> bool:
    """Is the user's everyday Chrome open? While it runs, Chrome keeps the
    `lockfile` in its user-data folder open exclusively, so trying to open it
    fails; once Chrome exits the file is gone or openable. Instant, and it
    ignores ANZO's own app window (that one uses its own --user-data-dir)."""
    lock = os.path.join(CHROME_USER_DATA, "lockfile")
    try:
        fd = os.open(lock, os.O_RDWR)
    except FileNotFoundError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    os.close(fd)
    return False


_chrome_lock = threading.Lock()


def ensure_user_chrome():
    """Open the user's everyday Chrome if it's closed: the Claude in Chrome
    extension only exists while it runs. Never closes or restarts it -- it's
    the user's own browser. Returns an error message, or None when it's up."""
    if os.environ.get("ANZO_NO_AUTOMATION") == "1":  # UI-only testing
        return None
    with _chrome_lock:
        if user_chrome_running():
            return None
        chrome = _find_chrome()
        if not chrome:
            return "No encontre Chrome instalado."
        print(f"Chrome no esta abierto; abriendolo (perfil {CHROME_PROFILE}).")
        subprocess.Popen([chrome, f"--profile-directory={CHROME_PROFILE}"],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not user_chrome_running():
            time.sleep(0.3)
        if not user_chrome_running():
            return "Chrome no termino de abrir."
        # Give the extension's service worker a moment to come up.
        time.sleep(3)
        return None


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


# Model the CLI reported for the latest turn, shown in the window. Always the
# user's own Claude membership in this version.
_last_turn = {"model": "", "ok": None}


def current_backend():
    if not _last_turn["model"]:
        return None
    ok = _last_turn["ok"] is not False
    return {"model": _last_turn["model"], "provider": "Claude",
            "ok": ok, "status": 200 if ok else 0}


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

    def _token_ok(self, parsed) -> bool:
        qs = parse_qs(parsed.query)
        return self._origin_ok() and qs.get("token", [""])[0] == TOKEN

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

        if parsed.path == "/api/model":
            if not self._token_ok(parsed):
                self._send_json(403, {"error": "forbidden"})
                return
            self._send_json(200, {"backend": current_backend()})
            return

        if parsed.path == "/api/ready":
            if not self._token_ok(parsed):
                self._send_json(403, {"error": "forbidden"})
                return
            self._send_json(200, dict(_boot_state))
            return

        # Static files under ui/ (app.js, style.css, ...).
        safe_name = os.path.basename(parsed.path)
        static_path = os.path.join(UI_DIR, safe_name)
        if os.path.commonpath([os.path.abspath(static_path), UI_DIR]) == UI_DIR and safe_name:
            ctype, _ = mimetypes.guess_type(static_path)
            self._send_file(static_path, ctype or "application/octet-stream")
            return

        self._send_json(404, {"error": "not found"})

    def _sse(self, ev):
        self.wfile.write(f"data: {json.dumps(ev)}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _handle_stream(self, parsed):
        qs = parse_qs(parsed.query)
        if not self._token_ok(parsed):
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
            # The user may have closed Chrome since the last turn; the
            # extension goes with it, so reopen it before Claude needs it.
            if _boot_state.get("ready") and not user_chrome_running():
                self._sse({"t": "warning", "message": "Abriendo Chrome…"})
                problem = ensure_user_chrome()
                if problem:
                    self._sse({"t": "warning", "message": problem})
            for ev in brain.run(message, session_id):
                self._sse(ev)
                t = ev.get("t")
                if t == "status" and ev.get("model"):
                    _last_turn.update(model=ev["model"], ok=None)
                elif t == "delta":
                    reply_parts.append(ev.get("text") or "")
                elif t == "complete":
                    _last_turn["ok"] = True
                    record_exchange(message, "".join(reply_parts))
                elif t == "error":
                    _last_turn["ok"] = False
                if t in ("complete", "error", "interrupted"):
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


def open_ui():
    """Open ANZO's window. Returns the process to wait on (app mode) or None.

    App mode = Chrome's --app window: no tabs, no address bar, its own profile.
    It has to be Chrome (not Edge/WebView): the voice UI relies on Chrome's
    Web Speech API. Kept out of the user's everyday Chrome on purpose, so
    Claude working there can never navigate the voice UI away."""
    url = f"http://{HOST}:{PORT}"
    if UI_MODE == "none":
        return None
    chrome = _find_chrome()
    if UI_MODE == "app" and chrome:
        return subprocess.Popen([
            chrome, f"--app={url}", f"--user-data-dir={UI_PROFILE_DIR}",
            "--window-size=460,740", "--no-first-run", "--no-default-browser-check",
        ])
    webbrowser.open(url)
    return None


def _boot():
    """Startup work that can take a few seconds, in a background thread so the
    window is already open meanwhile."""
    try:
        _boot_state["step"] = "Revisando Chrome…"
        problem = ensure_user_chrome()
        if problem:
            print(f"AVISO: {problem}")
    except Exception as e:  # never leave the UI stuck on "Iniciando"
        print(f"ERROR durante el arranque: {e!r}")
    finally:
        _boot_state.update(ready=True, step="")


def main():
    try:
        server = Server((HOST, PORT), Handler)
    except OSError:
        # Port taken: ANZO + Claude is already running. Its page injects the
        # token on each GET /, so just open a window onto it instead of
        # starting a second copy.
        print(f"ANZO + Claude ya esta corriendo en el puerto {PORT}; abriendo su ventana.")
        open_ui()
        return

    print(f"ANZO + Claude listening on http://{HOST}:{PORT}")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=_summary_loop, daemon=True).start()
    threading.Thread(target=_boot, daemon=True).start()

    ui_proc = open_ui()
    started = time.monotonic()
    try:
        if ui_proc:
            # Closing the window quits ANZO. The user's Chrome stays open:
            # it's their browser, not ours.
            ui_proc.wait()
            if time.monotonic() - started < 3:
                # Chrome handed the window to an already-running instance of
                # this profile and exited; we can't tell when it closes, so
                # keep serving until Ctrl+C / the process is killed.
                threading.Event().wait()
        else:
            threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        _maybe_flush_summary(force=True)


if __name__ == "__main__":
    main()
