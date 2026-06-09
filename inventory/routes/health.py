# inventory/routes/health.py
"""Endpoint /health — usado pelo launcher para testar as conexões."""
import time

from flask import Blueprint, jsonify
from sqlalchemy import text

from ..extensions import db

bp = Blueprint("health", __name__)

_START = time.time()


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
    }
    return jsonify(payload), (200 if all_ok else 503)
