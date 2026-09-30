"""Double-click launcher for ANZO + Claude (no console window).

Runs under pythonw.exe, which has no console, so stdout/stderr go to
logs/anzo.log instead -- and are pointed there at the OS level, so the child
processes server.py starts (Chrome, Playwright MCP, ccr) inherit the log rather
than a dead handle that would block them once its pipe buffer fills.

Opens ANZO's app window right away; closing that window quits ANZO (the
user's own Chrome stays open). If it is already running it just opens another window
onto it (see server.main)."""
import ctypes
import msvcrt
import os
import sys
import traceback
from ctypes import wintypes

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

log_dir = os.path.join(ROOT, "logs")
os.makedirs(log_dir, exist_ok=True)
log_path = os.path.join(log_dir, "anzo.log")
# Keep the log from growing forever: start a fresh one past ~1 MB.
if os.path.exists(log_path) and os.path.getsize(log_path) > 1_000_000:
    os.replace(log_path, log_path + ".old")

if sys.stdout is None or sys.stderr is None:  # pythonw: no console attached
    log = open(log_path, "a", buffering=1, encoding="utf-8")
    nul = open(os.devnull, "r")
    k32 = ctypes.windll.kernel32
    k32.SetStdHandle.argtypes = [wintypes.DWORD, wintypes.HANDLE]
    k32.SetStdHandle(wintypes.DWORD(-10 & 0xFFFFFFFF), msvcrt.get_osfhandle(nul.fileno()))
    k32.SetStdHandle(wintypes.DWORD(-11 & 0xFFFFFFFF), msvcrt.get_osfhandle(log.fileno()))
    k32.SetStdHandle(wintypes.DWORD(-12 & 0xFFFFFFFF), msvcrt.get_osfhandle(log.fileno()))
    sys.stdin, sys.stdout, sys.stderr = nul, log, log

print("\n=== ANZO + Claude start ===", flush=True)
try:
    import server
    server.main()
except Exception:
    traceback.print_exc()
    ctypes.windll.user32.MessageBoxW(
        0, f"ANZO + Claude no pudo iniciar.\nMira el detalle en:\n{log_path}", "ANZO + Claude", 0x10)
