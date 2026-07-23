"""Cotações no Mercado Livre (API oficial).

A busca pública do ML exige autenticação desde ~2023 (a anônima devolve 403 e o
site tem parede anti-robô). Usamos o fluxo *client_credentials*: o app definido
por MELI_CLIENT_ID/MELI_CLIENT_SECRET (criado grátis no DevCenter do Mercado
Livre) troca as credenciais por um token de ~6h, cacheado em memória e renovado
sozinho.

Tudo best-effort: `search()` nunca levanta exceção — devolve
{"ok": False, "error": "..."} em qualquer falha.
"""
import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

_CTX = ssl.create_default_context()
_API = "https://api.mercadolibre.com"

# Cache do token de app: {"token": str, "exp": epoch}
_tok = {"token": None, "exp": 0.0}


def _http(url, data=None, headers=None, timeout=12):
    """Requisição JSON. Retorna (status, dict|None)."""
    req = urllib.request.Request(
        url, data=data,
        headers={"User-Agent": "InvenSync", "Accept": "application/json",
                 **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", "replace") or "{}")
        except Exception:  # noqa: BLE001
            return e.code, None
    except Exception:  # noqa: BLE001
        return None, None


def _token(app):
    """Token de aplicação (client_credentials), cacheado até perto de expirar."""
    if _tok["token"] and time.time() < _tok["exp"]:
        return _tok["token"]
    cid = (app.config.get("MELI_CLIENT_ID") or "").strip()
    sec = (app.config.get("MELI_CLIENT_SECRET") or "").strip()
    if not cid or not sec:
        return None
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": cid, "client_secret": sec,
    }).encode()
    st, d = _http(f"{_API}/oauth/token", data=body,
                  headers={"Content-Type": "application/x-www-form-urlencoded"})
    if st == 200 and d and d.get("access_token"):
        _tok["token"] = d["access_token"]
        _tok["exp"] = time.time() + int(d.get("expires_in", 21600)) - 120
        return _tok["token"]
    return None


def _fmt_preco(v):
    try:
        return ("R$ {:,.2f}".format(float(v))
                .replace(",", "@").replace(".", ",").replace("@", "."))
    except (TypeError, ValueError):
        return "—"


def search(app, q, novos=True, limit=30):
    """Busca cotações no ML (site MLB), ordenadas por menor preço."""
    q = (q or "").strip()
    if not q:
        return {"ok": False, "error": "Digite o que deseja cotar."}
    cid = (app.config.get("MELI_CLIENT_ID") or "").strip()
    if not cid or not (app.config.get("MELI_CLIENT_SECRET") or "").strip():
        return {"ok": False, "error": "nao-configurado"}
    tok = _token(app)
    if not tok:
        return {"ok": False, "error": "Falha ao autenticar no Mercado Livre "
                                      "(confira MELI_CLIENT_ID/MELI_CLIENT_SECRET)."}
    params = {"q": q, "limit": max(1, min(50, int(limit))), "sort": "price_asc"}
    if novos:
        params["condition"] = "new"
    st, d = _http(f"{_API}/sites/MLB/search?" + urllib.parse.urlencode(params),
                  headers={"Authorization": f"Bearer {tok}"})
    if st in (401, 403):
        _tok["token"] = None   # token vencido/revogado: força renovar na próxima
        return {"ok": False, "error": "Mercado Livre recusou o acesso "
                                      f"(HTTP {st}). Tente de novo em instantes."}
    if st != 200 or not isinstance(d, dict):
        return {"ok": False, "error": f"Mercado Livre indisponível (HTTP {st})."}

    itens = []
    for r in d.get("results", []):
        preco = r.get("price")
        if preco is None:
            continue
        ship = r.get("shipping") or {}
        seller = r.get("seller") or {}
        inst = r.get("installments") or {}
        itens.append({
            "titulo": r.get("title") or "—",
            "preco": float(preco),
            "preco_fmt": _fmt_preco(preco),
            "link": r.get("permalink") or "#",
            "foto": (r.get("thumbnail") or "").replace("http://", "https://"),
            "vendedor": seller.get("nickname") or "",
            "loja_oficial": r.get("official_store_name") or "",
            "frete_gratis": bool(ship.get("free_shipping")),
            "full": (ship.get("logistic_type") == "fulfillment"),
            "novo": (r.get("condition") == "new"),
            "parcelas": (f"{inst.get('quantity')}x de {_fmt_preco(inst.get('amount'))}"
                         if inst.get("quantity") else ""),
        })
    itens.sort(key=lambda i: i["preco"])
    return {"ok": True, "total": d.get("paging", {}).get("total", len(itens)),
            "itens": itens}
