"""
Testes das melhorias dos lotes 1 e 2 (busca, exports, PWA, sessão, chamados).
Reaproveita as fixtures do conftest (app, client, auth_client, admin_email).
"""
import pytest


def test_pwa_assets(client):
    assert client.get("/sw.js").status_code == 200
    assert client.get("/static/manifest.webmanifest").status_code == 200
    assert client.get("/static/icon-192.png").status_code == 200


def test_global_search_requires_login(client):
    r = client.get("/busca?q=teste", follow_redirects=False)
    assert r.status_code in (301, 302)  # redireciona p/ login


def test_global_search_admin(auth_client):
    r = auth_client.get("/busca?q=ab")
    assert r.status_code == 200
    assert "results" in r.get_json()


def test_global_search_short_query(auth_client):
    # menos de 2 chars -> sem resultados
    assert auth_client.get("/busca?q=a").get_json()["results"] == []


def test_exports_xlsx(auth_client):
    for url in ("/machines/chips/export", "/colaboradores/export"):
        r = auth_client.get(url)
        assert r.status_code == 200
        assert "spreadsheet" in r.headers.get("Content-Type", "")


def test_per_page_option(auth_client):
    assert auth_client.get("/products?per_page=50").status_code == 200


def test_logout_others_rotates_token(app, admin_email):
    """Rotacionar o token muda o get_id (invalida outras sessões)."""
    from inventory.extensions import db
    from inventory.models.user import User
    with app.app_context():
        u = User.query.filter_by(email=admin_email).first()
        before = u.get_id()
        u.rotate_session_token()
        db.session.commit()
        assert u.get_id() != before


def test_ticket_aging_property():
    """Propriedades de envelhecimento do chamado."""
    from datetime import datetime, timedelta
    from inventory.models.ticket import Ticket
    t = Ticket(code="CH-TST", title="x", status="aberto",
               created_at=datetime.now() - timedelta(hours=50))
    assert t.is_open is True
    assert t.is_stuck(48) is True
    assert t.age_label.endswith("h") or t.age_label.endswith("d")
