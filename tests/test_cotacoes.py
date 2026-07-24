"""Cotações: deep-link para o Mercado Livre (sem API) e acesso admin-only."""


def test_pagina_cotacoes_admin(app, auth_client):
    r = auth_client.get("/cotacoes")
    assert r.status_code == 200
    assert "Mercado Livre".encode() in r.data


def test_deep_link_por_termo(app, auth_client):
    """A busca gera o link da lista completa do ML ordenada por menor preço."""
    r = auth_client.get("/cotacoes?q=toner+tn3492")
    assert r.status_code == 200
    assert b"https://lista.mercadolivre.com.br/toner-tn3492_OrderId_PRICE" in r.data


def test_cotacoes_bloqueia_nao_admin(app, common_client):
    assert common_client.get("/cotacoes").status_code in (403, 302)
