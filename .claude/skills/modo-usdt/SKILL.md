---
name: modo-usdt
description: Protocolo "Modo USDT" para el ciclo pesos colombianos <-> USDT en Binance. Lee el historial del usuario (modo-usdt.txt en la carpeta ANZO archivos), mira las ofertas P2P y el conversor de Binance, y dice si cambiar AHORA es rentable - vender USDT solo si recibe más pesos de lo que le costaron, y recomprar solo si recibe más USDT de los que entregó. También busca la mejor oferta para comprar o vender una cantidad ("compra 10 usdt" busca dónde comprarlos más barato, no compra nada), y anota en el historial cada cambio y cada aporte de plata nueva que el usuario dice que hizo. Usa esta skill SIEMPRE que el usuario diga "modo usdt" (con o sin "Viernes" o "Anzo" delante - "Viernes" es el nombre del asistente, no el día; el dictado puede escribirlo "modo u s d t", "modo usd" o "modo tether"), pida comprar o vender una cantidad de USDT, pregunte si conviene pasar los USDT a pesos o los pesos a USDT, o diga que compró o vendió USDT. Solo revisa y anota - nunca compra, vende, convierte ni abre órdenes.
---

# Modo USDT

El usuario va y viene entre pesos colombianos (COP) y USDT en Binance, y quiere ganar
en **cada** cambio:

- Vender USDT solo es rentable si recibe **más pesos** de lo que le costaron esos USDT.
- Recomprar USDT con los pesos del ciclo solo es rentable si recibe **más USDT** de los
  que entregó para tener esos pesos.

Lo que cuenta es lo que **de verdad recibiría**: el precio real de la oferta (que ya trae
el gap entre compra y venta) o la cotización real del conversor (que ya trae su costo).
Cualquier cantidad por encima de la meta cuenta como rentable.

Además puede meter **plata nueva** ("Anzo, compra 10 USDT"): ahí no hay meta que
superar, solo se busca la oferta más barata para esa cantidad. Cuando la compra, esa
plata se suma a lo que le costaron sus USDT.

## 0. Reglas que no se negocian

- **Solo revisas y anotas.** "Compra 10 USDT" o "vende 50 USDT" significa **buscar la
  mejor oferta**, nunca comprar ni vender. En P2P no abras ofertas, no pulses
  Comprar/Vender, no crees órdenes ni escribas a nadie. En el conversor no pulses ningún
  botón (ni Previsualizar, ni Convertir, ni Confirmar): solo escribes el monto y lees. No
  muevas fondos ni cambies nada de la cuenta. Si aparece un aviso de cookies, elige
  "Rechazar todas".
- **No inventes.** Si un dato no se ve, dilo. El historial solo guarda lo que el usuario
  dice que hizo, con las cantidades que él dice, nunca las de tu cotización.
- **Cuida las acciones.** Apunta a unas 8 llamadas y nunca pases de 15. Máximo 3
  intentos por paso; si un paso no sale, sigue sin él y dilo.
- No sabes los saldos reales del usuario: el historial es la única fuente.

## 1. El historial: `modo-usdt.txt`

Vive en la carpeta ANZO archivos (la que indica el prompt de sistema). Léelo primero con
Read. Lleva **dos saldos** y cada línea termina con cómo quedan después de esa
operación:

- **USDT** y **costaron COP**: cuántos USDT tiene y cuántos pesos le costaron en total.
- **COP** y **salieron de USDT**: cuántos pesos del ciclo tiene esperando recompra y de
  cuántos USDT salieron.

Formato exacto (texto plano, la línea más reciente al final):

```
MODO USDT - historial (lo lleva ANZO; puedes corregirlo a mano)
Inversion inicial: 500000 COP
APORTE = compraste USDT con plata nueva. VENTA = pasaste USDT a pesos para recomprar despues.
COMPRA = pasaste pesos del ciclo a USDT. RETIRO = vendiste USDT y sacaste los pesos.
fecha hora | operacion | entregaste | recibiste | precio COP por USDT | canal | USDT | costaron COP | COP | salieron de USDT
---
2026-11-10 09:15 | APORTE | 500000 COP | 152 USDT | 3289.47 | P2P | 152 | 500000 | 0 | 0
2026-11-11 10:00 | APORTE | 32720 COP | 10 USDT | 3272.00 | P2P | 162 | 532720 | 0 | 0
2026-11-12 14:02 | VENTA | 162 USDT | 540000 COP | 3333.33 | P2P | 0 | 0 | 540000 | 162
```

- El precio es pesos ÷ USDT de esa línea, con 2 decimales. Canal: P2P, Convert u Otro.
- Montos sin separador de miles (505000, no 505.000). USDT con hasta 2 decimales.
- "Inversion inicial" son los pesos del primer APORTE; no se cambia después.
- Fecha y hora de Colombia: las da el código de la sección 3 (`hora`). Si no lo
  corriste, usa la fecha del sistema y omite la hora.

**Cómo cambia cada operación los saldos** (parte de los saldos de la línea anterior;
"proporcional" = valor × lo que queda ÷ lo que había, redondeado; si se mueve todo,
queda en 0):

| Operación | USDT | costaron COP | COP | salieron de USDT |
|---|---|---|---|---|
| APORTE | + recibiste | + entregaste | igual | igual |
| VENTA | − entregaste | proporcional | + recibiste | + entregaste |
| COMPRA | + recibiste | + entregaste | − entregaste | proporcional |
| RETIRO | − entregaste | proporcional | igual | igual |

**Las metas salen de la última línea:**

- Con USDT > 0: vender es rentable si recibe **más de "costaron COP"**. Precio de
  equilibrio = costaron COP ÷ USDT (le tienen que pagar más que eso por USDT).
- Con COP > 0: recomprar es rentable si recibe **más de "salieron de USDT"**. Precio de
  equilibrio = COP ÷ salieron de USDT (tiene que pagar menos que eso por USDT).

## 2. ¿Qué pidió el usuario?

1. **Anotar algo que ya hizo**, en pasado y con las dos cantidades ("compré 152 USDT
   con 500 mil", "vendí los USDT y me llegaron 505000"): sección 6. No revises Binance.
2. **Buscar la mejor oferta para una cantidad** ("compra 10 USDT", "quiero comprar 100
   mil pesos de USDT", "vende 50 USDT", "voy a meter más plata"): sección 5. Si no dice
   la cantidad, pregúntala en una frase.
3. **"Modo usdt"** o "¿conviene cambiar?": si no hay historial, pregunta en una frase
   cuántos pesos invirtió y cuántos USDT recibió (no revises Binance todavía). Si hay,
   secciones 3 y 4.

El dictado puede quitar la tilde ("compre 10 usdt"): si dice cuántos pesos pagó es
anotar; si solo da una cantidad, es buscar oferta. Si de verdad no se sabe, pregunta.

## 3. Revisar Binance

Usa una pestaña de tu grupo; abre o reutiliza una en el conversor del lado que toca:

- Vender USDT (`SELL`): `https://www.binance.com/es/convert/USDT/COP`
- Comprar USDT (`BUY`): `https://www.binance.com/es/convert/COP/USDT`

**P2P, con una sola llamada a `javascript_tool`** en esa pestaña (la página debe ser de
www.binance.com; no hace falta sesión). Cambia solo las cuatro constantes de arriba:

- `LADO`: `'SELL'` (vender USDT) o `'BUY'` (comprar USDT).
- `UNIDAD` y `MONTO`: la cantidad y en qué está, `'USDT'` o `'COP'`.
- `META`: lo que hay que superar en el chequeo del ciclo (SELL con USDT: pesos; BUY con
  COP: USDT), o `null` si solo buscas la mejor oferta.

Toma solo ofertas pagadas por Nequi, Bancolombia, llaves Bre-B o Daviplata, que acepten
el monto completo y con buena reputación (90 % o más de órdenes completadas y al menos
20 órdenes en el mes). Si el usuario tiene USDT y pesos a la vez, corre el código una
vez por lado.

```js
await (async () => {
  const LADO = 'SELL', UNIDAD = 'USDT', MONTO = 152, META = 500000;
  const PAGOS = ['Nequi', 'BancolombiaSA', 'BreBKeys', 'Daviplata'];
  const j = (u, b) => fetch(u, b ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) } : undefined).then(r => r.json());
  const ref = (await j('/bapi/margin/v1/public/new-otc/pair-price-change?fromCoin=USDT&toCoin=COP')).data?.currentRate;
  const pesos = UNIDAD === 'COP' ? MONTO : Math.round(MONTO * ref);
  const d = await j('/bapi/c2c/v2/friendly/c2c/adv/search', { fiat: 'COP', asset: 'USDT', tradeType: LADO, page: 1, rows: 20, payTypes: PAGOS, publisherType: null, transAmount: String(pesos), countries: [] });
  const ofertas = (d.data || []).map(x => {
    const a = x.adv, u = x.advertiser, p = +a.price;
    const usdt = UNIDAD === 'USDT' ? MONTO : Math.floor(MONTO / p * 100) / 100;
    const cop = UNIDAD === 'COP' ? MONTO : Math.round(MONTO * p);
    return { precio: p, usdt, cop, min: +a.minSingleTransAmount, max: +a.maxSingleTransAmount, disponible: +a.tradableQuantity, pagos: a.tradeMethods.map(m => m.tradeMethodName).join(', '), usuario: u.nickName, ordenesMes: u.monthOrderCount, completadas: Math.round(u.monthFinishRate * 100) };
  }).filter(o => o.cop >= o.min && o.cop <= o.max && o.usdt <= o.disponible && o.completadas >= 90 && o.ordenesMes >= 20)
    .sort((a, b) => LADO === 'SELL' ? b.precio - a.precio : a.precio - b.precio).slice(0, 3);
  const mejor = ofertas[0], ciclo = META != null && UNIDAD === (LADO === 'SELL' ? 'USDT' : 'COP');
  const recibes = mejor ? (LADO === 'SELL' ? mejor.cop : mejor.usdt) : null;
  return { hora: new Date().toLocaleString('es-CO', { timeZone: 'America/Bogota' }), lado: LADO, unidad: UNIDAD, monto: MONTO, meta: META, equilibrio: ciclo ? +(LADO === 'SELL' ? META / MONTO : MONTO / META).toFixed(2) : null, referenciaConvert: ref, ofertas, rentable: ciclo && mejor ? recibes > META : null, diferencia: ciclo && mejor ? +(recibes - META).toFixed(2) : null };
})()
```

`ofertas` trae las 3 mejores ya filtradas: `usdt` y `cop` son lo que entrega y recibe
con cada una (al vender recibe `cop`; al comprar paga `cop` y recibe `usdt`). Si sale
vacío, ninguna oferta cumple: dilo. Si el código falla (Binance cambió algo), como
respaldo navega a `https://p2p.binance.com/es/trade/sell/USDT?fiat=COP` (SELL) o
`.../trade/buy/USDT?fiat=COP` (BUY), lee con `get_page_text` y aplica tú los mismos
filtros. `referenciaConvert` es una tasa de referencia sin el gap: **nunca la uses para
decidir**.

**Conversor (cotización real, necesita sesión).** Toma una captura de la pestaña. Si
"Saldo disponible" muestra un número, hay sesión: con `find` ubica el campo "De", haz
clic, escribe lo que entrega (sin separadores), espera 2 s y toma otra captura (todo en
un `browser_batch`). Lee lo que muestra el campo "A": eso es lo que recibiría. No pulses
ningún botón. Si dice "--", pide iniciar sesión o no muestra monto sin previsualizar,
sigue solo con P2P y dilo en una frase.

Ojo con el conversor: deja los pesos dentro de Binance (o los toma de ahí). Si el
usuario tiene la plata en el banco, pasarla tiene sus propios pasos y posibles costos
que no ves; menciónalo si el conversor es la mejor opción.

## 4. Veredicto del ciclo ("modo usdt")

La mejor opción es la que da más (más pesos si vende, más USDT si recompra) entre la
mejor oferta P2P y la cotización real del conversor. Por cada saldo mayor que 0:

- **SÍ ES RENTABLE** si la mejor opción supera la meta. Di cuánto gana (en pesos o USDT,
  y en %) y dónde: canal, precio, medio de pago, nombre del comprador o vendedor y su
  límite.
- **NO ES RENTABLE TODAVÍA** si ninguna la supera. Di cuánto le falta y el **precio de
  equilibrio**: al vender, "necesitas que te paguen más de X pesos por USDT, hoy la
  mejor oferta paga Y"; al recomprar, "necesitas pagar menos de X pesos por USDT, hoy lo
  más barato es Y". ANZO no vigila el precio: el usuario vuelve a decir "modo usdt" más
  tarde.

Los precios P2P cambian en minutos: lo que dices vale para este momento.

## 5. Mejor oferta para una cantidad ("compra 10 USDT")

1. Corre el código con `META = null`. Ejemplos: "compra 10 USDT" → `'BUY', 'USDT', 10`;
   "compra 100 mil pesos de USDT" → `'BUY', 'COP', 100000`; "vende 50 USDT" →
   `'SELL', 'USDT', 50`. Mira el conversor como en la sección 3.
2. Al comprar, la mejor es la de **precio más bajo**; al vender, la de **precio más
   alto**, siempre entre las que aceptan ese monto. Di: precio por USDT, cuánto pagaría
   o recibiría en total, medio de pago, usuario y reputación. Si la segunda paga por
   otro medio y casi al mismo precio, nómbrala también.
3. Si hay historial, ponlo en contexto con la cuenta de la sección 1, sin decirle qué
   hacer:
   - Comprar con plata nueva: "si la compras, quedarías con 162 USDT que te costaron
     532720 pesos; para vender con ganancia te tendrían que pagar más de 3288.4 por
     USDT".
   - Vender una parte: compara el precio con lo que le costó cada USDT (costaron COP ÷
     USDT) y di si a ese precio vendería por encima o por debajo de su costo.
4. Recuérdale que, si hace el cambio, te diga cuánto entregó y cuánto recibió para
   anotarlo.

## 6. Anotar lo que hizo

1. Necesitas **entregaste** y **recibiste** reales. Si falta uno (por ejemplo "ya
   vendí" sin decir cuántos pesos le llegaron), pregúntalo en una frase y no anotes
   nada todavía. "Recibí lo que me dijiste" no vale: pide el número que le llegó.
2. Elige la operación con los saldos de la última línea:
   - Compró USDT y **COP = 0**: APORTE (plata nueva).
   - Compró USDT y **COP > 0**: si usó todos los pesos del ciclo, COMPRA. Si el monto no
     coincide, pregunta en una frase si esos pesos salieron del ciclo o son plata nueva
     (APORTE).
   - Vendió **todos** sus USDT: VENTA, salvo que diga que sacó la plata (RETIRO).
   - Vendió **una parte**: pregunta en una frase si esos pesos son para recomprar
     después (VENTA) o si los sacó (RETIRO).
3. Si el archivo no existe, créalo con el encabezado de la sección 1. El primer APORTE
   fija la "Inversion inicial".
4. Calcula el precio y los cuatro saldos con la tabla de la sección 1, y agrega la línea
   al final con Edit (o reescribe el archivo completo con Write sin perder ninguna
   línea). Si entregó más de lo que el historial dice que tenía, anótalo igual y avísale
   en una frase que revise el archivo.
5. Confirma por voz lo anotado y cómo quedan las metas: "Anotado: compraste 10 USDT con
   32720 pesos de plata nueva. Ahora tienes 162 USDT que te costaron 532720 pesos; para
   vender con ganancia necesitas más de 3288.4 por USDT."

## 7. Cómo entregarlo (se lee en voz alta)

Frases cortas, sin markdown, sin listas y sin tablas. Pesos sin separador de miles
(493270 pesos), USDT con hasta 2 decimales y precios por USDT con 1 decimal como mucho.

- **Ciclo:** el veredicto primero ("Modo USDT: todavía no es rentable vender, recibirías
  493270 pesos y te costaron 500000."), luego dónde y por qué en dos o tres frases, y el
  precio de equilibrio si no es rentable.
- **Mejor oferta:** primero la oferta ("Para comprar 10 USDT, lo más barato ahora es
  Cambios_Zoeh a 3272 pesos por USDT: pagarías 32720 por Bancolombia."), luego la
  reputación y la alternativa, y el contexto del historial.

Después de revisar Binance (ciclo u oferta), con Write sobrescribe
`modo-usdt-revision.txt` en la carpeta ANZO archivos (un intento): fecha y hora, qué
se revisó, los saldos y metas del historial, las 3 ofertas P2P (precio, montos, medio de
pago, usuario, límites, reputación), el conversor (o por qué no se vio), la tasa de
referencia marcada como referencia, la conclusión y la línea de que es un cálculo con
precios del momento y la decisión es del usuario. **Al revisar no toques
`modo-usdt.txt`.** Di en una frase: "Dejé el detalle en la carpeta ANZO archivos, en
modo-usdt-revision.txt."

**Cierre obligatorio:** es un cálculo con los precios de este momento, no una
recomendación de inversión, y la decisión y la operación son del usuario. Nunca digas
"vende ya" ni "compra ya": di "es rentable vender a este precio" o "esta es la oferta más
barata" y por qué.
