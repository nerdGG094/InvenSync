# inventory/routes/health.py
"""Endpoint /health — usado pelo launcher para testar as conexões."""
import time
from datetime import datetime

from flask import Blueprint, jsonify, current_app
from sqlalchemy import text

from ..extensions import db

bp = Blueprint("health", __name__)

_START = time.time()


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
    # WhatsApp / e-mail configurados?
    try:
        from ..services import whatsapp, mailer
        out["whatsapp"] = {
            "enabled": bool(current_app.config.get("WHATSAPP_ENABLED")),
            "configured": whatsapp.configured(),
        }
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


@bp.route("/health")
def health():
    checks = {}

    t0 = time.perf_counter()
    try:
        db.session.execute(text("SELECT 1"))
        checks["PostgreSQL"] = {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        }
    except Exception as e:  # noqa: BLE001
        checks["PostgreSQL"] = {
            "status": "error",
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            "error": str(e),
        }

    all_ok = all(c["status"] == "ok" for c in checks.values())
    payload = {
        "status": "ok" if all_ok else "degraded",
        "uptime": _uptime(),
        "checks": checks,
        "info": _info(),
    }
    return jsonify(payload), (200 if all_ok else 503)
