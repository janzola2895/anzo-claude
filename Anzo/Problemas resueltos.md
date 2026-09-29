# Problemas resueltos

Bitácora de cada bug encontrado armando el flujo de voz → Claude → navegador, en el orden en que aparecieron. Léela antes de tocar `server.py`, `brain.py` o `mcp-config.json` — varios de estos ya se intentaron arreglar mal una vez antes de dar con la causa real.

## "estÃ¡" en vez de "está" (y a veces el proceso se caía del todo)

**Síntoma:** las respuestas de Anzo mostraban caracteres raros en las tildes; en el peor caso, `UnicodeDecodeError` tumbaba el hilo que lee la salida de `claude`.

**Causa:** `subprocess.Popen(..., text=True)` sin especificar `encoding` usa la codificación del sistema en Windows (cp1252), no UTF-8. La salida de `claude` sí es UTF-8.

**Arreglo:** `encoding="utf-8", errors="replace"` explícito en `brain.py`.

## Anzo leía los asteriscos del markdown en voz alta

**Causa:** las respuestas de Claude traen markdown normal (`**negrita**`, etc.) y se mandaban tal cual a `speechSynthesis`.

**Arreglo:** `stripMarkdown()` en `app.js`, aplicado justo antes de hablar cada oración ya completa (no a fragmentos parciales del streaming).

## Anzo usaba PowerShell/`Start-Process` en vez de la herramienta del navegador

**Síntoma:** al pedirle abrir Power Apps, llamaba a `PowerShell`/`Bash` para abrir el navegador por defecto, se quedaba esperando una aprobación que el modo headless nunca puede mostrar, y terminaba atascado.

**Causa real (no la primera que se probó):** no era un problema del servidor MCP — `browser` sí aparecía conectado en la lista de MCP de Claude (`(modelo: ..., mcp: [browser, ...])`). El problema era que nada le decía a Claude que **debía** usar `mcp__browser__*` para esto; sin instrucción explícita, recurría a su instinto general de agente de código.

**Arreglo:** `--append-system-prompt` en cada turno, diciéndole explícitamente que use solo `mcp__browser__*` para cualquier cosa de navegador/web, nunca Bash/PowerShell.

**Intentos previos que NO eran la causa (pero sí bugs reales, quedaron arreglados de paso):**
- Al `mcp-config.json` le faltaba `"type": "http"` en la entrada con `"url"` — Claude Code descarta esas entradas al arrancar, en silencio, sin avisar. Real, pero no era la causa de este síntoma específico (el server sí cargaba).

## La pestaña de Power Apps se cerraba sola, ~5 a 10 segundos después

Este fue el más largo de resolver, con varias causas distintas superpuestas:

**Intento 1 — arquitectura por turno:** al principio, Playwright MCP se lanzaba como hijo del propio proceso `claude -p` de cada turno (`--mcp-config` con `command`/`args`, no `url`). Al terminar el turno, moría el proceso y se llevaba el navegador. **Arreglo:** correr Playwright MCP como servidor HTTP independiente, lanzado una sola vez por `server.py`.

**Intento 2 — heartbeat de 5 segundos:** con el servidor ya independiente, la pestaña seguía cerrándose a los 5-10s. Encontrado en el propio issue tracker de Playwright MCP (`microsoft/playwright-mcp#1045`): el transporte HTTP moderno (`/mcp`) tiene un heartbeat cada 5 segundos; si el cliente (un `claude -p` ocupado "pensando") no responde a tiempo, el servidor cierra la sesión y el navegador con ella. **Arreglo:** usar el transporte SSE legado (`/sse`) en vez de `/mcp` — no tiene ese heartbeat. `mcp-config.json`: `{"type": "sse", "url": ".../sse"}`.

**Causa raíz real — "connection-is-a-lifetime":** incluso con SSE, la pestaña se seguía cerrando, pero exactamente al terminar cada turno (no a un tiempo fijo). Confirmado por el propio mantenedor de Playwright MCP respondiendo a un pedido de feature ("agregar una opción para no cerrar el navegador"): *"We rely on the connection-is-a-lifetime model, so this is by design."* (`microsoft/playwright-mcp#1302`). El navegador que Playwright MCP lanza y posee **siempre** muere cuando su cliente MCP se desconecta — no existe bandera para evitarlo, y como cada turno es un cliente que se conecta y desconecta, el navegador moría en cada turno.

**Arreglo final:** dejar de que Playwright MCP lance su propio navegador. Ahora `server.py` lanza Chrome directamente (`start_chrome`, con `--remote-debugging-port`), como proceso propio independiente de cualquier turno, y Playwright MCP solo se **conecta** a él por CDP (`--cdp-endpoint`) en vez de ser su dueño. Que un cliente se desconecte ya no mata un proceso que Playwright MCP nunca lanzó.

## "Dejó de escuchar" al pedirle abrir Power Apps

**Síntoma:** después del arreglo anterior, al pedir abrir Power Apps, la interfaz de voz dejaba de responder.

**Causa:** el usuario había cargado la página de Anzo (`localhost:8730`) dentro de la MISMA ventana de Chrome dedicada que `start_chrome()` abre para la automatización. Al navegar esa pestaña a Power Apps, se llevó por delante la propia página de Anzo (y su JavaScript de reconocimiento de voz) — no eran dos cosas separadas como debían ser.

**Arreglo:** `server.py` abre la interfaz de voz automáticamente con `webbrowser.open(...)`, que usa el navegador **por defecto** del sistema — un proceso/perfil distinto al de la ventana de automatización. Ya no hay pestaña que se pueda confundir entre las dos.

De paso, esto también explicaba unos `ConnectionAbortedError` sueltos en la consola: eran la conexión SSE de esa misma pestaña cortándose cuando Claude la navegó a otro lado a mitad de la petición — no un problema aparte.

## Anzo se queda "pensando" cuando va por el router (CCR)

**Síntoma:** después de llegar al límite de la suscripción, cualquier pedido dejaba a Anzo "pensando" sin responder, y aparecían varios `claude.exe` colgados con conexiones abiertas al puerto 3456.

**Causa:** Anzo pasó al router y el único proveedor de CCR, Codex en plan gratis, devolvía `429 usage_limit_reached` (cupo agotado ~14 días). La CLI reintenta los 429 en silencio, así que no salía texto hasta el timeout de 180s. El log de CCR (UI → Logs, o `request-logs.sqlite`) mostraba la respuesta 429 de `chatgpt.com/backend-api/codex/responses` una y otra vez. No había respaldo porque CCR tenía un solo proveedor.

**Arreglo:** proveedor Gemini (`gemini-3.8-flash`) + regla en Global Routing que lo hace principal y deja a Codex de respaldo. Detalle en `Decisiones.md`, sección "CCR probado en vivo".

**Cómo diagnosticarlo la próxima vez:** revisar primero **Logs** en la UI de CCR (código de estado y proveedor resuelto) antes de tocar `brain.py`.

## Gemini da 401 con la clave nueva de AI Studio (`AQ.…`)

**Síntoma:** `Start check` en CCR fallaba con "API keys are not supported by this API. Expected OAuth2 access token".

**Causa:** las claves nuevas de AI Studio empiezan con `AQ.`, no `AIza`. CCR 3.1.1 solo reconocía `AIza` y a las demás les mandaba también `Authorization: Bearer`, que Google rechaza junto con `x-goog-api-key`. Otras pistas que confundieron: una clave creada en un proyecto viejo de Google Cloud falló, la de un proyecto nuevo funcionó; y probar contra Vertex (`aiplatform.googleapis.com`) da 403 porque esa API está desactivada, no hace falta activarla.

**Arreglo:** parche local a dos archivos de CCR (ver `Decisiones.md`). Al probar una clave a mano, pegarla cuando `Read-Host` la pida, no dentro del texto del comando.

## El router responde 502 "Core gateway auth token is not initialized" (ANZO abierto sin terminal)

**Síntoma:** ANZO abierto con el acceso directo (sin terminal) se quedaba "pensando". En los logs de CCR cada petición daba 502 en ~10 ms, y la UI de CCR (`127.0.0.1:3458`, Overview) mostraba el banner "Service failed to start: Core gateway exited with 3221225786". Con `python server.py` desde una terminal no pasaba.

**Causa:** 3221225786 = `0xC000013A`, el proceso murió por un evento de control de consola. `ccr start` demoniza: el servicio y su hijo `gateway-bootstrap.js` sobreviven al comando. Sin terminal (`pythonw`, acceso directo) la consola en la que corrió `ccr start` desaparece al terminar el comando y se lleva al gateway. El servicio queda arriba (puertos 3456/3458 escuchando) pero sin gateway, así que acepta peticiones y falla al reenviarlas. Un `ccr stop`/`ccr start` desde una terminal real lo arreglaba, por eso "antes me funcionó con el stop y start".

**Arreglo (`server.py`):** `ccr start` se lanza con `CREATE_NO_WINDOW` (consola oculta que dura lo que dure el demonio). Al abrir ANZO se hace `ccr stop` + `ccr start` (nunca adoptar un demonio viejo), y al cerrar la ventana `ccr stop`. Comprobado: el gateway sigue vivo pasados 25 s y el banner desaparece.

**Cómo diagnosticarlo:** proceso `gateway-bootstrap.js` hijo del `serve --daemon-child` (si falta, el gateway está muerto) y el banner de Overview en la UI de CCR.

## Gemini gratis: 429 "generate_content_free_tier_requests, limit: 20" (2026-09-29)

**Síntoma:** con el router ya sano, Google respondía 429 a todo (log de CCR, `response_body_text`).

**Causa:** el plan gratis de Google AI Studio da **20 peticiones al día por proyecto y modelo** (`gemini-3.8-flash`; se reinicia a medianoche hora del Pacífico). Un turno de ANZO hace varias peticiones (una por cada paso con herramientas, más una llamada chica de fondo), y la CLI reintenta los 429, así que el cupo diario se gasta en pocos turnos. Con la clave nueva ya se había gastado.

**Estado:** sin resolver al cierre de la sesión; ver "Pendiente" en `Decisiones.md`.

## OVH anónimo como último respaldo: no viable por ahora (2026-09-29)

Se agregó a CCR el proveedor `OVH sin registro` (`https://oai.endpoints.kepler.ai.cloud.ovh.net/v1`, sin clave, modelo `Qwen3-Coder-30B-A3B-Instruct`) y a la regla "Todo a Gemini" como respaldo. Con las herramientas del navegador el modelo respondía bien en pruebas directas (~2 s, prompts de ~105 KB aceptados), pero en la prueba real de punta a punta **el respaldo no rindió**:

- **Protocolo equivocado:** CCR registró el proveedor como `anthropic_messages`. OVH responde `404 Unknown request URL: POST /v1/messages`; solo habla `/v1/chat/completions` (OpenAI). Habría que forzar el protocolo OpenAI Chat en el proveedor (Advanced settings, apagar "Auto detect protocols").
- **Límite del acceso anónimo: 2 peticiones por minuto** (`x-ratelimit-limit-minute: 2`), y aun esperando más de un minuto seguía respondiendo 429 con `remaining: 0`. Probablemente el límite es por IP y esta red lo agota (o lo agotamos con reintentos). Un turno de ANZO hace varias peticiones, y la CLI reintenta rápido los 429, así que se quema solo.
- Mecánica confirmada en el trace de CCR (UI → Logs, `request_route_traces`): Gemini 429 → CCR salta a OVH → OVH 429. El respaldo por reglas de CCR sí funciona; lo que falla es el destino.

**Estado:** el proveedor queda configurado pero no aporta nada hasta corregir el protocolo y solo si el límite por IP se libera. Sin suscripción ni cupo de Gemini, ANZO no tiene backend hasta que se reinicien (Gemini: medianoche hora del Pacífico, ~2 a.m. Colombia).

## Se cerró el Chrome de trabajo y ANZO no lo volvía a abrir (2026-09-29)

**Síntoma:** el usuario cerró por error la ventana de Chrome que ANZO controla; en el siguiente pedido Claude respondió que "el servicio del navegador no está corriendo" y pidió reiniciarlo a mano.

**Causa:** Chrome y Playwright MCP solo se lanzaban una vez al arrancar ANZO. Con Chrome cerrado, Playwright MCP seguía arriba pero con la conexión CDP muerta.

**Arreglo (`server.py`):** `ensure_browser()` se ejecuta antes de cada turno. Si el puerto de Chrome (9223) no responde, reabre Chrome y reinicia Playwright MCP; si solo falta Playwright MCP, lo reinicia. En la ventana aparece "⚠ Reabriendo el navegador de trabajo…". Tarda 6 a 8 s. Además el prompt le dice a Claude que, si el navegador falla a mitad de un turno, pida repetir la instrucción en vez de pedir reinicios. Probado con un Chrome de prueba (otro perfil y puertos, `ANZO_BROWSER_PROFILE`/`ANZO_CHROME_DEBUG_PORT`/`ANZO_BROWSER_MCP_PORT`) en los tres casos: nada arriba, Chrome cerrado, solo MCP caído. Límite: si Chrome se cierra **durante** un turno, ese turno falla; el siguiente ya lo encuentra reabierto.

## Otras notas sueltas

- La CLI de `claude` no viene con la app de escritorio — hay que instalarla aparte (`npm install -g @anthropic-ai/claude-code`) y loguearla una vez.
- **Instalaciones y logins hechos por Claude Code (por su cuenta, en su propia terminal) no se reflejan en las terminales reales del usuario, y viceversa.** Cualquier `npm install -g` o login debe correrlo el usuario mismo en su propia terminal.
- El voice tool de Windows/Chrome (`speechSynthesis`) suena robótico por defecto; instalar una voz "Natural" desde Configuración → Hora e idioma → Voz mejora esto (si el build de Windows la ofrece — no siempre aparece).
