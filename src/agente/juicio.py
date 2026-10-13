"""Capa 3 — Juicio. Preguntas tipadas sobre cada oferta, con confianza.

Dos implementaciones con la misma interfaz:
  - JuezGrok:       Grok sin razonamiento + votación (modo real).
  - JuezHeuristico: reglas simples para el modo mock / pruebas.

Cómo saca JuezGrok probabilidades sin logprobs (xAI no los expone):
  1. Respuesta tipada y mínima: una línea "S B N" (3 letras), no JSON.
  2. n respuestas en UNA llamada (parámetro n) a temperatura 1.
  3. Confianza = (votos del ganador + 0.5) / (respuestas válidas + 1).
  4. Si hay data/calibracion.json (ver calibrar.py), se calibra con Platt.

Lo que se puede calcular no se le pregunta al modelo: la confiabilidad del
proveedor sale del historial, en código. Eso ahorra tokens y es reproducible.
"""
from __future__ import annotations

import difflib
import re
from collections import Counter
from typing import Protocol

import pandas as pd

from .calibracion import Calibrador, confianza_votos
from .config import DATA, Config
from .modelos import Juicio, Necesidad, Oferta

ORDEN_PEOR_PRIMERO = "CBA"  # en empate de calidad, gana la peor (conservador)


class Juez(Protocol):
    def juzgar(self, oferta: Oferta, necesidad: Necesidad, historial: dict) -> Juicio: ...


def confiabilidad_proveedor(h) -> tuple[str, float]:
    """(nivel, confianza) desde el historial. La confianza crece con las entregas:
    5 entregas -> 0.50, 15 -> 0.75, 30 -> 0.86. Sin historial -> ('media', 0)."""
    if h is None or not h["entregas_totales"]:
        return "media", 0.0
    n = float(h["entregas_totales"])
    puntualidad = h["entregas_a_tiempo"] / n
    calidad = (h["calidad_promedio_1a5"] - 1) / 4
    sin_reclamos = 1 - min(1.0, 5 * h["reclamos"] / n)  # 1 reclamo cada 5 entregas ya es 0
    puntaje = 0.5 * puntualidad + 0.3 * calidad + 0.2 * sin_reclamos
    nivel = "alta" if puntaje >= 0.85 else "media" if puntaje >= 0.65 else "baja"
    return nivel, round(n / (n + 5), 2)


def _clave(nombre: str) -> str:
    sin_parentesis = re.sub(r"\(.*?\)", " ", nombre.lower())
    return " ".join(re.sub(r"[^a-z0-9áéíóúñ ]", " ", sin_parentesis).split())


def buscar_historial(historial: dict, proveedor: str):
    """El extractor no siempre copia el nombre exacto ("Plaza Central" vs
    "Plaza Central (puesto 14)"). Sin esto, un proveedor conocido parece nuevo."""
    if proveedor in historial:
        return historial[proveedor]
    claves = {_clave(k): k for k in historial}
    m = difflib.get_close_matches(_clave(proveedor), list(claves), n=1, cutoff=0.8)
    return historial[claves[m[0]]] if m else None


def _estado(oferta: Oferta, necesidad: Necesidad) -> str:
    """Lo que ve el modelo: solo el producto. El proveedor se evalúa en código."""
    return (
        f"Insumo de la receta: {necesidad.insumo}.\n"
        f"Oferta: {oferta.producto}. {oferta.cantidad_presentacion} {oferta.unidad} a "
        f"${oferta.precio_presentacion:,.0f} (${oferta.precio_unitario:,.0f}/{oferta.unidad}). "
        f"Notas: {oferta.notas_calidad or 'ninguna'}."
    )


# ----------------------------------------------------------------------------
# Grok sin razonamiento + votación
# ----------------------------------------------------------------------------
class JuezGrok:
    SISTEMA = """Eres comprador de un restaurante en Colombia. Responde SOLO una línea con 3 letras separadas por espacio:
1) ¿Es el MISMO producto que el insumo? S o N. Solo importa QUÉ producto es. Variedad, color, marca, grado (corriente/especial), madurez, segunda o presentación NO lo cambian: eso se juzga en calidad. N solo si es otro producto, o una forma que la receta no puede usar (con hueso cuando la receta usa pechuga limpia; con cáscara cuando usa desgranado).
2) Calidad: A = primera, marca reconocida o grado especial, fresco. B = estándar aceptable. C = segunda, defectos, sin marca o mucho procesamiento.
3) ¿Hay algo ambiguo o riesgoso que una persona deba revisar antes de comprar? S o N.
Ejemplos: "frijol cargamanto" vs "Frijol cargamanto rojo, bulto" -> S B N. "aguacate hass" vs "Aguacate hass segunda, algunos maduros" -> S C S. "pechuga de pollo" vs "Pechuga con hueso" -> N B S."""
    PATRON = re.compile(r"^\W*([SN])\W+([ABC])\W+([SN])\b", re.IGNORECASE)

    def __init__(self, cfg: Config):
        from .llm import Grok
        self.grok = Grok(cfg, model=cfg.juez_model)
        self.n = cfg.juez_muestras
        self.temperatura = cfg.juez_temperatura
        self.calibrador = Calibrador.cargar(DATA / "calibracion.json")

    def juzgar(self, oferta: Oferta, necesidad: Necesidad, historial: dict) -> Juicio:
        salidas = self.grok.votar(self.SISTEMA, _estado(oferta, necesidad), n=self.n, temperatura=self.temperatura)
        votos = [m.groups() for s in salidas if (m := self.PATRON.match(s.strip()))]
        nivel, conf_prov = confiabilidad_proveedor(buscar_historial(historial, oferta.proveedor))
        if not votos:  # el modelo no respetó el formato: que lo mire una persona
            return Juicio(mismo_producto=False, conf_mismo_producto=0, calidad="C", conf_calidad=0,
                          confiabilidad=nivel, conf_confiabilidad=conf_prov, requiere_revision=True,
                          fuente="grok-votos", votos=salidas)

        def ganador(i: int, empate_gana: str) -> tuple[str, float]:
            c = Counter(v[i].upper() for v in votos)
            mejor = max(c.values())
            empatados = [k for k, n in c.items() if n == mejor]
            k = empate_gana if empate_gana in empatados else sorted(empatados, key=ORDEN_PEOR_PRIMERO.find)[0]
            return k, confianza_votos(mejor, len(votos))

        mismo, p_mismo = ganador(0, "N")  # en empate, lo conservador
        calidad, p_cal = ganador(1, "")
        revision, p_rev = ganador(2, "S")
        crudas = {"mismo_producto": p_mismo, "calidad": p_cal, "requiere_revision": p_rev}
        cal = {k: self.calibrador.aplicar(k, p) for k, p in crudas.items()}
        return Juicio(
            mismo_producto=mismo == "S", conf_mismo_producto=round(cal["mismo_producto"], 3),
            calidad=calidad, conf_calidad=round(cal["calidad"], 3),
            confiabilidad=nivel, conf_confiabilidad=conf_prov,
            requiere_revision=revision == "S", fuente="grok-votos",
            crudas=crudas, votos=[" ".join(v).upper() for v in votos], calibrado=self.calibrador.activo,
        )


# ----------------------------------------------------------------------------
# Heurístico (mock)
# ----------------------------------------------------------------------------
class JuezHeuristico:
    def juzgar(self, oferta: Oferta, necesidad: Necesidad, historial: dict) -> Juicio:
        notas = oferta.notas_calidad.lower()
        mismo = oferta.insumo == necesidad.insumo and "con hueso" not in notas and "con cáscara" not in notas
        if any(k in notas for k in ("especial", "primera", "fresc", "colanta", "diana", "premier", "roa", "aa", "sin hueso", "desgranada")):
            calidad, conf_c = "A", 0.85
        elif any(k in notas for k in ("segunda", "corriente", "marca propia", "maduros")):
            calidad, conf_c = "C", 0.8
        else:
            calidad, conf_c = "B", 0.75
        nivel, conf_p = confiabilidad_proveedor(buscar_historial(historial, oferta.proveedor))
        revision = (not mismo and oferta.insumo == necesidad.insumo) or conf_c < 0.65
        return Juicio(
            mismo_producto=mismo, conf_mismo_producto=0.95 if mismo else 0.9,
            calidad=calidad, conf_calidad=conf_c,
            confiabilidad=nivel, conf_confiabilidad=conf_p,
            requiere_revision=revision, fuente="heuristica",
        )


def construir_juez(cfg: Config) -> Juez:
    if cfg.tiene_grok:
        return JuezGrok(cfg)
    return JuezHeuristico()


def cargar_historial(data_dir) -> dict:
    df = pd.read_csv(data_dir / "historial_proveedores.csv")
    return {r["proveedor"]: r for _, r in df.iterrows()}
