# Entregas

Cada entrega pide lo mismo: **URL del repositorio** (obligatoria), **URL del video**,
**URL del reporte técnico** y **notas** (qué se logró, qué falló, costo por tarea).

Convención: el repositorio es uno solo; cada entrega es un tag (`s1`, `s2`…) y su
reporte vive en `docs/`. Así el link del reporte apunta a la versión exacta entregada.

| Hito | Estado | Repo (tag) | Video | Reporte técnico |
|---|---|---|---|---|
| Formulario de validación | ✅ Aprobada | — | — | — |
| S1 · Agente corriendo end-to-end | 🟡 Lista para entregar | `s1` | pendiente de grabar | [docs/S1-reporte-tecnico.md](S1-reporte-tecnico.md) |
| S2 · 3 herramientas y video de 2 min | ⬜ | `s2` | obligatorio (2 min) | `docs/S2-reporte-tecnico.md` |
| S3 · Datos reales, evaluación propia y costo por tarea | ⬜ | `s3` | — | `docs/S3-reporte-tecnico.md` |
| S4 · Semana de carga (1.000 unidades, 12 h) | ⬜ | `s4` | — | `docs/S4-reporte-tecnico.md` |
| Entrega final | ⬜ | `final` | — | `docs/REPORTE-FINAL.md` |

---

## S1 · Agente corriendo end-to-end

- **URL del repositorio:** `https://github.com/Designedby-Radol/agente-compras/tree/s1`
- **URL del video:** _(grabar con el guion de abajo y subir como "no listado")_
- **URL del reporte técnico:** `https://github.com/Designedby-Radol/agente-compras/blob/s1/docs/S1-reporte-tecnico.md`
- **Notas de la entrega** (para pegar):

> Logrado: agente corriendo end-to-end con Grok real (demanda → extracción de 5 cotizaciones
> → juicio de 24 ofertas → plan → reporte para aprobación), con interfaz en vivo que muestra
> cada llamada y sus tokens.
> Idea clave: adaptamos el proceso para que cada tarea gaste solo los tokens que necesita.
> Las cuentas y la confiabilidad del proveedor se hacen en código (0 tokens); Grok con
> razonamiento solo lee cotizaciones; y el juez, que se repite por cada oferta, se rediseñó:
> modelo sin razonamiento, respuesta tipada de 3 letras y confianza por votación (5 muestras
> en una llamada, con el prompt reutilizado desde caché). Por oferta: razonamiento + salida
> de ~1.422 a 15 tokens (−99 %), entrada sin caché de 1.140 a ~150 (−87 %), y de ~27 s a
> ~0,8 s. En una corrida, el juicio pasa de ~11 min a 19 s, y el plan cubre 10 de 10 insumos
> (antes 2 de 10): $1.949.600 COP.
> Falló / pendiente: xAI no expone logprobs, así que la confianza sale de votos y aún no
> está calibrada. La extracción es el siguiente punto a optimizar (~8.200 tokens de
> razonamiento, ~40 s por cotización).
> Costo por corrida: 30 llamadas; 74.882 tokens, de los cuales 66 % de la entrada viene
> de caché y 10.710 son de razonamiento (casi todos en la extracción).

**Guion del video (~2 min):**
1. (15 s) Qué es: agente de compras para restaurantes; el dueño aprueba antes de comprar.
2. (20 s) `python ui.py` → modo Real → Correr. Mostrar la tabla de demanda.
3. (30 s) Columna Grok: una cotización cruda de WhatsApp convertida en ofertas normalizadas.
4. (30 s) Columna Juez: votos `S A N`, barras de confianza contra el umbral, motivos de revisión.
5. (20 s) Plan por proveedor y reporte estilo WhatsApp.
6. (5 s) Chip de tokens: costo de la corrida.

Tip: la extracción real tarda ~3 min; graba la corrida completa y corta, o graba en modo Mock
y muestra una corrida real ya terminada.

---

## S2 · 3 herramientas y video de 2 min
_Por definir con la rúbrica._ Candidatas en el código actual: lectura de cotizaciones
(extracción), juez de ofertas, optimizador de compra; o tools nuevas para el LLM
(búsqueda web de precios, consulta de inventario del POS, creación de orden de compra).

## S3 · Datos reales, evaluación propia y costo por tarea
- Datos reales: conector al POS / exportes del restaurante (ver arquitectura de conectores).
- Evaluación propia: set etiquetado (✓/✗ en la interfaz → `data/etiquetas.csv`) + `calibrar.py`.
- Costo por tarea: registrar `cost_in_usd_ticks` que devuelve xAI por llamada.

## S4 · Semana de carga (1.000 unidades, 12 h)
- 1.000 unidades en 12 h ≈ 1 cada 43 s. Hoy la extracción secuencial tarda ~40 s por
  cotización: hay que paralelizar, reintentar y medir errores.
