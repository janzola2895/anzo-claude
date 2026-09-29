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
ROUTER_MODE = os.environ.get("ANZO_ROUTER", "off").strip().lower()
if ROUTER_MODE not in ("off", "fallback", "always"):
    ROUTER_MODE = "off"
ROUTER_HOST = os.environ.get("ANZO_ROUTER_HOST", "127.0.0.1").strip()
ROUTER_PORT = int(os.environ.get("ANZO_ROUTER_PORT", "3456"))
ROUTER_URL = os.environ.get("ANZO_ROUTER_URL", "").strip() or f"http://{ROUTER_HOST}:{ROUTER_PORT}"
# A CCR client key (created on the router's "API Keys" page). Never logged.
ROUTER_KEY = os.environ.get("ANZO_ROUTER_KEY", "").strip()
# Model as the router names it (e.g. "openrouter,deepseek/deepseek-chat" or a
# tier alias). Empty = let the router's default/routing rules decide.
ROUTER_MODEL = os.environ.get("ANZO_ROUTER_MODEL", "").strip()

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
    if routed:
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
        cmd += ["--allowedTools", "mcp__browser,Skill"]
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
    """
    if ROUTER_MODE == "always":
        if not router_reachable():
            yield dict(t="error", message=(
                f"claude-code-router no responde en {ROUTER_URL}. "
                "Arrancalo (ccr start) o pon ANZO_ROUTER=off."))
            return
        yield from _finish(_run_once(message, session_id, routed=True), routed=True)
        return

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
        yield from _finish(_run_once(message, session_id, routed=True), routed=True)
        return


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

    # Summaries are background housekeeping: when a router is configured,
    # spend the router's tokens on them rather than the subscription's.
    if ROUTER_MODE == "always" or (ROUTER_MODE == "fallback" and router_reachable()):
        routed_out = attempt(True) if router_reachable() else None
        if routed_out:
            return routed_out
        if ROUTER_MODE == "always":
            return ""
    return attempt(False) or ""
