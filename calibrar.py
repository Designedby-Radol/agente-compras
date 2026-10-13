"""Calibra las confianzas del juez con las etiquetas que marcaste en la interfaz.

  python calibrar.py

Lee data/etiquetas.csv (una fila por cada ✓/✗), ajusta Platt por pregunta y
escribe data/calibracion.json. El juez lo carga solo en la siguiente corrida.
Muestra el error de calibración (ECE) antes y después: qué tan lejos está
"dije 0.8" de "acerté el 80%".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent / "src"))

from agente.calibracion import MIN_ETIQUETAS, PREGUNTAS, Calibrador, ajustar_platt, error_calibracion  # noqa: E402
from agente.config import DATA  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ruta = DATA / "etiquetas.csv"
    if not ruta.exists():
        sys.exit("No hay etiquetas todavía. Marca ✓/✗ en las tarjetas del juez (python ui.py, modo Real).")
    df = pd.read_csv(ruta)
    params: dict[str, dict] = {}
    print(f"{'pregunta':<18} {'n':>4} {'acierto':>8} {'ECE antes':>10} {'ECE después':>12}")
    for preg in PREGUNTAS:
        d = df[df["pregunta"] == preg]
        p, y = d["prob_cruda"].to_numpy(float), d["acierto"].to_numpy(float)
        if len(d) < MIN_ETIQUETAS or y.min() == y.max():
            print(f"{preg:<18} {len(d):>4}   faltan datos (mín. {MIN_ETIQUETAS}, con aciertos y fallos)")
            continue
        a, b = ajustar_platt(p, y)
        params[preg] = {"a": a, "b": b, "n": int(len(d))}
        calibradas = np.array([Calibrador(params).aplicar(preg, x) for x in p])
        print(f"{preg:<18} {len(d):>4} {y.mean():>8.0%} {error_calibracion(p, y):>10.3f} {error_calibracion(calibradas, y):>12.3f}")
    if not params:
        sys.exit("\nNada que calibrar aún. Sigue etiquetando.")
    (DATA / "calibracion.json").write_text(json.dumps(params, indent=2), encoding="utf-8")
    print("\nGuardado data/calibracion.json — el juez lo usa desde la próxima corrida.")


if __name__ == "__main__":
    main()
