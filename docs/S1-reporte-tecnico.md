# S1 · Agente de compras corriendo end-to-end — Reporte técnico

## Qué hace

Agente de compras para restaurantes: predice qué insumos se agotan, lee cotizaciones
crudas de proveedores (WhatsApp, PDF, voz transcrita, catálogo web), juzga cada oferta y
propone la compra de menor costo. **El dueño aprueba antes de que se compre nada.**

> **Datos ficticios.** En esta entrega el restaurante, las ventas, las recetas, el
> inventario, los proveedores, su historial y las cotizaciones son inventados (`data/`).
> Lo que es real: las llamadas a Grok y las mediciones de tokens, tiempo y comportamiento
> del juez. Los montos en pesos y el "10 de 10 insumos" describen este escenario de
> prueba, no un negocio. Correr con datos de un restaurante real es la entrega S3.

## Idea central: cada tarea gasta solo los tokens que necesita

En vez de mandar todo a un modelo grande que "piensa", el agente separa el proceso y
le da a cada tarea el recurso justo:

| Tarea | Qué necesita | Recurso asignado | Tokens |
|---|---|---|---|
| Calcular demanda, costos, envíos | exactitud | código | **0** |
| Confiabilidad del proveedor | contar historial | código | **0** |
| Leer cotizaciones desordenadas | comprensión | Grok con razonamiento | los necesarios |
| Juzgar cada oferta (×24) | una decisión corta | Grok **sin** razonamiento, 3 letras, votación | **mínimos** |
| Redactar el reporte | redacción | Grok | 1 llamada |

El juez es donde más se nota, porque se repite por cada oferta. Medido sobre la misma oferta:

| Por oferta | Antes (`grok-4.6`, JSON) | Ahora | Cambio |
|---|---|---|---|
| Razonamiento + salida | ~1.422 tokens | 15 | **−99 %** |
| Entrada nueva (sin caché) | 1.140 | ~150 | **−87 %** |
| Entrada desde caché (más barata) | solo las instrucciones fijas* | ~1.600 | sube |
| Tiempo | ~27 s | ~0,8 s | **−97 %** |

\* En la prueba (la misma oferta 3 veces) el juez anterior sacó 512–1.024 de sus 1.140 tokens
de caché; con ofertas distintas, solo se reutilizarían las instrucciones fijas.

En las 24 ofertas de una corrida (estimado a partir de la medición anterior):
**~34.000 tokens de razonamiento y salida pasan a ~360**, y el juicio pasa de ~11 min a 19 s.
Además mejora el resultado: el plan cubre 10 de 10 insumos en vez de 2.

Lo que queda por optimizar con la misma idea es la extracción: hoy concentra ~8.200
tokens de razonamiento y ~40 s por cotización.

## Arquitectura

| Etapa | Archivo | Quién | Qué hace |
|---|---|---|---|
| 1. Demanda | `demanda.py` | código | ventas × recetas − inventario, pronóstico por día de la semana, stock de seguridad 15 % |
| 2. Extracción | `busqueda.py` | Grok (`grok-4.6`) | texto crudo → ofertas normalizadas (kg / L / unidad, COP) con salida estructurada |
| 3. Juicio | `juicio.py` | Grok sin razonamiento | por oferta: ¿mismo producto?, calidad A/B/C, ¿requiere revisión?, con confianza |
| 4. Optimización | `optimizador.py` | código | menor costo real (redondeo a unidad de venta), envío, pedido mínimo |
| 5. Reporte | `reporte.py` | Grok | mensaje corto para el dueño pidiendo aprobación |

Interfaz en vivo: `python ui.py` (servidor de la librería estándar + Server-Sent Events).
Muestra cada llamada a Grok, cada juicio con sus votos y los tokens gastados.

## Diseño del juez

Objetivo: respuestas tipadas, probabilidades útiles, rapidez y pocos tokens, usando solo Grok.

- **Salida mínima:** una línea de 3 letras (`S B N`) en vez de JSON.
- **Sin razonamiento:** `grok-4.20-0309-non-reasoning`.
- **Probabilidad por votación:** xAI no devuelve logprobs (probado con 3 modelos). Se piden
  5 respuestas en una sola llamada (`n=5`, temperatura 1) y la confianza es
  (votos del ganador + 0,5) / (respuestas válidas + 1).
- **Calibración:** los ✓/✗ marcados en la interfaz se guardan en `data/etiquetas.csv`;
  `python calibrar.py` ajusta una regresión de Platt por pregunta.
- **Lo calculable no se pregunta:** la confiabilidad del proveedor sale del historial, en código.

### Medición (misma oferta)

| | Juez anterior (`grok-4.6`, JSON) | Juez nuevo |
|---|---|---|
| Tiempo | ~27 s | ~0,8 s |
| Tokens de razonamiento | ~1.370 | 0 |
| Tokens de salida | 52 | 15 (5 respuestas) |
| Tokens de entrada | 1.140 | 1.750, de ellos 1.600 desde caché |

Prueba de "mismo producto" en 12 casos: 12/12. Dos de los casos aparecen como ejemplos en
el prompt, así que la prueba independiente es 10/10.

## Resultado de la corrida real (datos de ejemplo, 6-oct-2026)

- 10 insumos por comprar, 5 proveedores, 30 ofertas extraídas, 24 juzgadas.
- Juicio: 16 aptas, 6 a revisión, 2 descartadas, en 19 s.
- Plan: **10 de 10 insumos cubiertos, $1.949.600 COP**, 2 proveedores
  (Distribuidora El Campo $1.496.000; Plaza Central $453.600).
- A revisión: ofertas de proveedores con historial malo (Fruver Express, Carnes La Hacienda).
- Antes de este rediseño, la misma corrida compraba 2 de 10 insumos: el juez anterior
  mandaba casi todo a revisión.

## Costo por corrida

| | Llamadas | Tokens |
|---|---|---|
| Extracción (5 cotizaciones) | 5 | ~12.500 (incluye ~8.200 de razonamiento) |
| Juicio (24 ofertas) | 24 | ~59.000 (≈ 2.460 por oferta; 66 % de la entrada total en caché) |
| Reporte | 1 | ~3.000 |
| **Total** | **30** | **74.882** (10.710 de razonamiento) |

Tiempo total ≈ 4 min, de los cuales ~3,4 min son extracción.

## Problemas encontrados y corregidos

1. Crash en la consola de Windows (`UnicodeEncodeError` con emojis del reporte).
2. El juez anterior confundía calidad con identidad ("cargamanto rojo" ≠ "frijol cargamanto").
3. La duda sobre un proveedor nuevo bloqueaba comprar un producto correcto.
4. El extractor escribió "Plaza Central" y el historial dice "Plaza Central (puesto 14)":
   el proveedor parecía nuevo. Ahora se busca por nombre aproximado.
5. Proveedores con mal historial ganaban por precio; ahora van a revisión.

## Limitaciones conocidas

- Confianzas aún sin calibrar (0 etiquetas).
- Extracción lenta (~40 s por cotización) y secuencial.
- Perecederos se compran para 7 días; falta vida útil por insumo.
- El tiempo de entrega no se considera al elegir proveedor.
- Envío y pedido mínimo se aplican después de elegir, no durante.
- Datos de ejemplo (CSV), no de un restaurante real todavía.

## Cómo correrlo

```bash
pip install -r requirements.txt
cp .env.example .env      # poner XAI_API_KEY
python main.py --mock     # sin APIs
python main.py            # con Grok
python ui.py              # interfaz en vivo en http://localhost:8765
```
