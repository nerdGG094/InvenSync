"""Troca de celular: a saída do aparelho novo devolve o antigo.

Estoque e Celulares eram cadastros que não se falavam — entregar um aparelho a
quem já tinha um exigia dois lançamentos manuais, e nada garantia que as duas
versões concordassem.
"""
import pytest

PESSOA = "Pytest Trocador"
OUTRA = "Pytest Alheio"


def _produto(db, sku, nome):
    from inventory.models.product import Product
    p = Product.query.filter_by(sku=sku).first()
    if p is None:
        p = Product(sku=sku, name=nome)
        db.session.add(p)
        db.session.commit()
    return p


def _aparelho(db, modelo, dono, **extra):
    from inventory.models.mobile import MobileDevice
    d = MobileDevice(brand="Samsung", model=modelo, assigned_employee=dono,
                     status="em_uso", sector="TI", **extra)
    db.session.add(d)
    db.session.commit()
    return d


@pytest.fixture
def cenario(app):
    """Pessoa com um aparelho em uso + os materiais de celular no Estoque."""
    from inventory.extensions import db
    from inventory.models.mobile import MobileDevice
    from inventory.models.movement import StockMovement

    with app.app_context():
        antigo = _produto(db, "CEL-ANTIGO-PYTEST", "Celular Galaxy A15")
        novo = _produto(db, "CEL-NOVO-PYTEST", "Celular Galaxy A25")
        dev = _aparelho(db, "Galaxy A15", PESSOA, patrimony="PAT-PYTEST")
        ids = {"antigo": antigo.id, "novo": novo.id, "dev": dev.id}
        yield ids
        MobileDevice.query.filter(MobileDevice.model.like("Galaxy A%")).delete(
            synchronize_session=False)
        StockMovement.query.filter(
            StockMovement.product_id.in_([ids["antigo"], ids["novo"]])).delete(
            synchronize_session=False)
        db.session.commit()


def _post_saida(client, ids, **extra):
    dados = {
        "product_id": ids["novo"],
        "movement_type": "OUT",
        "quantity": 1,
        "responsible_user": PESSOA,
        "troca_destino": "nada",
    }
    dados.update(extra)
    return client.post("/movements", data=dados, follow_redirects=True)


def test_devolucao_ao_estoque_gera_entrada_e_libera_o_aparelho(app, auth_client, cenario):
    from inventory.extensions import db
    from inventory.models.mobile import MobileDevice
    from inventory.models.movement import StockMovement

    r = _post_saida(auth_client, cenario, troca_mobile_id=cenario["dev"],
                    troca_destino="estoque", troca_product_id=cenario["antigo"])
    assert r.status_code == 200

    with app.app_context():
        entradas = StockMovement.query.filter_by(
            product_id=cenario["antigo"], movement_type="IN").all()
        assert len(entradas) == 1, "a devolução tinha de gerar UMA entrada"
        assert entradas[0].quantity == 1
        assert PESSOA in (entradas[0].note or "")

        dev = db.session.get(MobileDevice, cenario["dev"])
        assert dev.status == "disponivel"
        assert dev.assigned_employee is None
        # O material escolhido fica gravado: o modelo só se aponta uma vez.
        assert dev.product_id == cenario["antigo"]


def test_manutencao_nao_devolve_ao_estoque(app, auth_client, cenario):
    """Aparelho quebrado não pode virar saldo — é o erro que só aparece no inventário."""
    from inventory.extensions import db
    from inventory.models.mobile import MobileDevice
    from inventory.models.movement import StockMovement

    _post_saida(auth_client, cenario, troca_mobile_id=cenario["dev"],
                troca_destino="manutencao", troca_product_id=cenario["antigo"])

    with app.app_context():
        assert StockMovement.query.filter_by(
            product_id=cenario["antigo"], movement_type="IN").count() == 0
        dev = db.session.get(MobileDevice, cenario["dev"])
        assert dev.status == "manutencao"
        assert dev.assigned_employee is None


def test_sem_escolha_nada_acontece(app, auth_client, cenario):
    from inventory.extensions import db
    from inventory.models.mobile import MobileDevice
    from inventory.models.movement import StockMovement

    _post_saida(auth_client, cenario)          # troca_destino = "nada"

    with app.app_context():
        assert StockMovement.query.filter_by(
            product_id=cenario["antigo"], movement_type="IN").count() == 0
        dev = db.session.get(MobileDevice, cenario["dev"])
        assert dev.status == "em_uso"
        assert dev.assigned_employee == PESSOA
        # e a saída do aparelho novo foi registrada normalmente
        assert StockMovement.query.filter_by(
            product_id=cenario["novo"], movement_type="OUT").count() == 1


def test_aparelho_de_outra_pessoa_e_recusado(app, auth_client, cenario):
    """Id trocado na mão não pode mexer no celular de outro funcionário."""
    from inventory.extensions import db
    from inventory.models.mobile import MobileDevice
    from inventory.models.movement import StockMovement

    with app.app_context():
        alheio = _aparelho(db, "Galaxy A05", OUTRA)
        alheio_id = alheio.id

    _post_saida(auth_client, cenario, troca_mobile_id=alheio_id,
                troca_destino="estoque", troca_product_id=cenario["antigo"])

    with app.app_context():
        d = db.session.get(MobileDevice, alheio_id)
        assert d.status == "em_uso"
        assert d.assigned_employee == OUTRA
        assert StockMovement.query.filter_by(
            product_id=cenario["antigo"], movement_type="IN").count() == 0


def test_aparelho_compartilhado_fica_de_fora(app, cenario):
    """Devolver um aparelho que outras pessoas também usam tiraria o deles."""
    from inventory.extensions import db
    from inventory.services import troca_celular

    with app.app_context():
        _aparelho(db, "Galaxy A55", PESSOA, assigned_employee_2="Outro Alguem")
        achados = troca_celular.aparelhos_da_pessoa(PESSOA)
        modelos = [d.model for d in achados]
        assert "Galaxy A15" in modelos
        assert "Galaxy A55" not in modelos


def test_endpoint_json_responde_o_aparelho_atual(auth_client, cenario):
    r = auth_client.get(f"/movements/celular-do-responsavel?user={PESSOA}")
    assert r.status_code == 200
    ap = r.get_json()["aparelhos"]
    assert len(ap) == 1
    assert ap[0]["id"] == cenario["dev"]
    # palpite pelo nome: "Galaxy A15" casa com "Celular Galaxy A15"
    assert ap[0]["produto_id"] == cenario["antigo"]


def test_endpoint_json_vazio_para_quem_nao_tem_aparelho(auth_client, cenario):
    r = auth_client.get("/movements/celular-do-responsavel?user=Ninguem Com Esse Nome")
    assert r.status_code == 200
    assert r.get_json()["aparelhos"] == []
