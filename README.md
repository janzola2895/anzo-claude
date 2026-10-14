# ANZO + Claude

Asistente de voz personal que orquesta a Claude para desarrollar y diagnosticar Microsoft Power Platform (Canvas Apps + Power Automate) y analizar gráficos de trading, controlando **tu propio Chrome** con la extensión **Claude in Chrome** — sin APIs ni app registrations, usando las sesiones que ya tienes abiertas.

Es una copia independiente de ANZO (`C:\dev\anzo`) que **no tiene router ni otros proveedores**: solo usa tu cuenta de Claude (login de claude.ai) y la extensión. El código vive en un repo privado de GitHub: [janzola2895/anzo-claude](https://github.com/janzola2895/anzo-claude).

## Palabra clave

"Anzo" o "Hola Anzo". Mientras trabaja, solo se interrumpe si dices "Anzo" ("Anzo, para" lo detiene; "Anzo, <otra instrucción>" cambia la tarea).

## Modo oro

"Viernes modo oro" (o "Anzo, modo oro"): ANZO hace el análisis completo de XAUUSD intradía en TradingView (calendario económico, H4/H1/M15/M5, dólar DXY) y termina siempre en uno de tres veredictos: **hay setup válido** (entrada, stop, objetivos), **esperar** a que el oro llegue a un precio concreto para reevaluar ahí, o **no hay setup**. Cuando el oro llega al precio, vuelves a decir "modo oro" y reevalúa. El detalle (tabla de filtros y confluencias) queda en `Escritorio\ANZO archivos\modo-oro.md`. Solo analiza: nunca abre ni cierra operaciones. Protocolo en `.claude/skills/modo-oro/SKILL.md`.

## Cómo se abre

Doble clic en el acceso directo **ANZO + Claude** del Escritorio (o en `Anzo.pyw`). Abre la ventana de la app y, si tu Chrome estaba cerrado, lo abre (la extensión vive ahí). **Cerrar la ventana cierra ANZO**, pero tu Chrome queda abierto. Sin consola; el detalle queda en `logs/anzo.log`. Para crear el acceso directo en otra máquina: `powershell -File scripts\install-shortcut.ps1`.

No arranca solo con Windows.

## Requisitos

- Claude Code (`claude`) con sesión iniciada con tu cuenta de claude.ai (plan Pro, Max, Team o Enterprise). La integración con Chrome no funciona con clave de API.
- Extensión [Claude in Chrome](https://chromewebstore.google.com/detail/claude/fcoeoabgfenejglbffodgkkbkcdhcgfn) instalada en tu perfil de Chrome (por defecto `Default`).
- Python 3 (solo librería estándar).

## Instalar en otra máquina

```bash
git clone https://github.com/janzola2895/anzo-claude.git
cd anzo-claude
cp .env.example .env   # opcional: solo si quieres cambiar algún valor por defecto
```

Luego cumple los requisitos de arriba, crea el acceso directo (`powershell -File scripts\install-shortcut.ps1`) y carga la mini extensión de `chrome-extension/` (ver "Grupo de pestañas"). El repo es privado: hace falta iniciar sesión en GitHub con una cuenta que tenga acceso.

## Cómo trabaja

- Cada pedido corre `claude -p --chrome` con `--settings anzo-claude-settings.json`, que fuerza el endpoint oficial de Anthropic y tu login aunque la configuración global de Claude Code apunte a otro lado.
- Claude abre sus pestañas en un grupo propio dentro de tu Chrome y las deja abiertas entre turnos.
- Solo puede guardar en `Escritorio\ANZO archivos`: las capturas que pidas se copian ahí solas y los archivos de texto se escriben ahí.
- La pantalla muestra qué modelo respondió el último turno.
- Si un paso no le sale en 3 intentos, se detiene y pide ayuda. Como respaldo, a las 60 acciones en un mismo pedido para y pregunta si sigue ("Anzo, sigue"), para que un bucle no se coma el cupo.

Opciones (todas opcionales) en `.env`, ver `.env.example`: `ANZO_MODEL`, `ANZO_PORT` (8740; la ANZO original usa 8730), `ANZO_CHROME_PROFILE`, `ANZO_OUTPUT_DIR`, `ANZO_MAX_TOOL_CALLS` (60; 0 = sin tope).

## Grupo de pestañas "AnzoBot"

La extensión Claude in Chrome llama "Claude" al grupo de pestañas donde trabaja. La mini extensión de `chrome-extension/` (solo pide permiso sobre grupos de pestañas) lo renombra a **AnzoBot** y conserva los indicadores de estado (⌛ trabajando, 🔔 te necesita, ✅ terminó). Se instala una vez:

1. En Chrome abre `chrome://extensions`.
2. Activa **Modo de desarrollador** (arriba a la derecha).
3. Pulsa **Cargar descomprimida** y elige la carpeta `chrome-extension` de este repo (en esta máquina, `C:\dev\anzo-claude\chrome-extension`).

## Notas

Ver `Anzo/` (vault de Obsidian): `Decisiones.md` explica por qué existe esta versión y cómo se probó.

`Anzo/Bitacora/` guarda un resumen de cada conversación con ANZO y se sube al repo junto con el código. Por eso el repo debe seguir siendo privado.
