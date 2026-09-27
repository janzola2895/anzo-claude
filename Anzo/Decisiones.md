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

## Pendiente / mejoras futuras

- Probar tareas reales de desarrollo/diagnóstico en Power Apps y Power Automate (hasta ahora solo se probó navegación) — es el objetivo real del proyecto y todavía no se ha ejercitado
- El filtro de eco es una heurística de texto, no cancelación acústica real — usar audífonos sigue siendo lo más confiable si el falso-positivo persiste
- Evaluar Fish Audio (de pago) si ni la voz de Windows ni la de Google de Chrome resultan suficientemente naturales
