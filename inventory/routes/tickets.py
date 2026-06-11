# inventory/routes/tickets.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func

from ..extensions import db
from ..repositories import ticket_repo
from ..forms.tickets import TicketForm, CommentForm
from ..models.ticket import Ticket
from ..models.user import User
from ..models.machine import Machine

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


def _populate(form: TicketForm):
    users = User.query.filter_by(is_active=True).order_by(User.name).all()
    form.assigned_to_id.choices = [(0, "— Não atribuído —")] + [(u.id, u.name) for u in users]
    machines = Machine.query.order_by(Machine.assigned_user.asc().nullslast(),
                                      Machine.model.asc()).all()
    form.machine_id.choices = [(0, "— Nenhuma —")] + [(m.id, _machine_label(m)) for m in machines]


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

    counts = dict(db.session.query(Ticket.status, func.count(Ticket.id))
                  .group_by(Ticket.status).all())
    totals = {
        "aberto": counts.get("aberto", 0),
        "em_andamento": counts.get("em_andamento", 0),
        "resolvido": counts.get("resolvido", 0),
        "cancelado": counts.get("cancelado", 0),
        "total": sum(counts.values()),
    }
    return render_template("tickets/list.html", items=items, q=q, status=status,
                           priority=priority, totals=totals)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    form = TicketForm()
    _populate(form)
    if request.method == "GET":
        form.status.data = "aberto"
        form.priority.data = "media"
        form.assigned_to_id.data = current_user.id   # por padrão, quem está registrando
    if form.validate_on_submit():
        t = ticket_repo.create_ticket(opened_by_id=current_user.id, **_to_kwargs(form))
        flash(f"Chamado {t.code} criado!", "success")
        return redirect(url_for("tickets.detail", tid=t.id))
    return render_template("tickets/form.html", form=form, title="Novo Chamado",
                           machines_info=_machines_info())


@bp.route("/<int:tid>")
@login_required
def detail(tid):
    t = ticket_repo.get_ticket(tid)
    comment_form = CommentForm()
    return render_template("tickets/detail.html", t=t, comment_form=comment_form)


@bp.route("/<int:tid>/comment", methods=["POST"])
@login_required
def comment(tid):
    t = ticket_repo.get_ticket(tid)
    form = CommentForm()
    if form.validate_on_submit():
        ticket_repo.add_comment(t, body=form.body.data.strip(),
                                author_id=current_user.id,
                                new_status=form.new_status.data or None)
        flash("Andamento adicionado.", "success")
    else:
        flash("Escreva o andamento antes de enviar.", "warning")
    return redirect(url_for("tickets.detail", tid=t.id))


@bp.route("/<int:tid>/edit", methods=["GET", "POST"])
@login_required
def edit(tid):
    t = ticket_repo.get_ticket(tid)
    form = TicketForm(obj=t)
    _populate(form)
    if request.method == "GET":
        form.assigned_to_id.data = t.assigned_to_id or 0
        form.machine_id.data = t.machine_id or 0
    if form.validate_on_submit():
        ticket_repo.update_ticket(t, **_to_kwargs(form))
        flash("Chamado atualizado!", "success")
        return redirect(url_for("tickets.detail", tid=t.id))
    return render_template("tickets/form.html", form=form, title=f"Editar {t.code}",
                           machines_info=_machines_info())


@bp.route("/<int:tid>/delete", methods=["POST"])
@login_required
def delete(tid):
    t = ticket_repo.get_ticket(tid)
    ticket_repo.delete_ticket(t)
    flash("Chamado excluído.", "success")
    return redirect(url_for("tickets.list_view"))
