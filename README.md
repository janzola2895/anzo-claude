# ANZO

Asistente de voz personal que orquesta a Claude para desarrollar y diagnosticar Microsoft Power Platform (Canvas Apps + Power Automate) mediante control del navegador — sin APIs ni app registrations, usando la sesión ya autenticada del usuario.

## Palabra clave

"Anzo" o "Hola Anzo"

## Estado

En diseño. Ver `Anzo/` (vault de Obsidian) para decisiones de arquitectura y notas de avance.

## Alcance previsto

- Activación por voz (wake word), sin necesidad de tocar teclado/mouse para iniciar
- Narración hablada de lo que va haciendo
- Interrupción en caliente: poder detener, corregir o preguntar en cualquier momento, incluso a mitad de una tarea
- Ejecuta las instrucciones controlando el navegador (Power Apps Studio / Power Automate) igual que lo haría un humano

## Más tokens: claude-code-router (opcional)

Para que Anzo no dependa solo de la suscripción de Claude, puede pasar por [claude-code-router](https://github.com/musistudio/claude-code-router). Ver `Anzo/Decisiones.md` (sección "Integración con claude-code-router"). Resumen: `ANZO_ROUTER=fallback` usa la suscripción y, al llegar el límite, sigue automáticamente con otros proveedores configurados en el router.
