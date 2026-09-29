# Decisiones

- **Nombre del asistente:** ANZO
- **Palabra clave de activación:** "Anzo" o "Hola Anzo"
- **Repositorio de código:** `C:\dev\anzo`
- **Notas del proyecto:** esta bóveda de Obsidian, `C:\dev\anzo\Anzo`
- **Enfoque de control de pantalla:** navegador (Playwright vía MCP, sobre el perfil real de Chrome del usuario) — no API/OAuth propio a Power Platform, por decisión de IT de Indra.
- **Objetivo funcional:** desarrollar y diagnosticar Canvas Apps y flujos de Power Automate por instrucción de voz, con narración hablada e interrupción en caliente.

## Motor de Claude: sin API key, sobre la suscripción

El Claude Agent SDK oficial **requiere API key de pago** (no permite reusar el login/suscripción para apps de terceros). En vez de eso, ANZO usa la CLI de Claude Code directamente en modo headless:

```
claude -p "<mensaje>" --output-format stream-json --include-partial-messages --verbose [--resume <session_id>]
```

Esto autentica igual que cualquier sesión interactiva (con la suscripción), sin costo por token. Nunca usar `--bare` ni definir `ANTHROPIC_API_KEY`/`CLAUDE_CODE_*` en el entorno del proceso — eso fuerza autenticación por API key silenciosamente.

Confirmado como patrón real y probado en dos proyectos open-source:
- [ethanplusai/jarvis](https://github.com/ethanplusai/jarvis) — mayordomo completo con dashboard, pero macOS-only (AppleScript) y requiere Fish Audio de pago.
- [Itsme23476/jarvis-claude-code](https://github.com/Itsme23476/jarvis-claude-code) — más simple, sin dependencias de macOS, memoria en bóveda de Obsidian, voz gratis por defecto (Web Speech API del navegador). Base elegida para ANZO.

Ambos clonados y su código real leído en `C:\dev\_ref\` (temporal, no versionado) para copiar el mecanismo exacto: interrumpir = matar el proceso `claude -p` activo (`proc.terminate()`), cada turno relanza el proceso con `--resume <uuid>` para mantener contexto.

## Hito: núcleo validado (2026-09-27)

`brain.py` probado de punta a punta en la máquina real del usuario: `claude -p` autentica con la suscripción (modelo `claude-sonnet-5`, cero errores de login), el streaming oración/fragmento por fragmento funciona, y ya trae conectados los MCP propios de la cuenta claude.ai (Drive, Gmail, Calendar, Docs). Pendiente: requirió instalar la CLI standalone (`npm install -g @anthropic-ai/claude-code`) aparte de la app de escritorio — no venía incluida.

**Lección operativa importante:** los comandos que Claude Code ejecuta por su cuenta (vía su propia terminal) corren en un entorno aislado del escritorio real del usuario — instalaciones globales de npm y el login de `claude` hecho ahí NO se reflejan en las terminales reales del usuario, y viceversa. Cualquier instalación de paquete o login debe pedírsele al usuario que lo corra él mismo en su propia terminal; los archivos de texto (crear/editar código) sí se comparten normalmente entre ambos entornos.

## Hito: primer flujo completo funcionando (2026-09-27)

Voz → Claude → navegador → Power Apps, de punta a punta, en la máquina real. Ver [[Arquitectura]] para cómo queda armado y [[Problemas resueltos]] para la bitácora completa de cada bug encontrado en el camino (varios fueron bastante enredados — vale la pena leerla antes de tocar `server.py`/`brain.py`/`mcp-config.json`).

Palabras clave activas: "Anzo", "Hola Anzo", "Yarvis"/"Jarvis", "Viernes" (referencias a Iron Man).

## Mejoras aplicadas (2026-09-27, segunda ronda)

- **Interrupción más robusta:** se ignora habla que coincide con lo que Anzo acaba de decir (filtro de eco por similitud de texto — no es cancelación acústica real, la Web Speech API no da acceso a eso, pero funciona razonablemente bien). Además, después de que un turno termina, se sigue escuchando sin pedir la palabra clave de nuevo durante 12 segundos — para responder una pregunta de Anzo o corregirlo rápido sin repetir "Anzo" cada vez.
- **Voz:** se agregó preferencia por voces "Google" de Chrome (gratis, sin instalar nada) como segunda opción antes de caer a la voz robótica de Windows.
- **Permisos acotados:** se quitó `acceptEdits` del `--permission-mode` (quedó vacío = modo Manual de la CLI). Con `--allowedTools mcp__browser` ya alcanza para lo que ANZO hace hoy; cualquier otra cosa (editar archivos, comandos de sistema) ahora queda bloqueada en vez de auto-aprobada.
- Se borró `C:\dev\_ref\` (clones temporales de referencia, ya no se necesitaban).

## Hito: login real y navegación confirmados (2026-09-27)

El usuario inició sesión con sus credenciales reales de Indra en la ventana de Chrome dedicada, y Anzo pudo navegar por sus apps de Power Apps. Voz "Google" de Chrome confirmada como notablemente más natural que la de Windows. Con esto, todo el flujo (voz → Claude → navegador → sesión real → navegación) queda validado de punta a punta.

## Ampliación: análisis de gráficos de trading (2026-09-28)

Anzo ahora también puede analizar gráficos de trading (XAUUSD y similares) que estén visibles en la ventana de Chrome dedicada — no solo Power Platform. Decisiones del usuario: estilo intradía (M5-M15-H1), y combinar varias estrategias (price action/estructura, medias móviles, momentum RSI/MACD, Fibonacci/SMC-ICT) en vez de depender de un solo indicador, para tener una visión amplia del mercado.

**Implementación:** skill de Claude Code dedicada en `.claude/skills/trading-chart-analysis/SKILL.md` (no una simple ampliación del system prompt) — el usuario prefirió esta opción por ser más estructurada y fácil de ampliar después, aunque implica reabrir un poco el permiso que se había cerrado en el endurecimiento anterior. Cambios en `brain.py`:
- `--allowedTools` pasó de `"mcp__browser"` a `"mcp__browser,Skill"`. La herramienta `Skill` solo carga instrucciones a el contexto — no tiene acceso a archivos ni shell por su cuenta — así que el blast radius real (qué puede *hacer* Anzo) no cambió, solo qué puede *leer como instrucción*. Nota: `--allowedTools` no tiene una sintaxis confirmada para restringir a una sola skill (tipo `Skill(nombre)`, como sí existe para `Bash(git *)`) — quedó como allowlist del tool completo, que también destraba en teoría las demás skills instaladas a nivel de usuario/plugin (docx, pdf, xlsx, deep-research, etc.), aunque siguen sin poder *ejecutar* nada real sin Bash/Edit/Write.
- `BROWSER_SYSTEM_PROMPT` amplió su frase de rol (ya no dice solo "Power Platform") y agregó una línea explícita diciendo que use la herramienta Skill para pedidos de análisis de gráficos/trading — igual que con el browser tool, la lección ya aprendida en este proyecto es que sin instrucción explícita Claude no siempre usa lo que tiene disponible.

**Límite de diseño, no negociable:** la skill nunca da un "opera / no operes" como asesoría financiera personalizada — siempre lectura técnica educativa, decisión final del usuario. Igual de importante: instruye a tomar una captura visual real de la pantalla (no el snapshot de accesibilidad/texto de Playwright MCP, que no sirve para leer velas ni indicadores).

## Hito: primera prueba real de análisis de trading (2026-09-28)

Probado en vivo el mismo día: "abre TradingView" → navegó y lo abrió (por defecto mostraba AAPL); pedido de cambiar a XAUUSD por voz (con varias interrupciones en el camino mientras buscaba el símbolo — ver nota de falsos positivos más abajo); "analiza el gráfico, ¿hay oportunidad de operar a la alza o a la baja?" → **la skill se disparó sola, sin nombrarla** (confirma que la descripción del SKILL.md dispara bien). Cambió el gráfico a velas de 15 minutos por su cuenta (intradía, como quedó definido), tomó capturas reales, y dio una lectura combinando las cuatro lentes que pide la skill — dijo explícitamente que no había RSI/MACD/medias agregadas al gráfico en vez de inventar valores, y cerró con el disclaimer obligatorio casi textual al ejemplo del SKILL.md. Validación de punta a punta: exitosa.

Al pedirle "agrega los indicadores que hagan falta", el proceso se cortó a mitad de camino con `You've hit your weekly limit · resets 11pm (America/Bogota)` — el límite semanal del plan de Claude del usuario, no un bug de `server.py`/`brain.py`. Las 2 últimas interacciones se quedaron pensando y terminaron interrumpidas; coincide con el límite cortando la respuesta, posiblemente sumado al falso-positivo de interrupción por voz de fondo (limitación ya conocida, ver "Pendiente" más abajo).

## Segunda ronda de mejoras: UI, autostart, modo conversación, bitácora (2026-09-29)

Implementados los 4 pedidos priorizados de la lista de pendientes anterior. El punto de la interrupción por falsos positivos se revisó y se cierra sin cambio de código — ver la nota al final de esta sección.

**1. Interfaz — orbe de partículas con Three.js.** `ui/orb.js` (nuevo, ES module) reemplaza el `<div id="orb">` de CSS puro por un `<canvas>` con una esfera de ~650 partículas (`THREE.Points`), cargado vía `<script type="importmap">` apuntando a `three@0.160.1` en jsdelivr (sin instalar nada, igual que el resto del front end). Mantiene los mismos 4 estados que ya manejaba `app.js` (idle/listening/working/speaking) y la misma paleta de color — `setOrb(cls)` en `app.js` ahora llama a `window.setOrbState(cls)`, con guard (`if (window.setOrbState)`) para que un fallo del CDN no rompa el reconocimiento de voz, que es lo que de verdad importa. Verificado sirviendo `ui/` suelto con `python -m http.server` (nuevo `.claude/launch.json`, útil para iterar la UI sin levantar Chrome/voz) y abriéndolo en un navegador aislado: las partículas renderizan y los 4 estados cambian de color/pulso sin errores de consola.

**2. Autostart — tarea programada "al iniciar sesión", no servicio.** Se descartó un servicio real de Windows: corre en Session 0, sin escritorio, y no puede mostrar la ventana de Chrome ni usar el micrófono/parlantes de la sesión interactiva — limitación dura de Windows, no una preferencia. `scripts/install-autostart.ps1` (ya corrido, tarea `ANZO` registrada y en estado `Ready`) usa `Register-ScheduledTask` con trigger `AtLogOn` para el usuario actual, `RunLevel Limited` (sin admin), y reintentos automáticos (3 intentos, 1 min de espera) si falla al arrancar. `scripts/uninstall-autostart.ps1` la quita. Consola visible (no `pythonw`), a propósito, para poder ver errores de arranque de Chrome/Playwright MCP igual que corriéndolo a mano.

**3. Modo conversación.** Implementado en `ui/app.js` tal como quedó anotado abajo en la nota técnica anterior: "Anzo, modo conversación" (o el botón nuevo en la UI) activa un modo donde `finishTurn()` ya no expira la ventana de escucha de 12s — queda escuchando indefinidamente sin repetir la palabra clave. "Pausa" detiene sin cerrar la sesión (solo reacciona a "continúa"/"sigamos" mientras está pausado); "Cambio y fuera" la termina y vuelve al modo normal. Las tres frases de control se interceptan antes de mandarse a Claude como instrucción, en cualquier estado (incluso interrumpiendo un turno en curso).

**4. Bitácora — resumen automático, no transcripción cruda.** `server.py` acumula en memoria los intercambios (usuario, respuesta) de cada turno completado (`record_exchange`, llamado desde `_handle_stream` solo en `complete`, no en error/interrupted). Un hilo de fondo revisa cada 2 minutos si pasaron >10 min de inactividad con intercambios sin resumir, y si es así dispara `brain.summarize()` — un `claude -p` nuevo, sin herramientas (`--tools ""`), sin streaming, que condensa esos intercambios en un resumen corto en español. También se dispara al cerrar `server.py` limpio. Se agrega a `Anzo/Bitacora/<YYYY-MM-DD>.md` (carpeta nueva), una entrada con hora por corte. Deliberadamente no es turno-a-turno para no multiplicar consumo contra el límite semanal (lección del 2026-09-28).

**Dos bugs reales encontrados probando `brain.summarize()` en vivo, antes de darlo por bueno:**
- Corriendo con `cwd=WORKDIR` (`C:\dev\anzo`, lo mismo que usa `run()`), el resumen salía contaminado con la memoria/contexto de Claude Code de este mismo proyecto en vez de resumir el intercambio de prueba — la auto-memoria y el `CLAUDE.md` se cargan por directorio de trabajo. Arreglo: `summarize()` corre con `cwd=tempfile.gettempdir()`, no `WORKDIR` — no necesita contexto de proyecto para nada.
- Pasar el prompt como argumento de `-p` (en vez de por stdin) truncaba todo lo que venía después del primer salto de línea — routing por `cmd.exe` (`shell=True`, necesario por el shim `claude.cmd`) no soporta bien un argumento multilínea. Arreglo: `summarize()` manda el prompt por stdin (`subprocess.run(..., input=prompt)`), `run()` no lo necesitó nunca porque los mensajes de voz son siempre de una sola línea — pero si algún día `run()` recibe un mensaje multilínea, tiene el mismo riesgo.

**Cierre del falso-positivo de interrupción (sin cambio de código):** se revisó si el problema del 2026-09-28 (interrupciones repetidas narrando en voz alta mientras se buscaba un símbolo) era causado por el límite semanal — no, ocurrió mucho antes de tocar el límite. Se decidió mantener el comportamiento actual a propósito: es barato de corregir gracias a `--resume`, y esa narración a veces sirve como feedback útil en vivo (pasó en la prueba real). Se cierra como decisión, no queda como pendiente.

## Pendiente / mejoras futuras

- Probar tareas reales de **desarrollo/diagnóstico** de Power Platform (editar un campo de una Canvas App, revisar el historial de un flujo de Power Automate, etc.) — la navegación y el análisis de trading ya se probaron en vivo, esto sigue siendo lo no probado del objetivo original
- Avisar **antes** de llegar al límite semanal de uso, no solo cuando ya se cortó — investigado el 2026-09-28: ni `claude auth status` ni `claude --help` exponen un porcentaje de uso restante; falta confirmar si `/usage` funciona en modo headless (`claude -p`) y da un número aprovechable
- El filtro de eco (para no confundir la propia voz de Anzo con una interrupción) sigue siendo una heurística de texto, no cancelación acústica real — usar audífonos sigue siendo lo más confiable si llega a molestar
- Probar en vivo que la tarea programada arranca sola en el próximo inicio de sesión de Windows (quedó verificada como registrada y `Ready`, pero no probada con un logon real todavía)
