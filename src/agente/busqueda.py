"""Capa 2 — Búsqueda y normalización (Grok).

Entrada: texto crudo de cada proveedor (WhatsApp, PDF, catálogo, voz transcrita)
en data/proveedores/*.txt, y la lista de insumos que necesitamos.
Salida: lista de Oferta normalizadas (cantidad + unidad base + precio).

Grok hace lo que un LLM hace bien: leer texto desordenado y sacar datos.
Las conversiones de unidades las re-verificamos en código (normalizar_oferta)
porque ahí el LLM se equivoca más de lo que parece.

Para búsqueda web en vivo, ver `buscar_en_web` al final (opcional).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .config import Config
from .eventos import NULO, Eventos
from .llm import USO, Grok
from .modelos import Necesidad, Oferta, OfertasExtraidas

SISTEMA = """Eres un asistente de compras para restaurantes en Colombia.
Recibes el texto crudo de una cotización de un proveedor y una lista de insumos
que el restaurante necesita. Extrae CADA producto cotizado como una oferta.

Reglas:
- cantidad_presentacion y unidad describen UNA unidad de venta, en unidad base:
  kg para peso, L para volumen, unidad para piezas. Convierte: 1 libra = 0.5 kg,
  500 g = 0.5 kg, 1 cubeta de 30 huevos = 30 unidad, una "mano" de plátano usa el peso si lo dan.
- Si el precio es por kg o por libra, la presentación es 1 kg (ajusta el precio si era por libra: precio × 2).
- precio_presentacion es el precio en COP de esa unidad de venta, sin puntos de miles.
- insumo: el nombre EXACTO de la lista de insumos necesitados al que corresponde el producto,
  o null si no corresponde a ninguno. "Carne molida corriente" y "especial" ambas corresponden a
  "carne molida de res"; "pechuga con hueso" NO es "pechuga de pollo" sin hueso si la receta usa
  pechuga limpia: márcala igual como "pechuga de pollo" pero deja la diferencia en notas_calidad.
- notas_calidad: marca, grado ("especial", "de primera", "segunda"), estado (maduros, agotado), con hueso/sin hueso.
- disponible: false si dice agotado o sin existencias.
- pedido_minimo_cop, costo_envio_cop, envio_gratis_desde_cop, tiempo_entrega_horas: del texto, 0 o null si no aplica.
No inventes productos ni precios. Si un dato no está, usa null o 0."""


def cargar_textos_proveedores(data_dir: Path) -> dict[str, str]:
    return {p.stem: p.read_text(encoding="utf-8") for p in sorted((data_dir / "proveedores").glob("*.txt"))}


def normalizar_oferta(o: Oferta) -> Oferta:
    """Red de seguridad sobre lo que devuelve el LLM."""
    if o.cantidad_presentacion <= 0:
        o.cantidad_presentacion = 1.0
    if o.envio_gratis_desde_cop is not None and o.envio_gratis_desde_cop <= 0:
        o.envio_gratis_desde_cop = None
    return o


def _vista(o: Oferta) -> dict:
    return {**o.model_dump(), "precio_unitario": o.precio_unitario}


def extraer_ofertas(cfg: Config, data_dir: Path, necesidades: list[Necesidad],
                    eventos: Eventos = NULO) -> list[Oferta]:
    textos = cargar_textos_proveedores(data_dir)
    lista_insumos = "\n".join(f"- {n.insumo} ({n.unidad})" for n in necesidades)

    if not cfg.tiene_grok:
        return _ofertas_mock(data_dir, textos, eventos)

    grok = Grok(cfg)
    ofertas: list[Oferta] = []
    for nombre, texto in textos.items():
        eventos.emitir("extraccion_inicio", agente="grok", archivo=nombre, texto=texto)
        t0, antes = time.perf_counter(), dict(USO)
        usuario = f"INSUMOS NECESITADOS:\n{lista_insumos}\n\nCOTIZACIÓN ({nombre}):\n{texto}"
        salida = grok.estructurado(SISTEMA, usuario, OfertasExtraidas)
        nuevas = [normalizar_oferta(o) for o in salida.ofertas]
        ofertas.extend(nuevas)
        eventos.emitir("extraccion_fin", agente="grok", archivo=nombre,
                       ms=round((time.perf_counter() - t0) * 1000), ofertas=[_vista(o) for o in nuevas],
                       tokens={k: USO[k] - antes[k] for k in USO})
    return ofertas


def _ofertas_mock(data_dir: Path, textos: dict[str, str], eventos: Eventos = NULO) -> list[Oferta]:
    """Ofertas ya normalizadas, para correr el pipeline sin gastar tokens."""
    ruta = data_dir / "ofertas_mock.json"
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    ofertas = [normalizar_oferta(Oferta.model_validate(d)) for d in datos]
    # Para la interfaz: emitir por proveedor, como si se leyera cada cotización.
    por_proveedor = {_proveedor_declarado(t): (n, t) for n, t in textos.items()}
    for prov in dict.fromkeys(o.proveedor for o in ofertas):
        archivo, texto = por_proveedor.get(prov, (prov, ""))
        eventos.emitir("extraccion_inicio", agente="mock", archivo=archivo, texto=texto)
        eventos.paso()
        eventos.emitir("extraccion_fin", agente="mock", archivo=archivo, ms=0,
                       ofertas=[_vista(o) for o in ofertas if o.proveedor == prov])
    return ofertas


def _proveedor_declarado(texto: str) -> str:
    primera = texto.splitlines()[0] if texto else ""
    return primera.removeprefix("Proveedor:").strip()


# ----------------------------------------------------------------------------
# Opcional: búsqueda web en vivo con Grok.
#
# xAI expone herramientas de servidor (web_search, x_search) a través de su
# Responses API. La forma exacta de la llamada puede cambiar; verifica en
# https://docs.x.ai antes de activarla. La idea: pedirle a Grok que busque
# "precio {insumo} mayorista Bucaramanga" y devuelva el texto crudo, que luego
# pasa por el mismo extraer_ofertas. Déjalo apagado hasta validarlo.
# ----------------------------------------------------------------------------
def buscar_en_web(cfg: Config, insumo: str, ciudad: str = "Bucaramanga") -> str:
    grok = Grok(cfg)
    resp = grok.cliente.responses.create(
        model=cfg.grok_model,
        tools=[{"type": "web_search"}],
        input=(
            f"Busca proveedores mayoristas de '{insumo}' en {ciudad}, Colombia. "
            "Devuelve nombre del proveedor, producto, presentación, precio en COP y URL. "
            "Solo datos que aparezcan literalmente en las páginas."
        ),
    )
    return getattr(resp, "output_text", str(resp))
