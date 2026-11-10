# Guía de uso — ANZO + Claude

Cómo usar esta versión en el día a día. Detalle técnico en [[Arquitectura ANZO + Claude]].

## Abrir y cerrar

- Doble clic en **ANZO + Claude** (ícono naranja) en el Escritorio. El ícono azul **ANZO** es la versión original, que sigue existiendo aparte.
- Si tu Chrome estaba cerrado, ANZO lo abre: la extensión Claude in Chrome vive ahí.
- La primera vez, la ventana pide permiso de **micrófono**: acéptalo (queda recordado).
- Cerrar la ventana cierra ANZO. Tu Chrome y sus pestañas quedan abiertos.
- Al volver a abrir ANZO **retoma la sesión anterior** (si tiene menos de 12 horas): sigue viendo las pestañas del grupo AnzoBot y recuerda lo que estaban haciendo. La ventana lo avisa en el registro. Para empezar de cero di **"Anzo, sesión nueva"** (las pestañas viejas quedan abiertas, pero la sesión nueva no las ve). El plazo se cambia con `ANZO_SESSION_MAX_AGE_H` en `.env` (0 = nunca retomar). Ojo: una sesión larga cuesta más tokens por turno, porque cada turno relee todo.
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

**Modo USDT** (ciclo pesos ↔ USDT en Binance, ganando en cada cambio):

| Qué dices | Qué pasa |
|---|---|
| "Anzo, compra 10 USDT" / "compra 100 mil pesos de USDT" | **No compra**: busca la oferta P2P más barata que acepte ese monto (Nequi, Bancolombia, Bre-B, Daviplata, buena reputación). Dice cuánto pagarías y cómo quedaría tu meta si la compras. "Vende 50 USDT" hace lo mismo al revés |
| "Anzo, compré 152 USDT con 500 mil" | Lo anota en `ANZO archivos\modo-usdt.txt`. Si no tienes pesos del ciclo esperando, cuenta como plata nueva y se suma a lo que te costaron tus USDT. La primera compra queda como inversión inicial |
| "Viernes modo usdt" / "Anzo, modo usdt" | Mira tus saldos. Si tienes USDT, dice si venderlos hoy te da más pesos de lo que te costaron. Si tienes pesos del ciclo, si recomprar te da más USDT de los que entregaste. Usa P2P y el conversor. Si no es rentable, dice a qué precio lo sería. Deja el detalle en `ANZO archivos\modo-usdt-revision.txt` |
| "Anzo, vendí los USDT y me llegaron 540000" | Anota la venta. Desde ahí la meta es recomprar más USDT de los que entregaste. Si vendiste solo una parte, pregunta si esos pesos son para recomprar o los sacaste |

Cuenta lo que de verdad recibirías, con el gap ya incluido. La tasa de referencia del conversor no cuenta. La cotización real del conversor solo se ve si tienes sesión de Binance abierta en ese Chrome. Si no la tienes, revisa solo P2P y lo dice. ANZO no vigila el precio: vuelve a decir "modo usdt" más tarde. El historial es texto plano y lo puedes corregir a mano. Cada revisión cuesta del orden de 8 acciones del navegador.

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
| "Anzo, sesión nueva" | Olvida la sesión guardada y empieza una de cero |
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
- No ejecuta operaciones con dinero real: ni en modo oro, ni en modo USDT, ni en ningún otro caso (no toca el panel de trading, ni botones de comprar/vender/convertir, ni crea órdenes P2P).
- No guarda archivos fuera de `ANZO archivos`.
- No insiste sin fin: si un paso no le sale en 3 intentos, se detiene y te pide ayuda.

## La línea del modelo

Debajo del estado aparece `● Modelo: claude-sonnet-5 · Claude`. Punto verde: el último pedido salió bien. Punto rojo: falló (sin cupo o error). Antes del primer pedido muestra "Modelo: —".

## Si algo falla

| Síntoma | Qué hacer |
|---|---|
| "La extensión Claude in Chrome no está conectada" | Abre Chrome, revisa en `chrome://extensions` que Claude esté activa y repite el pedido. Si sigue, reinicia Chrome |
| "Llegaste al límite de uso de tu membresía de Claude" | Hay que esperar a que se reinicie el límite de tu plan |
| "Tu sesión de Claude se venció y no pude renovarla" | Abre una terminal, escribe `claude auth login` y entra con tu cuenta de claude.ai en el navegador. Luego repite el pedido; no hace falta reiniciar ANZO |
| Chrome pide permiso para un sitio | Acéptalo en Chrome; es el permiso por sitio de la extensión |
| Se queda "pensando" mucho rato | Mira el final de `C:\dev\anzo-claude\logs\anzo.log` |
| Modo oro dice que el gráfico sale en blanco / no puede leer las velas | Chrome cree que la ventana del grupo AnzoBot está tapada por otra y no la pinta. Déjala visible (segundo monitor, o junto a la ventana de ANZO, no debajo) y repite "modo oro". Alternativa: en `chrome://flags` pon "Calculate window occlusion on Windows" en Disabled y reinicia Chrome |
| "Llevo 60 acciones en esta tarea y todavía no termino..." | Paró solo para no gastar tokens. Si iba bien: "Anzo, sigue". Si estaba enredado, dile cómo hacerlo o hazlo tú. El tope se cambia con `ANZO_MAX_TOOL_CALLS` en `.env` |
| "Micrófono bloqueado" | Permite el micrófono en la ventana y vuelve a abrir ANZO |
| La extensión dejó de responder | Revisa si una página abrió una alerta y ciérrala a mano en Chrome |

## Dónde queda cada cosa

- Programa: `C:\dev\anzo-claude` (sin GitHub; los cambios se guardan con commits locales).
- Registro técnico: `C:\dev\anzo-claude\logs\anzo.log`.
- Capturas y archivos: `Escritorio\ANZO archivos`.
- Notas: esta bóveda (`C:\dev\anzo-claude\Anzo`); resúmenes de conversaciones en `Bitacora/`.
