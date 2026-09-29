"""
ANZO's brain: drives Claude Code headless (`claude -p`) as a subprocess.

This authenticates exactly like an interactive `claude` session — the
user's Claude subscription, no API key, no per-token billing. Never add
--bare and never let ANTHROPIC_* / CLAUDE_CODE_* reach the child process:
either one silently switches the CLI onto paid API billing while
`claude auth status` keeps reporting `loggedIn: true`.

Pattern verified against two working reference projects (ethanplusai/jarvis,
Itsme23476/jarvis-claude-code) before writing this from scratch. See
Anzo/Decisiones.md for why.

Router (claude-code-router, https://github.com/musistudio/claude-code-router):
optional local gateway that lets the same `claude` CLI talk to other
providers/accounts (OpenRouter, DeepSeek, Gemini, a second Anthropic key...)
so ANZO doesn't depend only on this account's subscription limits. See
ANZO_ROUTER below. The default keeps the exact subscription-only behavior
described above; the router is strictly opt-in, and only the *routed* child
process ever gets ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN.

Windows note: `claude` is installed as a `claude.cmd` shim (npm global
install), not a bare .exe. `subprocess.Popen([...], shell=False)` cannot
launch a .cmd directly on Windows and fails with WinError 2/193 depending
on the call — this is the exact class of bug this project's own setup
session hit with a different CLI tool earlier. `shell=True` with a list
argument is the safe fix: Python still quotes each argument via
`list2cmdline` (no shell-injection footgun), it just routes through
`cmd.exe` so the .cmd shim resolves.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections import deque

IS_WINDOWS = sys.platform == "win32"

# Every ANTHROPIC_* variable, not just the key: the base URL and model
# override redirect a child just as effectively as credentials do.
SCRUBBED_ENV_PREFIXES = ("CLAUDE_CODE_", "ANTHROPIC_")
SCRUBBED_ENV_KEYS = {"CLAUDECODE"}

MODEL = os.environ.get("ANZO_MODEL", "").strip()

# --- claude-code-router integration -------------------------------------
# ANZO_ROUTER:
#   off      (default) subscription only, exactly as before.
#   fallback use the subscription first; when it reports a usage/rate limit,
#            transparently retry the same turn through the router.
#   always   send every turn through the router (subscription untouched).
#   router_first  the router (its own provider chain) first; the Claude
#            subscription only as the last resort, when the router is down or
#            every provider behind it is out of quota.
ROUTER_MODE = os.environ.get("ANZO_ROUTER", "off").strip().lower()
if ROUTER_MODE not in ("off", "fallback", "always", "router_first"):
    ROUTER_MODE = "off"
ROUTER_HOST = os.environ.get("ANZO_ROUTER_HOST", "127.0.0.1").strip()
ROUTER_PORT = int(os.environ.get("ANZO_ROUTER_PORT", "3456"))
ROUTER_URL = os.environ.get("ANZO_ROUTER_URL", "").strip() or f"http://{ROUTER_HOST}:{ROUTER_PORT}"
# A CCR client key (created on the router's "API Keys" page). Never logged.
ROUTER_KEY = os.environ.get("ANZO_ROUTER_KEY", "").strip()
# Model as the router names it (e.g. "openrouter,deepseek/deepseek-chat" or a
# tier alias). Empty = let the router's default/routing rules decide.
ROUTER_MODEL = os.environ.get("ANZO_ROUTER_MODEL", "").strip()
# How many times the CLI retries a failed API call when routed (its own default
# is 10). Free provider tiers count every attempt, and a 429 is retried within
# seconds, so the default burns a whole day's quota on one stuck turn; 2 makes a
# real limit surface as a quick "el router devolvio un limite" instead.
try:
    ROUTER_MAX_RETRIES = max(0, int(os.environ.get("ANZO_ROUTER_MAX_RETRIES", "2")))
except ValueError:
    ROUTER_MAX_RETRIES = 2
# Bitacora summaries are optional housekeeping. Sending them through the router
# spends the same small free quota the live turns need, so by default they use
# the subscription instead; set to 1 to spend router tokens on them.
SUMMARY_VIA_ROUTER = os.environ.get("ANZO_SUMMARY_VIA_ROUTER", "").strip() == "1"

# CCR, once installed, rewrites the user's GLOBAL ~/.claude/settings.json
# (env ANTHROPIC_BASE_URL/ANTHROPIC_MODEL pointing at the gateway, plus an
# apiKeyHelper that hands the CLI the router's key). The CLI reads that file on
# every start, so scrubbing the child's environment isn't enough: a
# "subscription" turn silently went through CCR too. This file is passed with
# --settings (higher precedence than the user's settings) on non-routed runs
# only, putting the official endpoint back and disabling the apiKeyHelper so
# the CLI falls back to the claude.ai login.
SUBSCRIPTION_SETTINGS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "anzo-claude-settings.json")
CCR_LOG_DB = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                          "claude-code-router", "request-logs.sqlite")
# In router_first mode: if the router's last request failed on quota this
# recently, skip it and go straight to the subscription instead of waiting for
# the router to time out again (each attempt burns quota and ~40s).
ROUTER_COOLDOWN_S = int(os.environ.get("ANZO_ROUTER_COOLDOWN", "300"))

# Phrases the CLI prints when the plan/API runs out ("You've hit your weekly
# limit · resets 11pm", "Claude usage limit reached", 429s...). Only applied to
# SHORT messages: a normal answer that merely talks about rate limits must not
# trigger a fallback.
_LIMIT_RE = re.compile(
    r"hit your .{0,30}limit|usage limit|limit reached|rate.?limit|"
    r"credit balance|out of (?:extra )?usage|\b429\b|overloaded",
    re.IGNORECASE,
)
_LIMIT_MAX_LEN = 300
# Empty by default (falls back to the CLI's own "Manual" mode) rather than
# "acceptEdits": ANZO's whole job right now is browser control via
# --allowedTools mcp__browser below, not local file edits. acceptEdits also
# auto-approves filesystem commands (mkdir/mv/cp/...) that have nothing to
# do with that job -- unnecessary blast radius once this is actually
# touching real Indra business apps. Anything outside the browser allowlist
# now gets blocked instead of silently allowed.
PERMISSION_MODE = os.environ.get("ANZO_PERMISSION_MODE", "").strip()
WORKDIR = os.path.expanduser(os.environ.get("ANZO_WORKDIR", os.getcwd()))

def _desktop_dir() -> str:
    """The real Desktop folder. On this machine it lives under OneDrive
    ("OneDrive - Indra\\Escritorio"), not ~/Desktop -- ANZO guessed the latter
    and failed. Read from the shell-folders registry key, like Explorer does."""
    if IS_WINDOWS:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows"
                                r"\CurrentVersion\Explorer\User Shell Folders") as k:
                return os.path.expandvars(winreg.QueryValueEx(k, "Desktop")[0])
        except OSError:
            pass
    return os.path.join(os.path.expanduser("~"), "Desktop")


# The one folder outside the project ANZO may write to: screenshots/images
# (Playwright MCP gets it as --output-dir, its only extra allowed root) and
# text files like HTML/notes (a path-scoped Edit rule). Headless claude -p can't
# show a permission prompt, so anything not pre-approved is silently denied --
# that's why "save it to my desktop" failed with no dialog. Scoped to this
# folder on purpose, not the whole Desktop or disk.
OUTPUT_DIR = os.environ.get("ANZO_OUTPUT_DIR", "").strip() or os.path.join(
    _desktop_dir(), "ANZO archivos")


def _permission_path(path: str) -> str:
    """C:\\a\\b -> //c/a/b, the absolute-path form Claude Code permission rules use."""
    p = os.path.abspath(path).replace("\\", "/")
    if len(p) > 1 and p[1] == ":":
        p = "/" + p[0].lower() + p[2:]
    return "/" + p


_default_mcp_config = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp-config.json")
MCP_CONFIG_PATH = os.environ.get("ANZO_MCP_CONFIG", "").strip() or (
    _default_mcp_config if os.path.isfile(_default_mcp_config) else ""
)

# Without this, Claude defaults to its general-coding-agent instincts and
# reaches for Bash/PowerShell (Start-Process) to "open a browser" — a real,
# observed failure mode. Those commands don't drive the Playwright browser
# at all, and since headless mode can't show a permission prompt, they just
# hang waiting for an approval that will never come. This has to be said
# explicitly; having the tool available isn't enough for Claude to prefer it.
BROWSER_SYSTEM_PROMPT = (
    "Eres ANZO, un asistente de voz que ayuda a desarrollar y diagnosticar "
    "Microsoft Power Platform (Canvas Apps, Power Automate) y a analizar "
    "graficos de trading (XAUUSD y similares), siempre controlando un "
    "navegador real. "
    "Para CUALQUIER interaccion con paginas web o el navegador (abrir, navegar, "
    "hacer clic, escribir, leer la pantalla) usa EXCLUSIVAMENTE las herramientas "
    "mcp__browser__*. NUNCA uses Bash, PowerShell, cmd, Start-Process ni ningun "
    "comando de shell para abrir un navegador o una URL: esas herramientas no "
    "controlan el navegador correcto y se quedan bloqueadas esperando una "
    "aprobacion que nunca va a llegar. El navegador debe quedar SIEMPRE "
    "abierto entre turnos: nunca uses una herramienta para cerrar la "
    "pestana, la ventana ni el navegador, ni siquiera al terminar una "
    "tarea — el usuario sigue la conversacion en esa misma pantalla. "
    "Si te piden analizar, leer u opinar sobre un grafico, un precio o si "
    "conviene operar algo, usa la herramienta Skill para cargar la skill "
    "de analisis de trading antes de responder. "
    "Si te piden guardar una imagen, captura o archivo (o dejarlo en el "
    "escritorio), guardalo en la carpeta " + OUTPUT_DIR + " : las capturas con "
    "mcp__browser__browser_take_screenshot usando esa ruta completa en filename, "
    "y los archivos de texto (HTML, notas) con Write en esa misma carpeta. Es la "
    "unica carpeta donde puedes guardar; no intentes copiar con comandos de "
    "shell. "
    "Tus respuestas se leen en voz alta: responde en frases cortas y "
    "naturales, sin markdown ni listas."
)
IDLE_TIMEOUT_S = int(os.environ.get("ANZO_IDLE_TIMEOUT", "180"))

# One Claude subprocess at a time. Guarded so a new voice instruction can
# interrupt whatever is currently running.
_active_lock = threading.Lock()
_active_proc: subprocess.Popen | None = None


def child_env(routed: bool = False) -> dict:
    """Copy of the environment with anything that would redirect billing removed.

    routed=True is the one deliberate exception: the child is pointed at the
    local claude-code-router gateway instead of Anthropic. It gets *only* the
    gateway URL and the router's client key -- never an ambient
    ANTHROPIC_API_KEY, and the non-routed path above is untouched, so a
    subscription turn can never accidentally leak onto the router (or vice
    versa)."""
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(SCRUBBED_ENV_PREFIXES) and k not in SCRUBBED_ENV_KEYS
    }
    # The CLI makes a separate small-model request per session just to write a
    # title -- pure waste here (nobody sees it) and one more call against any
    # quota, subscription or router.
    env["CLAUDE_CODE_DISABLE_TERMINAL_TITLE"] = "1"
    if routed:
        env["CLAUDE_CODE_MAX_RETRIES"] = str(ROUTER_MAX_RETRIES)
        # No telemetry / feature-flag / availability calls through the router.
        env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
        env["ANTHROPIC_BASE_URL"] = ROUTER_URL
        # The CLI refuses to run without *some* credential once a base URL is
        # set; if the router has no client-key enforcement any placeholder works.
        env["ANTHROPIC_AUTH_TOKEN"] = ROUTER_KEY or "anzo-local-router"
    return env


def router_reachable() -> bool:
    """True if the router's gateway port accepts a TCP connection right now."""
    try:
        from urllib.parse import urlparse
        u = urlparse(ROUTER_URL)
        host = u.hostname or ROUTER_HOST
        port = u.port or (443 if u.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except OSError:
        return False


def router_recently_exhausted() -> bool:
    """True if claude-code-router's own log says its last request, within
    ROUTER_COOLDOWN_S, ended in a quota/rate-limit error (after its internal
    fallback chain). Read-only; any problem reading it -> False."""
    try:
        import sqlite3
        from datetime import datetime, timezone
        if not os.path.isfile(CCR_LOG_DB):
            return False
        uri = "file:" + CCR_LOG_DB.replace("\\", "/") + "?mode=ro"
        c = sqlite3.connect(uri, uri=True, timeout=1)
        try:
            row = c.execute("select status_code, created_at from request_logs "
                            "order by id desc limit 1").fetchone()
        finally:
            c.close()
        if not row or row[0] != 429:
            return False
        age = (datetime.now(timezone.utc)
               - datetime.fromisoformat(row[1].replace("Z", "+00:00"))).total_seconds()
        return age < ROUTER_COOLDOWN_S
    except Exception:  # noqa: BLE001 - best effort, never block a turn on this
        return False


def is_limit_error(text) -> bool:
    """Does this message look like 'you ran out of tokens/quota'?"""
    text = (text or "").strip()
    return bool(text) and len(text) <= _LIMIT_MAX_LEN and bool(_LIMIT_RE.search(text))


def _valid_session(sid) -> bool:
    try:
        return bool(sid) and str(uuid.UUID(str(sid))) == str(sid).lower()
    except (ValueError, AttributeError, TypeError):
        return False


def _resolve_claude() -> str:
    configured = os.environ.get("ANZO_CLAUDE_CMD", "").strip()
    if configured:
        return configured
    exe = shutil.which("claude")
    if exe:
        return exe
    raise RuntimeError(
        "claude CLI not found on PATH. Install it with "
        "'npm install -g @anthropic-ai/claude-code', log in once with "
        "'claude', then restart this terminal so PATH picks it up."
    )


def build_command(message: str, session_id: str | None = None, routed: bool = False) -> list[str]:
    cmd = [
        _resolve_claude(),
        "-p", message,
        "--output-format", "stream-json",
        "--include-partial-messages",
        "--verbose",
    ]
    if _valid_session(session_id):
        cmd += ["--resume", str(session_id)]
    model = (ROUTER_MODEL if routed else "") or MODEL
    if model:
        cmd += ["--model", model]
    if not routed and os.path.isfile(SUBSCRIPTION_SETTINGS):
        cmd += ["--settings", SUBSCRIPTION_SETTINGS]
    if PERMISSION_MODE:
        cmd += ["--permission-mode", PERMISSION_MODE]
    if MCP_CONFIG_PATH:
        cmd += ["--mcp-config", MCP_CONFIG_PATH]
        # Headless mode has no one to answer a permission prompt, and MCP
        # tools aren't covered by --permission-mode acceptEdits (that only
        # auto-approves file edits and a handful of filesystem commands) —
        # without this the browser tools would just be silently denied.
        # Pre-approving the whole "browser" server (not bypassPermissions
        # for everything) keeps the blast radius to just that tool. Skill is
        # allowlisted too, for the trading-chart-analysis skill under
        # .claude/skills/ — the Skill tool only loads instructions into
        # context, it has no filesystem/shell access of its own, so this
        # doesn't reopen the blast radius the permission tightening closed.
        cmd += ["--allowedTools", "mcp__browser,Skill",
                f"Edit({_permission_path(OUTPUT_DIR)}/**)"]
        cmd += ["--add-dir", OUTPUT_DIR]
        cmd += ["--append-system-prompt", BROWSER_SYSTEM_PROMPT]
    return cmd


def cancel_active() -> bool:
    """Interrupt whatever ANZO is currently doing. Called when new speech
    arrives mid-turn. Killing the subprocess is the whole mechanism — the
    next turn resumes the same session via --resume, so no context is lost."""
    with _active_lock:
        proc = _active_proc
    if proc is None or proc.poll() is not None:
        return False
    try:
        proc.terminate()
        return True
    except OSError:
        return False


def _run_once(message: str, session_id: str | None = None, routed: bool = False):
    """One attempt at a turn (subscription, or via the router if routed=True).
    Same events as run(), plus {t: "limit", message} when the account/provider
    is out of quota -- emitted INSTEAD of the error/text so run() can decide
    whether to retry through the router. Generator yielding dicts describing
    what Claude is doing, as it happens:
    {t: "status", model, tools, mcp}
    {t: "delta", text}                    -- streamed narration text
    {t: "tool", phase: "use"/"result", name, input?, ok?}
    {t: "usage", input_tokens, output_tokens}
    {t: "complete", session_id, ms}
    {t: "error", message}
    {t: "interrupted"}
    """
    global _active_proc

    cmd = build_command(message, session_id, routed)
    env = child_env(routed)

    popen_kwargs = dict(
        cwd=WORKDIR,
        text=True,
        # Windows' default subprocess text decoding uses the system locale
        # codepage (e.g. cp1252), not UTF-8 — claude's stdout is UTF-8, so
        # without this every accented character comes back mojibake'd
        # ("está" -> "estÃ¡"). errors="replace" keeps a rare bad byte from
        # crashing the stream instead of just showing oddly.
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    if IS_WINDOWS:
        # See module docstring: routes through cmd.exe so the claude.cmd
        # shim resolves. list2cmdline still quotes every argument.
        popen_kwargs["shell"] = True

    try:
        proc = subprocess.Popen(cmd, **popen_kwargs)
    except FileNotFoundError as e:
        yield dict(t="error", message=f"could not start claude CLI: {e}")
        return

    with _active_lock:
        _active_proc = proc

    out_q: deque = deque()
    err_buf: deque = deque(maxlen=120)
    out_lock = threading.Lock()
    done = threading.Event()

    pump_error: list = []

    def pump_out():
        try:
            for line in proc.stdout:
                with out_lock:
                    out_q.append(line)
        except Exception as e:  # noqa: BLE001 - surfaced via pump_error, not swallowed
            pump_error.append(e)
        finally:
            done.set()

    def pump_err():
        try:
            for line in proc.stderr:
                err_buf.append(line.rstrip())
        except Exception:
            pass

    threading.Thread(target=pump_out, daemon=True).start()
    threading.Thread(target=pump_err, daemon=True).start()

    started = time.monotonic()
    last_activity = started
    emitted_session = session_id
    streamed_text = False
    text_seen = False

    try:
        while not done.is_set() or out_q:
            line = None
            with out_lock:
                if out_q:
                    line = out_q.popleft()
            if line is None:
                if proc.poll() is not None and done.is_set():
                    break
                if proc.poll() is not None and proc.returncode not in (0, None):
                    # Killed via cancel_active() while waiting for more output.
                    with _active_lock:
                        was_ours = _active_proc is proc
                    if was_ours:
                        yield dict(t="interrupted")
                        return
                if time.monotonic() - last_activity > IDLE_TIMEOUT_S:
                    proc.kill()
                    yield dict(t="error", message=(
                        f"claude went quiet for {IDLE_TIMEOUT_S}s and was stopped. "
                        + " | ".join(list(err_buf)[-3:])
                    )[:400])
                    return
                time.sleep(0.03)
                continue

            last_activity = time.monotonic()
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue

            kind = ev.get("type")
            sid = ev.get("session_id")
            if _valid_session(sid):
                emitted_session = sid

            if (kind == "system" and ev.get("subtype") == "api_retry"
                    and routed and not text_seen):
                # CCR already walked its whole provider chain before answering
                # with an error, so a retry from the CLI can only hit the same
                # wall (and burn more free quota). Hand it back to run() now.
                proc.terminate()
                yield dict(t="limit", message=("El router no tiene cupo ahora "
                                               f"({ev.get('error') or 'error'})."))
                return

            if kind == "system" and ev.get("subtype") == "init":
                # mcp_server_errors: config entries Claude Code rejected at
                # startup (e.g. a "url" server missing "type") -- it skips
                # them and carries on silently otherwise, which is exactly
                # how this project's own browser MCP server config went
                # unnoticed as broken for a while. Surface it instead.
                for err in ev.get("mcp_server_errors") or []:
                    # "warning", not "error": the turn keeps going without
                    # that tool, so this must not be one of the types that
                    # makes server.py close the stream.
                    yield dict(t="warning", message=(
                        f"MCP server '{err.get('name')}' failed to load "
                        f"({err.get('type')}): {err.get('message')}"))
                yield dict(
                    t="status",
                    model=ev.get("model") or MODEL or "default",
                    tools=len(ev.get("tools") or []),
                    mcp=[s.get("name") for s in (ev.get("mcp_servers") or [])],
                    session_id=sid,
                )
                continue

            if kind == "stream_event":
                inner = ev.get("event") or {}
                if inner.get("type") == "content_block_delta":
                    delta = inner.get("delta") or {}
                    if delta.get("type") == "text_delta" and delta.get("text"):
                        streamed_text = True
                        text_seen = True
                        yield dict(t="delta", text=delta["text"])
                continue

            if kind == "assistant":
                for block in (ev.get("message") or {}).get("content") or []:
                    btype = block.get("type")
                    if (btype == "text" and not text_seen and is_limit_error(block.get("text"))):
                        # Quota message arrives as a synthetic assistant turn.
                        proc.terminate()
                        yield dict(t="limit", message=block["text"].strip())
                        return
                    if btype == "text" and not streamed_text and block.get("text"):
                        text_seen = True
                        yield dict(t="delta", text=block["text"])
                    elif btype == "tool_use":
                        yield dict(t="tool", phase="use", name=block.get("name", "tool"),
                                   input=block.get("input", {}))
                continue

            if kind == "user":
                for block in (ev.get("message") or {}).get("content") or []:
                    if block.get("type") == "tool_result":
                        yield dict(t="tool", phase="result",
                                   ok=not block.get("is_error"),
                                   name=block.get("name", ""))
                continue

            if kind == "result":
                usage = ev.get("usage") or {}
                if not text_seen and is_limit_error(ev.get("result")):
                    yield dict(t="limit", message=str(ev["result"]).strip())
                    return
                if ev.get("subtype") != "success" and not text_seen:
                    yield dict(t="error", message=str(ev.get("result") or "claude returned an error")[:400])
                    return
                if not text_seen and ev.get("result"):
                    yield dict(t="delta", text=str(ev["result"]))
                yield dict(t="usage",
                           input_tokens=usage.get("input_tokens", 0),
                           output_tokens=usage.get("output_tokens", 0))
                yield dict(t="complete", session_id=emitted_session,
                           ms=ev.get("duration_ms") or int((time.monotonic() - started) * 1000))
                return

        if pump_error:
            proc.kill()
            yield dict(t="error", message=f"lost the claude output stream: {pump_error[0]}"[:400])
            return

        try:
            rc = proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # pump_out saw EOF (done.set()) but the process itself hasn't
            # exited yet — give it a moment, then stop waiting on it rather
            # than crash the request thread.
            proc.kill()
            yield dict(t="error", message="claude did not exit after finishing output")
            return
        if rc not in (0, None):
            with _active_lock:
                was_ours = _active_proc is proc
            if was_ours:
                yield dict(t="interrupted")
            else:
                err_text = " | ".join(list(err_buf)[-6:])
                if not text_seen and any(is_limit_error(l) for l in err_buf):
                    yield dict(t="limit", message=err_text[:_LIMIT_MAX_LEN])
                    return
                yield dict(t="error", message=(err_text
                                               or f"claude exited with code {rc}")[:500])
            return
        yield dict(t="complete", session_id=emitted_session,
                   ms=int((time.monotonic() - started) * 1000))
    finally:
        if proc.poll() is None:
            proc.terminate()
        with _active_lock:
            if _active_proc is proc:
                _active_proc = None


def run(message: str, session_id: str | None = None):
    """Public entry point: same events as _run_once(), with router policy.

    off      -> subscription only (a limit surfaces as a normal error).
    always   -> router only.
    fallback -> subscription first; on a quota limit, retry once via router.
    router_first -> router first; the subscription only as the last resort.
    Also yields {t: "backend", kind: "router"|"subscription"} before each attempt.
    """
    if ROUTER_MODE == "router_first":
        yield from _run_router_first(message, session_id)
        return

    if ROUTER_MODE == "always":
        if not router_reachable():
            yield dict(t="error", message=(
                f"claude-code-router no responde en {ROUTER_URL}. "
                "Arrancalo (ccr start) o pon ANZO_ROUTER=off."))
            return
        yield dict(t="backend", kind="router")
        yield from _finish(_run_once(message, session_id, routed=True), routed=True)
        return

    yield dict(t="backend", kind="subscription")
    first = _run_once(message, session_id, routed=False)
    for ev in first:
        if ev.get("t") != "limit":
            yield ev
            continue
        if ROUTER_MODE != "fallback":
            yield dict(t="error", message=ev["message"][:400])
            return
        if not router_reachable():
            yield dict(t="error", message=(
                ev["message"] + " | Ademas claude-code-router no responde en "
                f"{ROUTER_URL}, asi que no hay respaldo.")[:400])
            return
        yield dict(t="warning", message=(
            "Se acabo el limite de la suscripcion; continuo con el router "
            "(otro proveedor)."))
        yield dict(t="backend", kind="router")
        yield from _finish(_run_once(message, session_id, routed=True), routed=True)
        return


def _run_router_first(message: str, session_id: str | None):
    """Router first (CCR walks its own provider chain: Gemini -> OVH ...), the
    Claude subscription only as the last resort. Falls to the subscription
    when the router is down, recently exhausted, or fails before saying
    anything; once the router has produced text, its errors stay errors (the
    user already heard part of an answer)."""
    reason = None
    if not router_reachable():
        reason = "el router no responde"
    elif router_recently_exhausted():
        reason = "los proveedores del router siguen sin cupo"
    else:
        yield dict(t="backend", kind="router")
        spoke = False
        for ev in _run_once(message, session_id, routed=True):
            t = ev.get("t")
            if t == "delta":
                spoke = True
            if t == "limit" or (t == "error" and not spoke):
                reason = ev.get("message") or "el router fallo"
                break
            yield ev
            if t in ("complete", "interrupted", "error"):
                return
        else:
            return
    yield dict(t="warning", message=(f"Uso la membresia de Claude: {reason}")[:400])
    yield dict(t="backend", kind="subscription")
    for ev in _run_once(message, session_id, routed=False):
        if ev.get("t") == "limit":
            yield dict(t="error", message=("La membresia de Claude tambien esta en su "
                                           "limite: " + ev["message"])[:400])
            return
        yield ev


def _finish(events, routed: bool):
    """Pass events through; a limit hit while already routed is a plain error
    (no further fallback -- there's nothing left to fall back to)."""
    for ev in events:
        if ev.get("t") == "limit":
            yield dict(t="error", message=("El router tambien devolvio un limite: "
                                           + ev["message"])[:400])
            return
        yield ev


def summarize(exchanges: list[tuple[str, str]]) -> str:
    """One-shot, non-streaming claude -p call that condenses a list of
    (user_message, anzo_reply) pairs into a short Spanish summary for
    Anzo/Bitacora/. No browser/MCP tools: --tools "" disables the built-in
    set entirely (stronger than just not pre-approving them, since this call
    has no legitimate use for any tool) and --mcp-config isn't passed at
    all. Deliberately not run after every turn -- server.py only calls this
    on an idle gap or clean shutdown, so it doesn't multiply usage against
    the same weekly limit the interactive turns already spend from.

    Runs from a neutral temp directory, NOT WORKDIR: cwd=C:\\dev\\anzo (used
    by run(), to find .claude/skills/) also auto-loads this project's own
    Claude Code memory/CLAUDE.md -- confirmed live, it made a test summary
    talk about the ANZO project itself instead of the sample exchange. This
    call needs zero project context, so it just avoids the directory that
    triggers it instead of fighting it with more flags (--bare would also
    dodge it, but breaks subscription auth -- never use --bare here).

    The prompt is piped via stdin, NOT passed as the -p positional argument:
    confirmed live that a multi-line argument gets silently truncated at the
    first newline when routed through cmd.exe (shell=True, needed for the
    claude.cmd shim -- see module docstring). Piping sidesteps that
    entirely; `claude -p` (no prompt arg) reads the message from stdin."""
    if not exchanges:
        return ""
    transcript = "\n\n".join(f"Usuario: {u}\nAnzo: {a}" for u, a in exchanges)
    prompt = (
        "Resumi en espanol, en 2 a 4 frases cortas, de que trato esta "
        "conversacion entre el usuario y ANZO (un asistente de voz). Texto "
        "plano, sin markdown ni listas.\n\n" + transcript
    )
    def attempt(routed: bool) -> str | None:
        cmd = [_resolve_claude(), "-p", "--tools", ""]
        model = (ROUTER_MODEL if routed else "") or MODEL
        if model:
            cmd += ["--model", model]
        if not routed and os.path.isfile(SUBSCRIPTION_SETTINGS):
            cmd += ["--settings", SUBSCRIPTION_SETTINGS]
        popen_kwargs = dict(
            cwd=tempfile.gettempdir(), text=True, encoding="utf-8", errors="replace",
            capture_output=True, env=child_env(routed), input=prompt,
        )
        if IS_WINDOWS:
            popen_kwargs["shell"] = True
        try:
            result = subprocess.run(cmd, timeout=60, **popen_kwargs)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None
        out = result.stdout.strip()
        if result.returncode != 0 or is_limit_error(out):
            return None
        return out

    # Summaries are background housekeeping. In "always" mode the subscription
    # isn't used at all, so they go through the router. Otherwise they stay on
    # the subscription unless ANZO_SUMMARY_VIA_ROUTER=1 -- the router's free
    # quota is small and the live turns need it more.
    if ROUTER_MODE == "always":
        return (attempt(True) if router_reachable() else None) or ""
    if ROUTER_MODE in ("fallback", "router_first") and SUMMARY_VIA_ROUTER and router_reachable():
        routed_out = attempt(True)
        if routed_out:
            return routed_out
    return attempt(False) or ""
