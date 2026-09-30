# ANZO + Claude

Asistente de voz personal que orquesta a Claude para desarrollar y diagnosticar Microsoft Power Platform (Canvas Apps + Power Automate) y analizar gráficos de trading, controlando **tu propio Chrome** con la extensión **Claude in Chrome** — sin APIs ni app registrations, usando las sesiones que ya tienes abiertas.

Es una copia independiente de ANZO (`C:\dev\anzo`, en GitHub) que **no tiene router ni otros proveedores**: solo usa tu cuenta de Claude (login de claude.ai) y la extensión. No está conectada a GitHub.

## Palabra clave

"Anzo" o "Hola Anzo". Mientras trabaja, solo se interrumpe si dices "Anzo" ("Anzo, para" lo detiene; "Anzo, <otra instrucción>" cambia la tarea).

## Cómo se abre

Doble clic en el acceso directo **ANZO + Claude** del Escritorio (o en `Anzo.pyw`). Abre la ventana de la app y, si tu Chrome estaba cerrado, lo abre (la extensión vive ahí). **Cerrar la ventana cierra ANZO**, pero tu Chrome queda abierto. Sin consola; el detalle queda en `logs/anzo.log`. Para crear el acceso directo en otra máquina: `powershell -File scripts\install-shortcut.ps1`.

No arranca solo con Windows.

## Requisitos

- Claude Code (`claude`) con sesión iniciada con tu cuenta de claude.ai (plan Pro, Max, Team o Enterprise). La integración con Chrome no funciona con clave de API.
- Extensión [Claude in Chrome](https://chromewebstore.google.com/detail/claude/fcoeoabgfenejglbffodgkkbkcdhcgfn) instalada en tu perfil de Chrome (por defecto `Default`).
- Python 3 (solo librería estándar).

## Cómo trabaja

- Cada pedido corre `claude -p --chrome` con `--settings anzo-claude-settings.json`, que fuerza el endpoint oficial de Anthropic y tu login aunque la configuración global de Claude Code apunte a otro lado.
- Claude abre sus pestañas en un grupo propio dentro de tu Chrome y las deja abiertas entre turnos.
- Solo puede guardar en `Escritorio\ANZO archivos`: las capturas que pidas se copian ahí solas y los archivos de texto se escriben ahí.
- La pantalla muestra qué modelo respondió el último turno.

Opciones (todas opcionales) en `.env`, ver `.env.example`: `ANZO_MODEL`, `ANZO_PORT` (8740; la ANZO original usa 8730), `ANZO_CHROME_PROFILE`, `ANZO_OUTPUT_DIR`.

## Notas

Ver `Anzo/` (vault de Obsidian): `Decisiones.md` explica por qué existe esta versión y cómo se probó.
