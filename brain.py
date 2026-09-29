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
import shutil
import subprocess
import sys
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


def child_env() -> dict:
    """Copy of the environment with anything that would redirect billing removed."""
    return {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(SCRUBBED_ENV_PREFIXES) and k not in SCRUBBED_ENV_KEYS
    }


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


def build_command(message: str, session_id: str | None = None) -> list[str]:
    cmd = [
        _resolve_claude(),
        "-p", message,
        "--output-format", "stream-json",
        "--include-partial-messages",
        "--verbose",
    ]
    if _valid_session(session_id):
        cmd += ["--resume", str(session_id)]
    if MODEL:
        cmd += ["--model", MODEL]
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


def run(message: str, session_id: str | None = None):
    """Generator yielding dicts describing what Claude is doing, as it happens:
    {t: "status", model, tools, mcp}
    {t: "delta", text}                    -- streamed narration text
    {t: "tool", phase: "use"/"result", name, input?, ok?}
    {t: "usage", input_tokens, output_tokens}
    {t: "complete", session_id, ms}
    {t: "error", message}
    {t: "interrupted"}
    """
    global _active_proc

    cmd = build_command(message, session_id)
    env = child_env()

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
                yield dict(t="error", message=(" | ".join(list(err_buf)[-6:])
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
