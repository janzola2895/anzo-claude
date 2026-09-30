# Guía de uso — ANZO + Claude

Cómo usar esta versión en el día a día. Detalle técnico en [[Arquitectura ANZO + Claude]].

## Abrir y cerrar

- Doble clic en **ANZO + Claude** (ícono naranja) en el Escritorio. El ícono azul **ANZO** es la versión original, que sigue existiendo aparte.
- Si tu Chrome estaba cerrado, ANZO lo abre: la extensión Claude in Chrome vive ahí.
- La primera vez, la ventana pide permiso de **micrófono**: acéptalo (queda recordado).
- Cerrar la ventana cierra ANZO. Tu Chrome y sus pestañas quedan abiertos.
- No arranca solo con Windows.

## Hablarle

| Qué dices | Qué pasa |
|---|---|
| "Anzo, <pedido>" o "Hola Anzo, <pedido>" | Hace el pedido |
| "Anzo" solo | Queda escuchando tu siguiente frase |
| También despierta con | "Jarvis" / "Yarvis" / "Viernes" |

**Mientras está trabajando** solo lo interrumpe la palabra clave:

| Qué dices | Qué pasa |
|---|---|
| Cualquier frase sin "Anzo" | Se ignora (la conversación de la sala no lo corta) |
| "Anzo, para" / "detente" / "basta" / "cancela" / "silencio" | Detiene la tarea |
| "Anzo, <otra instrucción>" | Cambia a la nueva instrucción |

**Modo conversación** (no hace falta repetir "Anzo" entre frases):

| Qué dices | Qué pasa |
|---|---|
| "Anzo, modo conversación" (o el botón de la ventana) | Lo activa |
| "pausa" | Deja de escuchar sin salir del modo |
| "continúa" / "sigamos" / "sigue" | Retoma después de una pausa |
| "cambio y fuera" | Sale del modo conversación |

## Qué puede hacer

- Navegar y trabajar en **tu Chrome**, con tus sesiones ya iniciadas: Power Apps, Power Automate, TradingView, etc. Trabaja en sus propias pestañas (un grupo de pestañas de Claude) y las deja abiertas entre pedidos.
- Analizar gráficos de trading con la skill de análisis técnico (lectura educativa, nunca una orden de compra o venta).
- Guardar capturas y archivos en **Escritorio\ANZO archivos** ("guarda una captura", "déjalo en el escritorio").

## Qué no hace

- No ve las pestañas que abriste tú: si quieres que mire algo, pídele que lo abra.
- No inicia sesión por ti ni resuelve CAPTCHAs: te pide que lo hagas tú en Chrome.
- No ejecuta operaciones con dinero real.
- No guarda archivos fuera de `ANZO archivos`.

## La línea del modelo

Debajo del estado aparece `● Modelo: claude-sonnet-5 · Claude`. Punto verde: el último pedido salió bien. Punto rojo: falló (sin cupo o error). Antes del primer pedido muestra "Modelo: —".

## Si algo falla

| Síntoma | Qué hacer |
|---|---|
| "La extensión Claude in Chrome no está conectada" | Abre Chrome, revisa en `chrome://extensions` que Claude esté activa y repite el pedido. Si sigue, reinicia Chrome |
| "Llegaste al límite de uso de tu membresía de Claude" | Hay que esperar a que se reinicie el límite de tu plan |
| Chrome pide permiso para un sitio | Acéptalo en Chrome; es el permiso por sitio de la extensión |
| Se queda "pensando" mucho rato | Mira el final de `C:\dev\anzo-claude\logs\anzo.log` |
| "Micrófono bloqueado" | Permite el micrófono en la ventana y vuelve a abrir ANZO |
| La extensión dejó de responder | Revisa si una página abrió una alerta y ciérrala a mano en Chrome |

## Dónde queda cada cosa

- Programa: `C:\dev\anzo-claude` (sin GitHub; los cambios se guardan con commits locales).
- Registro técnico: `C:\dev\anzo-claude\logs\anzo.log`.
- Capturas y archivos: `Escritorio\ANZO archivos`.
- Notas: esta bóveda (`C:\dev\anzo-claude\Anzo`); resúmenes de conversaciones en `Bitacora/`.
