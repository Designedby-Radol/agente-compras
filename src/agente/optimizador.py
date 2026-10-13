"""Capa 4 — Optimizador. Código determinista.

Con las ofertas ya juzgadas, arma el plan de compra de menor costo total:
  1. Filtra ofertas no válidas (no es el mismo producto, no disponible,
     calidad bajo el mínimo, confianza bajo el umbral -> va a revisión).
  2. Para cada insumo elige la oferta más barata por unidad base, contando
     el redondeo a unidades de venta (no puedes comprar medio bulto).
  3. Agrupa por proveedor, aplica envío y verifica pedido mínimo. Si un
     proveedor no alcanza el mínimo, mueve sus líneas a la siguiente mejor
     opción (una pasada; suficiente para un prototipo).
"""
from __future__ import annotations

import math
from collections import defaultdict

from .config import Config
from .modelos import LineaCompra, Necesidad, OfertaEvaluada, PedidoProveedor, PlanCompra, Sobrante

ORDEN_CALIDAD = {"A": 3, "B": 2, "C": 1}


def _linea(ev: OfertaEvaluada, nec: Necesidad) -> LineaCompra:
    o = ev.oferta
    unidades = max(1, math.ceil(nec.cantidad_a_comprar / o.cantidad_presentacion))
    return LineaCompra(
        insumo=nec.insumo, proveedor=o.proveedor, producto=o.producto,
        unidades_a_pedir=unidades, cantidad_total=round(unidades * o.cantidad_presentacion, 2),
        unidad=o.unidad, subtotal_cop=round(unidades * o.precio_presentacion),
        precio_unitario_cop=round(o.precio_unitario), calidad=ev.juicio.calidad,
        confianza=round(ev.juicio.confianza_minima, 2),
    )


def veredicto(cfg: Config, ev: OfertaEvaluada) -> tuple[str, str]:
    """('apta' | 'revision' | 'descartada', motivo). La regla que aplica _candidatas."""
    o, j = ev.oferta, ev.juicio
    if not o.disponible:
        return "descartada", "agotada"
    if not j.mismo_producto:
        return "descartada", "no es el mismo producto"
    if ORDEN_CALIDAD[j.calidad] < ORDEN_CALIDAD[cfg.calidad_minima]:
        return "descartada", f"calidad {j.calidad} bajo el mínimo {cfg.calidad_minima}"
    if j.requiere_revision:
        return "revision", "el juez pidió revisión humana"
    if j.confianza_minima < cfg.umbral_confianza:
        return "revision", f"confianza {j.confianza_minima:.2f} < umbral {cfg.umbral_confianza:.2f}"
    if j.confiabilidad == "baja" and j.conf_confiabilidad >= 0.5:  # malo y con historial que lo respalda
        return "revision", f"proveedor con historial malo ({j.conf_confiabilidad:.2f})"
    return "apta", ""


def _candidatas(cfg: Config, evaluadas: list[OfertaEvaluada], nec: Necesidad, revision: list[str]) -> list[OfertaEvaluada]:
    ok = []
    for ev in evaluadas:
        o, j = ev.oferta, ev.juicio
        if o.insumo != nec.insumo:
            continue
        estado, motivo = veredicto(cfg, ev)
        if estado == "descartada":
            continue
        if estado == "revision":
            revision.append(f"{nec.insumo} ← {o.proveedor}: {o.producto} — {motivo}")
            continue
        ok.append(ev)
    # Menor costo REAL de cubrir la necesidad (contando el redondeo a unidades de venta:
    # un bulto de 20 kg a $2.400/kg sale más caro que 6 kg a $2.800/kg si solo necesitas 5).
    # A igual costo, mejor calidad y proveedor más confiable.
    ok.sort(key=lambda ev: (_linea(ev, nec).subtotal_cop, -ORDEN_CALIDAD[ev.juicio.calidad], ev.juicio.confiabilidad != "alta"))
    return ok


def _armar_pedidos(lineas: list[LineaCompra], ofertas_por_prov: dict) -> list[PedidoProveedor]:
    por_prov: dict[str, list[LineaCompra]] = defaultdict(list)
    for l in lineas:
        por_prov[l.proveedor].append(l)
    pedidos = []
    for prov, ls in por_prov.items():
        ref = ofertas_por_prov[prov]
        subtotal = sum(l.subtotal_cop for l in ls)
        envio = ref.costo_envio_cop
        if ref.envio_gratis_desde_cop and subtotal >= ref.envio_gratis_desde_cop:
            envio = 0
        pedidos.append(PedidoProveedor(
            proveedor=prov, lineas=ls, subtotal_cop=subtotal, envio_cop=envio,
            total_cop=subtotal + envio, cumple_minimo=subtotal >= ref.pedido_minimo_cop,
        ))
    return pedidos


def optimizar(cfg: Config, necesidades: list[Necesidad], evaluadas: list[OfertaEvaluada],
              sobrantes: list[Sobrante]) -> PlanCompra:
    revision: list[str] = []
    sin_oferta: list[str] = []
    eleccion: dict[str, list[OfertaEvaluada]] = {}  # insumo -> candidatas ordenadas
    lineas: list[LineaCompra] = []

    for nec in necesidades:
        cands = _candidatas(cfg, evaluadas, nec, revision)
        if not cands:
            sin_oferta.append(nec.insumo)
            continue
        eleccion[nec.insumo] = cands
        lineas.append(_linea(cands[0], nec))

    ofertas_por_prov = {ev.oferta.proveedor: ev.oferta for ev in evaluadas}
    pedidos = _armar_pedidos(lineas, ofertas_por_prov)

    # Segunda pasada: proveedores que no llegan al mínimo -> reubicar sus líneas
    necesidad_por_insumo = {n.insumo: n for n in necesidades}
    for p in [p for p in pedidos if not p.cumple_minimo]:
        for l in p.lineas:
            alternativas = [ev for ev in eleccion[l.insumo] if ev.oferta.proveedor != p.proveedor]
            if alternativas:
                lineas = [x for x in lineas if not (x.insumo == l.insumo and x.proveedor == p.proveedor)]
                lineas.append(_linea(alternativas[0], necesidad_por_insumo[l.insumo]))
    pedidos = _armar_pedidos(lineas, ofertas_por_prov)

    return PlanCompra(
        pedidos=sorted(pedidos, key=lambda p: -p.total_cop),
        total_cop=sum(p.total_cop for p in pedidos),
        sin_oferta=sin_oferta, para_revision=revision, sobrantes=sobrantes,
    )
