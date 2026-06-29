# inventory/routes/machines.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy import func

from ..extensions import db
from ..repositories import machine_repo
from ..forms.machines import MachineForm
from ..models.machine import Machine
from ..services import people, patrimony

bp = Blueprint("machines", __name__)


def _group_by_sector(items: list) -> list:
    """Agrupa máquinas por setor (alfabético; 'Sem setor' por último)."""
    grupos_map = {}
    for it in items:
        setor = (it.sector or "").strip()
        grupos_map.setdefault(setor, []).append(it)
    nomeados = sorted((s for s in grupos_map if s), key=lambda s: s.lower())
    ordem = nomeados + ([""] if "" in grupos_map else [])
    return [{"name": s or None, "items": grupos_map[s]} for s in ordem]


def _form_to_kwargs(form: MachineForm) -> dict:
    def s(v):
        v = (v or "").strip()
        return v or None
    # Setor automático: se ficou em branco, busca do cadastro do colaborador.
    sector = s(form.sector.data)
    if not sector and form.assigned_user.data:
        sector = people.sector_for(form.assigned_user.data) or None
    return dict(
        kind=form.kind.data or "computador",
        name=s(form.name.data),
        brand=s(form.brand.data),
        model=s(form.model.data),
        assigned_user=s(form.assigned_user.data),
        ip_address=s(form.ip_address.data),
        sector=sector,
        patrimony=s(form.patrimony.data),
        serial_number=s(form.serial_number.data),
        notes=s(form.notes.data),
        is_active=bool(form.is_active.data),
        label_applied=bool(form.label_applied.data),
    )


@bp.route("")
@login_required
def list_view():
    q = (request.args.get("q") or "").strip()
    kind = (request.args.get("kind") or "").strip()
    items = machine_repo.list_machines(q or None, kind or None)

    # Contagem por tipo (sobre toda a base, para os cartões)
    counts = dict(
        db.session.query(Machine.kind, func.count(Machine.id))
        .group_by(Machine.kind).all()
    )
    totals = {
        "computador": counts.get("computador", 0),
        "notebook": counts.get("notebook", 0),
        "impressora": counts.get("impressora", 0),
        "total": sum(counts.values()),
    }
    grupos = _group_by_sector(items)
    return render_template("machines/list.html", items=items, q=q, kind=kind,
                           totals=totals, grupos=grupos)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    form = MachineForm()
    form.assigned_user.choices = people.user_choices("— Selecione —")
    if request.method == "GET":
        if not form.kind.data:
            form.kind.data = request.args.get("kind") or "computador"
        # Sugere um nº de patrimônio automático (editável pelo usuário).
        if not form.patrimony.data:
            form.patrimony.data = patrimony.next_patrimony()
    if form.validate_on_submit():
        machine_repo.create_machine(**_form_to_kwargs(form))
        flash("Máquina cadastrada!", "success")
        return redirect(url_for("machines.list_view"))
    return render_template("machines/form.html", form=form, title="Nova Máquina",
                           users_info=people.users_sector_map())


@bp.route("/<int:mid>/edit", methods=["GET", "POST"])
@login_required
def edit(mid):
    m = machine_repo.get_machine(mid)
    form = MachineForm(obj=m)
    form.assigned_user.choices = people.user_choices("— Selecione —")
    # Garante que o responsável atual apareça mesmo se o colaborador foi removido/inativado.
    if m.assigned_user and m.assigned_user not in [c[0] for c in form.assigned_user.choices]:
        form.assigned_user.choices.append((m.assigned_user, m.assigned_user))
    if form.validate_on_submit():
        machine_repo.update_machine(m, **_form_to_kwargs(form))
        flash("Máquina atualizada!", "success")
        return redirect(url_for("machines.list_view"))
    return render_template("machines/form.html", form=form, title="Editar Máquina",
                           users_info=people.users_sector_map())


@bp.route("/<int:mid>/delete", methods=["POST"])
@login_required
def delete(mid):
    m = machine_repo.get_machine(mid)
    machine_repo.delete_machine(m)
    flash("Máquina excluída.", "success")
    return redirect(url_for("machines.list_view"))


@bp.route("/<int:mid>/historico")
@login_required
def history(mid):
    """Linha do tempo do ativo: cadastro, limpezas, manutenções e chamados."""
    from datetime import datetime, date, time as _time
    from ..models.machine_cleaning import MachineCleaning
    from ..models.machine_maintenance import MachineMaintenance
    from ..models.ticket import Ticket

    m = machine_repo.get_machine(mid)

    def _dt(v):
        # normaliza date -> datetime para ordenar junto com datetimes
        if isinstance(v, datetime):
            return v
        if isinstance(v, date):
            return datetime.combine(v, _time.min)
        return None

    ev = []
    if m.created_at:
        ev.append({"when": m.created_at, "icon": "bi-plus-circle", "color": "success",
                   "title": "Máquina cadastrada", "sub": m.model or m.name or ""})

    for c in MachineCleaning.query.filter_by(machine_id=mid).all():
        dm = c.duration_min
        dur = (f" · {dm} min" if dm is not None else "")
        ev.append({"when": _dt(c.started_at), "icon": "bi-droplet-half", "color": "info",
                   "title": "Limpeza", "sub": f"{c.executed_by or 'sem executor'}{dur}",
                   "link": url_for("cleanings.list_view", q=(m.model or ''))})

    kind_lbl = {"preventiva": "Preventiva", "corretiva": "Corretiva", "upgrade": "Upgrade",
                "formatacao": "Formatação", "troca_peca": "Troca de peça", "outro": "Outro"}
    for mt in MachineMaintenance.query.filter_by(machine_id=mid).all():
        custo = (f" · R$ {mt.cost:.2f}" if mt.cost is not None else "")
        ev.append({"when": _dt(mt.date), "icon": "bi-tools", "color": "warning",
                   "title": f"Manutenção — {kind_lbl.get(mt.kind, mt.kind)}",
                   "sub": (mt.description or "")[:140] + (f" · {mt.performed_by}" if mt.performed_by else "") + custo})

    for t in Ticket.query.filter_by(machine_id=mid).all():
        ev.append({"when": t.created_at, "icon": "bi-headset", "color": "primary",
                   "title": f"Chamado {t.code}", "sub": t.title,
                   "link": url_for("tickets.detail", tid=t.id),
                   "status": t.status})

    ev = [e for e in ev if e["when"] is not None]
    ev.sort(key=lambda e: e["when"], reverse=True)
    return render_template("machines/history.html", m=m, events=ev)
