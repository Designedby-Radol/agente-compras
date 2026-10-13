"""Cliente de Grok (xAI). La API es compatible con OpenAI, así que usamos el
SDK de OpenAI apuntando a https://api.x.ai/v1.

Tres usos:
  - estructurado(): devuelve un objeto Pydantic validado (salida estructurada
    con JSON Schema). Es lo que usa la capa de búsqueda.
  - votar(): n respuestas cortas de la misma pregunta en UNA llamada. xAI no
    expone logprobs, así que el juez saca la probabilidad de estos votos.
  - texto(): texto libre, para el reporte final.

USO acumula los tokens de la corrida, para ver cuánto cuesta cada etapa.
"""
from __future__ import annotations

import json
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel

from .config import Config

T = TypeVar("T", bound=BaseModel)

USO = {"llamadas": 0, "entrada": 0, "cache": 0, "salida": 0, "razonamiento": 0}


def reiniciar_uso() -> None:
    for k in USO:
        USO[k] = 0


def _contar(resp) -> None:
    u = resp.usage
    USO["llamadas"] += 1
    if u is None:
        return
    USO["entrada"] += u.prompt_tokens or 0
    USO["salida"] += u.completion_tokens or 0
    det = getattr(u, "completion_tokens_details", None)
    USO["razonamiento"] += (getattr(det, "reasoning_tokens", 0) or 0) if det else 0
    pdet = getattr(u, "prompt_tokens_details", None)  # entrada repetida: xAI la cobra más barata
    USO["cache"] += (getattr(pdet, "cached_tokens", 0) or 0) if pdet else 0


class Grok:
    def __init__(self, cfg: Config, model: str | None = None):
        if not cfg.xai_api_key:
            raise RuntimeError("Falta XAI_API_KEY en el entorno (.env)")
        self.cliente = OpenAI(api_key=cfg.xai_api_key, base_url=cfg.xai_base_url)
        self.model = model or cfg.grok_model

    def estructurado(self, sistema: str, usuario: str, esquema: type[T], temperatura: float = 0) -> T:
        schema = esquema.model_json_schema()
        mensajes = [
            {"role": "system", "content": sistema},
            {"role": "user", "content": usuario},
        ]
        try:
            resp = self.cliente.chat.completions.create(
                model=self.model, temperature=temperatura, messages=mensajes,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": esquema.__name__, "schema": schema, "strict": False},
                },
            )
        except Exception as e:  # algunos proxies solo aceptan json_object
            if "response_format" not in str(e) and "json_schema" not in str(e):
                raise
            mensajes[0]["content"] += (
                "\n\nResponde ÚNICAMENTE con un JSON válido que cumpla este esquema:\n"
                + json.dumps(schema, ensure_ascii=False)
            )
            resp = self.cliente.chat.completions.create(
                model=self.model, temperature=temperatura, messages=mensajes,
                response_format={"type": "json_object"},
            )
        _contar(resp)
        contenido = (resp.choices[0].message.content or "{}").strip()
        if contenido.startswith("```"):  # por si el modelo envuelve en bloque de código
            contenido = contenido.strip("`").removeprefix("json").strip()
        return esquema.model_validate(json.loads(contenido))

    def votar(self, sistema: str, usuario: str, n: int, temperatura: float = 1.0, max_tokens: int = 8) -> list[str]:
        resp = self.cliente.chat.completions.create(
            model=self.model, n=n, temperature=temperatura, max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": sistema},
                {"role": "user", "content": usuario},
            ],
        )
        _contar(resp)
        return [c.message.content or "" for c in resp.choices]

    def texto(self, sistema: str, usuario: str, temperatura: float = 0.4) -> str:
        resp = self.cliente.chat.completions.create(
            model=self.model,
            temperature=temperatura,
            messages=[
                {"role": "system", "content": sistema},
                {"role": "user", "content": usuario},
            ],
        )
        _contar(resp)
        return resp.choices[0].message.content or ""
