---
name: modo-usdt
description: Protocolo "Modo USDT" para el ciclo pesos colombianos <-> USDT en Binance. Lee el historial de cambios del usuario (modo-usdt.txt en la carpeta ANZO archivos), mira las ofertas P2P y el conversor de Binance, y dice si cambiar AHORA es rentable - vender USDT solo si recibe más pesos de los que pagó en el último cambio, y comprar USDT solo si recibe más USDT de los que entregó. También anota en el historial cada cambio que el usuario dice que hizo y la inversión inicial. Usa esta skill SIEMPRE que el usuario diga "modo usdt" (con o sin "Viernes" o "Anzo" delante - "Viernes" es el nombre del asistente, no el día; el dictado puede escribirlo "modo u s d t", "modo usd" o "modo tether"), pregunte si conviene pasar los USDT a pesos o los pesos a USDT, o diga que compró o vendió USDT. Solo revisa y anota - nunca compra, vende, convierte ni abre órdenes.
---

# Modo USDT

El usuario va y viene entre pesos colombianos (COP) y USDT en Binance, y quiere ganar
en **cada** cambio:

- Si tiene **USDT**, venderlos solo es rentable si recibe **más pesos** de los que pagó
  por esos USDT en su último cambio.
- Si tiene **pesos**, comprar USDT solo es rentable si recibe **más USDT** de los que
  entregó en su último cambio.

Lo que cuenta es lo que **de verdad recibiría**: el precio real de la oferta (que ya trae
el gap entre compra y venta) o la cotización real del conversor (que ya trae su costo).
Cualquier cantidad por encima de la meta cuenta como rentable.

## 0. Reglas que no se negocian

- **Solo revisas y anotas.** Nunca compres, vendas ni conviertas. En P2P no abras
  ofertas, no pulses Comprar/Vender, no crees órdenes ni escribas a nadie. En el
  conversor no pulses ningún botón (ni Previsualizar, ni Convertir, ni Confirmar): solo
  escribes el monto y lees. No muevas fondos ni cambies nada de la cuenta. Si aparece un
  aviso de cookies, elige "Rechazar todas".
- **No inventes.** Si un dato no se ve, dilo. El historial solo guarda cambios que el
  usuario dice que hizo, con las cantidades que él dice, nunca las de tu cotización.
- **Cuida las acciones.** Apunta a unas 8 llamadas y nunca pases de 15. Máximo 3
  intentos por paso; si un paso no sale, sigue sin él y dilo.
- No sabes los saldos reales del usuario: el historial es la única fuente.

## 1. El historial: `modo-usdt.txt`

Vive en la carpeta ANZO archivos (la que indica el prompt de sistema). Léelo primero con
Read. Formato exacto (texto plano, una línea por cambio, la más reciente al final):

```
MODO USDT - historial de cambios (lo lleva ANZO; puedes corregirlo a mano)
Inversion inicial: 500000 COP
Formato: fecha hora | operacion | entregaste | recibiste | precio COP por USDT | canal
COMPRA = pesos a USDT. VENTA = USDT a pesos.
---
2026-11-10 09:15 | COMPRA | 500000 COP | 152 USDT | 3289.47 | P2P
2026-11-12 14:02 | VENTA | 152 USDT | 505000 COP | 3322.37 | P2P
```

- El precio es pesos ÷ USDT de esa línea, con 2 decimales. Canal: P2P, Convert u Otro.
- Montos sin separador de miles (505000, no 505.000). USDT con hasta 2 decimales.
- Fecha y hora de Colombia: la da el código de la sección 3 (`hora`); si aún no lo
  corriste, usa la fecha del sistema y omite la hora.

**La última línea dice dónde está el usuario:**

| Última operación | Tiene ahora | Revisa | Meta (debe superar) | Precio de equilibrio |
|---|---|---|---|---|
| COMPRA | los USDT de "recibiste" | vender USDT (lado `SELL`) | los COP de "entregaste" | meta ÷ USDT: te deben pagar **más** que esto por USDT |
| VENTA | los COP de "recibiste" | comprar USDT (lado `BUY`) | los USDT de "entregaste" | COP ÷ meta: debes pagar **menos** que esto por USDT |

## 2. ¿Qué pidió el usuario?

1. **Anotar un cambio** ("compré 152 USDT con 500 mil", "ya vendí, me llegaron 505000",
   "pasé los pesos a USDT y recibí 154.5"): ve a la sección 5. No revises Binance.
2. **"Modo usdt"** o "¿conviene cambiar?": si el archivo no existe o no tiene ninguna
   línea de cambio, pregunta en una frase cuántos pesos invirtió y cuántos USDT recibió
   (no revises Binance todavía). Si existe, sigue con la sección 3.

## 3. Revisar Binance

Usa una pestaña de tu grupo; abre o reutiliza una en el conversor del lado que toca:

- Vender USDT (`SELL`): `https://www.binance.com/es/convert/USDT/COP`
- Comprar USDT (`BUY`): `https://www.binance.com/es/convert/COP/USDT`

**P2P, con una sola llamada a `javascript_tool`** en esa pestaña (la página debe ser de
www.binance.com; no hace falta sesión). Cambia solo las tres constantes de arriba:
`LADO` (`'SELL'` o `'BUY'`), `MONTO` (SELL: los USDT que tiene; BUY: los pesos que
tiene) y `META` (SELL: pesos a superar; BUY: USDT a superar). Toma solo ofertas pagadas
por Nequi, Bancolombia, llaves Bre-B o Daviplata, que acepten ese monto completo y con
comprador o vendedor de buena reputación (90 % o más de órdenes completadas y al menos
20 órdenes en el mes).

```js
await (async () => {
  const LADO = 'SELL', MONTO = 152, META = 500000;
  const PAGOS = ['Nequi', 'BancolombiaSA', 'BreBKeys', 'Daviplata'];
  const j = (u, b) => fetch(u, b ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) } : undefined).then(r => r.json());
  const ref = (await j('/bapi/margin/v1/public/new-otc/pair-price-change?fromCoin=USDT&toCoin=COP')).data?.currentRate;
  const pesos = LADO === 'SELL' ? Math.round(MONTO * ref) : MONTO;
  const d = await j('/bapi/c2c/v2/friendly/c2c/adv/search', { fiat: 'COP', asset: 'USDT', tradeType: LADO, page: 1, rows: 20, payTypes: PAGOS, publisherType: null, transAmount: String(pesos), countries: [] });
  const ofertas = (d.data || []).map(x => {
    const a = x.adv, u = x.advertiser, p = +a.price;
    const cop = LADO === 'SELL' ? MONTO * p : MONTO;
    const usdt = LADO === 'SELL' ? MONTO : MONTO / p;
    return { precio: p, recibes: LADO === 'SELL' ? Math.round(cop) : Math.floor(usdt * 100) / 100, min: +a.minSingleTransAmount, max: +a.maxSingleTransAmount, disponible: +a.tradableQuantity, pagos: a.tradeMethods.map(m => m.tradeMethodName).join(', '), usuario: u.nickName, ordenesMes: u.monthOrderCount, completadas: Math.round(u.monthFinishRate * 100), cop, usdt };
  }).filter(o => o.cop >= o.min && o.cop <= o.max && o.usdt <= o.disponible && o.completadas >= 90 && o.ordenesMes >= 20)
    .sort((a, b) => LADO === 'SELL' ? b.precio - a.precio : a.precio - b.precio)
    .slice(0, 3).map(({ cop, usdt, ...o }) => o);
  const mejor = ofertas[0];
  return { hora: new Date().toLocaleString('es-CO', { timeZone: 'America/Bogota' }), lado: LADO, meta: META, equilibrio: LADO === 'SELL' ? +(META / MONTO).toFixed(2) : +(MONTO / META).toFixed(2), referenciaConvert: ref, ofertas, rentable: mejor ? mejor.recibes > META : null, diferencia: mejor ? +(mejor.recibes - META).toFixed(2) : null };
})()
```

`ofertas` trae las 3 mejores ya filtradas (en SELL `recibes` son pesos; en BUY, USDT).
Si sale vacío, ninguna oferta cumple: dilo. Si el código falla (Binance cambió algo),
como respaldo navega a `https://p2p.binance.com/es/trade/sell/USDT?fiat=COP` (SELL) o
`.../trade/buy/USDT?fiat=COP` (BUY), lee con `get_page_text` y aplica tú los mismos
filtros. `referenciaConvert` es una tasa de referencia sin el gap: **nunca la uses para
el veredicto**.

**Conversor (cotización real, necesita sesión).** Toma una captura de la pestaña. Si
"Saldo disponible" muestra un número, hay sesión: con `find` ubica el campo "De", haz
clic, escribe el monto (`MONTO`, sin separadores), espera 2 s y toma otra captura (todo
en un `browser_batch`). Lee lo que muestra el campo "A": eso es lo que recibiría. No
pulses ningún botón. Si dice "--", pide iniciar sesión o no muestra monto sin
previsualizar, sigue solo con P2P y dilo en una frase.

Ojo con el conversor: deja los pesos dentro de Binance (o los toma de ahí). Si el
usuario tiene la plata en el banco, pasarla tiene sus propios pasos y posibles costos
que no ves; menciónalo si el conversor es la mejor opción.

## 4. Veredicto

La mejor opción es la que da más (más pesos si vende, más USDT si compra) entre la mejor
oferta P2P y la cotización real del conversor.

- **SÍ ES RENTABLE** si la mejor opción supera la meta. Di cuánto gana (en pesos o USDT,
  y en %) y dónde: canal, precio, medio de pago, nombre del comprador o vendedor y su
  límite.
- **NO ES RENTABLE TODAVÍA** si ninguna la supera. Di cuánto le falta y el **precio de
  equilibrio**: al vender, "necesitas que te paguen más de X pesos por USDT, hoy la
  mejor oferta paga Y"; al comprar, "necesitas pagar menos de X pesos por USDT, hoy lo
  más barato es Y". ANZO no vigila el precio: el usuario vuelve a decir "modo usdt" más
  tarde.

Los precios P2P cambian en minutos: lo que dices vale para este momento.

Luego, con Write, sobrescribe `modo-usdt-revision.txt` en la carpeta ANZO archivos (un
intento): fecha y hora, qué tiene, la meta y el precio de equilibrio, las 3 ofertas P2P
(precio, recibes, medio de pago, usuario, límites, reputación), el conversor (o por qué
no se vio), la tasa de referencia marcada como referencia, el veredicto y la línea de
que es un cálculo con precios del momento y la decisión es del usuario. **No toques
`modo-usdt.txt` al revisar.**

## 5. Anotar un cambio

1. Necesitas **entregaste** y **recibiste** reales. Si falta uno (por ejemplo "ya
   vendí" sin decir cuántos pesos le llegaron), pregúntalo en una frase y no anotes
   nada todavía. "Recibí lo que me dijiste" no vale: pide el número que le llegó.
2. Si el archivo no existe, créalo con el encabezado de la sección 1. La primera COMPRA
   fija la "Inversion inicial" con los pesos que entregó.
3. Agrega la línea al final con Edit (o reescribe el archivo completo con Write sin
   perder ninguna línea anterior). Calcula el precio. Si el monto entregado no coincide
   con lo que tenía según la última línea, anótalo igual y avísale en una frase: desde
   ahora la meta sale de esta línea.
4. Confirma por voz lo anotado y la nueva meta: "Anotado: vendiste 152 USDT y
   recibiste 505000 pesos. Para que la recompra sea rentable necesitas recibir más de
   152 USDT, o sea pagar menos de 3322.4 pesos por USDT."

## 6. Cómo entregarlo (se lee en voz alta)

Frases cortas, sin markdown, sin listas y sin tablas. Pesos sin separador de miles
(493270 pesos), USDT con hasta 2 decimales y precios por USDT con 1 decimal como mucho.
Orden:

1. **El veredicto primero**: "Modo USDT: sí es rentable vender tus 152 USDT ahora." /
   "Modo USDT: todavía no es rentable vender, recibirías 493270 pesos y pagaste 500000."
2. **Dónde y por qué**, en dos o tres frases: la mejor oferta P2P (precio, medio de
   pago, reputación) y qué dio el conversor. Si es rentable, cuánto ganaría.
3. **El precio de equilibrio** si no es rentable.
4. Una frase: "Dejé el detalle en la carpeta ANZO archivos, en modo-usdt-revision.txt."
   Si haces el cambio, dime cuánto entregaste y cuánto recibiste para anotarlo.
5. **Cierre obligatorio:** es un cálculo con los precios de este momento, no una
   recomendación de inversión, y la decisión y la operación son del usuario. Nunca
   digas "vende ya" ni "compra ya": di "es rentable vender a este precio" y por qué.
