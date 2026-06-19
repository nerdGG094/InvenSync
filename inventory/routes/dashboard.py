# inventory/routes/dashboard.py
from datetime import date, timedelta

from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy import func

from ..repositories.product_repo import list_products, current_stock
from ..services.inventory_service import low_stock_products
from ..extensions import db
from ..models.movement import StockMovement
from ..models.product import Product
from ..models.user import User
from ..models.machine import Machine
from ..models.ticket import Ticket
from ..models.mobile import MobileDevice
from ..models.router import Router
from ..models.license import License
from ..models.domain import Domain
from ..models.credential import Credential
from ..models.kb import KbArticle
from ..models.machine_cleaning import MachineCleaning
from ..models.audit import AuditLog

bp = Blueprint("dashboard", __name__)


def _safe_count(model):
    """Contagem tolerante a tabelas ainda inexistentes (módulo recém-criado)."""
    try:
        return int(db.session.query(func.count(model.id)).scalar() or 0)
    except Exception:
        db.session.rollback()
        return 0


@bp.route("/")
@login_required
def index():
    # ===== Produtos / Estoque geral =====
    products = list_products() or []
    total_items = sum(max(current_stock(p) or 0, 0) for p in products)
    low = low_stock_products(products) or []

    # ===== Métricas para gráficos de Baixo Estoque =====
    def metrics(p):
        estoque = int(current_stock(p) or 0)
        minimo = int(p.min_stock or 0)
        pct = (estoque / minimo * 100.0) if minimo > 0 and estoque > 0 else 0.0
        return {"sku": p.sku, "name": p.name, "estoque": estoque, "minimo": minimo, "pct": pct}

    low_metrics = [metrics(p) for p in low]
    zero_count = sum(1 for m in low_metrics if m["estoque"] <= 0)
    below_count = sum(1 for m in low_metrics if m["estoque"] > 0 and m["estoque"] < m["minimo"])
    top10_criticos = sorted(low_metrics, key=lambda m: m["pct"])[:10]

    chart_data = {
        "labels": [f'{m["sku"]} - {m["name"]}' for m in top10_criticos],
        "estoque": [m["estoque"] for m in top10_criticos],
        "minimo": [m["minimo"] for m in top10_criticos],
        "zeroCount": zero_count,
        "belowCount": below_count,
    }

    # ===== Top 10 Itens mais movimentados (soma de quantidades IN+OUT) =====
    rows_items = (
        db.session.query(
            Product.sku,
            Product.name,
            func.sum(StockMovement.quantity).label("qty"),
        )
        .join(StockMovement, StockMovement.product_id == Product.id)
        .group_by(Product.id)
        .order_by(func.sum(StockMovement.quantity).desc())
        .limit(10)
        .all()
    )
    top_items_data = {
        "labels": [f"{sku} - {name}" for sku, name, _ in rows_items],
        "data": [int(qty or 0) for _, _, qty in rows_items],
    }

    # ===== Top 10 Usuários que mais movimentaram =====
    rows_users = (
        db.session.query(
            User.name,
            func.count(StockMovement.id).label("movs"),
            func.sum(StockMovement.quantity).label("qty"),
        )
        .join(StockMovement, StockMovement.user_id == User.id)
        .group_by(User.id)
        .order_by(func.sum(StockMovement.quantity).desc())
        .limit(10)
        .all()
    )
    top_users_data = {
        "labels": [name or "—" for name, _, _ in rows_users],
        "qty": [int(qty or 0) for _, _, qty in rows_users],
        "movs": [int(movs or 0) for _, movs, _ in rows_users],
    }

    # ===================================================================
    # ===== NOVO: Visão geral de TI (Ativos, Chamados, Vencimentos) =====
    # ===================================================================
    today = date.today()
    soon = today + timedelta(days=60)

    # ----- Cards de contagem -----
    counts = {
        "machines": _safe_count(Machine),
        "machines_active": 0,
        "tickets_open": 0,
        "mobiles": _safe_count(MobileDevice),
        "routers": _safe_count(Router),
        "colaboradores": _safe_count(User),
        "credentials": _safe_count(Credential),
        "kb": _safe_count(KbArticle),
        "licenses": _safe_count(License),
        "domains": _safe_count(Domain),
    }

    try:
        counts["machines_active"] = int(
            db.session.query(func.count(Machine.id))
            .filter(Machine.is_active.is_(True)).scalar() or 0
        )
    except Exception:
        db.session.rollback()

    # Chamados abertos = tudo que não está resolvido/fechado
    try:
        counts["tickets_open"] = int(
            db.session.query(func.count(Ticket.id))
            .filter(~Ticket.status.in_(["resolvido", "fechado"])).scalar() or 0
        )
    except Exception:
        db.session.rollback()

    # ----- Chamados por status (rosca) -----
    tickets_status = {"labels": [], "data": []}
    try:
        rows = (
            db.session.query(Ticket.status, func.count(Ticket.id))
            .group_by(Ticket.status)
            .order_by(func.count(Ticket.id).desc())
            .all()
        )
        tickets_status["labels"] = [s or "—" for s, _ in rows]
        tickets_status["data"] = [int(c or 0) for _, c in rows]
    except Exception:
        db.session.rollback()

    # ----- Chamados por prioridade (barras) -----
    tickets_priority = {"labels": [], "data": []}
    try:
        order = {"critica": 0, "alta": 1, "media": 2, "baixa": 3}
        rows = (
            db.session.query(Ticket.priority, func.count(Ticket.id))
            .filter(~Ticket.status.in_(["resolvido", "fechado"]))
            .group_by(Ticket.priority)
            .all()
        )
        rows = sorted(rows, key=lambda r: order.get((r[0] or "").lower(), 99))
        tickets_priority["labels"] = [p or "—" for p, _ in rows]
        tickets_priority["data"] = [int(c or 0) for _, c in rows]
    except Exception:
        db.session.rollback()

    # ----- Máquinas por tipo (rosca) -----
    machines_kind = {"labels": [], "data": []}
    try:
        rows = (
            db.session.query(Machine.kind, func.count(Machine.id))
            .group_by(Machine.kind)
            .order_by(func.count(Machine.id).desc())
            .all()
        )
        machines_kind["labels"] = [k or "—" for k, _ in rows]
        machines_kind["data"] = [int(c or 0) for _, c in rows]
    except Exception:
        db.session.rollback()

    # ----- Celulares por status (barras) -----
    mobiles_status = {"labels": [], "data": []}
    try:
        rows = (
            db.session.query(MobileDevice.status, func.count(MobileDevice.id))
            .group_by(MobileDevice.status)
            .order_by(func.count(MobileDevice.id).desc())
            .all()
        )
        mobiles_status["labels"] = [s or "—" for s, _ in rows]
        mobiles_status["data"] = [int(c or 0) for _, c in rows]
    except Exception:
        db.session.rollback()

    # ----- Licenças e domínios a vencer (próximos 60 dias ou já vencidos) -----
    expiring = []  # cada item: {tipo, name, info, expiry, days, status}
    try:
        for lic in (
            db.session.query(License)
            .filter(License.expiry_date.isnot(None), License.expiry_date <= soon)
            .order_by(License.expiry_date.asc())
            .limit(20)
            .all()
        ):
            expiring.append({
                "tipo": "Licença", "name": lic.name, "info": lic.vendor or lic.kind,
                "expiry": lic.expiry_date, "days": lic.days_left, "status": lic.status,
            })
    except Exception:
        db.session.rollback()
    try:
        for dom in (
            db.session.query(Domain)
            .filter(Domain.expiry_date.isnot(None), Domain.expiry_date <= soon)
            .order_by(Domain.expiry_date.asc())
            .limit(20)
            .all()
        ):
            expiring.append({
                "tipo": "Domínio", "name": dom.name, "info": dom.company or dom.registrar,
                "expiry": dom.expiry_date, "days": dom.days_left, "status": dom.status,
            })
    except Exception:
        db.session.rollback()
    expiring.sort(key=lambda e: e["expiry"])
    expiring = expiring[:12]
    expiring_count = len(expiring)

    # ----- Limpezas de máquinas atrasadas (next_date < hoje) -----
    cleanings_due = 0
    try:
        cleanings_due = int(
            db.session.query(func.count(MachineCleaning.id))
            .filter(MachineCleaning.next_date.isnot(None),
                    MachineCleaning.next_date < today).scalar() or 0
        )
    except Exception:
        db.session.rollback()

    # ----- Máquinas mais próximas da próxima limpeza -----
    # Para cada máquina, o "next_date" que vale é o do registro de limpeza
    # mais recente (o último a ser feito agenda a próxima). Pegamos o mais
    # recente por máquina e ordenamos pela data mais próxima.
    cleanings_next = []
    try:
        rows = (
            db.session.query(MachineCleaning, Machine)
            .join(Machine, Machine.id == MachineCleaning.machine_id)
            .filter(MachineCleaning.next_date.isnot(None))
            .order_by(MachineCleaning.started_at.desc().nullslast(),
                      MachineCleaning.id.desc())
            .all()
        )
        seen = set()
        for cln, mac in rows:
            if mac.id in seen:
                continue
            seen.add(mac.id)
            days = (cln.next_date - today).days
            cleanings_next.append({
                "machine_id": mac.id,
                "machine": mac.model or mac.name or f"#{mac.id}",
                "kind": mac.kind,
                "user": mac.assigned_user,
                "sector": mac.sector,
                "period_days": cln.period_days,
                "next_date": cln.next_date,
                "days": days,
                "overdue": days < 0,
                "executed_by": cln.executed_by,
            })
        cleanings_next.sort(key=lambda c: c["next_date"])
        cleanings_next = cleanings_next[:8]
    except Exception:
        db.session.rollback()

    # ----- Atividade recente (trilha de auditoria) -----
    recent_audit = []
    try:
        recent_audit = (
            db.session.query(AuditLog)
            .order_by(AuditLog.created_at.desc())
            .limit(8)
            .all()
        )
    except Exception:
        db.session.rollback()

    it_overview = {
        "counts": counts,
        "tickets_status": tickets_status,
        "tickets_priority": tickets_priority,
        "machines_kind": machines_kind,
        "mobiles_status": mobiles_status,
        "expiring": expiring,
        "expiring_count": expiring_count,
        "cleanings_due": cleanings_due,
        "cleanings_next": cleanings_next,
    }

    return render_template(
        "dashboard.html",
        low_stock=low,
        total_items=int(total_items),
        total_products=len(products),
        current_stock=current_stock,
        chart_data=chart_data,
        top_items_data=top_items_data,
        top_users_data=top_users_data,
        it=it_overview,
        recent_audit=recent_audit,
    )
