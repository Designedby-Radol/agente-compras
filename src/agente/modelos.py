"""Modelos de datos del pipeline. Pydantic nos da validación y JSON Schema
para las salidas estructuradas de Grok."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

UnidadBase = Literal["kg", "L", "unidad"]
Calidad = Literal["A", "B", "C"]


class Necesidad(BaseModel):
    """Lo que hay que comprar de un insumo para cubrir el horizonte."""
    insumo: str
    unidad: UnidadBase
    demanda_estimada: float = Field(description="Consumo estimado en el horizonte")
    inventario_actual: float
    cantidad_a_comprar: float
    dias_cobertura_actual: float = Field(description="Días que dura el inventario actual")


class Sobrante(BaseModel):
    insumo: str
    unidad: UnidadBase
    inventario_actual: float
    demanda_estimada: float
    dias_cobertura_actual: float


class Oferta(BaseModel):
    """Una oferta de un proveedor, ya normalizada a unidades base."""
    proveedor: str
    producto: str = Field(description="Nombre tal como lo describe el proveedor")
    insumo: Optional[str] = Field(
        default=None,
        description="Insumo de la lista de necesidades al que corresponde, o null si no corresponde a ninguno",
    )
    cantidad_presentacion: float = Field(description="Cantidad por unidad de venta (p. ej. 25 para un bulto de 25 kg)")
    unidad: UnidadBase
    precio_presentacion: float = Field(description="Precio en COP de una unidad de venta")
    disponible: bool = True
    notas_calidad: str = Field(default="", description="Marca, grado, estado (primera/segunda), cualquier señal de calidad")
    pedido_minimo_cop: float = 0
    costo_envio_cop: float = 0
    envio_gratis_desde_cop: Optional[float] = None
    tiempo_entrega_horas: Optional[float] = None

    @property
    def precio_unitario(self) -> float:
        return self.precio_presentacion / self.cantidad_presentacion if self.cantidad_presentacion else float("inf")


class OfertasExtraidas(BaseModel):
    """Esquema de salida estructurada que le pedimos a Grok por cada proveedor."""
    ofertas: list[Oferta]


class Juicio(BaseModel):
    """Decisiones del juez sobre una oferta."""
    mismo_producto: bool
    conf_mismo_producto: float
    calidad: Calidad
    conf_calidad: float
    confiabilidad: Literal["baja", "media", "alta"]
    conf_confiabilidad: float = Field(description="Cuánto historial respalda el nivel (0 = proveedor nuevo)")
    requiere_revision: bool
    fuente: str = Field(description="grok-votos | heuristica")
    crudas: dict[str, float] = Field(default_factory=dict, description="Confianzas antes de calibrar")
    votos: list[str] = Field(default_factory=list, description="Respuestas de cada muestra, p. ej. 'S B N'")
    calibrado: bool = False

    @property
    def confianza_minima(self) -> float:
        # Solo las decisiones sobre el PRODUCTO. Que un proveedor sea nuevo no
        # significa que dudemos de qué está vendiendo; eso lo maneja veredicto().
        return min(self.conf_mismo_producto, self.conf_calidad)


class OfertaEvaluada(BaseModel):
    oferta: Oferta
    juicio: Juicio


class LineaCompra(BaseModel):
    insumo: str
    proveedor: str
    producto: str
    unidades_a_pedir: int
    cantidad_total: float
    unidad: UnidadBase
    subtotal_cop: float
    precio_unitario_cop: float
    calidad: Calidad
    confianza: float


class PedidoProveedor(BaseModel):
    proveedor: str
    lineas: list[LineaCompra]
    subtotal_cop: float
    envio_cop: float
    total_cop: float
    cumple_minimo: bool


class PlanCompra(BaseModel):
    pedidos: list[PedidoProveedor]
    total_cop: float
    sin_oferta: list[str] = Field(default_factory=list, description="Insumos que nadie ofrece")
    para_revision: list[str] = Field(default_factory=list, description="Ofertas con baja confianza que un humano debe mirar")
    sobrantes: list[Sobrante] = Field(default_factory=list)
