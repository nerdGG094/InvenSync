"""Cotações no Mercado Livre: serviço (parse/ordenação) e acesso ao módulo."""
from inventory.services import mercado_livre as ml


def test_busca_vazia_e_sem_credenciais(app):
    with app.app_context():
        assert ml.search(app, "")["ok"] is False
        app.config["MELI_CLIENT_ID"] = ""
        app.config["MELI_CLIENT_SECRET"] = ""
        r = ml.search(app, "tn3492")
        assert r["ok"] is False and r["error"] == "nao-configurado"


def test_parse_e_ordenacao(app, monkeypatch):
    """Payload do ML -> itens normalizados, do mais barato ao mais caro."""
    fake = {
        "paging": {"total": 2},
        "results": [
            {"title": "Toner Caro", "price": 300.0, "permalink": "http://x/caro",
             "thumbnail": "http://img/caro.jpg", "condition": "new",
             "shipping": {"free_shipping": True, "logistic_type": "fulfillment"},
             "seller": {"nickname": "LOJA_A"},
             "installments": {"quantity": 10, "amount": 30.0}},
            {"title": "Toner Barato", "price": 199.9, "permalink": "http://x/barato",
             "thumbnail": "http://img/barato.jpg", "condition": "new",
             "shipping": {"free_shipping": False}, "seller": {"nickname": "LOJA_B"}},
        ],
    }
    with app.app_context():
        app.config["MELI_CLIENT_ID"] = "id"
        app.config["MELI_CLIENT_SECRET"] = "sec"
        monkeypatch.setattr(ml, "_token", lambda a: "tok")
        monkeypatch.setattr(ml, "_http", lambda *a, **k: (200, fake))
        r = ml.search(app, "tn3492")
    assert r["ok"] is True and len(r["itens"]) == 2
    assert r["itens"][0]["titulo"] == "Toner Barato"          # menor preço primeiro
    assert r["itens"][0]["preco_fmt"] == "R$ 199,90"
    assert r["itens"][0]["foto"].startswith("https://")        # http -> https
    assert r["itens"][1]["frete_gratis"] and r["itens"][1]["full"]
    assert r["itens"][1]["parcelas"] == "10x de R$ 30,00"


def test_token_recusado_gera_erro_amigavel(app, monkeypatch):
    with app.app_context():
        app.config["MELI_CLIENT_ID"] = "id"
        app.config["MELI_CLIENT_SECRET"] = "sec"
        monkeypatch.setattr(ml, "_token", lambda a: "tok")
        monkeypatch.setattr(ml, "_http", lambda *a, **k: (403, {"message": "forbidden"}))
        r = ml.search(app, "x")
    assert r["ok"] is False and "recusou" in r["error"]


def test_pagina_admin_e_bloqueio(app, auth_client, common_client):
    r = auth_client.get("/cotacoes")
    assert r.status_code == 200
    # sem credenciais configuradas, mostra o guia de configuração
    assert "Mercado Livre".encode() in r.data
    assert common_client.get("/cotacoes").status_code in (403, 302)


def test_deep_link_sem_credenciais(app, auth_client):
    """Sem API configurada, a busca oferece o link do SITE do ML ordenado por preço."""
    with app.app_context():
        app.config["MELI_CLIENT_ID"] = ""
        app.config["MELI_CLIENT_SECRET"] = ""
    r = auth_client.get("/cotacoes?q=toner+tn3492")
    assert r.status_code == 200
    assert b"https://lista.mercadolivre.com.br/toner-tn3492_OrderId_PRICE" in r.data
