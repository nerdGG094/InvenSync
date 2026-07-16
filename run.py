import os

from inventory import create_app

app = create_app()

if __name__ == "__main__":
    # Servidor de DESENVOLVIMENTO. O debugger interativo do Werkzeug = execução
    # remota de código, então fica DESLIGADO por padrão e só liga com
    # FLASK_DEBUG=1. Bind em 127.0.0.1 por padrão (não exponha o dev server na
    # rede); para acessar de outra máquina no dev, defina RUN_HOST. Produção usa
    # serve.py (waitress), nunca este arquivo.
    host = os.environ.get("RUN_HOST", "127.0.0.1")
    port = int(os.environ.get("RUN_PORT", "5090"))
    debug = os.environ.get("FLASK_DEBUG", "0") in ("1", "true", "True")
    app.run(host=host, port=port, debug=debug)
