# inventory/routes/dev.py — módulo DEV (backlog/sprints/board estilo Monday), admin/dev
from flask import (Blueprint, render_template, request, redirect, url_for, flash, abort,
                   jsonify)
from flask_login import login_required, current_user

from ..extensions import db
from ..repositories import dev_repo
from ..forms.dev import (DevTaskForm, DevSprintForm, STATUS_CHOICES, PRIORITY_CHOICES)
from ..models.dev import DevTask, DevSprint
from ..models.user import User
from ..services import audit

bp = Blueprint("dev", __name__)

STATUS_META = dict(STATUS_CHOICES)          # slug -> label
PRIORITY_META = dict(PRIORITY_CHOICES)


@bp.before_request
@login_required
def _only_admin():
    if not current_user.is_admin:
        abort(403)


def _assignee_choices():
    users = (User.query.filter_by(is_active=True)
             .order_by(User.name.asc()).all())
    return [(0, "— ninguém —")] + [(u.id, u.name) for u in users if (u.name or "").strip()]


def _sprint_choices():
    return [(0, "— sem sprint (backlog) —")] + [
        (s.id, s.name) for s in dev_repo.active_sprints()]


def _fill_choices(form, task=None):
    form.assignee_id.choices = _assignee_choices()
    form.sprint_id.choices = _sprint_choices()
    # garante que o item atual apareça mesmo se a sprint já foi concluída
    if task is not None and task.sprint_id and task.sprint_id not in [c[0] for c in form.sprint_id.choices]:
        form.sprint_id.choices.append((task.sprint_id, task.sprint.name if task.sprint else "sprint"))


def _task_kwargs(form):
    def s(v):
        v = (v or "").strip()
        return v or None
    return dict(
        title=(form.title.data or "").strip(),
        description=s(form.description.data),
        status=form.status.data or "backlog",
        priority=form.priority.data or "media",
        sprint_id=(form.sprint_id.data or None),
        assignee_id=(form.assignee_id.data or None),
        tags=s(form.tags.data),
        code_ref=s(form.code_ref.data),
    )


# ----- Painel -----
@bp.route("")
def index():
    """Painel do modulo: atalhos + analises do que foi lancado no board."""
    return render_template("dev/index.html", st=dev_repo.estatisticas(),
                           status_meta=STATUS_META, priority_meta=PRIORITY_META,
                           sprints=dev_repo.list_sprints())


# ----- Board -----
@bp.route("/board")
def board():
    q = (request.args.get("q") or "").strip()
    sprint = (request.args.get("sprint") or "").strip()   # '', 'backlog' ou id
    sprint_id = "backlog" if sprint == "backlog" else (int(sprint) if sprint.isdigit() else None)
    cols = dev_repo.board(sprint_id=sprint_id, q=q or None)
    totais = {s: len(v) for s, v in cols.items()}
    return render_template("dev/board.html", cols=cols, totais=totais,
                           statuses=STATUS_CHOICES, status_meta=STATUS_META,
                           priority_meta=PRIORITY_META, sprints=dev_repo.list_sprints(),
                           sprint_sel=sprint, q=q,
                           total=sum(totais.values()))


# ----- Tarefas -----
@bp.route("/task/new", methods=["GET", "POST"])
def task_new():
    form = DevTaskForm()
    _fill_choices(form)
    if request.method == "GET":
        form.status.data = request.args.get("status") or "backlog"
        sp = request.args.get("sprint")
        if sp and sp.isdigit():
            form.sprint_id.data = int(sp)
    if form.validate_on_submit():
        t = dev_repo.create_task(created_by_id=current_user.id, **_task_kwargs(form))
        audit.record("create", "dev_task", t.id, f"Criou tarefa DEV '{t.title}'")
        flash("Tarefa criada!", "success")
        return redirect(url_for("dev.task_detail", tid=t.id))
    return render_template("dev/task_form.html", form=form, title="Nova Tarefa")


@bp.route("/task/<int:tid>/edit", methods=["GET", "POST"])
def task_edit(tid):
    t = dev_repo.get_task(tid)
    form = DevTaskForm(obj=t)
    _fill_choices(form, t)
    if form.validate_on_submit():
        dev_repo.update_task(t, **_task_kwargs(form))
        audit.record("update", "dev_task", t.id, f"Editou tarefa DEV '{t.title}'")
        flash("Tarefa atualizada!", "success")
        return redirect(url_for("dev.task_detail", tid=t.id))
    return render_template("dev/task_form.html", form=form, title="Editar Tarefa", task=t)


@bp.route("/task/<int:tid>")
def task_detail(tid):
    t = dev_repo.get_task(tid)
    return render_template("dev/task.html", t=t, status_meta=STATUS_META,
                           priority_meta=PRIORITY_META, statuses=STATUS_CHOICES)


@bp.route("/task/<int:tid>/move", methods=["POST"])
def task_move(tid):
    t = dev_repo.get_task(tid)
    dev_repo.move_task(t, (request.form.get("status") or "").strip())
    # arrastar-e-soltar no board: responde JSON em vez de re-renderizar a pagina
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify(ok=True, status=t.status)
    if request.form.get("next"):
        return redirect(request.form.get("next"))
    return redirect(url_for("dev.board", sprint=request.form.get("sprint") or ""))


@bp.route("/task/<int:tid>/update", methods=["POST"])
def task_update(tid):
    t = dev_repo.get_task(tid)
    body = (request.form.get("body") or "").strip()
    code_ref = (request.form.get("code_ref") or "").strip() or None
    if not body and not code_ref:
        flash("Escreva algo ou informe o commit/PR.", "warning")
    else:
        dev_repo.add_update(t, current_user.id, body or "(sem texto)", code_ref)
        audit.record("update", "dev_task", t.id, f"Atualizou tarefa DEV '{t.title}'")
        flash("Atualização registrada.", "success")
    return redirect(url_for("dev.task_detail", tid=t.id))


@bp.route("/task/<int:tid>/delete", methods=["POST"])
def task_delete(tid):
    t = dev_repo.get_task(tid)
    audit.record("delete", "dev_task", t.id, f"Excluiu tarefa DEV '{t.title}'")
    dev_repo.delete_task(t)
    flash("Tarefa excluída.", "success")
    return redirect(url_for("dev.board"))


# ----- Sprints -----
@bp.route("/sprints")
def sprints():
    return render_template("dev/sprints.html", sprints=dev_repo.list_sprints())


@bp.route("/sprints/new", methods=["GET", "POST"])
def sprint_new():
    form = DevSprintForm()
    if form.validate_on_submit():
        s = dev_repo.create_sprint(name=(form.name.data or "").strip(),
                                   goal=(form.goal.data or "").strip() or None,
                                   start_date=form.start_date.data, end_date=form.end_date.data,
                                   status=form.status.data or "planejada")
        audit.record("create", "dev_sprint", s.id, f"Criou sprint '{s.name}'")
        flash("Sprint criada!", "success")
        return redirect(url_for("dev.sprints"))
    return render_template("dev/sprint_form.html", form=form, title="Nova Sprint")


@bp.route("/sprints/<int:sid>/edit", methods=["GET", "POST"])
def sprint_edit(sid):
    s = dev_repo.get_sprint(sid)
    form = DevSprintForm(obj=s)
    if form.validate_on_submit():
        dev_repo.update_sprint(s, name=(form.name.data or "").strip(),
                               goal=(form.goal.data or "").strip() or None,
                               start_date=form.start_date.data, end_date=form.end_date.data,
                               status=form.status.data or "planejada")
        flash("Sprint atualizada!", "success")
        return redirect(url_for("dev.sprints"))
    return render_template("dev/sprint_form.html", form=form, title="Editar Sprint", sprint=s)


@bp.route("/sprints/<int:sid>/delete", methods=["POST"])
def sprint_delete(sid):
    s = dev_repo.get_sprint(sid)
    audit.record("delete", "dev_sprint", s.id, f"Excluiu sprint '{s.name}'")
    dev_repo.delete_sprint(s)
    flash("Sprint excluída (tarefas foram para o backlog).", "success")
    return redirect(url_for("dev.sprints"))
