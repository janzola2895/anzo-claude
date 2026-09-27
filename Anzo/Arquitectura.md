# Arquitectura

Estado: primer flujo completo funcionando de punta a punta (2026-09-27).

```
Tu navegador normal (Chrome, se abre solo al iniciar server.py)
  http://127.0.0.1:8730 — interfaz de voz de ANZO (ui/index.html + app.js)
        │
        │  reconocimiento de voz continuo (Web Speech API del navegador, gratis)
        │  detecta "Anzo" / "Hola Anzo" / "Yarvis" / "Jarvis" / "Viernes"
        ▼
server.py (Python stdlib, sin pip installs)
  - GET /api/stream  → Server-Sent Events, un turno de conversación
  - POST /api/interrupt → mata el proceso claude -p activo
  - Al arrancar, lanza y administra DOS procesos propios (independientes
    de cada turno de conversación):
      1. Chrome dedicado, con puerto de depuración (start_chrome)
      2. Playwright MCP, conectado a ESE Chrome vía CDP (start_browser_mcp)
        │
        ▼
brain.py — por cada turno, un proceso nuevo:
  claude -p "<mensaje>" --output-format stream-json --include-partial-messages
            --resume <session_id> --permission-mode acceptEdits
            --mcp-config mcp-config.json --allowedTools mcp__browser
            --append-system-prompt "<instrucciones de ANZO>"
        │
        │  entorno limpiado de ANTHROPIC_*/CLAUDE_CODE_* — nunca --bare
        │  → corre sobre la suscripción de Claude del usuario, $0 por token
        ▼
Texto de respuesta en streaming, fragmentado por oraciones
        │
        ▼
speechSynthesis del navegador (voz de Windows) — markdown limpiado antes de hablar
```

**La ventana de Chrome dedicada (Power Apps/Automate) es una cosa aparte de tu navegador normal.** No se debe usar esa ventana para cargar la interfaz de voz — son dos procesos/perfiles distintos a propósito (ver [[Problemas resueltos]], "la pestaña se navegaba sola").

## Por qué cada turno es un proceso nuevo, no uno persistente

`claude -p` se relanza en cada turno (no es un proceso único que vive toda la conversación). El contexto se mantiene con `--resume <session_id>`, que Claude Code guarda en su propio historial de sesión. Interrumpir = matar ese proceso (`brain.cancel_active()` → `proc.terminate()`); el siguiente turno retoma con `--resume` sin perder contexto. Este patrón viene de estudiar el código real de `Itsme23476/jarvis-claude-code` (no se copió el código, se reescribió el mecanismo).

## Por qué el navegador vive en procesos separados de cada turno

Playwright MCP cierra el navegador que él mismo lanza en cuanto su cliente MCP se desconecta ("connection-is-a-lifetime", confirmado por su propio mantenedor — no es configurable). Como cada turno de `claude -p` es un cliente MCP que se conecta y se desconecta, el navegador se cerraba al terminar cada turno. Solución: `server.py` lanza Chrome por su cuenta (proceso propio, vive mientras viva `server.py`) y Playwright MCP solo se **conecta** a él por CDP (`--cdp-endpoint`) en vez de lanzarlo y ser dueño de él. Detalle completo en [[Problemas resueltos]].

## Archivos clave

| Archivo | Qué hace |
|---|---|
| `server.py` | Servidor HTTP local, orquesta Chrome + Playwright MCP, puente SSE hacia el navegador |
| `brain.py` | Arma y lanza cada turno de `claude -p`, parsea su salida `stream-json` |
| `mcp-config.json` | Le dice a `claude -p` cómo conectarse al Playwright MCP (transporte SSE, no HTTP moderno — ver [[Problemas resueltos]]) |
| `ui/app.js` | Reconocimiento de voz, palabras clave, interrupción, texto a voz |
| `.browser-profile/` | Perfil persistente de Chrome (sesión de Power Apps) — no versionado |
| `.playwright-mcp/` | Trazas/capturas propias de Playwright MCP — no versionado |
