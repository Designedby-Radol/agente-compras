"""Capa 1 — Demanda. Código determinista, sin IA.

ventas (por plato) × recetas (insumo por porción) − inventario = qué comprar.

El pronóstico es un promedio por día de la semana sobre las últimas semanas,
que captura el patrón fin de semana vs. entre semana. Cuando tengas más datos
puedes reemplazar `pronosticar_platos` por un modelo de series de tiempo sin
tocar el resto del pipeline.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from .config import Config
from .modelos import Necesidad, Sobrante

# Conversión a unidades base: kg, L, unidad
A_BASE = {
    "g": ("kg", 0.001), "kg": ("kg", 1.0), "lb": ("kg", 0.5), "libra": ("kg", 0.5),
    "ml": ("L", 0.001), "l": ("L", 1.0), "L": ("L", 1.0),
    "unidad": ("unidad", 1.0), "und": ("unidad", 1.0), "u": ("unidad", 1.0),
}


def a_base(cantidad: float, unidad: str) -> tuple[float, str]:
    base, factor = A_BASE[unidad.strip()]
    return cantidad * factor, base


def pronosticar_platos(ventas: pd.DataFrame, desde: date, dias: int) -> dict[str, float]:
    """Porciones esperadas por plato en los próximos `dias`, por día de la semana."""
    v = ventas.copy()
    v["fecha"] = pd.to_datetime(v["fecha"])
    v["dow"] = v["fecha"].dt.dayofweek
    promedio = v.groupby(["plato", "dow"])["cantidad"].mean()
    global_ = v.groupby("plato")["cantidad"].mean()

    resultado: dict[str, float] = {}
    for plato in v["plato"].unique():
        total = 0.0
        for i in range(dias):
            d = desde + timedelta(days=i)
            total += float(promedio.get((plato, d.weekday()), global_[plato]))
        resultado[plato] = total
    return resultado


def calcular_necesidades(cfg: Config, data_dir: Path, hoy: date | None = None) -> tuple[list[Necesidad], list[Sobrante]]:
    hoy = hoy or date.today()
    ventas = pd.read_csv(data_dir / "ventas.csv")
    recetas = pd.read_csv(data_dir / "recetas.csv")
    inventario = pd.read_csv(data_dir / "inventario.csv")

    porciones = pronosticar_platos(ventas, hoy, cfg.horizonte_dias)

    # demanda por insumo en unidades base
    demanda: dict[str, tuple[float, str]] = {}
    for _, r in recetas.iterrows():
        cant, base = a_base(r["cantidad_por_porcion"], r["unidad"])
        total = cant * porciones.get(r["plato"], 0.0)
        prev = demanda.get(r["insumo"], (0.0, base))
        demanda[r["insumo"]] = (prev[0] + total, base)

    stock: dict[str, float] = {}
    for _, r in inventario.iterrows():
        cant, _ = a_base(r["cantidad"], r["unidad"])
        stock[r["insumo"]] = cant

    necesidades, sobrantes = [], []
    for insumo, (dem, base) in demanda.items():
        inv = stock.get(insumo, 0.0)
        diario = dem / cfg.horizonte_dias if cfg.horizonte_dias else 0
        cobertura = inv / diario if diario else float("inf")
        objetivo = dem * (1 + cfg.stock_seguridad)
        faltante = objetivo - inv
        if faltante > 0:
            necesidades.append(Necesidad(
                insumo=insumo, unidad=base, demanda_estimada=round(dem, 2),
                inventario_actual=round(inv, 2), cantidad_a_comprar=round(faltante, 2),
                dias_cobertura_actual=round(cobertura, 1),
            ))
        elif inv > dem * 2.5:  # más de 2.5 horizontes en bodega: señal de sobrante
            sobrantes.append(Sobrante(
                insumo=insumo, unidad=base, inventario_actual=round(inv, 2),
                demanda_estimada=round(dem, 2), dias_cobertura_actual=round(cobertura, 1),
            ))
    necesidades.sort(key=lambda n: n.dias_cobertura_actual)
    return necesidades, sobrantes
