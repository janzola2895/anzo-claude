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

## Pendiente / mejoras futuras

- Probar tareas reales de **desarrollo/diagnóstico** (editar un campo de una Canvas App, revisar el historial de un flujo de Power Automate, etc.) — la navegación ya funciona, pero esto sigue siendo lo no probado del objetivo original
- El filtro de eco es una heurística de texto, no cancelación acústica real — usar audífonos sigue siendo lo más confiable si el falso-positivo persiste
- Evaluar Fish Audio (de pago) si la voz de Google de Chrome no resulta suficiente

### Pedidos del usuario (2026-09-27), a resolver más adelante

1. **Interfaz más amigable/"tecnológica".** Hoy es solo una esfera + log de texto (`ui/`). Referencia posible: el HUD de `ethanplusai/jarvis` (orbe en three.js, 2000 partículas reactivas a la voz) — vale la pena mirarlo de nuevo como inspiración visual, no para copiar código.

2. **Arrancar solo al iniciar Windows.** Hoy hay que correr `python server.py` a mano cada vez. Opciones a evaluar: acceso directo en la carpeta de Inicio de Windows (`shell:startup`), una tarea programada (Task Scheduler, "al iniciar sesión"), o un servicio de Windows (más robusto, más complejo de montar). Probablemente la carpeta de Inicio es la más simple para empezar.

3. **Dos modos de activación.** El usuario quiere poder elegir entre:
   - **Modo actual (ya funciona):** hay que decir la palabra clave ("Anzo"/"Yarvis"/"Viernes") antes de cada petición.
   - **Modo conversación (nuevo):** una vez activado, no hace falta repetir la palabra clave en cada turno — se habla natural y seguido. Se pausa con una palabra (propuso "Pausa") y se termina con una frase de despedida tipo radio (propuso "Cambio y fuera"). Pidió explícitamente recomendaciones.

   **Nota técnica para cuando se retome:** el "modo conversación" es, en el fondo, extender indefinidamente la ventana de seguimiento post-turno de 12 segundos que ya existe (`FOLLOW_UP_WINDOW_MS` en `app.js`) hasta que se diga la palabra de pausa/fin, en vez de que expire sola. Recomendación: activar/desactivar el modo también por voz (ej. "Anzo, modo conversación") además de un botón en la interfaz nueva del punto 1; mantener "Cambio y fuera" tal cual lo propuso (encaja bien con el tono del proyecto) y usar "Pausa" para detener sin cerrar la sesión — quizás agregar "Anzo, continúa" o similar para reanudar desde pausa.

4. **Bitácora de conversaciones.** Un registro de lo que se ha hablado con Anzo — resumen o texto completo pero compactado, para no ocupar mucho espacio. Sin definir todavía si es resumen automático o transcripción condensada. Posible lugar natural: una nota (o una por día) en esta misma bóveda de Obsidian, ya que el patrón "memoria = notas de Obsidian" ya lo usa `Itsme23476/jarvis-claude-code` como referencia. Nota: Claude Code ya guarda una transcripción cruda de cada turno (`--resume` se apoya en eso), pero es formato JSON disperso en varios archivos, no algo pensado para que el usuario lo lea — esto sería algo aparte, legible.
