"""Bus de eventos del pipeline. La interfaz en vivo (ui.py) se suscribe;
la línea de comandos usa NULO y todo sigue igual."""
from __future__ import annotations

import time
from typing import Any, Callable


class Eventos:
    def __init__(self, oyente: Callable[[dict], None] | None = None, pausa: float = 0.0):
        self.oyente = oyente
        self.pausa = pausa  # segundos entre pasos; solo para que el modo mock se vea "en vivo"

    def emitir(self, tipo: str, **datos: Any) -> None:
        if self.oyente:
            self.oyente({"tipo": tipo, "t": time.time(), **datos})

    def paso(self) -> None:
        if self.pausa:
            time.sleep(self.pausa)


NULO = Eventos()
