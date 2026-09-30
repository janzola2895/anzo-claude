# ANZO + Claude — Índice

Vault de notas de ANZO + Claude: asistente de voz que orquesta a Claude para desarrollar y diagnosticar Power Platform (Canvas Apps + Power Automate) y analizar gráficos de trading, usando solo tu cuenta de Claude y la extensión Claude in Chrome.

Esta bóveda nació el 2026-09-29 como copia de la de la ANZO original (`C:\dev\anzo`). Las notas de la original se conservan completas como historia: muchas siguen aplicando (voz, eco, interrupción, bitácora).

## ANZO + Claude (esta versión)
- [[Guía de uso ANZO + Claude]] — cómo abrirla, comandos de voz, qué hace y qué no, qué hacer si algo falla
- [[Arquitectura ANZO + Claude]] — cómo está armada, qué cambió respecto a la original, pendientes
- [[Decisiones]] — secciones "Nace ANZO + Claude" e "Investigación: Claude in Chrome (la extensión) como navegador de ANZO"

## ANZO original (histórico)
- [[Decisiones]] — todo lo decidido antes de la separación, en orden cronológico
- [[Arquitectura]] — arquitectura de la ANZO original (Chrome aparte + Playwright MCP + router)
- [[Problemas resueltos]] — cada bug encontrado y su causa real (léela antes de tocar el código de nuevo)
- `Bitacora/` — resúmenes de las conversaciones

## Contexto de origen

Nace después de que IT de Indra denegó el registro de una app Entra (MCP con permisos de API a Power Platform) y recomendó en su lugar un enfoque de control de pantalla sobre la sesión ya autenticada del usuario — sin permisos nuevos que aprobar.
