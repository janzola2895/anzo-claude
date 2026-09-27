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

## Pendiente por decidir / construir

- ~~Motor de wake-word~~ / ~~Proveedor de voz~~ / ~~Cómo se conecta con Claude~~ → resuelto arriba
- Implementar la palabra clave "Anzo"/"Hola Anzo" (ninguno de los dos proyectos base la tiene)
- Implementar interrupción en caliente real mientras un turno ya está corriendo (ambos proyectos base suspenden la escucha durante un turno — lo opuesto a lo que necesitamos)
- Conectar un MCP de navegador (Playwright) para Power Apps / Power Automate
- Definir `--permission-mode` (bypassPermissions vs. algo más acotado, dado que va a tocar apps reales de negocio)
