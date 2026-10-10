"""
ANZO + Claude's brain: drives Claude Code headless (`claude -p`) as a
subprocess, with the Claude in Chrome extension as its browser.

This version uses only the user's own Claude membership (claude.ai login) and
the Claude in Chrome extension -- no router, no other providers, no Playwright.
(The original ANZO, with claude-code-router and Playwright MCP, lives on in
C:\\dev\\anzo; see Anzo/Decisiones.md for why this copy exists.)

Authentication: exactly like an interactive `claude` session -- the user's
subscription, no API key, no per-token billing. Never add --bare and never let
ANTHROPIC_* / CLAUDE_CODE_* reach the child process: either one silently
switches the CLI onto API billing (or onto a gateway) while `claude auth
status` keeps reporting `loggedIn: true`. The Chrome integration also *requires*
the claude.ai login: with an API key or token the CLI keeps it off.

Windows note: `claude` is installed as a `claude.cmd` shim (npm global
install), not a bare .exe. `subprocess.Popen([...], shell=False)` cannot
launch a .cmd directly on Windows and fails with WinError 2/193 depending
on the call. `shell=True` with a list argument is the safe fix: Python still
quotes each argument via `list2cmdline` (no shell-injection footgun), it just
routes through `cmd.exe` so the .cmd shim resolves.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import shutil
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

# claude-code-router, once installed on this machine, rewrote the user's GLOBAL
# ~/.claude/settings.json (env ANTHROPIC_BASE_URL/ANTHROPIC_MODEL pointing at
# its gateway, plus an apiKeyHelper that hands the CLI the router's key). The
# CLI reads that file on every start, so scrubbing the child's environment
# isn't enough. This file, passed with --settings (higher precedence than the
# user's settings), puts the official endpoint back and disables the
# apiKeyHelper so the CLI uses the claude.ai login -- which the Chrome
# integration needs anyway. Harmless if the global file is ever cleaned up.
CLAUDE_SETTINGS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "anzo-claude-settings.json")

# Phrases the CLI prints when the plan runs out ("You've hit your weekly
# limit · resets 11pm", "Claude usage limit reached", 429s...). Only applied to
# SHORT messages: a normal answer that merely talks about rate limits must not
# be mistaken for one.
_LIMIT_RE = re.compile(
    r"hit your .{0,30}limit|usage limit|limit reached|rate.?limit|"
    r"credit balance|out of (?:extra )?usage|\b429\b|overloaded",
    re.IGNORECASE,
)
_LIMIT_MAX_LEN = 300
# Empty by default (the CLI's own "Manual" mode): ANZO's job is browser control
# through the extension, and anything outside the allowlist in build_command()
# gets blocked instead of silently allowed.
PERMISSION_MODE = os.environ.get("ANZO_PERMISSION_MODE", "").strip()
WORKDIR = os.path.expanduser(os.environ.get("ANZO_WORKDIR", os.getcwd()))


def _desktop_dir() -> str:
    """The real Desktop folder. On this machine it lives under OneDrive
    ("OneDrive - Indra\\Escritorio"), not ~/Desktop. Read from the
    shell-folders registry key, like Explorer does."""
    if IS_WINDOWS:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows"
                                r"\CurrentVersion\Explorer\User Shell Folders") as k:
                return os.path.expandvars(winreg.QueryValueEx(k, "Desktop")[0])
        except OSError:
            pass
    return os.path.join(os.path.expanduser("~"), "Desktop")


# The one folder outside the project ANZO may write to. Text files (HTML,
# notes) go there through a path-scoped Edit rule; screenshots are saved by the
# extension to a temp folder and copied here by _collect_screenshot(). Headless
# claude -p can't show a permission prompt, so anything not pre-approved is
# silently denied -- scoped to this folder on purpose, not the whole disk.
OUTPUT_DIR = os.environ.get("ANZO_OUTPUT_DIR", "").strip() or os.path.join(
    _desktop_dir(), "ANZO archivos")


def _permission_path(path: str) -> str:
    """C:\\a\\b -> //c/a/b, the absolute-path form Claude Code permission rules use."""
    p = os.path.abspath(path).replace("\\", "/")
    if len(p) > 1 and p[1] == ":":
        p = "/" + p[0].lower() + p[2:]
    return "/" + p


# Without explicit instructions Claude falls back to general-coding-agent
# instincts (reaching for Bash/PowerShell to "open a browser", which headless
# mode can't approve) and to the claude-in-chrome skill's defaults, which tell
# it to close the tabs it opens. ANZO needs the opposite: the user follows the
# conversation on those same tabs, turn after turn.
SYSTEM_PROMPT = (
    "Eres ANZO, un asistente de voz que ayuda a desarrollar y diagnosticar "
    "Microsoft Power Platform (Canvas Apps, Power Automate) y a analizar "
    "graficos de trading (XAUUSD y similares), controlando el Chrome real del "
    "usuario con la extension Claude in Chrome. "
    "Para CUALQUIER interaccion con paginas web (abrir, navegar, hacer clic, "
    "escribir, leer la pantalla) usa EXCLUSIVAMENTE las herramientas "
    "mcp__claude-in-chrome__*. NUNCA uses Bash, PowerShell, cmd ni comandos de "
    "shell para abrir un navegador o una URL. "
    "Al empezar llama tabs_context_mcp con createIfEmpty true y trabaja en las "
    "pestanas de tu grupo; entre turnos sigue usando las mismas pestanas. "
    "NUNCA cierres pestanas, ventanas ni el grupo, ni siquiera al terminar una "
    "tarea, salvo que el usuario lo pida explicitamente: el usuario sigue la "
    "conversacion en esa misma pantalla. Esto tiene prioridad sobre cualquier "
    "otra indicacion de cerrar las pestanas que abras. "
    "Si una pagina pide iniciar sesion o un CAPTCHA, pidele al usuario que lo "
    "haga el mismo. "
    "Si te piden analizar, leer u opinar sobre un grafico, un precio o si "
    "conviene operar algo, usa la herramienta Skill para cargar la skill "
    "de analisis de trading antes de responder. "
    "Si el usuario dice 'modo oro' (con o sin 'viernes' o 'anzo' delante: "
    "'viernes' es tu nombre, no el dia), carga con la herramienta Skill la "
    "skill modo-oro y sigue su protocolo completo, sin abrir, modificar ni "
    "cerrar operaciones en ninguna plataforma. "
    "Si te piden guardar una captura o imagen (o dejarla en el escritorio), "
    "tomala con computer action screenshot y save_to_disk true: ANZO la copia "
    "sola a la carpeta " + OUTPUT_DIR + " ; dile al usuario que quedo en la "
    "carpeta ANZO archivos del escritorio. Los archivos de texto (HTML, notas) "
    "guardalos con Write en esa misma carpeta. Es la unica carpeta donde puedes "
    "guardar; no intentes copiar con comandos de shell. "
    "Si las herramientas del navegador no responden, dile al usuario que revise "
    "que Chrome este abierto y repita la instruccion; no le pidas reiniciar nada. "
    # A 2026-09-29 turn spent ~190 tool calls clicking the same Power Apps
    # formula bar over and over (every call re-reads the whole context, so a
    # loop like that burned ~20% of the session). MAX_TOOL_CALLS below is the
    # hard backstop; this is the rule that should stop it much earlier.
    "Si un paso no te sale (un clic que no hace nada, una formula que no queda, "
    "un boton que no encuentras), intentalo como maximo 3 veces y cada vez de "
    "una forma distinta; nunca repitas la misma accion esperando otro resultado. "
    "Si al tercer intento sigue sin funcionar, detente ahi y no sigas probando "
    "variaciones: dile al usuario en una o dos frases que paso intentabas, que "
    "probaste y que falla, y pidele que lo haga el o que te diga como. Cada "
    "accion gasta tokens de su membresia. Para ahorrar, agrupa en una sola "
    "llamada con browser_batch las acciones que puedas prever (por ejemplo "
    "clic, escribir y Enter) y no tomes dos capturas seguidas sin haber hecho "
    "nada entre ellas. "
    "Tus respuestas se leen en voz alta: responde en frases cortas y "
    "naturales, sin markdown ni listas."
)
IDLE_TIMEOUT_S = int(os.environ.get("ANZO_IDLE_TIMEOUT", "180"))

# Hard cap on tool calls in a single turn (0 = no cap). Past it ANZO stops the
# turn and asks the user whether to go on, so a Claude stuck retrying the same
# step can't drain the membership on its own. Counted per tool call, not per
# browser action: each call is one more request that re-reads the whole
# context, which is where the tokens go. Real app builds took 100-150 calls
# before browser_batch was suggested, so they may need one "Anzo, sigue".
MAX_TOOL_CALLS = int(os.environ.get("ANZO_MAX_TOOL_CALLS", "").strip() or 60)

# Sessions whose last turn hit MAX_TOOL_CALLS. The next message on that session
# carries a note saying so, so Claude doesn't pick the same loop back up. One
# line with no "%": it goes through cmd.exe as a -p argument (see summarize()).
_capped_sessions: set = set()
_CAPPED_NOTE = ("(Nota de ANZO: detuve tu turno anterior porque llego al maximo "
                "de acciones sin terminar. Si estabas repitiendo intentos sobre el "
                "mismo paso, no insistas igual: prueba otra forma o pidele ayuda "
                "al usuario.) ")

# "Screenshot saved to: C:\...\claude-chrome-screenshots-XXXX\screenshot-N.jpg"
# -- the text the extension's screenshot tool returns with save_to_disk=true.
_SAVED_RE = re.compile(r"(?:saved to|guardad[oa] en):?\s*(\S.+?\.(?:png|jpe?g|gif|webp))",
                       re.IGNORECASE)

# One Claude subprocess at a time. Guarded so a new voice instruction can
# interrupt whatever is currently running.
_active_lock = threading.Lock()
_active_proc: subprocess.Popen | None = None


def child_env() -> dict:
    """Copy of the environment with anything that would redirect billing removed."""
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(SCRUBBED_ENV_PREFIXES) and k not in SCRUBBED_ENV_KEYS
    }
    # The CLI makes a separate small-model request per session just to write a
    # title -- pure waste here (nobody sees it) and one more call against the
    # membership's limits.
    env["CLAUDE_CODE_DISABLE_TERMINAL_TITLE"] = "1"
    return env


def is_limit_error(text) -> bool:
    """Does this message look like 'you ran out of tokens/quota'?"""
    text = (text or "").strip()
    return bool(text) and len(text) <= _LIMIT_MAX_LEN and bool(_LIMIT_RE.search(text))


def _limit_message(detail: str) -> str:
    return ("Llegaste al limite de uso de tu membresia de Claude. " + detail)[:400]


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
        # Claude in Chrome integration: the extension in the user's own Chrome
        # becomes the browser (mcp__claude-in-chrome__* tools).
        "--chrome",
    ]
    if _valid_session(session_id):
        cmd += ["--resume", str(session_id)]
    if MODEL:
        cmd += ["--model", MODEL]
    if os.path.isfile(CLAUDE_SETTINGS):
        cmd += ["--settings", CLAUDE_SETTINGS]
    if PERMISSION_MODE:
        cmd += ["--permission-mode", PERMISSION_MODE]
    # Headless mode has no one to answer a permission prompt, so the browser
    # tools have to be pre-approved or every action is silently denied. The
    # whole claude-in-chrome server (sites are still gated by the extension's
    # own site permissions), Skill for the trading-chart-analysis skill under
    # .claude/skills/ (it only loads instructions), and writes limited to
    # OUTPUT_DIR.
    cmd += ["--allowedTools", "mcp__claude-in-chrome,Skill",
            f"Edit({_permission_path(OUTPUT_DIR)}/**)"]
    cmd += ["--add-dir", OUTPUT_DIR]
    cmd += ["--append-system-prompt", SYSTEM_PROMPT]
    return cmd


def _kill_tree(proc: subprocess.Popen):
    """Stop a claude subprocess for real. On Windows `proc` is the cmd.exe that
    shell=True puts in front of claude.cmd: proc.terminate() only kills that
    cmd.exe and leaves claude itself running (and clicking) in the background,
    orphaned. taskkill /T takes the whole tree down -- the same fix the
    original ANZO needed for Playwright MCP's node.exe."""
    if IS_WINDOWS:
        try:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        proc.kill()
    except OSError:
        pass


def cancel_active() -> bool:
    """Interrupt whatever ANZO is currently doing. Called when new speech
    arrives mid-turn. Killing the subprocess is the whole mechanism -- the
    next turn resumes the same session via --resume, so no context is lost."""
    with _active_lock:
        proc = _active_proc
    if proc is None or proc.poll() is not None:
        return False
    _kill_tree(proc)
    return True


def _collect_screenshot(block) -> str | None:
    """If this tool result says the extension saved a screenshot to disk, copy
    it into OUTPUT_DIR with a readable name and return the new path. Done here,
    in ANZO's own process, so Claude never needs a file-copy tool."""
    content = block.get("content")
    parts = content if isinstance(content, list) else [{"type": "text", "text": content or ""}]
    for part in parts:
        if not isinstance(part, dict) or part.get("type") != "text":
            continue
        m = _SAVED_RE.search(part.get("text") or "")
        if not m:
            continue
        src = m.group(1).strip().strip('"')
        if not os.path.isfile(src):
            continue
        try:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            ext = os.path.splitext(src)[1].lower() or ".jpg"
            dst = os.path.join(OUTPUT_DIR, f"captura_{stamp}{ext}")
            n = 2
            while os.path.exists(dst):
                dst = os.path.join(OUTPUT_DIR, f"captura_{stamp}_{n}{ext}")
                n += 1
            shutil.copy2(src, dst)
            return dst
        except OSError:
            return None
    return None


def run(message: str, session_id: str | None = None):
    """One turn. Generator yielding dicts describing what Claude is doing, as
    it happens:
    {t: "status", model, tools, mcp}
    {t: "delta", text}                    -- streamed narration text
    {t: "tool", phase: "use"/"result", name, input?, ok?}
    {t: "saved", path}                    -- a screenshot copied to OUTPUT_DIR
    {t: "warning", message}
    {t: "usage", input_tokens, output_tokens}
    {t: "complete", session_id, ms}
    {t: "error", message}
    {t: "interrupted"}
    """
    global _active_proc

    if session_id in _capped_sessions:
        _capped_sessions.discard(session_id)
        message = _CAPPED_NOTE + message
    cmd = build_command(message, session_id)
    popen_kwargs = dict(
        cwd=WORKDIR,
        text=True,
        # Windows' default subprocess text decoding uses the system locale
        # codepage (e.g. cp1252), not UTF-8 -- claude's stdout is UTF-8, so
        # without this every accented character comes back mojibake'd.
        # errors="replace" keeps a rare bad byte from crashing the stream.
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=child_env(),
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
    tool_calls = 0

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
                    _kill_tree(proc)
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
                servers = {s.get("name"): s.get("status") for s in (ev.get("mcp_servers") or [])}
                chrome = servers.get("claude-in-chrome")
                if chrome != "connected":
                    # "warning", not "error": the turn keeps going (it may not
                    # need the browser), so the stream must stay open.
                    yield dict(t="warning", message=(
                        "La extension Claude in Chrome no esta conectada"
                        + (f" ({chrome})" if chrome else "")
                        + ": abre Chrome y revisa que la extension este activa."))
                for err in ev.get("mcp_server_errors") or []:
                    yield dict(t="warning", message=(
                        f"MCP server '{err.get('name')}' failed to load "
                        f"({err.get('type')}): {err.get('message')}"))
                yield dict(
                    t="status",
                    model=ev.get("model") or MODEL or "default",
                    tools=len(ev.get("tools") or []),
                    mcp=list(servers),
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
                        _kill_tree(proc)
                        yield dict(t="error", message=_limit_message(block["text"].strip()))
                        return
                    if btype == "text" and not streamed_text and block.get("text"):
                        text_seen = True
                        yield dict(t="delta", text=block["text"])
                    elif btype == "tool_use":
                        tool_calls += 1
                        yield dict(t="tool", phase="use", name=block.get("name", "tool"),
                                   input=block.get("input", {}))
                        if MAX_TOOL_CALLS and tool_calls >= MAX_TOOL_CALLS:
                            # A normal "complete", not an error: the session is
                            # fine and "Anzo, sigue" resumes it where it stopped.
                            _kill_tree(proc)
                            if _valid_session(emitted_session):
                                _capped_sessions.add(emitted_session)
                            # Don't have ANZO say the wake word or the exact phrase
                            # the user must answer with: the UI's echo filter
                            # (looksLikeEcho in ui/app.js) drops any heard phrase
                            # found in what was just spoken, so "dime: Anzo, sigue"
                            # made the real "Anzo, sigue" get ignored as echo.
                            yield dict(t="delta", text=(
                                f"\nLlevo {tool_calls} acciones en esta tarea y todavía "
                                "no termino, así que paré para no gastar tus tokens "
                                "de más. Si voy bien, dime que siga. Si me ves "
                                "enredado, dime cómo hacerlo o hazlo tú."))
                            yield dict(t="complete", session_id=emitted_session,
                                       ms=int((time.monotonic() - started) * 1000))
                            return
                continue

            if kind == "user":
                for block in (ev.get("message") or {}).get("content") or []:
                    if block.get("type") == "tool_result":
                        saved = _collect_screenshot(block)
                        if saved:
                            yield dict(t="saved", path=saved)
                        yield dict(t="tool", phase="result",
                                   ok=not block.get("is_error"),
                                   name=block.get("name", ""))
                continue

            if kind == "result":
                usage = ev.get("usage") or {}
                if not text_seen and is_limit_error(ev.get("result")):
                    yield dict(t="error", message=_limit_message(str(ev["result"]).strip()))
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
            _kill_tree(proc)
            yield dict(t="error", message=f"lost the claude output stream: {pump_error[0]}"[:400])
            return

        try:
            rc = proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # pump_out saw EOF (done.set()) but the process itself hasn't
            # exited yet -- give it a moment, then stop waiting on it rather
            # than crash the request thread.
            _kill_tree(proc)
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
                    yield dict(t="error", message=_limit_message(err_text[:_LIMIT_MAX_LEN]))
                    return
                yield dict(t="error", message=(err_text
                                               or f"claude exited with code {rc}")[:500])
            return
        yield dict(t="complete", session_id=emitted_session,
                   ms=int((time.monotonic() - started) * 1000))
    finally:
        if proc.poll() is None:
            # Usually the CLI is just exiting after its "result" event; give
            # it a moment to finish writing the session before forcing it.
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                _kill_tree(proc)
        with _active_lock:
            if _active_proc is proc:
                _active_proc = None


def summarize(exchanges: list[tuple[str, str]]) -> str:
    """One-shot, non-streaming claude -p call that condenses a list of
    (user_message, anzo_reply) pairs into a short Spanish summary for
    Anzo/Bitacora/. No tools at all (--tools ""), no --chrome. Deliberately not
    run after every turn -- server.py only calls this on an idle gap or clean
    shutdown, so it doesn't multiply usage against the membership's limits.

    Runs from a neutral temp directory, NOT WORKDIR: the project directory also
    auto-loads this project's own Claude Code memory/CLAUDE.md, which once made
    a test summary talk about ANZO itself instead of the sample exchange.

    The prompt is piped via stdin, NOT passed as the -p positional argument: a
    multi-line argument gets silently truncated at the first newline when
    routed through cmd.exe (shell=True, needed for the claude.cmd shim)."""
    if not exchanges:
        return ""
    transcript = "\n\n".join(f"Usuario: {u}\nAnzo: {a}" for u, a in exchanges)
    prompt = (
        "Resumi en espanol, en 2 a 4 frases cortas, de que trato esta "
        "conversacion entre el usuario y ANZO (un asistente de voz). Texto "
        "plano, sin markdown ni listas.\n\n" + transcript
    )
    cmd = [_resolve_claude(), "-p", "--tools", ""]
    if MODEL:
        cmd += ["--model", MODEL]
    if os.path.isfile(CLAUDE_SETTINGS):
        cmd += ["--settings", CLAUDE_SETTINGS]
    popen_kwargs = dict(
        cwd=tempfile.gettempdir(), text=True, encoding="utf-8", errors="replace",
        capture_output=True, env=child_env(), input=prompt,
    )
    if IS_WINDOWS:
        popen_kwargs["shell"] = True
    try:
        result = subprocess.run(cmd, timeout=60, **popen_kwargs)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""
    out = result.stdout.strip()
    if result.returncode != 0 or is_limit_error(out):
        return ""
    return out
