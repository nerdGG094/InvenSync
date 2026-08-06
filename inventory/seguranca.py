# inventory/seguranca.py
"""Utilidades pequenas de segurança usadas em vários módulos."""
from urllib.parse import urlparse

from flask import redirect, request


def destino_seguro(candidato: str | None) -> str | None:
    """Devolve `candidato` se ele apontar para ESTE site; senão, None.

    `request.referrer` (e qualquer `?next=`) é dado do cliente: uma página
    externa consegue fazer o app devolver o usuário para o endereço que ela
    escolher, o que dá ao golpe a credibilidade de ter partido do sistema.

    Recusa, portanto:
      * outro host  — `https://falso.example/login`
      * relativo a protocolo — `//falso.example` (o urlparse já lê como host)
      * esquemas executáveis — `javascript:`, `data:`
      * `/\falso.example` — o urlparse lê como caminho, mas o navegador
        normaliza a barra invertida para barra comum e acaba tratando como
        `//falso.example`, ou seja, host externo. É um desvio conhecido desta
        checagem, e é por isso que não basta exigir que comece com "/".
    """
    if not candidato:
        return None
    u = urlparse(candidato)
    if u.scheme not in ("", "http", "https"):
        return None
    if u.netloc:
        return candidato if u.netloc == urlparse(request.host_url).netloc else None
    # Sem host: só caminho absoluto deste site, e nunca "//" nem "/\"
    if not candidato.startswith("/") or candidato[:2] in ("//", "/\\"):
        return None
    return candidato


def voltar(padrao: str):
    """`redirect` para a página anterior quando ela é deste site, senão para
    `padrao`. Substitui o `redirect(request.referrer or ...)`, que aceitava
    qualquer destino."""
    return redirect(destino_seguro(request.referrer) or padrao)
