# inventory/routes/tickets.py
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func

from ..extensions import db
from ..repositories import ticket_repo
from ..forms.tickets import (TicketForm, CommentForm, STATUS_CHOICES,
                             CATEGORY_CHOICES, PRIORITY_CHOICES)
from ..models.ticket import Ticket
from ..models.user import User
from ..models.machine import Machine
from ..services import people, whatsapp, audit

STATUS_LABELS = dict(STATUS_CHOICES)

bp = Blueprint("tickets", __name__)


KIND_LABELS = {"computador": "Computador", "notebook": "Notebook", "impressora": "Impressora"}


def _machine_label(m: Machine) -> str:
    # Lidera pelo usuário (depois modelo e tipo), para facilitar a escolha.
    user = m.assigned_user or "s/ usuário"
    return f"{user} · {m.model or '—'} · {KIND_LABELS.get(m.kind, m.kind)}"


def _machines_info() -> dict:
    """Dados das máquinas para auto-preencher o chamado ao selecionar."""
    info = {}
    for m in Machine.query.all():
        info[m.id] = {
            "user": m.assigned_user or "",
            "sector": m.sector or "",
            "ip": m.ip_address or "",
            "model": m.model or "",
            "kind": KIND_LABELS.get(m.kind, m.kind),
        }
    return info


def _users_info() -> dict:
    """Mapa usuário (cadastrado em Máquinas) -> setor."""
    return people.users_sector_map()


def _populate(form: TicketForm):
    users = User.query.filter_by(is_active=True).order_by(User.name).all()
    form.assigned_to_id.choices = [(0, "— Não atribuído —")] + [(u.id, u.name) for u in users]
    machines = Machine.query.order_by(Machine.assigned_user.asc().nullslast(),
                                      Machine.model.asc()).all()
    form.machine_id.choices = [(0, "— Nenhuma —")] + [(m.id, _machine_label(m)) for m in machines]
    form.requester.choices = people.user_choices()


def _to_kwargs(form: TicketForm) -> dict:
    def s(v):
        v = (v or "").strip()
        return v or None
    return dict(
        title=(form.title.data or "").strip(),
        description=s(form.description.data),
        requester=s(form.requester.data),
        sector=s(form.sector.data),
        category=form.category.data or "outro",
        priority=form.priority.data or "media",
        status=form.status.data or "aberto",
        assigned_to_id=form.assigned_to_id.data or None,
        machine_id=form.machine_id.data or None,
        resolution=s(form.resolution.data),
    )


@bp.route("")
@login_required
def list_view():
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    priority = (request.args.get("priority") or "").strip()
    items = ticket_repo.list_tickets(q or None, status or None, priority or None)

    cnt = db.session.query(Ticket.status, func.count(Ticket.id))
    # Usuário comum só vê os próprios chamados
    if not current_user.is_admin:
        items = [t for t in items if t.opened_by_id == current_user.id]
        cnt = cnt.filter(Ticket.opened_by_id == current_user.id)
    counts = dict(cnt.group_by(Ticket.status).all())
    totals = {
        "aberto": counts.get("aberto", 0),
        "em_andamento": counts.get("em_andamento", 0),
        "resolvido": counts.get("resolvido", 0),
        "cancelado": counts.get("cancelado", 0),
        "total": sum(counts.values()),
    }
    return render_template("tickets/list.html", items=items, q=q, status=status,
                           priority=priority, totals=totals, is_admin=current_user.is_admin)


@bp.route("/painel")
@login_required
def dashboard():
    """Painel de indicadores de chamados (somente equipe de TI)."""
    if not current_user.is_admin:
        abort(403)

    cat_labels = dict(CATEGORY_CHOICES)
    prio_labels = dict(PRIORITY_CHOICES)
    status_labels = dict(STATUS_CHOICES)

    all_tickets = Ticket.query.all()
    open_statuses = ("aberto", "em_andamento")

    counts = {"aberto": 0, "em_andamento": 0, "resolvido": 0, "cancelado": 0}
    for t in all_tickets:
        if t.status in counts:
            counts[t.status] += 1
    counts["total"] = len(all_tickets)
    counts["abertos_total"] = counts["aberto"] + counts["em_andamento"]

    # SLA simples por prioridade (horas até considerar "atrasado")
    sla_hours = {"urgente": 4, "alta": 24, "media": 48, "baixa": 120}
    now = datetime.now()
    overdue = []
    for t in all_tickets:
        if t.status in open_statuses and t.created_at:
            limite = sla_hours.get(t.priority, 48)
            idade_h = (now - t.created_at).total_seconds() / 3600.0
            if idade_h > limite:
                overdue.append((t, idade_h, limite))
    overdue.sort(key=lambda x: x[1] - x[2], reverse=True)

    # Tempo médio de resolução (horas) dos resolvidos
    durations = [
        (t.resolved_at - t.created_at).total_seconds() / 3600.0
        for t in all_tickets
        if t.status == "resolvido" and t.resolved_at and t.created_at
    ]
    avg_resolution_h = round(sum(durations) / len(durations), 1) if durations else None

    # Distribuições (entre abertos/em andamento)
    by_category, by_priority, by_assignee = {}, {}, {}
    for t in all_tickets:
        if t.status in open_statuses:
            by_category[t.category] = by_category.get(t.category, 0) + 1
            by_priority[t.priority] = by_priority.get(t.priority, 0) + 1
            nome = t.assigned_to.name if t.assigned_to else "— Não atribuído —"
            by_assignee[nome] = by_assignee.get(nome, 0) + 1

    cat_data = sorted(([cat_labels.get(k, k), v] for k, v in by_category.items()),
                      key=lambda x: x[1], reverse=True)
    prio_order = {"urgente": 0, "alta": 1, "media": 2, "baixa": 3}
    prio_data = sorted(([prio_labels.get(k, k), v, k] for k, v in by_priority.items()),
                       key=lambda x: prio_order.get(x[2], 9))
    assignee_data = sorted(([k, v] for k, v in by_assignee.items()),
                           key=lambda x: x[1], reverse=True)

    # Abertos nos últimos 14 dias
    since = now - timedelta(days=13)
    daily = {}
    for t in all_tickets:
        if t.created_at and t.created_at >= since.replace(hour=0, minute=0, second=0, microsecond=0):
            key = t.created_at.strftime("%d/%m")
            daily[key] = daily.get(key, 0) + 1
    trend_labels, trend_values = [], []
    for i in range(13, -1, -1):
        d = (now - timedelta(days=i)).strftime("%d/%m")
        trend_labels.append(d)
        trend_values.append(daily.get(d, 0))

    return render_template(
        "tickets/dashboard.html",
        counts=counts,
        overdue=overdue[:15],
        overdue_count=len(overdue),
        avg_resolution_h=avg_resolution_h,
        cat_data=cat_data,
        prio_data=prio_data,
        assignee_data=assignee_data,
        trend={"labels": trend_labels, "values": trend_values},
        status_labels=status_labels,
        prio_labels=prio_labels,
    )


@bp.route("/api/recent")
@login_required
def api_recent():
    """Polling de novos chamados — usado pela notificação da equipe de TI."""
    if not current_user.is_admin:
        return jsonify(tickets=[], latest_id=0, open_count=0)
    since = request.args.get("since_id", type=int) or 0
    open_count = Ticket.query.filter_by(status="aberto").count()
    recent = Ticket.query.order_by(Ticket.id.desc()).limit(10).all()
    latest_id = recent[0].id if recent else 0
    novos = [t for t in recent if t.id > since] if since else []
    return jsonify(
        latest_id=latest_id,
        open_count=open_count,
        tickets=[{
            "id": t.id,
            "code": t.code,
            "title": t.title,
            "requester": t.requester or "",
            "sector": t.sector or "",
            "priority": t.priority,
        } for t in novos],
    )


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    is_admin = current_user.is_admin
    form = TicketForm()
    _populate(form)
    if request.method == "GET":
        form.status.data = "aberto"
        form.priority.data = "media"
        if is_admin:
            form.assigned_to_id.data = current_user.id   # admin: atribui a si por padrão
    if form.validate_on_submit():
        data = _to_kwargs(form)
        if not is_admin:
            # Usuário comum abre em nome próprio; setor vem do seu cadastro
            data["requester"] = current_user.name
            data["sector"] = current_user.sector or None
            data["status"] = "aberto"
            data["assigned_to_id"] = None
            data["resolution"] = None
        t = ticket_repo.create_ticket(opened_by_id=current_user.id, **data)
        # Notifica a equipe de TI por WhatsApp (best-effort)
        whatsapp.notify_ti(
            f"🆕 *Novo chamado {t.code}*\n"
            f"Aberto por: {t.requester or current_user.name}"
            f"{(' · ' + t.sector) if t.sector else ''}\n"
            f"Prioridade: {t.priority}\n"
            f"{t.title}"
        )
        flash(f"Chamado {t.code} aberto!", "success")
        return redirect(url_for("tickets.detail", tid=t.id))
    return render_template("tickets/form.html", form=form, title="Novo Chamado",
                           machines_info=_machines_info(), users_info=_users_info(),
                           is_admin=is_admin)


@bp.route("/<int:tid>")
@login_required
def detail(tid):
    t = ticket_repo.get_ticket(tid)
    if not current_user.is_admin and t.opened_by_id != current_user.id:
        abort(403)
    comment_form = CommentForm()
    return render_template("tickets/detail.html", t=t, comment_form=comment_form,
                           is_admin=current_user.is_admin)


@bp.route("/<int:tid>/comment", methods=["POST"])
@login_required
def comment(tid):
    t = ticket_repo.get_ticket(tid)
    if not current_user.is_admin and t.opened_by_id != current_user.id:
        abort(403)
    form = CommentForm()
    if form.validate_on_submit():
        body = form.body.data.strip()
        # Usuário comum não muda status (só a equipe de TI)
        new_status = form.new_status.data if current_user.is_admin else None
        ticket_repo.add_comment(t, body=body, author_id=current_user.id,
                                new_status=new_status or None)
        # Notificações por WhatsApp (best-effort)
        if current_user.is_admin:
            whatsapp.notify_user(
                t.opened_by,
                f"🔔 *Chamado {t.code}* atualizado por {current_user.name}:\n{body}\n"
                f"Status: {STATUS_LABELS.get(t.status, t.status)}"
            )
        else:
            whatsapp.notify_ti(
                f"💬 *{t.requester or current_user.name}* respondeu no chamado {t.code}:\n{body}"
            )
        flash("Andamento adicionado.", "success")
    else:
        flash("Escreva o andamento antes de enviar.", "warning")
    return redirect(url_for("tickets.detail", tid=t.id))


@bp.route("/<int:tid>/edit", methods=["GET", "POST"])
@login_required
def edit(tid):
    if not current_user.is_admin:
        abort(403)
    t = ticket_repo.get_ticket(tid)
    form = TicketForm(obj=t)
    _populate(form)
    # Garante que o solicitante atual apareça no combobox, mesmo que a máquina
    # tenha sido removida/renomeada depois.
    if t.requester and t.requester not in [c[0] for c in form.requester.choices]:
        form.requester.choices.append((t.requester, t.requester))
    if request.method == "GET":
        form.assigned_to_id.data = t.assigned_to_id or 0
        form.machine_id.data = t.machine_id or 0
        form.requester.data = t.requester or ""
    if form.validate_on_submit():
        ticket_repo.update_ticket(t, **_to_kwargs(form))
        flash("Chamado atualizado!", "success")
        return redirect(url_for("tickets.detail", tid=t.id))
    return render_template("tickets/form.html", form=form, title=f"Editar {t.code}",
                           machines_info=_machines_info(), users_info=_users_info())


@bp.route("/<int:tid>/delete", methods=["POST"])
@login_required
def delete(tid):
    if not current_user.is_admin:
        abort(403)
    t = ticket_repo.get_ticket(tid)
    audit.record("delete", "ticket", t.id, f"Excluiu chamado {t.code} — {t.title}")
    ticket_repo.delete_ticket(t)
    flash("Chamado excluído.", "success")
    return redirect(url_for("tickets.list_view"))
