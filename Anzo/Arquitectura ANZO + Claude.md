# Arquitectura — ANZO + Claude

Estado: funcionando de punta a punta desde el 2026-09-29 (probado sin ventana con el Chrome real del usuario). Es una copia independiente de la ANZO original; la arquitectura de la original sigue documentada en [[Arquitectura]].

```
Acceso directo "ANZO + Claude" (Escritorio, ícono naranja)
        │  pythonw.exe Anzo.pyw  (sin consola; salida en logs/anzo.log)
        ▼
server.py — 127.0.0.1:8740 (solo esta máquina, token por arranque)
  - GET /                → interfaz de voz (ui/index.html + app.js + orb.js)
  - GET /api/stream      → Server-Sent Events de un turno
  - GET /api/ready       → progreso del arranque para la ventana
  - GET /api/model       → modelo que respondió el último turno
  - POST /api/interrupt  → corta el turno en curso
  - Si tu Chrome normal está cerrado, lo abre (la extensión vive ahí). Nunca lo cierra.
  - Bitácora: resume las conversaciones en Anzo/Bitacora/
        │
        ├──► Ventana de la app: Chrome --app con perfil propio (.ui-profile/)
        │      reconocimiento de voz (Web Speech API) + voz de respuesta (speechSynthesis)
        │
        ▼
brain.py — un proceso nuevo por turno:
  claude -p "<mensaje>" --chrome --output-format stream-json --include-partial-messages
         --resume <session_id> --settings anzo-claude-settings.json
         --allowedTools mcp__claude-in-chrome,Skill  "Edit(<ANZO archivos>/**)"
         --add-dir "<ANZO archivos>" --append-system-prompt "<instrucciones de ANZO>"
        │  entorno limpio de ANTHROPIC_*/CLAUDE_CODE_*; nunca --bare
        │  → corre sobre tu membresía de Claude (login de claude.ai)
        ▼
Extensión Claude in Chrome (conector nativo com.anthropic.claude_code_browser_extension)
        │
        ▼
Tu Chrome de siempre (perfil Default), en un grupo de pestañas de Claude,
con tus sesiones ya iniciadas (Power Apps, Power Automate, TradingView...)
```

## Qué cambió respecto a la ANZO original

| | ANZO original (`C:\dev\anzo`) | ANZO + Claude (`C:\dev\anzo-claude`) |
|---|---|---|
| Modelo | Router (Gemini, OVH…) primero, membresía al final | Solo tu membresía de Claude |
| Navegador | Chrome aparte (`.browser-profile/`) + Playwright MCP | Tu Chrome normal + extensión Claude in Chrome |
| Procesos propios | Chrome, Playwright MCP (`npx`), router (`ccr`) | Ninguno aparte de la ventana |
| Puerto | 8730 | 8740 (pueden convivir) |
| GitHub | `janzola2895/anzo` | Sin remoto (solo local) |
| Autoarranque con Windows | Quitado el 2026-09-29 | No existe |

## Por qué `--settings anzo-claude-settings.json`

claude-code-router, al instalarse, reescribió la configuración **global** de Claude Code (`~/.claude/settings.json`): la dirección de la API apunta a su gateway y un `apiKeyHelper` le pasa a la CLI la clave del router. La CLI lee ese archivo en cada arranque, así que limpiar el entorno no basta. Este archivo del proyecto (sin secretos) vuelve a poner el endpoint oficial, el modelo `sonnet` y anula el `apiKeyHelper`, de modo que la CLI usa tu login de claude.ai. Además, la integración con Chrome **exige** ese login: con una clave la CLI la apaga. Si algún día se limpia la config global, este archivo no estorba.

## Pestañas entre turnos

La extensión agrupa las pestañas que abre Claude en un grupo ligado a la sesión. Como cada turno reanuda la misma sesión (`--resume`), el siguiente turno ve el mismo grupo y las mismas pestañas (probado). Al terminar un proceso, la CLI no cierra un grupo que tenga páginas. El prompt de ANZO le prohíbe a Claude cerrar pestañas salvo que el usuario lo pida, porque la skill `chrome-browser` (que se carga sola) le dice lo contrario. Claude solo actúa sobre las pestañas de su grupo: no ve las que el usuario abrió por su cuenta.

## Archivos y capturas

- Única carpeta de escritura: `Escritorio\ANZO archivos` (el Escritorio real, en OneDrive, se lee del registro de Windows).
- Capturas: Claude usa `computer` → `screenshot` con `save_to_disk`; la extensión la guarda en una carpeta temporal y responde `Screenshot saved to: <ruta>`. `brain._collect_screenshot()` la copia a `ANZO archivos` como `captura_<fecha>_<hora>.jpg` y la ventana muestra "Captura guardada". Claude no necesita permiso para copiar archivos.
- Archivos de texto (HTML, notas): `Write` en esa carpeta, gracias a la regla `Edit(...)` limitada a ella.
- Las capturas que Claude toma solo para mirar la pantalla no se guardan en ningún lado.

## Permisos

`claude -p` no puede mostrar avisos de aprobación: lo que no está permitido de antemano se rechaza en silencio. Permitido: todas las herramientas de la extensión, `Skill` (para la skill de trading) y escribir en `ANZO archivos`. Los sitios siguen sujetos a los permisos por sitio de la propia extensión: si Chrome pide permiso para un sitio nuevo, lo aceptas ahí.

## Archivos clave

| Archivo | Qué hace |
|---|---|
| `Anzo.pyw` | Lanzador de doble clic (sin consola), manda la salida a `logs/anzo.log` |
| `server.py` | Servidor local, abre la ventana, asegura que Chrome esté abierto, bitácora |
| `brain.py` | Arma cada turno de `claude -p --chrome`, lee su `stream-json`, copia capturas |
| `anzo-claude-settings.json` | Fuerza endpoint oficial + login de claude.ai (ver arriba) |
| `ui/app.js` | Palabra clave, interrupción, modo conversación, voz, línea del modelo |
| `ui/orb.js`, `ui/style.css` | Orbe animado y aspecto de la ventana |
| `.claude/skills/trading-chart-analysis/` | Skill de análisis técnico de gráficos |
| `scripts/install-shortcut.ps1` | Crea el acceso directo del Escritorio |
| `.env` (opcional, no versionado) | `ANZO_MODEL`, `ANZO_PORT`, `ANZO_CHROME_PROFILE`, `ANZO_OUTPUT_DIR` — ver `.env.example` |

## Pendiente / no probado todavía

- Voz real (micrófono y parlantes) en la ventana de ANZO + Claude; la primera vez pide permiso de micrófono.
- Tareas reales de Power Apps / Power Automate y TradingView con la extensión.
- Arranque con el Chrome del usuario **cerrado** (la apertura automática solo se probó con Chrome ya abierto).
- Qué pasa al llegar al límite de la membresía: debería mostrar "Llegaste al límite de uso de tu membresía de Claude", sin verificar en vivo.
- Si una página abre una alerta de JavaScript, la extensión deja de responder hasta cerrarla a mano en Chrome.
