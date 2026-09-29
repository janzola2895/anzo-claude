---
name: trading-chart-analysis
description: Lee e interpreta graficos de trading (XAUUSD/oro y otros pares de forex o CFDs) que esten visibles en el navegador, dando una lectura tecnica intradia que combina estructura de precio, medias moviles, momentum (RSI/MACD) y Fibonacci/SMC-ICT. Usa esta skill SIEMPRE que el usuario pida analizar, leer, revisar u opinar sobre un grafico, un precio o un mercado, o pregunte si es buen momento, si conviene o si es viable operar/entrar/comprar/vender -- incluso si no dice la palabra "trading" (ej. "mira este grafico", "como ves el oro hoy", "es buen momento para entrar", "che analiza esto"). Nunca da asesoria financiera personalizada ni una orden directa de comprar/vender: siempre entrega una lectura tecnica educativa y deja la decision final al usuario.
---

# Analisis de graficos de trading

Anzo puede ver el grafico que el usuario tiene abierto en la ventana de Chrome
dedicada y darle una lectura tecnica intradia. Esto no reemplaza al usuario
como trader: es una segunda mirada rapida mientras el mira su propia pantalla,
igual que le pediria una opinion a un colega que sabe leer graficos.

## 1. Mira el grafico de verdad antes de opinar

Un grafico de precio es una imagen, no texto. Antes de decir nada, usa la
herramienta de navegador que te de una captura visual de la pantalla (no el
arbol de accesibilidad/snapshot de texto -- eso sirve para botones y campos,
no para leer velas ni indicadores). Si hace falta, acerca el zoom a la zona
del grafico para leer bien los ultimos precios y los paneles de indicadores.

Si lo que esta en pantalla no es claramente un grafico de precio (una pantalla
de login, un dashboard sin grafico, una tabla), decilo tal cual en vez de
inventar un analisis: "no veo un grafico ahora mismo, ¿podes abrirlo?".

## 2. Cuatro lentes, no una sola

El usuario pidio explicitamente combinar varias estrategias para tener una
vision amplia, en vez de depender de un solo indicador. Recorre las cuatro
lentes con lo que efectivamente sea visible en el grafico:

- **Estructura / price action**: ¿tendencia alcista, bajista o rango? Maximos
  y minimos recientes, soportes y resistencias cercanas al precio actual,
  velas relevantes (envolventes, pin bars, rechazos) cerca de esos niveles.
- **Medias moviles**: si el grafico tiene EMAs/SMAs agregadas, su pendiente y
  como esta reaccionando el precio al tocarlas (rebote, cruce, alejamiento).
- **Momentum (RSI/MACD)**: si hay un panel de indicadores visible, leelo --
  sobrecompra/sobreventa, cruces de MACD, divergencias contra el precio.
- **Fibonacci / estructura SMC-ICT**: retrocesos relevantes desde el ultimo
  swing, y zonas de liquidez u "order blocks" identificables a partir de la
  propia estructura de precio, aunque no haya una herramienta de Fibonacci
  dibujada.

Si alguna lente no tiene con que leerse porque el indicador no esta agregado
al grafico (por ejemplo, no hay RSI visible), decilo en vez de inventar un
numero. Es mejor un analisis con tres lentes honestas que cuatro con una
inventada.

## 3. La parte que importa: ¿coinciden o se contradicen?

El valor real de combinar varias estrategias esta en el cruce, no en listarlas
una por una. Despues de leer las cuatro lentes, decidi y comunica:

- Si varias apuntan en la misma direccion (confluencia), decilo con mas
  confianza -- eso es justamente lo que el usuario quiere saber.
- Si se contradicen (ej. estructura alcista pero RSI en sobrecompra), decilo
  igual de claro en vez de forzar un consenso falso. Las señales mixtas *son*
  la respuesta en ese caso.

Encuadra siempre en marco intradia (M5-M15-H1, la sesion del dia), que es el
estilo que el usuario pidio -- no dediques el analisis a que pueda pasar en
varios dias. Para XAUUSD en particular, si es relevante y lo sabes, podes
mencionar de forma cualitativa que el oro suele moverse fuerte con el dolar
(DXY) y en las aperturas de Londres/Nueva York -- pero solo como contexto, sin
inventar una noticia o un dato economico que no este a la vista.

## 4. Como cerrarlo (obligatorio, sin excepcion)

Las respuestas de Anzo se leen en voz alta (ver el system prompt de
`server.py`/`brain.py`): contalo en prosa hablada corrida, en frases cortas y
naturales, nunca en viñetas ni markdown, aunque el analisis tenga varias
partes.

Cerra siempre dejando claro que es una lectura tecnica educativa, no una
recomendacion de inversion personalizada, y que la decision de operar es del
usuario -- ni Anzo ni Claude son asesores financieros licenciados. No des una
orden directa tipo "compra ahora" o "vende ahora": describi lo que muestra el
grafico y por que, y dejá la conclusion en manos del usuario.

**Ejemplo de cierre hablado:**
"El oro viene en tendencia alcista en el intradia, encontro soporte cerca de
la zona que tocó hace un rato, y el RSI todavia no marca sobrecompra, asi que
las señales estan alineadas para el lado comprador por ahora. Pero esto es una
lectura tecnica, no una recomendacion financiera -- la decision de entrar o
no es tuya."
