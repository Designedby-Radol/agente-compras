"""Interfaz en vivo: ver a Grok extrayendo ofertas y al juez (Grok + votación) decidiendo.

  python ui.py               # abre http://localhost:8765
  python ui.py --puerto 9000

Solo librería estándar: un servidor HTTP que corre el pipeline en un hilo y
transmite cada evento al navegador por Server-Sent Events.
"""
from __future__ import annotations

import argparse
import json
import queue
import sys
import threading
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).parent / "src"))

from agente.calibracion import Calibrador, contar_etiquetas, guardar_etiqueta  # noqa: E402
from agente.config import DATA, Config  # noqa: E402
from agente.eventos import Eventos  # noqa: E402
from agente.pipeline import ejecutar  # noqa: E402

PAGINA = Path(__file__).parent / "ui" / "index.html"
TUTORIAL = Path(__file__).parent / "ui" / "tutorial.html"
_corriendo = threading.Lock()  # una corrida a la vez: todas escriben en salida/


class Manejador(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/":
            self._responder(200, "text/html; charset=utf-8", PAGINA.read_bytes())
        elif u.path == "/tutorial":
            self._responder(200, "text/html; charset=utf-8", TUTORIAL.read_bytes())
        elif u.path == "/estado":
            cfg = Config()
            self._json({"tiene_grok": bool(cfg.xai_api_key), "grok_model": cfg.grok_model,
                        "juez_model": cfg.juez_model, "muestras": cfg.juez_muestras,
                        "etiquetas": contar_etiquetas(DATA / "etiquetas.csv"),
                        "calibrado": Calibrador.cargar(DATA / "calibracion.json").activo,
                        "umbral": cfg.umbral_confianza, "calidad_minima": cfg.calidad_minima})
        elif u.path == "/correr":
            self._correr(q)
        else:
            self._responder(404, "text/plain", b"no existe")

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/etiquetar":
            return self._responder(404, "text/plain", b"no existe")
        fila = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        guardar_etiqueta(DATA / "etiquetas.csv", fila)
        self._json({"etiquetas": contar_etiquetas(DATA / "etiquetas.csv")})

    def _correr(self, q: dict) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        cola: queue.Queue = queue.Queue()
        if not _corriendo.acquire(blocking=False):
            cola.put({"tipo": "error", "mensaje": "Ya hay una corrida en curso."})
        else:
            mock = q.get("mock", "1") == "1"
            cfg = Config(mock=mock)
            hoy = date.fromisoformat(q["hoy"]) if q.get("hoy") else None
            pausa = float(q.get("pausa", "0.35")) if mock else 0.0

            def trabajo() -> None:
                try:
                    if not cfg.mock and not cfg.xai_api_key:
                        raise RuntimeError("Falta XAI_API_KEY en .env (o usa modo mock).")
                    ejecutar(cfg, hoy=hoy, verbose=False, eventos=Eventos(cola.put, pausa))
                    cola.put({"tipo": "fin"})
                except Exception as e:  # se muestra en la interfaz
                    cola.put({"tipo": "error", "mensaje": f"{type(e).__name__}: {e}"})
                finally:
                    _corriendo.release()

            threading.Thread(target=trabajo, daemon=True).start()

        while True:
            ev = cola.get()
            try:
                self.wfile.write(f"data: {json.dumps(ev, ensure_ascii=False, default=str)}\n\n".encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return  # el navegador cerró; el hilo termina solo
            if ev["tipo"] in ("fin", "error"):
                return

    def _json(self, datos: dict) -> None:
        self._responder(200, "application/json", json.dumps(datos).encode())

    def _responder(self, codigo: int, tipo: str, cuerpo: bytes) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, *args) -> None:
        pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--puerto", type=int, default=8765)
    ap.add_argument("--sin-navegador", action="store_true")
    args = ap.parse_args()
    url = f"http://localhost:{args.puerto}"
    servidor = ThreadingHTTPServer(("127.0.0.1", args.puerto), Manejador)
    print(f"Interfaz en {url}  (Ctrl+C para salir)")
    if not args.sin_navegador:
        webbrowser.open(url)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
