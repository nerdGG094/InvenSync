"""
Alertas proativos do InvenSync.

Verifica periodicamente três pendências operacionais e publica um resumo na
**Central de Avisos** (mantendo UM aviso automático, atualizado a cada rodada)
e avisa a TI por WhatsApp (uma vez ao dia, quando há pendências):

  1. Estoque no/abaixo do mínimo (materiais com min_stock definido).
  2. Licenças/garantias vencidas ou vencendo (≤ ALERTS_LICENSE_DAYS dias).
  3. Chamados parados: abertos/em andamento há mais de ALERTS_TICKET_STUCK_HOURS.

Tolerante a falhas: qualquer erro nunca derruba o app/servidor.
"""
import os
import threading
import time
from datetime import date, datetime, timedelta

from ..extensions import db
from ..models.announcement import Announcement
from ..models.license import License
from ..models.product import Product
from ..models.ticket import Ticket
from ..repositories import product_repo
from . import whatsapp

# Título fixo do aviso automático (upsert: criamos uma vez, depois atualizamos).
AUTO_TITLE = "🔔 Alertas automáticos do sistema"

_started = False
_lock = threading.Lock()
_last_wpp_date = None  # evita repetir o WhatsApp no mesmo dia


# ---------------------------------------------------------------------------
# Coletores
# ---------------------------------------------------------------------------
def _low_stock():
    """[(produto, estoque_atual, minimo)] para itens no/abaixo do mínimo."""
    out = []
    for p in Product.query.all():
        mn = int(p.min_stock or 0)
        if mn <= 0:
            continue
        est = product_repo.current_stock(p)
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


# ---------------------------------------------------------------------------
# Montagem do texto
# ---------------------------------------------------------------------------
def _render_body(low, lic, stuck, days, hours) -> str:
    if not (low or lic or stuck):
        return "Nenhuma pendência no momento. ✅"

    lines = []
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
# Publicação (upsert no aviso + WhatsApp)
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
            total = len(low) + len(lic) + len(stuck)
            body = _render_body(low, lic, stuck, days, hours)
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

            _maybe_whatsapp(total, low, lic, stuck, hours)
            return total
        except Exception:  # noqa: BLE001
            db.session.rollback()
            return -1


def _maybe_whatsapp(total, low, lic, stuck, hours):
    """Envia o digest à TI no máximo uma vez por dia (quando há pendências)."""
    global _last_wpp_date
    if total <= 0:
        return
    today = date.today()
    if _last_wpp_date == today:
        return
    _last_wpp_date = today
    try:
        whatsapp.notify_ti(
            "🔔 *InvenSync — alertas do dia*\n"
            f"📦 Estoque no mínimo: {len(low)}\n"
            f"📅 Licenças/garantias: {len(lic)}\n"
            f"🎫 Chamados parados (>{hours}h): {len(stuck)}\n"
            "Veja os detalhes na Central de Avisos."
        )
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Agendador em background
# ---------------------------------------------------------------------------
def start_scheduler(app):
    """Thread daemon que publica os alertas a cada ALERTS_INTERVAL_HOURS horas."""
    global _started
    # Sob o reloader do Flask (debug), só roda no processo filho real.
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return
    with _lock:
        if _started:
            return
        _started = True

    interval = int(app.config.get("ALERTS_INTERVAL_HOURS", 6) or 6) * 3600

    def loop():
        time.sleep(25)  # deixa o servidor subir antes da 1ª rodada
        while True:
            try:
                publish(app)
            except Exception:  # noqa: BLE001
                pass
            time.sleep(interval)

    threading.Thread(target=loop, daemon=True, name="alerts").start()
    try:
        app.logger.info("Alertas proativos iniciados (intervalo=%sh).", interval // 3600)
    except Exception:  # noqa: BLE001
        pass
