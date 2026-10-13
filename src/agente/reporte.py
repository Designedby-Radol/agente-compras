"""Capa 5 — Reporte para el dueño/chef. Con Grok redacta un mensaje corto estilo
WhatsApp; en mock usa una plantilla. En ambos casos el humano aprueba antes de
que se ejecute cualquier compra."""
from __future__ import annotations

from .config import Config
from .modelos import Necesidad, PlanCompra


def _cop(x: float) -> str:
    return f"${x:,.0f}".replace(",", ".")


def reporte_plantilla(plan: PlanCompra, necesidades: list[Necesidad]) -> str:
    out = ["*Propuesta de compra para la semana*", ""]
    urgentes = [n for n in necesidades if n.dias_cobertura_actual < 2]
    if urgentes:
        out.append("⚠️ Se agotan en menos de 2 días: " + ", ".join(f"{n.insumo} ({n.dias_cobertura_actual} d)" for n in urgentes))
        out.append("")
    for p in plan.pedidos:
        out.append(f"*{p.proveedor}* — total {_cop(p.total_cop)}" + ("" if p.cumple_minimo else " (no llega al pedido mínimo)"))
        for l in p.lineas:
            out.append(f"  • {l.unidades_a_pedir} × {l.producto} = {l.cantidad_total} {l.unidad} → {_cop(l.subtotal_cop)} [calidad {l.calidad}]")
        if p.envio_cop:
            out.append(f"  • envío {_cop(p.envio_cop)}")
        out.append("")
    out.append(f"*Total: {_cop(plan.total_cop)}*")
    if plan.sin_oferta:
        out.append("\nSin oferta válida (hay que cotizar): " + ", ".join(plan.sin_oferta))
    if plan.para_revision:
        out.append("\nPara que revises tú:")
        out += [f"  – {r}" for r in plan.para_revision]
    if plan.sobrantes:
        out.append("\nSobrantes en bodega (no comprar, revisar rotación): " +
                   ", ".join(f"{s.insumo} ({s.dias_cobertura_actual} días)" for s in plan.sobrantes))
    out.append("\n¿Apruebo el pedido? Responde *sí*, o dime qué cambiar.")
    return "\n".join(out)


SISTEMA = """Eres el asistente de compras de un restaurante en Colombia. Recibes un plan de compra ya
calculado y debes redactar un mensaje corto de WhatsApp para el dueño o chef.
Reglas: no cambies ningún número ni proveedor; sé concreto; empieza por lo urgente; usa pesos con
puntos de miles ($1.234.567); máximo 25 líneas; termina pidiendo aprobación. Sin saludos largos."""


def generar_reporte(cfg: Config, plan: PlanCompra, necesidades: list[Necesidad]) -> str:
    base = reporte_plantilla(plan, necesidades)
    if not cfg.tiene_grok:
        return base
    from .llm import Grok
    return Grok(cfg).texto(SISTEMA, f"PLAN CALCULADO:\n{base}\n\nDATOS:\n{plan.model_dump_json(indent=1)}")
