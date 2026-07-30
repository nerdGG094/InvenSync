"""#4 uptime: impressoras/DVRs/routers viram hosts monitorados automaticamente."""


def test_sync_cria_e_remove_auto_hosts(app):
    from inventory.extensions import db
    from inventory.models.monitor import MonitoredHost
    from inventory.models.machine import Machine
    from inventory.models.dvr import Dvr
    from inventory.models.router import Router
    from inventory.services import monitoring

    with app.app_context():
        pr = Machine(kind="impressora", model="AUTOSYNC-PR", ip_address="10.9.0.1", is_active=True)
        dv = Dvr(model="AUTOSYNC-DVR", ip_address="10.9.0.2", status="em_uso")
        rt = Router(model="AUTOSYNC-RT", ip_address="10.9.0.3", status="em_uso")
        pc = Machine(kind="computador", model="AUTOSYNC-PC", ip_address="10.9.0.9", is_active=True)
        dhcp = Machine(kind="impressora", model="AUTOSYNC-DHCP", ip_address="DHCP", is_active=True)
        db.session.add_all([pr, dv, rt, pc, dhcp])
        db.session.commit()
        ids = {"pr": pr.id, "dv": dv.id, "rt": rt.id}

        monitoring._sync_auto_hosts()
        srcs = {h.auto_source for h in
                MonitoredHost.query.filter(MonitoredHost.auto_source.isnot(None)).all()}
        assert f"impressora:{ids['pr']}" in srcs
        assert f"dvr:{ids['dv']}" in srcs
        assert f"router:{ids['rt']}" in srcs
        # PC comum e impressora DHCP NÃO entram (não são infra com IP fixo)
        assert f"impressora:{pc.id}" not in srcs
        assert f"impressora:{dhcp.id}" not in srcs

        # inativar a impressora -> sync remove o host automático dela
        pr.is_active = False
        db.session.commit()
        monitoring._sync_auto_hosts()
        srcs2 = {h.auto_source for h in
                 MonitoredHost.query.filter(MonitoredHost.auto_source.isnot(None)).all()}
        assert f"impressora:{ids['pr']}" not in srcs2

        # limpeza
        MonitoredHost.query.filter(MonitoredHost.auto_source.in_(
            [f"impressora:{ids['pr']}", f"dvr:{ids['dv']}", f"router:{ids['rt']}"])).delete(synchronize_session=False)
        for o in (pr, pc, dhcp, dv, rt):
            db.session.delete(db.session.get(type(o), o.id))
        db.session.commit()
