"""Orquestación: demanda → búsqueda → juicio → optimizador → reporte."""
from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

from .busqueda import extraer_ofertas
from .config import DATA, Config
from .demanda import calcular_necesidades
from .calibracion import contar_etiquetas
from .eventos import NULO, Eventos
from .llm import USO, reiniciar_uso
from .juicio import cargar_historial, construir_juez
from .modelos import OfertaEvaluada, PlanCompra
from .optimizador import optimizar, veredicto
from .reporte import generar_reporte

_FUENTE_JUEZ = {"JuezGrok": "grok-votos", "JuezHeuristico": "heuristica"}


def _tokens(antes: dict) -> dict:
    return {k: USO[k] - antes[k] for k in USO}


def ejecutar(cfg: Config, data_dir: Path = DATA, hoy: date | None = None, verbose: bool = True,
             eventos: Eventos = NULO) -> tuple[PlanCompra, str]:
    log = print if verbose else (lambda *a, **k: None)
    reiniciar_uso()
    juez = construir_juez(cfg)
    eventos.emitir("agentes", mock=cfg.mock, grok=cfg.grok_model if cfg.tiene_grok else None,
                   juez=_FUENTE_JUEZ.get(type(juez).__name__, type(juez).__name__),
                   juez_model=cfg.juez_model, muestras=cfg.juez_muestras,
                   calibrado=bool(getattr(getattr(juez, "calibrador", None), "activo", False)),
                   etiquetas=contar_etiquetas(data_dir / "etiquetas.csv"),
                   umbral=cfg.umbral_confianza, calidad_minima=cfg.calidad_minima)

    log("1) Demanda…")
    eventos.emitir("etapa", n=1, estado="inicio")
    necesidades, sobrantes = calcular_necesidades(cfg, data_dir, hoy)
    for n in necesidades:
        log(f"   {n.insumo:<22} comprar {n.cantidad_a_comprar:>7} {n.unidad:<6} (cobertura {n.dias_cobertura_actual} d)")
    eventos.emitir("etapa", n=1, estado="fin", necesidades=[n.model_dump() for n in necesidades],
                   sobrantes=[s.model_dump() for s in sobrantes])

    log(f"2) Búsqueda/normalización ({'mock' if not cfg.tiene_grok else cfg.grok_model})…")
    eventos.emitir("etapa", n=2, estado="inicio")
    ofertas = extraer_ofertas(cfg, data_dir, necesidades, eventos)
    log(f"   {len(ofertas)} ofertas de {len({o.proveedor for o in ofertas})} proveedores")
    eventos.emitir("etapa", n=2, estado="fin", ofertas=len(ofertas), uso=dict(USO))

    log(f"3) Juicio ({type(juez).__name__})…")
    eventos.emitir("etapa", n=3, estado="inicio")
    historial = cargar_historial(data_dir)
    por_insumo = {n.insumo: n for n in necesidades}
    evaluadas: list[OfertaEvaluada] = []
    for o in ofertas:
        if o.insumo not in por_insumo:
            continue
        i = len(evaluadas)
        eventos.emitir("juicio_inicio", id=i, oferta={**o.model_dump(), "precio_unitario": o.precio_unitario})
        eventos.paso()
        t0, antes = time.perf_counter(), dict(USO)
        j = juez.juzgar(o, por_insumo[o.insumo], historial)
        ev = OfertaEvaluada(oferta=o, juicio=j)
        evaluadas.append(ev)
        estado, motivo = veredicto(cfg, ev)
        eventos.emitir("juicio_fin", id=i, ms=round((time.perf_counter() - t0) * 1000), tokens=_tokens(antes),
                       juicio={**j.model_dump(), "confianza_minima": j.confianza_minima},
                       veredicto=estado, motivo=motivo)
    log(f"   {len(evaluadas)} ofertas evaluadas")
    eventos.emitir("etapa", n=3, estado="fin", evaluadas=len(evaluadas), uso=dict(USO))

    log("4) Optimización…")
    eventos.emitir("etapa", n=4, estado="inicio")
    plan = optimizar(cfg, necesidades, evaluadas, sobrantes)
    elegidas = {(l.proveedor, l.producto) for p in plan.pedidos for l in p.lineas}
    eventos.emitir("etapa", n=4, estado="fin", plan=plan.model_dump(),
                   elegidas=[i for i, ev in enumerate(evaluadas)
                             if (ev.oferta.proveedor, ev.oferta.producto) in elegidas])

    log("5) Reporte…")
    eventos.emitir("etapa", n=5, estado="inicio", agente="grok" if cfg.tiene_grok else "plantilla")
    eventos.paso()
    t0 = time.perf_counter()
    texto = generar_reporte(cfg, plan, necesidades)
    eventos.emitir("etapa", n=5, estado="fin", texto=texto, ms=round((time.perf_counter() - t0) * 1000), uso=dict(USO))

    salida = data_dir.parent / "salida"
    salida.mkdir(exist_ok=True)
    (salida / "plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    (salida / "evaluaciones.json").write_text(
        json.dumps([e.model_dump() for e in evaluadas], ensure_ascii=False, indent=1), encoding="utf-8")
    (salida / "reporte.txt").write_text(texto, encoding="utf-8")
    return plan, texto
