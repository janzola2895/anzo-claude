# Decisiones

- **Nombre del asistente:** ANZO
- **Palabra clave de activación:** "Anzo" o "Hola Anzo"
- **Repositorio de código:** `C:\dev\anzo`
- **Notas del proyecto:** vault de Obsidian en `C:\dev\anzo\Notas` (esta carpeta)
- **Enfoque de control:** navegador (Chrome, vía extensión Claude for Chrome) sobre la sesión ya autenticada del usuario — no API/OAuth propio, por decisión de IT de Indra.
- **Objetivo funcional:** desarrollar y diagnosticar Canvas Apps y flujos de Power Automate por instrucción de voz, con narración hablada e interrupción en caliente.

## Pendiente por decidir (fase de arquitectura)

- Motor de wake-word
- Proveedor de voz→texto y texto→voz
- Cómo la app de voz se conecta con Claude (Agent SDK vs. otra vía)
- Cómo se maneja la interrupción a mitad de tarea
