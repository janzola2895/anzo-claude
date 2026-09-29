# ANZO

Asistente de voz personal que orquesta a Claude para desarrollar y diagnosticar Microsoft Power Platform (Canvas Apps + Power Automate) mediante control del navegador — sin APIs ni app registrations, usando la sesión ya autenticada del usuario.

## Palabra clave

"Anzo" o "Hola Anzo"

## Cómo se abre

Doble clic en el acceso directo **ANZO** del Escritorio (o en `Anzo.pyw`). Abre la ventana de la app, levanta el Chrome de trabajo, Playwright MCP y el router, y **cerrar la ventana apaga todo**. Sin consola; el detalle queda en `logs/anzo.log`. Para crear el acceso directo en otra máquina: `powershell -File scripts\install-shortcut.ps1`. La configuración (`ANZO_ROUTER`, `ANZO_ROUTER_KEY`...) va en `.env` (ver `.env.example`).

## Estado

En diseño. Ver `Anzo/` (vault de Obsidian) para decisiones de arquitectura y notas de avance.

## Alcance previsto

- Activación por voz (wake word), sin necesidad de tocar teclado/mouse para iniciar
- Narración hablada de lo que va haciendo
- Interrupción en caliente: poder detener, corregir o preguntar en cualquier momento, incluso a mitad de una tarea
- Ejecuta las instrucciones controlando el navegador (Power Apps Studio / Power Automate) igual que lo haría un humano

## Más tokens: claude-code-router (opcional)

Para que Anzo no dependa solo de la suscripción de Claude, puede pasar por [claude-code-router](https://github.com/musistudio/claude-code-router). Ver `Anzo/Decisiones.md` (sección "Integración con claude-code-router"). Resumen: `ANZO_ROUTER=router_first` (el de `.env`) usa primero los proveedores del router y la membresía de Claude como último recurso; `ANZO_ROUTER=fallback` hace lo contrario. La pantalla de ANZO muestra qué modelo respondió.
