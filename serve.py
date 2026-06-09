"""
Servidor de produção do InvenSync via waitress.

Executado pelo launcher.py (ou diretamente: `python serve.py`).
Para desenvolvimento com debug/reload, continue usando run.py.

Variáveis aceitas (além das já usadas pelo Config/.env):
    SERVE_HOST  default 0.0.0.0
    SERVE_PORT  default 5090
"""
import logging
import os
import sys
import traceback
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv

load_dotenv()

from waitress import serve

from inventory import create_app


def main():
    host = os.environ.get("SERVE_HOST", "0.0.0.0")
    port = int(os.environ.get("SERVE_PORT", "5090"))

    # Log no stdout (aparece no painel do launcher)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )

    # Log adicional em arquivo rotativo (serve.log na raiz do projeto)
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "serve.log")
    fh = RotatingFileHandler(
        log_path, mode="a", encoding="utf-8",
        maxBytes=5 * 1024 * 1024, backupCount=5,
    )
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S"))
    logging.getLogger().addHandler(fh)

    flask_app = create_app()

    # Garante que tracebacks de 500 sempre apareçam nos logs.
    flask_app.logger.setLevel(logging.INFO)
    if not any(isinstance(h, logging.StreamHandler) for h in flask_app.logger.handlers):
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] flask: %(message)s", datefmt="%H:%M:%S"))
        flask_app.logger.addHandler(h)

    @flask_app.errorhandler(Exception)
    def _log_unhandled(e):
        from flask import request
        flask_app.logger.error(
            "500 em %s %s\n%s",
            getattr(request, "method", "?"),
            getattr(request, "path", "?"),
            traceback.format_exc(),
        )
        raise e

    print(f"[invensync] servindo em http://{host}:{port} (waitress)", flush=True)

    serve(flask_app, host=host, port=port, threads=8, ident="invensync")


if __name__ == "__main__":
    main()
