# inventory/routes/health.py
"""Endpoint /health — usado pelo launcher para testar as conexões."""
import time
from datetime import datetime

from flask import Blueprint, jsonify, current_app, request
from sqlalchemy import text

from ..extensions import db

bp = Blueprint("health", __name__)

_START = time.time()


def _coletor(modulo, ligado: bool, intervalo: int) -> dict:
    """Saúde de um coletor de fundo a partir do carimbo do último ciclo.

    Tolera 3 ciclos (com piso de 5 min) antes de chamar de parado, para um
    ciclo mais demorado não virar alarme falso. Enquanto o primeiro ciclo não
    fecha, `ha_segundos` é None: aí a régua é o tempo de vida do processo, já
    que a thread dorme alguns segundos antes de começar.

    Desligado por configuração **não é** `stale` -- um agendador que ninguém
    quer não é uma falha, e marcá-lo como problema ensinaria a ignorar o campo.
    """
    try:
        s = modulo.saude()
    except Exception:  # noqa: BLE001
        return {"enabled": ligado, "running": False, "ha_segundos": None, "stale": False}
    ha = s.get("ha_segundos")
    limite = max(intervalo * 3, 300)
    if not ligado or not s.get("rodando"):
        parado = False
    elif ha is None:
        parado = (time.time() - _START) > (intervalo + limite)
    else:
        parado = ha > limite
    return {"enabled": ligado, "running": bool(s.get("rodando")),
            "ha_segundos": ha, "stale": parado}


def _info() -> dict:
    """Informações operacionais (não afetam o status crítico)."""
    out = {}
    # Schedulers em segundo plano
    try:
        from ..services import monitoring, alerts
        out["monitoring"] = {
            "enabled": bool(current_app.config.get("MONITORING_ENABLED")),
            "running": bool(getattr(monitoring, "_started", False)),
        }
        out["alerts"] = {
            "enabled": bool(current_app.config.get("ALERTS_ENABLED")),
            "running": bool(getattr(alerts, "_started", False)),
        }
    except Exception:  # noqa: BLE001
        pass
    # Escutas de detecção do CFTV. Existe porque a detecção ficou 6 dias fora
    # do ar sem ninguém notar: o app monitorava impressora, roteador e DVR, mas
    # não monitorava os próprios coletores. `stale` marca a escuta que está sem
    # receber nem heartbeat.
    try:
        from ..services import dvr_events
        s = dvr_events.saude()
        if s:
            # `is None` explicito, nao `or`: ha_segundos == 0 (heartbeat no
            # mesmo instante do /health) e saudavel, mas `0 or 1e9` daria 1e9.
            paradas = [i for i, v in s.items()
                       if not v["ok"]
                       or v["ha_segundos"] is None or v["ha_segundos"] > 300]
            out["dvr_eventos"] = {
                "enabled": bool(current_app.config.get("DVR_EVENTS_ENABLED")),
                "escutas": len(s),
                "paradas": paradas,
                "stale": bool(paradas),
            }
    except Exception:  # noqa: BLE001
        pass
    # Coletores periódicos (impressoras e tomadas). Mesma lição do CFTV: a
    # thread existir não prova nada -- a escuta dos DVRs passou 6 dias "viva",
    # parada num read() sem timeout. O sinal é o ciclo parar de avançar, e o
    # sintoma desses dois seria igualmente silencioso: a baixa de toner
    # simplesmente deixa de acontecer, o horário programado simplesmente não
    # dispara. (O backup não precisa disto: `last_backup` já mede o resultado,
    # que é um sinal melhor que o estado da thread.)
    try:
        from ..services import printer_monitor, plug_scheduler
        out["printer_monitor"] = _coletor(
            printer_monitor,
            bool(current_app.config.get("PRINTER_MONITOR_ENABLED")),
            max(10, int(current_app.config.get("PRINTER_MONITOR_MINUTES", 60) or 60)) * 60,
        )
        out["plug_scheduler"] = _coletor(
            plug_scheduler,
            bool(current_app.config.get("PLUG_SCHEDULER_ENABLED")),
            30,      # acorda 2x por minuto
        )
    except Exception:  # noqa: BLE001
        pass
    # E-mail configurado?
    try:
        from ..services import mailer
        out["email"] = {
            "enabled": bool(current_app.config.get("MAIL_ENABLED")),
            "configured": mailer.configured(),
        }
    except Exception:  # noqa: BLE001
        pass
    # Último backup e idade
    try:
        import backup_db
        items = backup_db.list_backups()
        if items:
            last = items[0]["mtime"]
            age_h = (datetime.now() - last).total_seconds() / 3600.0
            out["last_backup"] = {
                "name": items[0]["name"],
                "age_hours": round(age_h, 1),
                "stale": age_h > 26,  # mais de ~1 dia sem backup
            }
        else:
            out["last_backup"] = {"name": None, "age_hours": None, "stale": True}
    except Exception:  # noqa: BLE001
        pass
    return out


def _uptime() -> str:
    s = int(time.time() - _START)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m {sec:02d}s"
    if m:
        return f"{m}m {sec:02d}s"
    return f"{sec}s"


def _is_local() -> bool:
    """Requisição vinda do próprio servidor (launcher em 127.0.0.1)?"""
    return (request.remote_addr or "") in ("127.0.0.1", "::1", "localhost")


@bp.route("/health")
def health():
    """Público: só status/uptime/checks. Detalhes de infra (último backup,
    schedulers, e-mail) e a mensagem de erro do banco ficam apenas para o
    launcher local — não vazam para qualquer um na rede."""
    local = _is_local()
    checks = {}

    t0 = time.perf_counter()
    try:
        db.session.execute(text("SELECT 1"))
        checks["PostgreSQL"] = {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        }
    except Exception as e:  # noqa: BLE001
        try:
            current_app.logger.warning("healthcheck DB falhou: %s", e)
        except Exception:  # noqa: BLE001
            pass
        checks["PostgreSQL"] = {
            "status": "error",
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            # str(e) do psycopg pode conter host/porta/usuário/db — só p/ o local.
            "error": str(e) if local else "erro de conexão",
        }

    all_ok = all(c["status"] == "ok" for c in checks.values())
    payload = {
        "status": "ok" if all_ok else "degraded",
        "uptime": _uptime(),
        "checks": checks,
    }
    if local:
        payload["info"] = _info()
    return jsonify(payload), (200 if all_ok else 503)
