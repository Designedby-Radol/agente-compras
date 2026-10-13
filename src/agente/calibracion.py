"""Calibración de las confianzas del juez.

La confianza cruda sale de la votación: (votos del ganador + 0.5) / (muestras + 1).
Es mejor que pedirle al modelo "dame un número", pero no está calibrada: un
0.80 crudo no garantiza acertar 8 de cada 10.

Cada vez que alguien marca en la interfaz si el juez acertó (✓/✗), se guarda
en data/etiquetas.csv. `python calibrar.py` ajusta una regresión de Platt por
pregunta, p' = sigmoide(a·logit(p) + b), y la guarda en data/calibracion.json.
Desde ahí el juez devuelve probabilidades calibradas.
"""
from __future__ import annotations

import csv
import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np

PREGUNTAS = ("mismo_producto", "calidad", "requiere_revision")
MIN_ETIQUETAS = 20  # por pregunta, y con aciertos y fallos


def confianza_votos(votos_ganador: int, validas: int) -> float:
    return (votos_ganador + 0.5) / (validas + 1) if validas else 0.0


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


class Calibrador:
    def __init__(self, params: dict | None = None):
        self.params: dict[str, dict] = params or {}

    @classmethod
    def cargar(cls, ruta: Path) -> "Calibrador":
        if not ruta.exists():
            return cls()
        return cls(json.loads(ruta.read_text(encoding="utf-8")))

    def aplicar(self, pregunta: str, p: float) -> float:
        prm = self.params.get(pregunta)
        if not prm or p <= 0:
            return p
        z = prm["a"] * float(_logit(np.array([p]))[0]) + prm["b"]
        return 1 / (1 + math.exp(-z))

    @property
    def activo(self) -> bool:
        return bool(self.params)


def ajustar_platt(p: np.ndarray, y: np.ndarray, iteraciones: int = 50) -> tuple[float, float]:
    """Regresión logística de 1 variable (logit de p) por Newton-Raphson."""
    x = _logit(p)
    a, b = 1.0, 0.0
    for _ in range(iteraciones):
        q = 1 / (1 + np.exp(-(a * x + b)))
        g = np.array([np.sum((q - y) * x), np.sum(q - y)])
        w = q * (1 - q) + 1e-9
        h = np.array([[np.sum(w * x * x), np.sum(w * x)], [np.sum(w * x), np.sum(w)]]) + 1e-6 * np.eye(2)
        paso = np.linalg.solve(h, g)
        a, b = a - paso[0], b - paso[1]
        if np.abs(paso).max() < 1e-6:
            break
    return float(a), float(b)


def error_calibracion(p: np.ndarray, y: np.ndarray, cubetas: int = 5) -> float:
    """ECE: diferencia promedio entre confianza y tasa de acierto real."""
    bordes = np.linspace(0, 1, cubetas + 1)
    total = 0.0
    for lo, hi in zip(bordes[:-1], bordes[1:]):
        m = (p >= lo) & (p < hi if hi < 1 else p <= hi)
        if m.any():
            total += m.sum() * abs(p[m].mean() - y[m].mean())
    return total / len(p)


# --- etiquetas ----------------------------------------------------------------
COLUMNAS = ["fecha", "proveedor", "producto", "insumo", "pregunta", "respuesta", "prob_cruda", "acierto"]


def guardar_etiqueta(ruta: Path, fila: dict) -> None:
    nueva = not ruta.exists()
    with ruta.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS)
        if nueva:
            w.writeheader()
        w.writerow({"fecha": datetime.now().isoformat(timespec="seconds"), **{k: fila.get(k, "") for k in COLUMNAS[1:]}})


def contar_etiquetas(ruta: Path) -> int:
    if not ruta.exists():
        return 0
    with ruta.open(encoding="utf-8") as f:
        return max(0, sum(1 for _ in f) - 1)
