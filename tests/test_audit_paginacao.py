"""A trilha de auditoria precisa ser navegável até o fim, não só os 400 últimos.

A tela buscava `list_logs(limit=400)` e paginava a lista em memória: o que
estivesse além disso não tinha como ser aberto, e o rodapé anunciava "400
registros" como se fosse o total. Numa trilha que só se consulta depois que
algo aconteceu, o histórico antigo é exatamente o que se procura.
"""
from datetime import datetime, timedelta

import pytest

MARCA = "pytest-paginacao"


@pytest.fixture
def trilha(app):
    """Cria 450 eventos marcados — acima do antigo teto de 400 — e limpa depois."""
    from inventory.extensions import db
    from inventory.models.audit import AuditLog

    with app.app_context():
        AuditLog.query.filter_by(entity=MARCA).delete()
        db.session.commit()
        base = datetime.now() - timedelta(days=10)
        db.session.bulk_save_objects([
            AuditLog(action="update", entity=MARCA, entity_id=i,
                     user_name="Fulano Auditado" if i % 2 else "Beltrano Auditado",
                     summary=f"evento numero {i}", ip="10.9.9.9",
                     created_at=base + timedelta(minutes=i))
            for i in range(450)
        ])
        db.session.commit()
        yield 450
        AuditLog.query.filter_by(entity=MARCA).delete()
        db.session.commit()


def test_total_e_o_real_nao_o_teto(auth_client, trilha):
    """O contador precisa falar do conjunto inteiro."""
    r = auth_client.get(f"/audit?entity={MARCA}")
    assert r.status_code == 200
    assert b"450 registros" in r.data


def test_o_evento_mais_antigo_e_alcancavel(auth_client, trilha):
    """Com 450 eventos e 100 por página, o primeiro está na página 5.

    Era o caso impossível: com o teto de 400, a página 5 vinha vazia e o
    'evento numero 0' simplesmente não existia para quem usasse a tela.
    """
    r = auth_client.get(f"/audit?entity={MARCA}&per_page=100&page=5")
    assert r.status_code == 200
    assert "evento numero 0".encode() in r.data


def test_paginas_diferentes_trazem_registros_diferentes(auth_client, trilha):
    p1 = auth_client.get(f"/audit?entity={MARCA}&per_page=20&page=1").data
    p2 = auth_client.get(f"/audit?entity={MARCA}&per_page=20&page=2").data
    assert "evento numero 449".encode() in p1     # mais recente primeiro
    assert "evento numero 449".encode() not in p2
    assert "evento numero 429".encode() in p2


def test_filtro_por_usuario(auth_client, trilha):
    r = auth_client.get(f"/audit?entity={MARCA}&user=Beltrano")
    assert r.status_code == 200
    assert b"225 registros" in r.data           # metade dos 450
    assert b"Fulano Auditado" not in r.data


def test_filtro_por_periodo_inclui_o_dia_final(app, auth_client, trilha):
    """'até <dia>' precisa pegar o próprio dia, senão some tudo o que houve nele."""
    from inventory.models.audit import AuditLog

    with app.app_context():
        ultimo = (AuditLog.query.filter_by(entity=MARCA)
                  .order_by(AuditLog.id.desc()).first())
        dia = ultimo.created_at.strftime("%Y-%m-%d")

    r = auth_client.get(f"/audit?entity={MARCA}&end={dia}")
    assert r.status_code == 200
    assert "evento numero 449".encode() in r.data


def test_filtro_por_texto_na_descricao(auth_client, trilha):
    r = auth_client.get(f"/audit?entity={MARCA}&q=evento+numero+123")
    assert r.status_code == 200
    assert "evento numero 123".encode() in r.data
    assert "evento numero 124".encode() not in r.data


def test_data_invalida_nao_derruba_a_pagina(auth_client, trilha):
    """Data digitada à mão (ou colada errada) não pode virar 500."""
    r = auth_client.get(f"/audit?entity={MARCA}&start=18/09/2026&end=xx")
    assert r.status_code == 200


def test_pagina_fora_do_intervalo_responde(auth_client, trilha):
    r = auth_client.get(f"/audit?entity={MARCA}&page=9999")
    assert r.status_code == 200
