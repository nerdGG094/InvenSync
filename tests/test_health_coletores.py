"""O /health precisa vigiar os coletores de fundo, não só o banco.

Vem da queda que passou despercebida: a escuta de eventos dos DVRs ficou 6
dias fora do ar porque o app monitorava impressora, roteador e DVR — e não os
próprios coletores. A coleta das impressoras e o agendador das tomadas tinham
exatamente o mesmo ponto cego, com sintomas igualmente silenciosos (a baixa de
toner deixa de acontecer; o horário programado não dispara).
"""
import time


def _info(client):
    """O /health só devolve 'info' para quem chama local — o test client é."""
    r = client.get("/health")
    assert r.status_code in (200, 503)
    return r.get_json().get("info", {})


def test_coletores_aparecem_no_health(client):
    info = _info(client)
    for chave in ("printer_monitor", "plug_scheduler"):
        assert chave in info, f"{chave} sumiu do /health"
        assert set(info[chave]) >= {"enabled", "running", "stale"}


def test_desligado_nao_e_falha(client, app):
    """Agendador desligado por configuração não pode marcar 'stale'.

    Se marcasse, o campo viraria ruído permanente em qualquer instalação que
    não use o módulo — e campo ruidoso é campo ignorado.
    """
    app.config["PRINTER_MONITOR_ENABLED"] = False
    info = _info(client)
    assert info["printer_monitor"]["stale"] is False


def test_ciclo_velho_marca_stale(client, app, monkeypatch):
    """Ligado, rodando, mas sem fechar ciclo há horas => parado."""
    from inventory.services import printer_monitor

    app.config["PRINTER_MONITOR_ENABLED"] = True
    app.config["PRINTER_MONITOR_MINUTES"] = 60
    monkeypatch.setattr(printer_monitor, "_started", True)
    monkeypatch.setattr(printer_monitor, "_ultimo_ciclo", time.time() - 6 * 3600)

    assert _info(client)["printer_monitor"]["stale"] is True


def test_ciclo_recente_esta_saudavel(client, app, monkeypatch):
    from inventory.services import printer_monitor

    app.config["PRINTER_MONITOR_ENABLED"] = True
    app.config["PRINTER_MONITOR_MINUTES"] = 60
    monkeypatch.setattr(printer_monitor, "_started", True)
    monkeypatch.setattr(printer_monitor, "_ultimo_ciclo", time.time() - 30)

    saude = _info(client)["printer_monitor"]
    assert saude["stale"] is False
    assert saude["ha_segundos"] is not None and saude["ha_segundos"] < 120


def test_saude_nao_levanta_sem_ciclo_nenhum():
    """Antes do primeiro ciclo, `saude()` responde com ha_segundos=None."""
    from inventory.services import plug_scheduler, printer_monitor

    for mod in (printer_monitor, plug_scheduler):
        s = mod.saude()
        assert set(s) >= {"rodando", "ultimo_ciclo", "ha_segundos"}
        if s["ultimo_ciclo"] is None:
            assert s["ha_segundos"] is None
