---
name: modo-oro
description: Protocolo "Modo oro" para XAUUSD intradía. Hace el análisis completo (noticias, sesión, sesgo H4/H1, zona, confluencias, gatillo en M15/M5) y termina siempre en uno de tres veredictos técnicos - hay setup válido (con entrada, stop y objetivos), esperar a que el oro llegue a un precio y reevaluar allí, o no hay setup ahora. Usa esta skill SIEMPRE que el usuario diga "modo oro" (con o sin "Viernes" o "Anzo" delante - "Viernes" es el nombre con el que llama al asistente, no el día) o pida repetir o reevaluar el análisis del oro cuando llegue a un nivel. Solo analiza - nunca abre, modifica ni cierra operaciones.
---

# Modo oro

El usuario dice "Viernes modo oro" (o "Anzo, modo oro") y espera el análisis completo
de XAUUSD con una conclusión clara: **¿hay operación ahora, o hay que esperar a que el
oro llegue a un precio y evaluar de nuevo ahí?** Esta skill es autosuficiente: no
necesitas cargar `trading-chart-analysis` (usa las mismas lentes de estructura, medias,
momentum y Fibonacci/SMC, más contexto, filtros y un veredicto).

## 0. Reglas que no se negocian

- **Solo analizas.** Nunca abras, modifiques ni cierres operaciones. No toques el panel
  de trading ni el broker conectado en TradingView, ni botones Comprar/Vender/Buy/Sell,
  ni órdenes. No crees alertas ni cambies configuración de la cuenta: si una alerta
  ayuda, sugiérela y que la ponga el usuario.
- **No inventes.** Si un indicador o un dato no se ve (no hay RSI, el calendario no
  cargó), dilo y baja la confianza. Mejor un análisis con menos datos honestos que uno
  completo con datos inventados.
- **Cuida las acciones** (cada una gasta tokens de la membresía). Apunta a unas 15
  llamadas y nunca pases de 30. Agrupa con `browser_batch` (navegar, esperar 2 s,
  captura), no tomes dos capturas seguidas sin hacer nada entre ellas y respeta la regla
  de máximo 3 intentos por paso. Si un paso no sale, sigue sin él y dilo.
- **No dejes el análisis a medias por perfección.** Si faltan datos, entrega el
  veredicto con lo que viste y di qué faltó.

## 1. ¿Análisis nuevo o reevaluación?

Es **reevaluación** si en esta conversación ya hiciste un modo oro hoy y su veredicto fue
"esperar", o si existe `modo-oro.md` en la carpeta ANZO archivos con la fecha de hoy
(léelo con Read; si no puedes leerlo, haz el análisis completo). En ese caso ve a la
sección 6. Si no, sigue con la 2.

## 2. Reunir los datos

Todo sale de tradingview.com, donde el usuario ya tiene sesión (no pide permisos nuevos).
Usa la pestaña de TradingView de tu grupo si ya existe; si no, abre una. Orden:

1. **Calendario económico.** Navega a `https://www.tradingview.com/economic-calendar/` y
   toma una captura. Ahí lees: la hora local actual (arriba a la derecha, p. ej.
   "10:26 (UTC-5)" es hora de Colombia), el día, los eventos de EE. UU. (bandera) de las
   próximas horas, su impacto (las barras del icono: más barras llenas, más impacto) y
   los "Coming in".
2. **Gráfico del oro, por URL**, una captura por intervalo (probado: la URL cambia
   símbolo e intervalo, y el título de la pestaña muestra el precio, p. ej.
   "XAUUSD 4190.7 ▲ +1.38%"):
   - H4: `https://www.tradingview.com/chart/?symbol=OANDA%3AXAUUSD&interval=240`
   - H1: el mismo con `interval=60`
   - M15: `interval=15`
   - M5: `interval=5`

   Si la URL no cambia el intervalo, como último recurso haz clic en el gráfico, escribe
   el número del intervalo (240, 60, 15 o 5) y pulsa Enter. Usa `zoom` solo si necesitas
   leer bien precios o paneles.
3. **Dólar (DXY).** `https://www.tradingview.com/chart/?symbol=TVC%3ADXY&interval=60`,
   una captura: el oro suele moverse al revés del dólar. El US10Y (`TVC%3AUS10Y`) solo
   si te sobra presupuesto.
4. **Indicadores.** Lee los que ya estén en el gráfico (EMAs, VWAP, RSI, MACD, ATR). No
   gastes acciones agregándolos (un intento como máximo). Si faltan, dilo y sugiere que
   el usuario guarde un layout con EMA 20/50/200, VWAP, RSI, MACD y ATR para que modo oro
   los lea sin gastar acciones.

Sesión líquida, en hora de Colombia: Londres aprox. 2:00-5:00 a.m. y Nueva York aprox.
7:00-11:00 a.m. (puede variar 1 h por los cambios de horario). Asia suele ser rango.

## 3. Filtros: si falla uno, no hay entrada ahora

- **F1 Noticia:** un dato de EE. UU. de impacto alto, o un discurso importante de la
  Fed, dentro de ±30 minutos. Se espera por tiempo: reevaluar 15-30 min después.
- **F2 Sesión:** fuera de sesión líquida, o viernes después de las 11:00 a.m. (hora de
  Colombia). Se espera a la siguiente apertura o al lunes.
- **F3 Volatilidad y spread:** velas diminutas sin recorrido para llegar a 1:2, o spread
  anormal si se ve.
- **F4 Riesgo-beneficio:** con el stop detrás de la estructura que invalida la idea (más
  un colchón de ATR o spread), el objetivo en la liquidez o nivel opuesto debe dar al
  menos **1:2**. Si no da, no vale la pena aunque el resto se vea bien.

## 4. Las 8 confluencias

Evalúa el lado que marca el sesgo. Si H4 y H1 se contradicen, la confluencia 1 falla y
dilo. Cuenta cuántas se cumplen y cuáles.

1. **Sesgo H4:** dirección clara y el trade va a su favor.
2. **Estructura H1:** máximos/mínimos crecientes o decrecientes, BOS/CHoCH alineado.
3. **Nivel clave:** el precio está en o cerca de un máximo/mínimo del día anterior o de
   Asia, un número redondo (xx00/xx50) o un soporte/resistencia respetado.
4. **Liquidez:** hubo un barrido de máximos/mínimos iguales, o hay un objetivo claro de
   liquidez al otro lado.
5. **Zona:** el precio está dentro de un Order Block, FVG/imbalance o zona de
   oferta/demanda.
6. **Fibonacci:** retroceso de 50 % a 78.6 % del último swing, comprando en descuento o
   vendiendo en premium.
7. **Gatillo M5/M15:** CHoCH o BOS en la dirección del trade más una vela de rechazo ya
   cerrada. Entrar solo porque el precio llegó a la zona no cuenta.
8. **Indicadores:** EMAs, VWAP, RSI/MACD apoyan o, al menos, no contradicen (una
   divergencia en contra sí cuenta como fallo).

## 5. Veredicto: exactamente uno de tres

**A. HAY SETUP VÁLIDO** si los 4 filtros pasan, se cumplen al menos 5 de las 8
confluencias **incluyendo la 5 (zona) y la 7 (gatillo)**, y el precio está en la zona
ahora. Da: lado, entrada, stop, TP1 y TP2, riesgo-beneficio y el precio que invalida la
idea.

**B. ESPERAR Y REEVALUAR** si el sesgo es claro y hay una zona identificable, pero el
precio aún no está en ella o falta el gatillo (o un filtro de tiempo, F1 o F2, bloquea).
Da: el **precio exacto o el rango** donde reevaluar, qué debe verse ahí (por ejemplo,
barrido y CHoCH en M5 con cierre de rechazo), el **precio que invalida** la idea (si
llega ahí antes, se descarta) y, si el bloqueo es por noticia o sesión, la **hora** de
reevaluación. Sugiere una alerta de TradingView en ese precio, porque Anzo no vigila el
mercado por su cuenta: el usuario vuelve a decir "modo oro" cuando llegue.

**C. NO HAY SETUP** si no hay sesgo (H4 y H1 se contradicen o es rango sin estructura),
no hay zona identificable o F3/F4 fallan sin arreglo. Di por qué y qué tendría que
cambiar (por ejemplo, que rompa tal nivel con cierre en H1).

Cuando dudes entre A y B, di B. Cuando dudes entre B y C, explica la duda y elige C.

## 6. Reevaluación

Cuando el usuario vuelve a decir "modo oro" con un plan en espera:

1. Recupera el plan (conversación o `modo-oro.md`). Mira el precio actual: basta el
   título de la pestaña de TradingView (`tabs_context_mcp` lo devuelve) o una captura.
2. **Si el precio no llegó al nivel:** dilo en una o dos frases ("sigue en X, falta Y
   para la zona") y mantén el plan, sin repetir el análisis. Si ya pasó la hora que
   dejaste, repite solo el calendario.
3. **Si llegó al nivel:** repite filtros F1 y F2 (calendario), toma M15 y M5 (y H1 si
   hay duda), comprueba la condición que dejaste escrita y entrega A, B (con un nivel
   nuevo) o C.
4. **Si tocó el precio de invalidación:** dilo, descarta el plan y ofrece un análisis
   completo nuevo.
5. Actualiza `modo-oro.md`.

## 7. Cómo entregarlo (se lee en voz alta)

Frases cortas y naturales, sin markdown, sin listas y sin tablas. Los precios sin coma de
miles y con un decimal como mucho (4190.5), para que la voz los lea bien. Orden:

1. **El veredicto primero**, en una frase. Ejemplos: "Modo oro: hay setup comprador
   válido." / "Modo oro: todavía no entres, espera a que el oro llegue a 4175." / "Modo
   oro: ahora no hay setup."
2. **Por qué**, en tres o cuatro frases: noticia y sesión, sesgo en H4 y H1, zona, y
   cuántas confluencias de ocho se cumplen (nombra las que faltan).
3. **Los niveles**, según el veredicto. A: entrada, stop, objetivos y riesgo-beneficio.
   B: dónde reevaluar, qué debe verse ahí y qué precio invalida. C: qué tendría que
   cambiar.
4. Una frase: "Dejé el detalle en la carpeta ANZO archivos, en modo-oro.md."
5. **Cierre obligatorio:** es una lectura técnica educativa, no una recomendación de
   inversión personalizada, y la decisión de operar es del usuario. Nunca digas "compra
   ahora" ni "vende ahora": di "hay setup válido de compra" y describe por qué.

## 8. El archivo con el detalle

Con Write, sobrescribe `modo-oro.md` en la carpeta ANZO archivos (la misma que indica el
prompt de sistema). Un intento; si falla, dilo y sigue. Contenido, en markdown (el
archivo sí puede llevar tablas):

- Título con fecha y hora local, precio del oro y veredicto (A, B o C) con el lado.
- El plan: entrada, stop, TP1, TP2, riesgo-beneficio, precio que invalida y dónde o a
  qué hora reevaluar.
- Una tabla `| # | Elemento | Resultado |` con F1-F4 y las 8 confluencias (cumple,
  no cumple o no se vio, con el dato corto que lo respalda).
- Una nota de tamaño: arriesgar 0.5-1 % de la cuenta; en XAUUSD 1 lote = 100 oz, así que
  lotes = riesgo en dólares ÷ (distancia al stop en dólares × 100).
- La línea de que es una lectura técnica educativa y la decisión es del usuario.
