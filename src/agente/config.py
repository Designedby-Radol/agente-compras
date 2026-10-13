"""Configuración central. Todo se lee de variables de entorno (.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

RAIZ = Path(__file__).resolve().parents[2]
DATA = RAIZ / "data"


@dataclass
class Config:
    # --- Grok (xAI) ---------------------------------------------------------
    xai_api_key: str = field(default_factory=lambda: os.getenv("XAI_API_KEY", ""))
    xai_base_url: str = field(default_factory=lambda: os.getenv("XAI_BASE_URL", "https://api.x.ai/v1"))
    # Extracción y reporte: leen texto desordenado, aquí sí vale un modelo con razonamiento.
    grok_model: str = field(default_factory=lambda: os.getenv("GROK_MODEL", "grok-4.3"))

    # --- Juez (Grok sin razonamiento + votación) ----------------------------
    # Un modelo con razonamiento gasta ~400 tokens pensando para responder una letra.
    juez_model: str = field(default_factory=lambda: os.getenv("JUEZ_MODEL", "grok-4.20-0309-non-reasoning"))
    # Respuestas por pregunta; la confianza sale de cuántas coinciden.
    juez_muestras: int = field(default_factory=lambda: int(os.getenv("JUEZ_MUESTRAS", "5")))
    juez_temperatura: float = field(default_factory=lambda: float(os.getenv("JUEZ_TEMPERATURA", "1.0")))

    # --- Reglas del negocio -------------------------------------------------
    horizonte_dias: int = field(default_factory=lambda: int(os.getenv("HORIZONTE_DIAS", "7")))
    stock_seguridad: float = field(default_factory=lambda: float(os.getenv("STOCK_SEGURIDAD", "0.15")))
    # Umbral de confianza: por debajo de esto, la oferta se marca para revisión humana.
    umbral_confianza: float = field(default_factory=lambda: float(os.getenv("UMBRAL_CONFIANZA", "0.70")))
    calidad_minima: str = field(default_factory=lambda: os.getenv("CALIDAD_MINIMA", "B"))

    # --- Modo de ejecución --------------------------------------------------
    mock: bool = False  # sin llamadas a APIs; útil para probar el pipeline

    @property
    def tiene_grok(self) -> bool:
        return bool(self.xai_api_key) and not self.mock
