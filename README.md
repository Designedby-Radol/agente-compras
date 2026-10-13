# Agente de compras para restaurantes

Predice qué insumos se agotan, lee cotizaciones de proveedores, juzga cada
oferta con Grok y propone la compra de menor costo.
El dueño aprueba antes de que se ejecute nada.

## Arquitectura

```
ventas.csv + recetas.csv + inventario.csv
            │
    1) demanda.py        código puro: qué comprar y cuánto (pronóstico por día de la semana)
            │
    2) busqueda.py       GROK: lee las cotizaciones crudas (WhatsApp, PDF, voz, catálogo)
            │            y las convierte en ofertas normalizadas (kg / L / unidad, COP)
            │
    3) juicio.py         GROK sin razonamiento, por votación. Por cada oferta, una línea
            │            de 3 letras tipadas ("S B N"), pedida n veces en UNA llamada:
            │              ¿es el mismo producto?  S/N
            │              ¿qué calidad?            A/B/C
            │              ¿requiere revisión?      S/N
            │            confianza = votos del ganador (+ calibración con tus etiquetas)
            │            ¿proveedor confiable? → código, desde el historial (sin tokens)
            │
    4) optimizador.py    código puro: menor costo real por insumo, agrupa por proveedor,
            │            aplica envío y pedido mínimo, reubica si no alcanza el mínimo
            │
    5) reporte.py        GROK: mensaje corto estilo WhatsApp pidiendo aprobación
            │
       salida/plan.json · evaluaciones.json · reporte.txt
```

Las decisiones con confianza por debajo de `UMBRAL_CONFIANZA` o marcadas
"requiere revisión" no entran al plan: van a una lista para que un humano las mire.

## Correr

```bash
pip install -r requirements.txt
python main.py --mock               # sin APIs: usa data/ofertas_mock.json y un juez heurístico
cp .env.example .env                # pon tu XAI_API_KEY
python main.py                      # modo real
python main.py --hoy 2026-10-06     # fija la fecha de pronóstico
```

### Interfaz en vivo

```bash
python ui.py                        # abre http://localhost:8765
```

Muestra en dos columnas a Grok leyendo cada cotización y al juez decidiendo cada
oferta (votos, confianza contra el umbral, tokens), y abajo la demanda,
el plan y el reporte. Elige *Mock* o *Real* en la barra superior. Sin dependencias
extra: servidor de la librería estándar + Server-Sent Events.

## Juez: probabilidades calibradas con Grok

Queríamos lo que da un modelo de decisión dedicado (respuestas tipadas, probabilidades
calibradas, rapidez y pocos tokens) usando solo Grok. Cómo:

- **Tipadas y mínimas**: la respuesta es una línea de 3 letras, no JSON. ~5 tokens de salida.
- **Sin razonamiento**: `JUEZ_MODEL` es un modelo *non-reasoning*. Medido: `grok-4.6`
  gastó 407 tokens de razonamiento y 8.5 s para responder una letra; el modelo sin
  razonamiento, 0 tokens y 0.9 s.
- **Probabilidad por votación**: xAI no expone logprobs (probado). Se piden
  `JUEZ_MUESTRAS` respuestas en una llamada (`n`) y la confianza es
  (votos del ganador + 0.5) / (muestras + 1).
- **Calibración**: en la interfaz (modo Real) marca ✓/✗ en cada respuesta del juez.
  Con 20+ etiquetas por pregunta, `python calibrar.py` ajusta Platt y escribe
  `data/calibracion.json`; desde ahí "0.80" significa acertar ~8 de cada 10.
- **Lo calculable no se pregunta**: la confiabilidad del proveedor sale del historial
  en código. Su confianza crece con el número de entregas registradas.

## Conectar un restaurante real

Reemplaza los archivos en `data/`:

| archivo | columnas | de dónde sale |
|---|---|---|
| `ventas.csv` | fecha, plato, cantidad | el POS (exportar ventas por producto) |
| `recetas.csv` | plato, insumo, cantidad_por_porcion, unidad (g, ml, unidad) | el chef, una vez |
| `inventario.csv` | insumo, cantidad, unidad (kg, L, unidad) | conteo semanal |
| `historial_proveedores.csv` | proveedor, entregas_totales, entregas_a_tiempo, calidad_promedio_1a5, reclamos | se va llenando con cada compra |
| `proveedores/*.txt` | texto crudo de cada cotización | WhatsApp, PDF, voz transcrita, web |

Los nombres de insumo deben coincidir entre recetas e inventario (son la llave).

## Costo por corrida (orientativo)

Con 5 proveedores y ~30 ofertas, el modo real hace ~5 llamadas de extracción,
~25 de juicio y 1 de reporte. La interfaz muestra los tokens reales de cada llamada
y el total de la corrida (chip *tokens* arriba).

## Qué falta para producción

- **Búsqueda web en vivo**: `busqueda.buscar_en_web` usa la herramienta `web_search`
  de xAI (Responses API). Está apagada; valida la forma de la llamada en docs.x.ai.
- **Entrada por WhatsApp**: hoy las cotizaciones se pegan en `.txt`. Conectar la
  API de WhatsApp Business para recibirlas y enviar el reporte.
- **Aprendizaje**: después de cada compra, registrar precio pagado, calidad recibida
  y puntualidad en `historial_proveedores.csv`. Eso es lo que hace al juez cada vez mejor.
- **Pronóstico**: `demanda.pronosticar_platos` es un promedio por día de la semana.
  Con 3+ meses de datos, cambiar por un modelo de series de tiempo.
- **Mermas**: la receta hoy es cantidad neta; agregar un factor de merma por insumo.
