"""#5 senha longa de router não trunca; #4 status do backup offsite (mirror)."""
import backup_db


def test_router_senha_longa_round_trip(app):
    """Senha longa -> token Fernet grande -> cabe em 255 e decifra igual."""
    from inventory.extensions import db
    from inventory.models.router import Router
    from inventory.repositories import router_repo
    from inventory.services import crypto
    senha = "S3nh@-muito-longa-de-router-" + ("x" * 90)   # ~117 chars de texto
    with app.app_context():
        r = router_repo.create_router(model="PYTEST-RT-LONG", admin_password=senha)
        rid = r.id
        raw = db.session.get(Router, rid).admin_password
        assert crypto.looks_encrypted(raw) and len(raw) > 120   # token maior que o antigo limite
        assert crypto.decrypt(raw) == senha                     # não truncou
        db.session.delete(db.session.get(Router, rid))
        db.session.commit()


def test_mirror_status_desligado(monkeypatch):
    monkeypatch.delenv("BACKUP_MIRROR_DIR", raising=False)
    assert backup_db.mirror_status() == {"configured": False}


def test_mirror_status_configurado(monkeypatch, tmp_path):
    monkeypatch.setenv("BACKUP_MIRROR_DIR", str(tmp_path))
    st = backup_db.mirror_status()
    assert st["configured"] and st["reachable"] and st["count"] == 0 and st["last"] is None
    # cria um .dump e confere que passa a contar
    (tmp_path / "inventario_almox_20260101_020000.dump").write_bytes(b"x")
    st2 = backup_db.mirror_status()
    assert st2["count"] == 1 and st2["last"] is not None
