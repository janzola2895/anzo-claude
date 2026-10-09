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
- Si la pestaña de la interfaz de voz queda minimizada/en segundo plano por un rato largo, Chrome puede retrasar temporizadores (`setTimeout`) del propio `app.js` — confirmado en pruebas que esto puede demorar mucho la recuperación de `inEchoWindow` (ver bug de abajo). En uso normal la pestaña suele quedar visible, pero si Anzo deja de reaccionar después de estar mucho tiempo sin usarse, esta es la primera sospechosa

- **Cupo de Gemini gratis (20 peticiones/día por modelo)** es muy poco para ANZO: decidir entre varios modelos Gemini como respaldo en cadena (cada uno con su propio cupo), activar facturación de pago por uso en el proyecto de Google (Flash cuesta centavos por día) u otro proveedor. Es el bloqueo actual del respaldo por CCR
- **Fallo rápido con el router:** hacer que Anzo avise de inmediato cuando un proveedor del router devuelve un límite (429), en vez de esperar el timeout de 180s. Pendiente de implementar en `brain.py`; solo hace falta si vuelve a pasar
- **Reaplicar el parche de CCR** para claves `AQ.` si se actualiza CCR con npm (ver "CCR probado en vivo") y Gemini vuelve a dar 401; o revisar si una versión nueva de CCR ya lo trae corregido
- Confirmar en uso real la ventana de app: permiso de micrófono la primera vez, voz de ida y vuelta, y que el acceso directo del Escritorio arranque todo. Decidir si la tarea de autoarranque `ANZO` se mantiene (abriría la ventana en cada inicio de sesión) o se desinstala con `scripts/uninstall-autostart.ps1`
- Cuando se reinicie el cupo de Codex (~2026-10-13) revisar si conviene dejarlo como respaldo o quitarlo de la regla

## ANZO como aplicación de escritorio (2026-09-29)

**Pedido:** abrir ANZO era tedioso (terminal, variables, `python server.py`); el usuario quería doble clic y una animación más elegante, sin bordes visibles.

**Decisión:** mantener la interfaz web y no pasarla a Tkinter. El reconocimiento de voz depende de la Web Speech API de Chrome (Tkinter no la tiene; WebView2 tampoco la garantiza). En su lugar `server.py` abre una ventana de aplicación de Chrome (`--app`, sin pestañas ni barra de direcciones) con su propio perfil (`.ui-profile/`), separado del Chrome de automatización (`.browser-profile/`) y del navegador diario del usuario, por el mismo motivo de siempre: si Claude navega la pestaña de la UI, ANZO se queda sordo.

**Cómo funciona:**
- `Anzo.pyw` (con `pythonw`, sin consola) redirige stdout/stderr a `logs/anzo.log` **a nivel del sistema operativo** (`SetStdHandle`), para que los procesos hijos (Chrome, Playwright MCP, `ccr`) hereden el archivo y no un handle muerto que los bloquearía al llenarse el pipe. Acceso directo con ícono en el Escritorio: `scripts/install-shortcut.ps1` (ícono generado con `scripts/make_icon.py`, solo librería estándar).
- La ventana abre **de inmediato**; el arranque lento (Chrome de trabajo, Playwright MCP, router) corre en un hilo aparte y la UI consulta `/api/ready` y muestra el paso actual ("Conectando las herramientas del navegador…"). Mientras no esté listo se ignora la voz.
- **Cerrar la ventana cierra ANZO** y lo que inició. Si ya hay una instancia corriendo (puerto ocupado, p. ej. la tarea de autoarranque), solo abre otra ventana sobre ella.
- `.env` (ignorado por git; plantilla `.env.example`) se lee al arrancar. Motivo: `ANZO_ROUTER`, `ANZO_ROUTER_KEY`, etc. solo existían `set` en la terminal del usuario, y un doble clic no los hereda: ANZO habría vuelto a usar solo la suscripción. Las variables reales del entorno siguen ganando sobre el archivo.
- Modos de UI con `ANZO_UI`: `app` (defecto), `browser` (pestaña del navegador por defecto, comportamiento anterior), `none`. `ANZO_NO_AUTOMATION=1` salta Chrome/MCP/router para probar solo la interfaz.

**Animación:** el "borde" era real. El lienzo era un cuadrado de 220 px y la esfera, al pulsar, se salía del cuadro y quedaba recortada. Ahora el lienzo cubre toda la ventana, las partículas son sprites redondos suaves con mezcla aditiva, hay un núcleo y un halo que llegan a transparente antes del borde, y un resplandor CSS (`#aura`) que cambia de color con el estado y se desvanece igual. El tamaño se recalcula con la ventana. El registro de la conversación se desvanece arriba en vez de cortarse.

**Arreglos de paso:**
- Micrófono denegado: `onend` reintentaba sin parar y llenaba el registro; ahora se detiene y pide dar permiso.
- `_stop()` solo terminaba el `cmd.exe` de `npx` y dejaba el `node.exe` de Playwright MCP vivo en el 8931 tras cerrar; ahora usa `taskkill /T`.

**Probado:** interfaz en el navegador aislado (estados y colores) y el ciclo completo con `pythonw` (abrir → `/api/ready` en ~4 s → cerrar ventana → sin procesos en 8731/8931). **No probado por mí:** voz real dentro de la ventana de la app; el permiso de micrófono se pide una vez en la ventana (perfil nuevo) y se recuerda. Three.js sigue viniendo de un CDN (jsdelivr); sin internet el orbe no se dibuja pero el resplandor CSS y todo lo demás funcionan.

## Menos peticiones por turno y modelo visible en pantalla (2026-09-29)

**Contexto:** con cupos gratis muy chicos (Gemini: 20 peticiones/día por modelo), cada petición cuenta. Medido en el log de CCR, cada llamada de la CLI iba acompañada de otra pequeña que solo pedía **el título de la sesión** ("Write the title in the predominant language…"), y la CLI reintenta los 429 hasta 10 veces.

**Cambios en `brain.py`:**
- `CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1` en todos los hijos: se acaba la petición del título (una menos por turno).
- Solo por el router: `CLAUDE_CODE_MAX_RETRIES` = `ANZO_ROUTER_MAX_RETRIES` (defecto 2, antes 10) y `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`.
- Los resúmenes de la bitácora ya no pasan por el router (gastaban el mismo cupo chico que los turnos en vivo): usan la suscripción, salvo `ANZO_ROUTER=always` o `ANZO_SUMMARY_VIA_ROUTER=1`.

**No resuelto:** con Gemini agotado el turno sigue sin fallar rápido. CCR respeta el `Retry-After` de Google (~41 s) y hace su propio respaldo antes de contestarle a la CLI, así que limitar los reintentos de la CLI solo no basta.

**Hallazgo importante:** el `~/.claude/settings.json` del usuario tiene `ANTHROPIC_BASE_URL` y `ANTHROPIC_MODEL` apuntando a CCR (CCR "tomó" el perfil global de Claude Code). Por eso **toda** llamada de la CLI en esta máquina, también el intento que ANZO cree "de suscripción", pasa por CCR: `brain.child_env()` limpia el entorno del proceso pero la CLI vuelve a leer esos valores del archivo de settings. Consecuencias: la suscripción de Claude hoy no se usa en ANZO, el mensaje "se acabó el límite de la suscripción" en realidad era el límite del proveedor del router, y el modelo que reporta la CLI es solo el alias. No se tocó ese archivo (es del usuario); se resolvió con un `--settings` propio, ver la sección siguiente.

**Modelo visible:** debajo del estado, una línea "● Modelo: gemini-3.8-flash · Google Gemini" (verde si respondió bien, rojo con "sin cupo"/"error N" si falló). Se actualiza cada 4 s y al terminar cada turno, y destella al cambiar (p. ej. cuando el router salta a otro proveedor). El servidor la saca de `/api/model`, que lee **solo lectura** el `request-logs.sqlite` de CCR (`response_model`/`resolved_model` de la última petición, si es de los últimos 30 min), porque la CLI solo conoce el alias que pidió. Sin tráfico reciente cae al modelo que reporta la CLI. Probado con el log real y simulando cambios de modelo en la UI; no con un turno exitoso (no hay cupo hoy).

## Router primero, membresía de Claude como último recurso (2026-09-29)

**Pedido:** usar primero los proveedores del router (Gemini → OVH) y la membresía de Claude solo cuando ninguno tenga cupo.

**`--settings` propio (`anzo-claude-settings.json`, en el repo, sin secretos):** CCR reescribió el `~/.claude/settings.json` global con `ANTHROPIC_BASE_URL`/`ANTHROPIC_MODEL` hacia el gateway **y un `apiKeyHelper`** que le entrega a la CLI la clave del router. Limpiar el entorno del hijo no basta, porque la CLI lee ese archivo al arrancar. Los intentos de membresía pasan `--settings` con el endpoint oficial (`https://api.anthropic.com`), modelo `sonnet` y `"apiKeyHelper": ""`. Sin anular el `apiKeyHelper` la CLI mandaba la clave del router a Anthropic y fallaba con `authentication_failed` en bucle (se veía como "se queda pensando"). Verificado: `apiKeySource=none` (login de claude.ai), modelo `claude-sonnet-5`, y cero peticiones nuevas en el log de CCR. Los intentos ruteados no llevan el archivo y siguen usando la config global de CCR.

**Modo `ANZO_ROUTER=router_first`** (ahora el de `.env`): `brain._run_router_first()`.
- Si el router no responde, o su última petición (según su propio log, solo lectura) fue un 429 hace menos de `ANZO_ROUTER_COOLDOWN` segundos (300), va directo a la membresía.
- Si no, intenta por el router. Un `system/api_retry` de la CLI en un turno ruteado significa que CCR ya recorrió toda su cadena y falló: se corta en ese momento y pasa a la membresía (antes la CLI reintentaba 10 veces y ANZO se quedaba pensando hasta el timeout de 180 s).
- Si el router ya empezó a hablar, un error posterior se queda como error (no se repite la respuesta con otro modelo).
- Cada intento emite `{t: "backend", kind}`; el servidor lo usa para que la etiqueta de modelo diga "claude-sonnet-5 · Claude (membresía)" cuando responde la membresía (el log de CCR no la ve).

**Probado de punta a punta** (instancia de prueba, Gemini y OVH sin cupo): primer turno → router → `api_retry rate_limit` → membresía respondió; segundo turno → se saltó el router por el enfriamiento y respondió la membresía en ~3 s. No medido: cuánto tarda exactamente el primer intento por el router antes del `api_retry` (CCR respeta el `Retry-After` de Google, del orden de 40 s).

## Nace ANZO + Claude: sin router, con la extensión Claude in Chrome (2026-09-29)

**Pedido del usuario:** quitar el autoarranque con Windows, hacer una copia del proyecto separada de GitHub para no afectar la versión original, y que esta copia ("ANZO + Claude") use solo su cuenta de Claude y la extensión de Chrome, sin el router.

**Qué se hizo:**
- La tarea programada `ANZO` (autoarranque) se eliminó; esta versión no incluye los scripts de autoarranque.
- Copia en `C:\dev\anzo-claude` con el historial de git, **sin remoto** (se quitó `origin`). La original sigue en `C:\dev\anzo`, conectada a `janzola2895/anzo`.
- **Sin router:** se quitó todo lo de claude-code-router (modos, reintentos, lectura de su log, arranque y parada de `ccr`). Cada turno es la membresía con `--settings anzo-claude-settings.json` (sigue haciendo falta: la config global de Claude Code sigue apuntando a CCR).
- **Navegador = la extensión:** `claude -p --chrome`, `--allowedTools mcp__claude-in-chrome,Skill` + escritura solo en `ANZO archivos`. Se quitaron el Chrome aparte (`.browser-profile`), Playwright MCP, `mcp-config.json` y el reabridor del navegador. En su lugar, el servidor solo se asegura de que el Chrome normal del usuario esté abierto (lo detecta por el `lockfile` de su perfil) y lo abre si está cerrado; nunca lo cierra.
- El prompt le pide a Claude trabajar en su grupo de pestañas y **no cerrarlas** salvo pedido explícito (la skill `chrome-browser` que se carga sola dice lo contrario).
- Capturas: la extensión guarda con `save_to_disk` en una carpeta temporal y responde `Screenshot saved to: <ruta>`; `brain._collect_screenshot()` la copia a `ANZO archivos` como `captura_<fecha>.jpg`. Claude no necesita permiso para copiar archivos.
- Si al arrancar un turno la extensión no aparece conectada, la ventana muestra un aviso.
- Puerto 8740 (la original usa 8730), título y acceso directo "ANZO + Claude", ícono naranja para no confundirla con la azul.

**Probado de punta a punta** (sin ventana, con el Chrome real): abrir example.com (14 s), guardar captura en el escritorio (14 s, llegó a `ANZO archivos`), cerrar la pestaña al pedirlo (10 s); modelo `claude-sonnet-5`; **cero** peticiones al router durante la prueba. No probado aquí: voz real en la ventana nueva y tareas de Power Platform.

## El grupo de pestañas se llama "AnzoBot", no "Claude" (2026-09-29)

Pedido del usuario: que el grupo de pestañas donde trabaja ANZO no diga "Claude" sino "AnzoBot". El nombre lo pone la extensión Claude in Chrome y no se puede configurar, así que se agregó una mini extensión propia (`chrome-extension/`, solo permiso `tabGroups`) que lo renombra y conserva los prefijos de estado. El usuario la instala una vez con "Cargar descomprimida" en `chrome://extensions` (requiere Modo de desarrollador). Detalle y prueba en [[Arquitectura ANZO + Claude]].

## Investigación: Claude in Chrome (la extensión) como navegador de ANZO (2026-09-29)

Pregunta del usuario: ¿puede ANZO usar la extensión Claude in Chrome en vez del Chrome aparte + Playwright MCP? Probado en esta máquina (CLI 2.1.283, extensión 1.0.94 en el perfil Default de Chrome). Sin cambios de código todavía.

- **Modo sin ventana (`claude -p --chrome`) funciona** con la membresía (`--settings anzo-claude-settings.json`, login de claude.ai): `claude-in-chrome` conectado con 22 herramientas, abrió una pestaña en el Chrome normal del usuario (con sus sesiones), leyó la página y respondió (~20-30 s en una tarea simple; parte es la carga automática de la skill `chrome-browser`). La primera ejecución registró el conector nativo de la CLI (`HKCU\Software\Google\Chrome\NativeMessagingHosts\com.anthropic.claude_code_browser_extension`). Convive con la sesión de la app de escritorio de Claude sin conflicto.
- **Continuidad entre turnos:** las pestañas van a un grupo ligado a la sesión; con `--resume` el siguiente turno ve el mismo grupo y la misma pestaña. Al salir, la CLI no cierra un grupo con páginas abiertas.
- **Por el router no funciona:** con la clave del router (`apiKeyHelper`) la CLI apaga la integración (0 herramientas), como dice la documentación. Con el login de claude.ai apuntando al router, la integración sí carga, pero hay que pedir un modelo de Claude (`--model sonnet`; el alias de CCR da `unrecognized_model`) y CCR rechaza ese login con 401 porque exige su propia clave de cliente. Solo funcionaría quitando esa exigencia en CCR (cualquier programa local podría usar el router); no probado de punta a punta (sin cupo).
- **A ajustar si se adopta:** la skill `chrome-browser` le dice a Claude que cierre las pestañas que abre; ANZO tendría que pedir lo contrario en su prompt. La extensión actúa en el Chrome personal del usuario, con todas sus cuentas.

## Cambio de diseño: interrumpir exige la palabra clave (2026-09-29)

Reportado en vivo: con una tarea corriendo, una conversación de fondo en la sala ("champiñones Camilo se quiere ir o hay sándwich con queso...") interrumpió la tarea y se mandó a Claude como instrucción nueva. Causa: por diseño, mientras ANZO estaba `WORKING` cualquier frase lo interrumpía (requisito original de "interrupción en caliente").

**Decisión:** la interrupción en caliente se mantiene, pero ahora requiere la palabra clave, en modo normal y en modo conversación. "Anzo, <instrucción>" cambia la tarea en curso; "Anzo" solo, o "Anzo para/detente/basta/cancela/silencio", la detiene sin mandar nada nuevo. Cualquier otra frase durante una tarea se ignora. "pausa" y "cambio y fuera" siguen funcionando sin palabra clave en modo conversación. Probado en el navegador aislado simulando cada caso.

## Cambio de diseño: modo normal ya no tiene ventana de gracia (2026-09-29)

El usuario reportó que en modo normal (no modo conversación) Anzo a veces seguía reaccionando sin que dijera la palabra clave. Causa: después de cada turno, `finishTurn()` dejaba a Anzo en `LISTENING` (sin pedir "Anzo") durante 12 segundos de gracia (`FOLLOW_UP_WINDOW_MS`) antes de volver a `IDLE` -- pensado originalmente para responder una pregunta rápido, pero era también una ventana donde cualquier habla suelta (o un eco que el filtro no cachara) se tomaba como instrucción nueva sin que el usuario lo pidiera.

**Decisión:** modo normal ahora siempre vuelve directo a `IDLE` al terminar un turno -- pide "Anzo" de nuevo cada vez, sin excepción. "Seguir escuchando sin repetir la palabra clave" queda exclusivamente como el trabajo de modo conversación (que sigue funcionando igual, activado a propósito). Se eliminó `listeningTimeout`/`FOLLOW_UP_WINDOW_MS` de `ui/app.js` -- ya no existía ningún camino que los necesitara. La interrupción en caliente mientras Anzo está `WORKING` (hablar por encima sin decir "Anzo") no se tocó -- eso sigue siendo un requisito original del proyecto, distinto de la ventana de gracia post-turno que sí se quitó.

Probado en el navegador aislado: tras un turno normal, una frase sin "Anzo" se ignora (vuelve a pedir la palabra clave); con "Anzo" sí se acepta; en modo conversación una frase sin "Anzo" se sigue aceptando igual que antes. Nota: esto reduce pero no elimina del todo el riesgo de auto-eco -- el filtro de texto sigue siendo una heurística, no cancelación acústica real (ver limitación ya anotada arriba).

## Bug real: Anzo se escuchaba a sí mismo y se autorespondía (2026-09-29)

Reportado en vivo: tras una respuesta corta de Anzo, el micrófono recogió la cola de su propia voz saliendo por los parlantes y la tomó como un mensaje nuevo del usuario — Anzo le contestó a su propia frase, esa respuesta se volvió a autoescuchar, y así en cadena. No era eco de la sala (el usuario confirmó que no estaba en un lugar con eco): era la propia voz de Anzo filtrándose del parlante al micrófono, sin auriculares.

**Causa real:** el filtro de eco (`looksLikeEcho`, pensado exactamente para este caso) solo se revisaba dentro de la rama `state === WORKING` de `onFinalUtterance`. Pero el evento `complete` de un turno (que mueve el estado a `LISTENING`) llega apenas termina el *texto*, mientras que `speechSynthesis` sigue leyéndolo en voz alta varios segundos más — el hueco de eco real está sobre todo *después* de `WORKING`, justo donde el filtro no se aplicaba.

**Arreglo en `ui/app.js`:**
- `looksLikeEcho()` ahora se revisa primero en `onFinalUtterance`, antes de mirar el estado — cubre `LISTENING`, modo conversación, e incluso `IDLE` (una respuesta de Anzo que mencione "viernes" de pasada no debería auto-activarlo).
- La ventana de eco (`inEchoWindow`) ya no depende del estado de la conversación sino de si `speechSynthesis` realmente está reproduciendo algo, vía los eventos `onend`/`onerror` de cada `SpeechSynthesisUtterance`.
- **Segundo bug encontrado probando el arreglo:** en pruebas, `onend`/`onerror` a veces no dispararon nunca aunque `speechSynthesis.speaking` ya había vuelto a `false` — un punto débil conocido de Chrome, no exclusivo del entorno de prueba. Sin red de seguridad, eso deja `inEchoWindow` trabado en `true` para siempre y Anzo deja de reaccionar a todo. Arreglo: un `setTimeout` de respaldo (~70ms por carácter, mínimo 3s) que libera la ventana igual si el evento nunca llega.

**Tercer bug, el que de verdad seguía causando el problema en vivo (reportado de nuevo después del arreglo de arriba):** `flushSentence()` llama a `speak()` una vez por oración, así que una respuesta corta son 2 o 3 utterances separadas. El reconocimiento de voz frecuentemente las escucha como una sola frase continua, cruzando el punto entre oraciones (confirmado con el texto real: "...gráficos. ¿En qué te ayudo?" dicho como dos oraciones, escuchado como "...graficos En que te ayudo" de un tirón). `recentlySpoken` seguía guardando la puntuación de cada oración, así que la comparación por substring nunca coincidía justo en ese cruce — el filtro fallaba silenciosamente en el caso más común (una respuesta de varias oraciones), que es exactamente lo que se vio en vivo dos veces seguidas. Arreglo: `normalizeForEcho()` (nueva) quita puntuación de ambos lados antes de comparar, no solo acentos/mayúsculas. Confirmado con el texto exacto del reporte: ahora se detecta bien, y un mensaje real distinto (aunque comparta palabras) no se bloquea de más.

Con este arreglo, la siguiente prueba en vivo (saludo + pedido) ya no mostró el auto-eco.

## Bug: "la herramienta del navegador no está conectada" al primer pedido (2026-09-29)

Reportado en vivo: el usuario ve la ventana de Chrome dedicada abrirse normalmente al arrancar `server.py`, pero el primer pedido que necesita el navegador ("abre TradingView...") falla con un error de conexión de la herramienta del navegador.

**Diagnóstico:** revisados puertos 9223/8931, procesos `chrome.exe`/`node.exe` y el lock file del perfil (`.browser-profile/SingletonLock`) — nada quedó huérfano de una sesión anterior, así que no era un residuo viejo. Causa más probable: `main()` esperaba un `time.sleep(2)` fijo después de lanzar Chrome antes de lanzar Playwright MCP (`npx @playwright/mcp@latest`), asumiendo que 2 segundos alcanzan siempre. `npx` puede tardar bastante más si tiene que revisar o descargar el paquete — si el usuario le habla a Anzo casi de inmediato (como pasó: "cómo estás" y enseguida "abre TradingView"), el pedido de navegador puede llegar antes de que Playwright MCP esté realmente escuchando en el puerto 8931.

**Arreglo en `server.py`:** `_wait_for_port()` (nueva) reemplaza el `sleep(2)` fijo por un polling real — espera hasta 20s a que el puerto de depuración de Chrome (9223) responda antes de lanzar Playwright MCP, y hasta 60s a que Playwright MCP (8931) responda antes de abrir la interfaz de voz. Si algo no responde a tiempo, avisa por consola en vez de fallar en silencio.

**Primera vuelta de este arreglo, probada en vivo:** sí abrió, pero tardó el minuto entero. La consola mostraba a Playwright MCP con su propio banner ("Listening on http://localhost:8931") bastante antes de que la interfaz de voz apareciera — `_wait_for_port()` solo probaba conectarse a `127.0.0.1`, no a `localhost`, y en esta máquina esos dos no resuelven igual para un listener de Node recién levantado. Se agotaba el timeout de 60s completo cada vez antes de rendirse y seguir igual. Arreglo: prueba ambos hosts (`127.0.0.1` y `localhost`) en cada intento de poll. Probado en aislado: detecta rápido un listener en cualquiera de los dos.

## Hito: flujo de punta a punta confirmado sano de nuevo (2026-09-29)

Con los cuatro arreglos de esta sección (eco por hueco de estado, eco por puntuación entre oraciones, espera fija de arranque, `127.0.0.1` vs `localhost`), el usuario confirmó que corriendo `python server.py` normal el flujo completo (voz → Claude → navegador → TradingView/Power Apps → voz de vuelta) ya funciona de punta a punta sin el auto-eco ni el error de conexión del navegador. Todo comiteado y subido a `origin/master` (`janzola2895/anzo`, privado) en cada paso — nada quedó pendiente de subir.

**Lo que sigue sin confirmarse en vivo** (no se tocó en esta ronda de pruebas):
- Modo conversación y "pausa"/"cambio y fuera" dichos por voz real (el toggle por botón sí se probó, ver sección de UI/autostart/bitácora más arriba)
- La bitácora escribiendo de verdad en `Anzo/Bitacora/` después de una conversación real
- La tarea programada arrancando sola en un inicio de sesión real de Windows (sigue como pendiente más abajo)
- Tareas reales de desarrollo/diagnóstico de Power Platform (Canvas Apps / Power Automate) — sigue siendo lo no probado del objetivo original, ver "Pendiente"

## Integración con claude-code-router (2026-09-29)

**Problema:** Anzo dependía solo de la suscripción de Claude del usuario; al llegar el límite semanal (ver 2026-09-28) todo se detenía.

**Solución:** [musistudio/claude-code-router](https://github.com/musistudio/claude-code-router) (CCR) es un gateway local (`127.0.0.1:3456`) que la misma CLI `claude` puede usar vía `ANTHROPIC_BASE_URL`, y desde ahí enruta a otros proveedores/cuentas (OpenRouter, DeepSeek, Gemini, otra key de Anthropic, rotación de credenciales, fallbacks). No se copió su código: Anzo lo usa como servicio externo, igual que Chrome/Playwright MCP.

**Modos (`ANZO_ROUTER`):**
- `off` (defecto): sin cambios, solo suscripción.
- `fallback` (recomendado): suscripción primero; si la CLI reporta límite (`hit your weekly limit`, `usage limit`, 429, etc.), `brain.run()` reintenta el mismo turno por el router y avisa con un evento `warning`.
- `always`: todo por el router.

**Reglas que se mantienen:** el entorno sigue limpiándose de `ANTHROPIC_*`/`CLAUDE_CODE_*`; solo el proceso *ruteado* recibe `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN` (la clave de cliente de CCR, `ANZO_ROUTER_KEY`). Las claves de los proveedores viven en la config de CCR (`~/.claude-code-router`), nunca en este repo. La detección de límite solo mira mensajes cortos (<300 caracteres) para no confundir una respuesta que hable de "rate limits". Los resúmenes de la bitácora usan el router primero cuando está disponible, para no gastar suscripción en tareas de fondo.

**Configuración (una vez):**
```
npm install -g @musistudio/claude-code-router   # Node 22+
ccr ui                                           # agregar proveedor + modelo, crear API key de cliente
set ANZO_ROUTER=fallback
set ANZO_ROUTER_KEY=<clave de cliente de CCR>
set ANZO_ROUTER_MODEL=<modelo tal como lo nombra CCR>   # opcional
```
`server.py` corre `ccr start --no-open` al arrancar si el modo no es `off`. Otras variables: `ANZO_ROUTER_URL`, `ANZO_ROUTER_HOST`, `ANZO_ROUTER_PORT`.

**Limitaciones conocidas:** un turno reintentado por el router hace `--resume` de una sesión creada con Claude; si el modelo del proveedor rechaza ese historial, habrá que reintentar sin `--resume`. Modelos que no son de Anthropic pueden manejar peor las herramientas `mcp__browser`. (La duda de si funcionaba contra un CCR real quedó cerrada el mismo día, ver la sección siguiente.)

## CCR probado en vivo: Gemini como principal (2026-09-29)

**Qué pasó:** con CCR real, el único proveedor era Codex (`gpt-5.6-terra`, plan gratis de ChatGPT), que devolvía `429 usage_limit_reached` hasta cerca del 2026-10-13. La CLI `claude` reintenta los 429 en silencio, así que Anzo se quedaba "pensando" hasta el timeout de inactividad (180s). No cambiaba de modelo solo porque Anzo solo tiene un salto (suscripción → router) y CCR tenía un único proveedor sin cadena de respaldo. Los `git checkout`/`pull` que el usuario corrió antes no tuvieron nada que ver.

**Decisión:** no cambiar de router (LiteLLM, OpenRouter y demás también necesitan un proveedor con cupo detrás; Ollama local no sirve en este equipo, 15 GB de RAM y sin GPU; Groq gratis tiene un tope por minuto menor que el prompt de Anzo, ~30k tokens por petición). Se agregó **una sola** clave gratis, de Google AI Studio.

**Configuración final (en la UI de CCR, `http://127.0.0.1:3458`):**
- Proveedor Google Gemini, modelo `gemini-3.8-flash`. `gemini-2.5-flash` ya no está disponible para cuentas nuevas.
- Global Routing, regla "Todo a Gemini": condición `request.body.model != nada` (siempre verdadera), reescribe `request.body.model = gemini-3.8-flash`, y en fallo va a Codex `gpt-5.6-terra`.
- Probado por el usuario: Anzo responde de punta a punta por Gemini.

**Parche local a CCR 3.1.1 (importante):** las claves nuevas de AI Studio empiezan con `AQ.`, no `AIza`. CCR solo trataba `AIza` como clave de Gemini y a las demás les agregaba `Authorization: Bearer` además de `x-goog-api-key`; Google rechaza las dos credenciales juntas (401). Se parcheó `%APPDATA%\npm\node_modules\@musistudio\claude-code-router\dist\main\cli.js` y `upstream-header-sanitizer.js` para tratar `AIza` y `AQ.` igual. Hay copias `*.bak-anzo` al lado. **Una actualización de CCR con npm borra el parche.**

**Sin resolver a propósito:** si un proveedor devuelve un límite mientras Anzo va por el router, la CLI sigue reintentando en silencio y Anzo puede volver a quedarse "pensando" en vez de avisar. Con el respaldo de CCR es menos probable, así que no se tocó `brain.py`.

## Límite de reintentos y tope de acciones por turno (2026-09-30)

**Reportado por el usuario:** en uso real, un turno se enredó y repitió lo mismo muchas veces; se gastó ~20% de los tokens de la sesión. Pidió que intente unas 3 a 5 veces como máximo y, si no lo logra, pida ayuda.

**Qué pasó (leído de la transcripción de la sesión `43e16a42`):** el pedido era arreglar el cuerpo del correo en el flujo; Claude se quedó escribiendo la fórmula `OnSelect` del botón en la barra de fórmulas de Power Apps: ~190 llamadas de herramienta seguidas (clics en los mismos puntos, `ctrl+a`, `Delete`, escribir `'PowerAppV2`, capturas) sin avanzar, hasta que se acabó el cupo de la sesión (`You've hit your session limit`). Ninguna llamada dio error, así que un detector de errores no lo habría visto. Lo que lo hizo tan caro: cada llamada es una petición que vuelve a leer todo el contexto, y ese contexto ya iba en ~300-380 mil tokens por las capturas de los turnos anteriores (el turno completo: 208 llamadas, ~104 millones de tokens de entrada, casi todo lectura de caché). Además, ninguna llamada usó `browser_batch` y muchas eran dos capturas seguidas.

**Qué se hizo:**
- **Regla en el prompt:** si un paso no sale, máximo 3 intentos y cada uno de forma distinta; al tercero se detiene y le dice al usuario qué intentaba, qué probó y qué falla, y le pide ayuda. También: agrupar acciones previsibles con `browser_batch` y no tomar dos capturas seguidas.
- **Tope duro en `brain.py`** (`ANZO_MAX_TOOL_CALLS`, 60 por defecto, 0 = sin tope): al llegar a 60 llamadas en un turno, ANZO corta el proceso y dice "Llevo 60 acciones en esta tarea y todavía no termino... Si voy bien, dime: Anzo, sigue". Termina como turno normal (no como error), así que la sesión sigue y "Anzo, sigue" retoma donde quedó. El siguiente mensaje en esa sesión lleva una nota para Claude ("detuve tu turno anterior... si estabas repitiendo intentos, no insistas igual") para que no vuelva a entrar al mismo bucle.
- **Por qué un tope y no un detector de acciones repetidas:** se probó contra las transcripciones reales. Contar clics idénticos marcaba antes el turno sano de construir la app (varios "Insertar" en el mismo lugar) que el bucle. Contar llamadas es simple y predecible; la regla del prompt es la que debería frenar antes.
- **Por qué 60:** cada intento del bucle ocupaba ~10-15 llamadas, así que 60 son unos 5 intentos. Con el tope, ese turno se habría cortado en la llamada 60 en vez de la 208. Las construcciones reales de apps y flujos tomaron 100-150 llamadas (sin `browser_batch`), así que pueden pedir un "Anzo, sigue"; si molesta, se sube en `.env`.
- De paso se encontró y arregló que interrumpir no mataba de verdad a Claude en Windows (ver [[Problemas resueltos]]).

**Probado** con un `claude` falso que emite 200 acciones: se corta en 60, el proceso queda muerto, la nota va solo en el siguiente mensaje de esa sesión y la interrupción detiene todo el árbol. **No probado en vivo:** que Claude real respete la regla de 3 intentos y cuánto baja el número de llamadas con `browser_batch`.

**Pendiente, no hecho:** el contexto crece turno a turno con cada captura (`--resume` mantiene todo), así que cada acción cuesta más a medida que avanza la conversación. Empezar una sesión nueva de vez en cuando lo reiniciaría, pero se perdería la continuidad entre pedidos.


## "Viernes modo oro": análisis completo de XAUUSD con veredicto (2026-10-09)

**Pedido del usuario:** al decir "Viernes modo oro", que ANZO haga el análisis completo del oro y diga si se debe abrir alguna operación o si se debe esperar a que el oro llegue a un precio y ahí evaluar de nuevo. La lista de qué debe tener un buen análisis intradía (contexto, sesión, sesgo multi-temporalidad, estructura, zona, gatillo, plan de trade) salió de la conversación del mismo día y quedó codificada en la skill.

**Cómo llega la frase a Claude:** "viernes" ya era palabra clave (ver 2026-09-27), así que `stripWakeWord` la quita y a Claude le llega solo "modo oro" ("Anzo, modo oro" da lo mismo; en modo conversación llega "viernes modo oro" completo). Sin cambios en `ui/app.js`. Por eso la skill avisa que "Viernes" es el nombre del asistente, no el día.

**Implementación:**
- Skill nueva `.claude/skills/modo-oro/SKILL.md`, autosuficiente (no hace falta cargar `trading-chart-analysis`, para ahorrar una llamada). Una línea nueva en `SYSTEM_PROMPT` de `brain.py` le dice a Claude que la cargue al oír "modo oro": la lección ya anotada es que sin instrucción explícita no siempre usa lo que tiene.
- **Todo en tradingview.com** (el usuario ya tiene sesión, no pide permisos de sitio nuevos): calendario económico (`/economic-calendar/`), XAUUSD en H4/H1/M15/M5 y DXY. Probado en un navegador aislado: la URL `/chart/?symbol=OANDA%3AXAUUSD&interval=240` cambia símbolo e intervalo (60, 240...), `TVC%3ADXY` carga el índice del dólar, el **título de la pestaña trae el precio** (útil para reevaluar sin captura) y el calendario muestra la hora local (UTC-5), banderas, barras de impacto y "Coming in". Una URL por intervalo + una captura cabe en un `browser_batch`.
- **Filtros** (si falla uno no hay entrada ahora): noticia de EE. UU. de impacto alto en ±30 min, sesión líquida (y viernes después de las 11:00 a.m. hora Colombia), volatilidad/spread, y riesgo-beneficio ≥ 1:2. **8 confluencias**; setup válido = filtros OK + al menos 5, incluyendo zona y gatillo, con el precio ya en la zona.
- **Tres veredictos:** A hay setup válido (entrada, stop, TP1/TP2, R:R, invalidación); B esperar y reevaluar (precio o rango exacto, qué debe verse ahí, precio que invalida, hora si el bloqueo es por noticia o sesión); C no hay setup. Ante la duda entre A y B, B.
- **Reevaluación:** si ya hubo un modo oro "esperar" hoy (en la conversación o en `ANZO archivos\modo-oro.md`), el siguiente "modo oro" compara con el plan: si el precio no llegó, lo dice sin repetir el análisis; si llegó, repite calendario, M15 y M5 y da el nuevo veredicto; si tocó el precio de invalidación, descarta el plan.
- **Salida:** hablada y corta (veredicto primero, por qué, niveles, cierre). El detalle, con la tabla de filtros y confluencias, va a `ANZO archivos\modo-oro.md` (se sobrescribe cada vez), porque una tabla no se puede leer en voz alta.
- **Presupuesto:** apunta a ~15 llamadas y no pasar de 30 (el tope duro sigue en 60). No agrega indicadores al gráfico (un intento como máximo): si faltan EMA/RSI/MACD/ATR, lo dice y sugiere guardar un layout con ellos.

**Cómo convive con el límite de diseño "nunca un opera / no operes":** el límite era no dar asesoría financiera personalizada ni órdenes directas. El modo oro entrega un **veredicto técnico del setup** (válido / esperar un precio / no hay), no una orden: nunca dice "compra ahora" sino "hay setup válido de compra" y por qué, no conoce la cuenta ni el apetito de riesgo del usuario, y cierra siempre con "lectura técnica educativa, la decisión es tuya". Además queda escrito que **solo analiza**: no toca el panel de trading ni el broker, ni botones de comprar/vender, ni crea alertas (las sugiere).

**Limitación que se mantiene:** ANZO solo actúa cuando se le habla; no vigila el precio. "Esperar a que llegue a X" significa que el usuario vuelve a decir "modo oro" (o pone una alerta de TradingView en X para que le avise).

**Probado:** compilación de `brain.py`, que el prompt no tiene caracteres que `cmd.exe` interprete, que la frase de voz llega como "modo oro" (con "Viernes", "Viernes,", "Anzo," y "hola viernes"), el frontmatter de la skill, y las URLs de TradingView arriba. **No probado:** un modo oro de punta a punta con el Chrome real del usuario (gasta membresía y maneja su navegador): cuántas acciones gasta de verdad, si respeta el formato hablado, y cómo se ven los indicadores en su layout real.

### Primera prueba real del modo oro (2026-10-09): el gráfico sale en blanco si Chrome lo cree tapado

Corrida real por `brain.run("modo oro")` (misma ruta que la app, con el Chrome del usuario): la skill se cargó sola a los 5 s con solo "modo oro", intentó leer `modo-oro.md` (no existía, así que hizo análisis nuevo), leyó el calendario (10:31 a.m.), y se detuvo a los 138 s con 16 llamadas, **sin veredicto**: las capturas del gráfico de TradingView salían en blanco. Hizo lo que pide el prompt (3 formas distintas, F5, clic, pestaña nueva) y pidió ayuda.

**Causa (diagnosticada en otra sesión del mismo Chrome):** `document.visibilityState` = `"hidden"` y `hasFocus()` = false aunque la ventana está en pantalla (`screenX/Y` = 0, 1536×912, no minimizada). Los canvas del gráfico seguían en 300×150, el tamaño por defecto: TradingView nunca llegó a dibujar. Chrome en Windows marca como ocultas las ventanas totalmente tapadas por otra (acá, la app de escritorio de Claude), deja de pintarlas, y el DOM estático (encabezado y precio) sí aparece en la captura pero los canvas no. Un clic desde la extensión no lo arregla (da foco, no visibilidad). El precio sí se lee, porque sale en el título de la pestaña.

**Qué se hizo:** la skill ahora dice, ante un gráfico en blanco, que no recargue ni abra pestañas, que haga una sola comprobación de `document.visibilityState`, que si es `hidden` le pida al usuario dejar visible la ventana AnzoBot y que entregue precio y calendario **sin veredicto** (sin velas no hay A, B ni C). También limita el scroll del calendario (en la prueba gastó 4 llamadas en él).

**Qué debe hacer el usuario:** dejar la ventana de Chrome del grupo AnzoBot visible (por ejemplo en un segundo monitor o junto a la ventana de ANZO, no debajo). Alternativa conocida, **sin verificar aquí** (no pude abrir `chrome://flags` desde la extensión): en `chrome://flags`, "Calculate window occlusion on Windows" en *Disabled* y reiniciar Chrome; hace que Chrome no trate como ocultas las ventanas tapadas. Pendiente: confirmar con una corrida con la ventana visible que el gráfico pinta y que el modo oro llega al veredicto.
