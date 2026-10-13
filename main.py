"""Punto de entrada.

  python main.py --mock            # sin APIs, para ver el pipeline completo
  python main.py                   # usa Grok (XAI_API_KEY): extracción, juez por votación y reporte
  python main.py --hoy 2026-10-06  # fija la fecha de pronóstico
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from agente.config import Config  # noqa: E402
from agente.pipeline import ejecutar  # noqa: E402


def main() -> None:
    # La consola de Windows (cp1252) revienta con los emojis del reporte.
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="No llama a ninguna API")
    ap.add_argument("--hoy", type=date.fromisoformat, default=None)
    args = ap.parse_args()

    cfg = Config(mock=args.mock)
    if not cfg.mock and not cfg.xai_api_key:
        sys.exit("Falta XAI_API_KEY. Copia .env.example a .env y pon tu llave, o corre con --mock.")

    plan, texto = ejecutar(cfg, hoy=args.hoy)
    print("\n" + "=" * 60)
    print(texto)
    print("=" * 60)
    print("Archivos: salida/plan.json, salida/evaluaciones.json, salida/reporte.txt")


if __name__ == "__main__":
    main()
