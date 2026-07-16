"""
Alertas proativos do InvenSync.

Verifica periodicamente três pendências operacionais e publica um resumo na
**Central de Avisos** (mantendo UM aviso automático, atualizado a cada rodada)
e avisa a TI por e-mail (uma vez ao dia, quando há pendências):

  1. Estoque no/abaixo do mínimo (materiais com min_stock definido).
  2. Licenças/garantias vencidas ou vencendo (≤ ALERTS_LICENSE_DAYS dias).
  3. Chamados parados: abertos/em andamento há mais de ALERTS_TICKET_STUCK_HOURS.

Tolerante a falhas: qualquer erro nunca derruba o app/servidor.
"""
import os
import threading
import time
from datetime import datetime, timedelta

from ..extensions import db
from ..models.announcement import Announcement
from ..models.license import License
from ..models.product import Product
from ..models.ticket import Ticket
from ..repositories import product_repo
from . import mailer

# Título fixo do aviso automático (upsert: criamos uma vez, depois atualizamos).
AUTO_TITLE = "🔔 Alertas automáticos do sistema"

_started = False
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Coletores
# ---------------------------------------------------------------------------
def _low_stock():
    """[(produto, estoque_atual, minimo)] para itens no/abaixo do mínimo."""
    smap = product_repo.stock_map()   # saldo de todos numa query (sem N+1)
    out = []
    for p in Product.query.all():
        mn = int(p.min_stock or 0)
        if mn <= 0:
            continue
        est = smap.get(p.id, 0)
        if est <= mn:
            out.append((p, est, mn))
    out.sort(key=lambda x: (x[1] - x[2]))  # mais críticos primeiro
    return out


def _expiring_licenses(days: int):
    """[(licenca, dias_restantes)] vencidas ou a vencer em até `days` dias."""
    out = []
    for lic in License.query.filter(License.expiry_date.isnot(None)).all():
        d = lic.days_left
        if d is not None and d <= days:
            out.append((lic, d))
    out.sort(key=lambda x: x[1])  # vencidas/mais próximas primeiro
    return out


def _stuck_tickets(hours: int):
    cutoff = datetime.now() - timedelta(hours=hours)
    return (Ticket.query
            .filter(Ticket.status.in_(("aberto", "em_andamento")))
            .filter(Ticket.created_at <= cutoff)
            .order_by(Ticket.created_at.asc())
            .all())


def _stale_backup(app):
    """(idade_horas, nome|None) se o último backup está velho demais; senão None.
    Rede de segurança: mesmo com o agendador interno, avisa se algo travar."""
    try:
        import sys
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if root not in sys.path:
            sys.path.insert(0, root)
        import backup_db
        limit = int(app.config.get("ALERTS_BACKUP_STALE_HOURS", 48) or 48)
        items = backup_db.list_backups()
        if not items:
            return (None, None)  # nenhum backup existe — crítico
        age = (datetime.now() - items[0]["mtime"]).total_seconds() / 3600.0
        if age > limit:
            return (age, items[0]["name"])
        return None
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Montagem do texto
# ---------------------------------------------------------------------------
def _render_body(low, lic, stuck, days, hours, stale=None) -> str:
    if not (low or lic or stuck or stale):
        return "Nenhuma pendência no momento. ✅"

    lines = []
    if stale is not None:
        age, nome = stale
        if nome is None:
            lines.append("🗄️ Backup: NENHUM backup encontrado! Verifique o agendador.")
        else:
            lines.append(f"🗄️ Backup atrasado: último há ~{int(age)}h ({nome}).")
        lines.append("")
    if low:
        lines.append(f"📦 Estoque no/abaixo do mínimo ({len(low)}):")
        for p, est, mn in low[:25]:
            lines.append(f"  • {p.sku} — {p.name}: {est} / mín {mn}")
        if len(low) > 25:
            lines.append(f"  … e mais {len(low) - 25}.")
        lines.append("")

    if lic:
        lines.append(f"📅 Licenças/garantias vencidas ou ≤ {days} dias ({len(lic)}):")
        for l, d in lic[:25]:
            quando = "VENCIDA" if d < 0 else (f"vence hoje" if d == 0 else f"{d} dias")
            data = l.expiry_date.strftime('%d/%m/%Y') if l.expiry_date else "—"
            lines.append(f"  • {l.name} ({l.kind}): {quando} — {data}")
        if len(lic) > 25:
            lines.append(f"  … e mais {len(lic) - 25}.")
        lines.append("")

    if stuck:
        lines.append(f"🎫 Chamados parados há mais de {hours}h ({len(stuck)}):")
        for t in stuck[:25]:
            aberto = t.created_at.strftime('%d/%m') if t.created_at else "—"
            lines.append(f"  • {t.code} — {t.title} ({t.status}, desde {aberto})")
        if len(stuck) > 25:
            lines.append(f"  … e mais {len(stuck) - 25}.")
        lines.append("")

    lines.append(f"Atualizado em {datetime.now().strftime('%d/%m/%Y %H:%M')}.")
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Publicação (upsert no aviso + e-mail)
# ---------------------------------------------------------------------------
def publish(app) -> int:
    """Atualiza o aviso automático e retorna o total de pendências (-1 em erro)."""
    days = int(app.config.get("ALERTS_LICENSE_DAYS", 30) or 30)
    hours = int(app.config.get("ALERTS_TICKET_STUCK_HOURS", 48) or 48)
    with app.app_context():
        try:
            low = _low_stock()
            lic = _expiring_licenses(days)
            stuck = _stuck_tickets(hours)
            stale = _stale_backup(app)
            total = len(low) + len(lic) + len(stuck) + (1 if stale is not None else 0)
            body = _render_body(low, lic, stuck, days, hours, stale)
            level = "urgente" if total else "info"

            a = Announcement.query.filter_by(title=AUTO_TITLE).first()
            if a is None:
                a = Announcement(title=AUTO_TITLE, body=body, level=level,
                                 is_pinned=bool(total), is_active=bool(total),
                                 author_id=None)
                db.session.add(a)
            else:
                a.body = body
                a.level = level
                a.is_pinned = bool(total)
                # Sem pendências: despublica (some do mural), mas mantém o registro.
                a.is_active = bool(total)
            db.session.commit()
            return total
        except Exception:  # noqa: BLE001
            db.session.rollback()
            return -1


# ---------------------------------------------------------------------------
# Digest por e-mail — só nas horas-alvo (ex.: 8 e 17), 1x por janela/dia.
# O controle é persistido em arquivo, então reiniciar o servidor NÃO reenvia.
# ---------------------------------------------------------------------------
def _target_hours(app):
    out = set()
    for part in str(app.config.get("ALERTS_DIGEST_HOURS", "8,17")).split(","):
        part = part.strip()
        if part.isdigit() and 0 <= int(part) <= 23:
            out.add(int(part))
    return out or {8, 17}


def _state_file(app):
    return os.path.join(app.instance_path, "alerts_wpp.txt")


def send_digest_if_window(app):
    """Dispara o digest se a hora atual é uma das horas-alvo e ainda não foi
    enviado nesta janela (data#hora). Marca a janela ANTES de enviar para nunca
    duplicar, mesmo com vários ticks ou reinícios dentro da mesma hora."""
    with app.app_context():
        now = datetime.now()
        if now.hour not in _target_hours(app):
            return
        slot = f"{now.date().isoformat()}#{now.hour}"
        path = _state_file(app)
        try:
            with open(path, "r", encoding="utf-8") as f:
                if f.read().strip() == slot:
                    return  # já processado nesta janela
        except Exception:  # noqa: BLE001
            pass

        try:
            days = int(app.config.get("ALERTS_LICENSE_DAYS", 30) or 30)
            hours = int(app.config.get("ALERTS_TICKET_STUCK_HOURS", 48) or 48)
            low = _low_stock()
            lic = _expiring_licenses(days)
            stuck = _stuck_tickets(hours)
            total = len(low) + len(lic) + len(stuck)
            # Nada a enviar? NÃO marca a janela — se surgir pendência mais tarde
            # na mesma hora (ex.: host cai às 08:20), o digest ainda sai.
            if total <= 0:
                return
            resumo = (
                f"📦 Estoque no mínimo: {len(low)}\n"
                f"📅 Licenças/garantias: {len(lic)}\n"
                f"🎫 Chamados parados (>{hours}h): {len(stuck)}\n"
                "Veja os detalhes na Central de Avisos."
            )
            mailer.notify_ti("[InvenSync] Alertas do dia", "Alertas do dia\n\n" + resumo)
            # Marca a janela como consumida SÓ após enviar (evita duplicar no
            # próximo tick da mesma hora).
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(slot)
            except Exception as e:  # noqa: BLE001
                try:
                    app.logger.warning("alerts: não gravou estado do digest: %s", e)
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            db.session.rollback()


# ---------------------------------------------------------------------------
# Agendador em background
# ---------------------------------------------------------------------------
def _sec_state_file(app):
    return os.path.join(app.instance_path, "sec_alerts_lastid.txt")


def check_suspicious_activity(app):
    """Varre a auditoria a cada rodada e avisa a TI por e-mail quando um padrão
    suspeito cruza o limite na janela (muitas falhas de login, revelações do
    Cofre em massa, exclusões em lote). Só analisa registros novos desde a última
    checagem; a 1ª rodada apenas marca o ponto de partida (sem alerta retroativo).
    """
    with app.app_context():
        if not app.config.get("SECURITY_ALERTS_ENABLED",
                              app.config.get("ALERTS_ENABLED", True)):
            return []
        from collections import Counter
        from ..models.audit import AuditLog
        path = _sec_state_file(app)
        try:
            with open(path, encoding="utf-8") as f:
                last_id = int(f.read().strip())
        except Exception:  # noqa: BLE001
            last_id = None

        if last_id is None:
            newest = db.session.query(db.func.max(AuditLog.id)).scalar() or 0
            _write_state(path, str(newest))
            return []

        rows = AuditLog.query.filter(AuditLog.id > last_id).all()
        if not rows:
            return []
        _write_state(path, str(max(r.id for r in rows)))

        cnt = Counter((r.action or "").lower() for r in rows)
        mins = int(app.config.get("ALERTS_CHECK_MINUTES", 30) or 30)
        regras = [
            ("login_fail", "falhas de login", int(app.config.get("SEC_ALERT_LOGINFAIL", 15) or 15)),
            ("reveal", "revelações de senha do Cofre", int(app.config.get("SEC_ALERT_REVEAL", 20) or 20)),
            ("delete", "exclusões", int(app.config.get("SEC_ALERT_DELETE", 25) or 25)),
        ]
        hits = [f"• {cnt[a]} {label} nos últimos ~{mins} min (limite {thr})"
                for a, label, thr in regras if cnt.get(a, 0) >= thr]
        if hits:
            corpo = ("Atividade suspeita detectada na auditoria:\n\n"
                     + "\n".join(hits) + "\n\nConfira em Admin → Auditoria.")
            mailer.notify_ti("[InvenSync] ⚠️ Alerta de atividade suspeita", corpo)
        return hits


def _write_state(path, value):
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(value)
    except Exception:  # noqa: BLE001
        pass


def start_scheduler(app):
    """Thread daemon: a cada ALERTS_CHECK_MINUTES atualiza o aviso e, nas
    horas-alvo, envia o digest por e-mail (no máximo 1x por janela/dia)."""
    global _started
    # Sob o reloader do Flask (debug), só roda no processo filho real.
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return
    with _lock:
        if _started:
            return
        _started = True

    check = max(5, int(app.config.get("ALERTS_CHECK_MINUTES", 30) or 30)) * 60

    def loop():
        time.sleep(25)  # deixa o servidor subir antes da 1ª rodada
        while True:
            try:
                publish(app)                 # atualiza o aviso (sem e-mail)
                send_digest_if_window(app)   # e-mail só nas horas-alvo
                check_suspicious_activity(app)  # avisa a TI de padrões suspeitos
            except Exception as e:  # noqa: BLE001
                try:
                    with app.app_context():
                        from . import errorlog
                        errorlog.record("alerts", exc=e)
                except Exception:  # noqa: BLE001
                    pass
            time.sleep(check)

    threading.Thread(target=loop, daemon=True, name="alerts").start()
    try:
        app.logger.info("Alertas proativos iniciados (checa a cada %s min; digest em %s).",
                        check // 60, sorted(_target_hours(app)))
    except Exception:  # noqa: BLE001
        pass
