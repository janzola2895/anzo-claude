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

import contextlib
import datetime
import json
import mimetypes
import os
import secrets
import shutil
import socket
import sqlite3
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

PORT = int(os.environ.get("ANZO_PORT", "8730"))
HOST = "127.0.0.1"
TOKEN = secrets.token_urlsafe(24)
UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
ALLOWED_ORIGIN = f"http://{HOST}:{PORT}"

BROWSER_MCP_PORT = int(os.environ.get("ANZO_BROWSER_MCP_PORT", "8931"))
CHROME_DEBUG_PORT = int(os.environ.get("ANZO_CHROME_DEBUG_PORT", "9223"))
PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".browser-profile")
# Separate Chrome profile for ANZO's own app window (mic permission, etc.), so
# it never mixes with the automation Chrome above or the user's daily browser.
UI_PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".ui-profile")
# app (default): Chrome --app window, no tabs/address bar. browser: default
# browser tab (old behavior). none: don't open anything.
UI_MODE = os.environ.get("ANZO_UI", "app").strip().lower()

# Shared with the UI through /api/ready so the window can open immediately and
# show startup progress instead of the user staring at nothing for ~30s.
_boot_state = {"ready": False, "step": "Iniciando…"}

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


def _clean_console_logs():
    """Playwright MCP also drops a console-<timestamp>.log into its output dir
    for every client session (one per ANZO turn). Those would pile up in the
    user's desktop folder, so remove them at startup and shutdown. Only files
    matching that exact pattern are touched."""
    import glob
    for f in glob.glob(os.path.join(brain.OUTPUT_DIR, "console-*.log")):
        try:
            os.remove(f)
        except OSError:
            pass


def start_browser_mcp():
    """Launch the Playwright MCP server as its own long-lived process, attached
    to the Chrome instance from start_chrome() via CDP rather than launching
    (and owning) its own browser."""
    npx = shutil.which("npx")
    if not npx:
        print("WARNING: npx not found — browser control will not be available "
              "(install Node.js). Continuing with voice-only.")
        return None
    os.makedirs(brain.OUTPUT_DIR, exist_ok=True)
    _clean_console_logs()
    cmd = [npx, "@playwright/mcp@latest",
           "--port", str(BROWSER_MCP_PORT),
           # Its only extra allowed root, so screenshots can land in the
           # user's "ANZO archivos" desktop folder (see brain.OUTPUT_DIR).
           "--output-dir", brain.OUTPUT_DIR,
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


# `ccr start` daemonizes: the service and its gateway child outlive the command.
# On Windows the gateway child is killed with exit 0xC000013A (a console
# control event) if the console `ccr start` ran in disappears -- which is what
# happens when ANZO is launched without a terminal (pythonw / desktop
# shortcut): the console dies as soon as the command returns and takes the
# gateway with it, leaving a router that accepts requests and answers 502
# "Core gateway auth token is not initialized". CREATE_NO_WINDOW gives the
# command a hidden console that lives as long as the daemon, so it survives.
_CCR_KWARGS = {"creationflags": 0x08000000, "shell": True} if sys.platform == "win32" else {}


def _ccr(*args, timeout=60):
    ccr = shutil.which("ccr")
    if not ccr:
        return None
    return subprocess.run([ccr, *args], timeout=timeout, capture_output=True, **_CCR_KWARGS)


def start_router():
    """(Re)start claude-code-router's background service (gateway on :3456)
    when ANZO_ROUTER is fallback/always. Always `stop` first: reusing whatever
    daemon was left over from an earlier run is how the gateway ended up half
    dead. Providers, keys and routing rules are configured once in CCR's own UI
    (`ccr ui`), never stored in this repo."""
    if brain.ROUTER_MODE == "off":
        return False
    if not shutil.which("ccr"):
        print("WARNING: ANZO_ROUTER esta activo pero no encuentro `ccr` en PATH. "
              "Instalalo con 'npm install -g @musistudio/claude-code-router' "
              "(Node 22+). Sin router, Anzo sigue solo con la suscripcion.")
        return False
    try:
        _ccr("stop", timeout=30)
        _ccr("start", "--no-open", timeout=60)
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"WARNING: `ccr start` fallo: {e}")
        return False
    print(f"claude-code-router iniciado (modo {brain.ROUTER_MODE}), "
          f"gateway en {brain.ROUTER_URL}")
    return True


def stop_router():
    """Counterpart of start_router(): stop the service when ANZO closes, so
    the next launch starts from a clean state instead of adopting a stale one."""
    if brain.ROUTER_MODE == "off" or not _boot_state.get("router_started"):
        return
    try:
        _ccr("stop", timeout=30)
        print("claude-code-router detenido.")
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"WARNING: `ccr stop` fallo: {e}")


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


CCR_LOG_DB = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                          "claude-code-router", "request-logs.sqlite")
# A log row older than this no longer says what's answering *now*.
MODEL_FRESH_S = 30 * 60
_PROVIDER_NAMES = {"google-gemini": "Google Gemini", "codex-api": "Codex",
                   "ovh-sin-registro": "OVH"}
_model_cache = {"at": 0.0, "value": None}
# Which backend the latest turn went to (brain yields {t: "backend"}) and what
# the CLI reported. The router's log can't see subscription turns, so for those
# this is the only source.
_last_turn = {"kind": None, "model": "", "ok": None}


def current_backend():
    """What model is actually answering, per claude-code-router's own request
    log (read-only). The claude CLI only knows the alias it asked for (e.g.
    "Codex API/gpt-5.6-terra"); the router rewrites it and may fall back to
    another provider, so the log's resolved model is the real answer. Returns
    None when the router has no recent traffic (UI then falls back to the model
    the CLI itself reported)."""
    if _last_turn["kind"] == "subscription":
        return {"model": _last_turn["model"] or "Claude",
                "provider": "Claude (membresía)",
                "ok": _last_turn["ok"] is not False,
                "status": 200 if _last_turn["ok"] is not False else 0}
    now = time.monotonic()
    if now - _model_cache["at"] < 1.5:
        return _model_cache["value"]
    value = None
    try:
        if os.path.isfile(CCR_LOG_DB):
            uri = "file:" + CCR_LOG_DB.replace("\\", "/") + "?mode=ro"
            with contextlib.closing(sqlite3.connect(uri, uri=True, timeout=1)) as c:
                row = c.execute(
                    "select provider, coalesce(nullif(response_model,''), resolved_model), "
                    "status_code, created_at from request_logs order by id desc limit 1"
                ).fetchone()
            if row:
                provider, model, status, created = row
                age = (datetime.datetime.now(datetime.timezone.utc)
                       - datetime.datetime.fromisoformat(created.replace("Z", "+00:00"))).total_seconds()
                if model and age < MODEL_FRESH_S:
                    key = (provider or "").split("::")[0]
                    value = {"model": model,
                             "provider": _PROVIDER_NAMES.get(key, key if key != "unknown" else ""),
                             "ok": status == 200, "status": status}
    except (sqlite3.Error, OSError, ValueError):
        value = None
    _model_cache.update(at=now, value=value)
    return value


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

        if parsed.path == "/api/model":
            qs = parse_qs(parsed.query)
            if not self._origin_ok() or qs.get("token", [""])[0] != TOKEN:
                self._send_json(403, {"error": "forbidden"})
                return
            self._send_json(200, {"backend": current_backend()})
            return

        if parsed.path == "/api/ready":
            qs = parse_qs(parsed.query)
            if not self._origin_ok() or qs.get("token", [""])[0] != TOKEN:
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
                t = ev.get("t")
                if t == "backend":
                    _last_turn.update(kind=ev.get("kind"), model="", ok=None)
                elif t == "status" and ev.get("model"):
                    _last_turn["model"] = ev["model"]
                elif t == "complete":
                    _last_turn["ok"] = True
                elif t == "error":
                    _last_turn["ok"] = False
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
        if sys.platform == "win32":
            # `npx` runs through a cmd.exe shim (shell=True), so terminate()
            # only killed the shim and left node.exe (Playwright MCP) alive on
            # its port. taskkill /T takes the whole tree down.
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           capture_output=True)
            return
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


def open_ui():
    """Open ANZO's window. Returns the process to wait on (app mode) or None.

    App mode = Chrome's --app window: no tabs, no address bar, its own profile.
    It has to be Chrome (not Edge/WebView): the voice UI relies on Chrome's
    Web Speech API. Kept separate from the automation Chrome on purpose --
    loading this page in that window once got it navigated away by Claude
    (see Anzo/Problemas resueltos.md)."""
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


def _boot(procs):
    """Everything slow (automation Chrome, Playwright MCP, router). Runs in a
    background thread so the window is already open while this works."""
    try:
        if os.environ.get("ANZO_NO_AUTOMATION") == "1":  # UI-only testing
            return
        _boot_state["step"] = "Abriendo el navegador de trabajo…"
        procs["chrome"] = start_chrome()
        if procs["chrome"]:
            print("Esperando a que el puerto de depuracion de Chrome responda...")
            _wait_for_port(CHROME_DEBUG_PORT, 20, "Chrome devtools")
        _boot_state["step"] = "Conectando las herramientas del navegador…"
        procs["mcp"] = start_browser_mcp() if procs["chrome"] else None
        if procs["mcp"]:
            print("Esperando a que el servidor de Playwright MCP responda "
                  "(la primera vez puede tardar mientras npx descarga el paquete)...")
            _wait_for_port(BROWSER_MCP_PORT, 60, "Playwright MCP")
        _boot_state["step"] = "Conectando el router…"
        if start_router():
            _boot_state["router_started"] = True
            if not _wait_for_port(brain.ROUTER_PORT, 15, "claude-code-router gateway"):
                print("AVISO: el gateway del router no esta arriba. CCR no lo levanta hasta "
                      "que haya al menos un proveedor con modelo configurado: corre `ccr ui`, "
                      "agrega uno y pulsa Start en la pagina Server.")
            if not brain.ROUTER_KEY:
                print("AVISO: ANZO_ROUTER_KEY vacio. Si el router exige clave de cliente "
                      "(pagina API Keys de `ccr ui`), ponla en .env o exportala.")
    except Exception as e:  # never leave the UI stuck on "Iniciando"
        print(f"ERROR durante el arranque: {e!r}")
    finally:
        _boot_state.update(ready=True, step="")


def main():
    try:
        server = Server((HOST, PORT), Handler)
    except OSError:
        # Port taken: ANZO is already running (autostart task, earlier
        # launch). Its page injects the token on each GET /, so just open a
        # window onto it instead of starting a second copy.
        print(f"ANZO ya esta corriendo en el puerto {PORT}; abriendo su ventana.")
        open_ui()
        return

    print(f"ANZO listening on http://{HOST}:{PORT}")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=_summary_loop, daemon=True).start()
    procs = {}
    threading.Thread(target=_boot, args=(procs,), daemon=True).start()

    ui_proc = open_ui()
    started = time.monotonic()
    try:
        if ui_proc:
            # Closing the window quits ANZO and everything it started.
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
        _stop(procs.get("mcp"), "browser MCP")
        _stop(procs.get("chrome"), "Chrome")
        _clean_console_logs()
        stop_router()
        _maybe_flush_summary(force=True)


if __name__ == "__main__":
    main()
