# Guía de uso — ANZO + Claude

Cómo usar esta versión en el día a día. Detalle técnico en [[Arquitectura ANZO + Claude]].

## Abrir y cerrar

- Doble clic en **ANZO + Claude** (ícono naranja) en el Escritorio. El ícono azul **ANZO** es la versión original, que sigue existiendo aparte.
- Si tu Chrome estaba cerrado, ANZO lo abre: la extensión Claude in Chrome vive ahí.
- La primera vez, la ventana pide permiso de **micrófono**: acéptalo (queda recordado).
- Cerrar la ventana cierra ANZO. Tu Chrome y sus pestañas quedan abiertos.
- No arranca solo con Windows.

## Grupo de pestañas "AnzoBot"

Las pestañas donde trabaja ANZO se agrupan en Chrome. La extensión Claude in Chrome llama a ese grupo "Claude"; la mini extensión **AnzoBot** (carpeta `chrome-extension/` del proyecto) lo renombra a "AnzoBot" y conserva el indicador de estado: ⌛ trabajando, 🔔 te necesita, ✅ terminó. Se instala una sola vez:

1. En Chrome abre `chrome://extensions`.
2. Activa **Modo de desarrollador** (arriba a la derecha).
3. Pulsa **Cargar descomprimida** y elige la carpeta `C:\dev\anzo-claude\chrome-extension`.

Si Chrome no deja activar el Modo de desarrollador, es una política del equipo de la empresa: el grupo seguirá diciendo "Claude" (puedes renombrarlo a mano con clic derecho sobre el nombre del grupo).

## Hablarle

| Qué dices | Qué pasa |
|---|---|
| "Anzo, <pedido>" o "Hola Anzo, <pedido>" | Hace el pedido |
| "Anzo" solo | Queda escuchando tu siguiente frase |
| También despierta con | "Jarvis" / "Yarvis" / "Viernes" |

**Modo oro** (análisis completo de XAUUSD con veredicto):

| Qué dices | Qué pasa |
|---|---|
| "Viernes modo oro" / "Anzo, modo oro" | Mira el calendario, el oro en H4/H1/M15/M5 y el dólar, y dice si hay setup válido, si hay que esperar a que el oro llegue a un precio, o si no hay setup. Deja el detalle en `ANZO archivos\modo-oro.md` |
| "Viernes modo oro" otra vez, cuando el oro llegó al precio | Reevalúa: si falta, lo dice sin repetir todo; si llegó, revisa noticia, sesión y gatillo y da el nuevo veredicto |

"Viernes" es el nombre del asistente, no el día. ANZO no vigila el precio por su cuenta: para que te avise, pon una alerta de TradingView en el precio que te diga. Funciona mejor si el gráfico ya tiene un layout guardado con EMA 20/50/200, VWAP, RSI, MACD y ATR (si faltan, lo dice y no gasta acciones agregándolos). Cada modo oro cuesta del orden de 15 acciones del navegador.

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
- No ejecuta operaciones con dinero real: ni en modo oro ni en ningún otro caso (no toca el panel de trading ni botones de comprar/vender).
- No guarda archivos fuera de `ANZO archivos`.
- No insiste sin fin: si un paso no le sale en 3 intentos, se detiene y te pide ayuda.

## La línea del modelo

Debajo del estado aparece `● Modelo: claude-sonnet-5 · Claude`. Punto verde: el último pedido salió bien. Punto rojo: falló (sin cupo o error). Antes del primer pedido muestra "Modelo: —".

## Si algo falla

| Síntoma | Qué hacer |
|---|---|
| "La extensión Claude in Chrome no está conectada" | Abre Chrome, revisa en `chrome://extensions` que Claude esté activa y repite el pedido. Si sigue, reinicia Chrome |
| "Llegaste al límite de uso de tu membresía de Claude" | Hay que esperar a que se reinicie el límite de tu plan |
| Chrome pide permiso para un sitio | Acéptalo en Chrome; es el permiso por sitio de la extensión |
| Se queda "pensando" mucho rato | Mira el final de `C:\dev\anzo-claude\logs\anzo.log` |
| "Llevo 60 acciones en esta tarea y todavía no termino..." | Paró solo para no gastar tokens. Si iba bien: "Anzo, sigue". Si estaba enredado, dile cómo hacerlo o hazlo tú. El tope se cambia con `ANZO_MAX_TOOL_CALLS` en `.env` |
| "Micrófono bloqueado" | Permite el micrófono en la ventana y vuelve a abrir ANZO |
| La extensión dejó de responder | Revisa si una página abrió una alerta y ciérrala a mano en Chrome |

## Dónde queda cada cosa

- Programa: `C:\dev\anzo-claude` (sin GitHub; los cambios se guardan con commits locales).
- Registro técnico: `C:\dev\anzo-claude\logs\anzo.log`.
- Capturas y archivos: `Escritorio\ANZO archivos`.
- Notas: esta bóveda (`C:\dev\anzo-claude\Anzo`); resúmenes de conversaciones en `Bitacora/`.
