"""
Backup automático do banco em segundo plano (thread daemon).

Substitui a dependência de uma Tarefa Agendada externa do Windows (que pode ser
desativada/quebrar em silêncio): garante **um backup por dia**, criado a partir
de BACKUP_HOUR (default 02:00). Se o servidor estiver fora do ar no horário, faz
assim que voltar (self-heal — cobre o caso de dias sem backup). Reaproveita
`backup_db.run_backup()` (mesmo pg_dump/rotação da rota admin de Backups).

Tolerante a falhas: qualquer erro nunca derruba o app/servidor.
"""
import os
import sys
import threading
import time
from datetime import datetime

_started = False
_lock = threading.Lock()


def _backup_db():
    """Importa backup_db.py (raiz do projeto, fora do pacote inventory)."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    import backup_db
    return backup_db


def _has_backup_today(bkp) -> bool:
    hoje = datetime.now().date()
    for it in bkp.list_backups():
        if it["mtime"].date() >= hoje:
            return True
    return False


def maybe_backup(app) -> bool:
    """Gera o backup do dia se ainda não houver um (e já passou de BACKUP_HOUR).
    Retorna True se gerou agora."""
    bkp = _backup_db()
    hora = int(app.config.get("BACKUP_HOUR", 2) or 0)
    if datetime.now().hour < hora:
        return False
    if _has_backup_today(bkp):
        return False
    ok, msg, _ = bkp.run_backup()
    try:
        if ok:
            app.logger.info("Backup automático: %s", msg)
        else:
            app.logger.error("Backup automático FALHOU: %s", msg)
    except Exception:  # noqa: BLE001
        pass
    return ok


def start_scheduler(app):
    """Thread daemon que verifica de tempos em tempos se o backup do dia já foi
    feito. Idempotente por processo; respeita o reloader do Flask."""
    global _started
    # Sob o reloader do Flask (debug), só roda no processo filho real.
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return
    with _lock:
        if _started:
            return
        _started = True

    interval = max(60, int(app.config.get("BACKUP_CHECK_SECONDS", 1800) or 1800))

    def loop():
        time.sleep(20)  # deixa o servidor subir
        while True:
            try:
                maybe_backup(app)
            except Exception as e:  # noqa: BLE001
                try:
                    with app.app_context():
                        from . import errorlog
                        errorlog.record("backup", exc=e)
                except Exception:  # noqa: BLE001
                    pass
            time.sleep(interval)

    threading.Thread(target=loop, daemon=True, name="db-backup").start()
    try:
        app.logger.info("Agendador de backup iniciado (a partir das %sh).",
                        app.config.get("BACKUP_HOUR", 2))
    except Exception:  # noqa: BLE001
        pass
