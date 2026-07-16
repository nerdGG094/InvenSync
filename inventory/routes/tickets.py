# inventory/routes/tickets.py
import os
import time
from datetime import datetime, timedelta

from flask import (Blueprint, render_template, request, redirect, url_for, flash,
                   abort, jsonify, current_app, send_from_directory)
from flask_login import login_required, current_user
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from werkzeug.utils import secure_filename

from ..extensions import db
from ..repositories import ticket_repo
from ..models.ticket_attachment import TicketAttachment
from ..forms.tickets import (TicketForm, CommentForm, STATUS_CHOICES,
                             CATEGORY_CHOICES, PRIORITY_CHOICES)
from ..models.ticket import Ticket
from ..models.user import User
from ..services import people, audit, mailer
from ..services.exports import xlsx_response

STATUS_LABELS = dict(STATUS_CHOICES)

bp = Blueprint("tickets", __name__)


def _users_info() -> dict:
    """Mapa usuário (cadastrado em Máquinas) -> setor."""
    return people.users_sector_map()


def _is_requester(user, t) -> bool:
    """É o solicitante do chamado? Casado por ID ESTÁVEL (nunca pelo nome, que o
    usuário edita livremente no perfil). Sem solicitante vinculado, só quem abriu
    (e apenas se não há um nome de solicitante de terceiro). Quem avalia o CSAT."""
    if t.requester_id:
        return t.requester_id == user.id
    return t.opened_by_id == user.id and not (t.requester or "").strip()


def _is_participant(user, t) -> bool:
    """Não-admin pode ver/comentar o chamado se o abriu OU é o solicitante."""
    return t.opened_by_id == user.id or _is_requester(user, t)


def _requester_user(t):
    """Usuário a notificar sobre o chamado: o solicitante (por id vinculado).
    Cai para quem registrou quando não há solicitante identificável."""
    if t.requester_id:
        return t.requester_user
    return t.opened_by if not (t.requester or "").strip() else None


def _period_range(args):
    """Interpreta os parâmetros de período (hoje/7/30/todos/custom) → intervalo
    de datas. Compartilhado entre a lista e a exportação Excel."""
    period = (args.get("period") or "hoje").strip()
    date_from_s = (args.get("from") or "").strip()
    date_to_s = (args.get("to") or "").strip()
    date_from = date_to = None
    today = datetime.now().date()
    if period == "custom":
        try:
            date_from = datetime.strptime(date_from_s, "%Y-%m-%d") if date_from_s else None
        except ValueError:
            date_from = None
        try:
            date_to = (datetime.strptime(date_to_s, "%Y-%m-%d") + timedelta(days=1)
                       - timedelta(seconds=1)) if date_to_s else None
        except ValueError:
            date_to = None
        if not date_from and not date_to:
            period = "todos"
    elif period == "7":
        date_from = datetime.combine(today - timedelta(days=6), datetime.min.time())
    elif period == "30":
        date_from = datetime.combine(today - timedelta(days=29), datetime.min.time())
    elif period == "todos":
        pass
    else:
        period = "hoje"
        date_from = datetime.combine(today, datetime.min.time())
    return period, date_from, date_to, date_from_s, date_to_s


def _populate(form: TicketForm):
    # Responsáveis (atendentes): apenas o time de TI — usuários do departamento
    # "Tecnologia" com login ativo. São eles que atendem os chamados.
    users = (User.query
             .filter_by(is_active=True, can_login=True)
             .filter(db.func.lower(User.sector) == "tecnologia")
             .order_by(User.name).all())
    form.assigned_to_id.choices = [(0, "— Não atribuído —")] + [(u.id, u.name) for u in users]
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
        resolution=s(form.resolution.data),
    )


@bp.route("")
@login_required
def list_view():
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    priority = (request.args.get("priority") or "").strip()
    sla = (request.args.get("sla") or "").strip()   # 'late' = só os que estouraram o SLA
    period, date_from, date_to, date_from_s, date_to_s = _period_range(request.args)

    # Sem filtro de status, pendentes (aberto/em andamento) aparecem sempre,
    # mesmo fora do período — para nada em aberto sumir da lista.
    items = ticket_repo.list_tickets(q or None, status or None, priority or None,
                                     date_from=date_from, date_to=date_to,
                                     include_open_always=not status)

    cnt = db.session.query(Ticket.status, func.count(Ticket.id))
    # Usuário comum vê os que abriu E aqueles em que é o solicitante (por nome).
    if not current_user.is_admin:
        items = [t for t in items if _is_participant(current_user, t)]
        cnt = cnt.filter(db.or_(Ticket.opened_by_id == current_user.id,
                                Ticket.requester_id == current_user.id))
    counts = dict(cnt.group_by(Ticket.status).all())
    totals = {
        "aberto": counts.get("aberto", 0),
        "em_andamento": counts.get("em_andamento", 0),
        "resolvido": counts.get("resolvido", 0),
        "cancelado": counts.get("cancelado", 0),
        "total": sum(counts.values()),
    }

    # SLA: total de atrasados (sobre os abertos do escopo) + filtro opcional.
    open_q = Ticket.query.filter(Ticket.status.in_(("aberto", "em_andamento")))
    if not current_user.is_admin:
        open_q = open_q.filter(db.or_(Ticket.opened_by_id == current_user.id,
                                      Ticket.requester_id == current_user.id))
    overdue_total = sum(1 for t in open_q.all() if t.sla_overdue)
    if sla == "late":
        items = [t for t in items if t.sla_overdue]

    return render_template("tickets/list.html", items=items, q=q, status=status,
                           priority=priority, sla=sla, period=period, date_from=date_from_s,
                           date_to=date_to_s, totals=totals, overdue_total=overdue_total,
                           is_admin=current_user.is_admin)


@bp.route("/export")
@login_required
def export():
    if not current_user.is_admin:
        abort(403)
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    priority = (request.args.get("priority") or "").strip()
    # Respeita o mesmo período da tela (senão o Excel exporta tudo e diverge).
    _p, date_from, date_to, _f, _t = _period_range(request.args)
    items = ticket_repo.list_tickets(q or None, status or None, priority or None,
                                     date_from=date_from, date_to=date_to)
    cat_lbl = dict(CATEGORY_CHOICES)
    prio_lbl = dict(PRIORITY_CHOICES)
    status_lbl = dict(STATUS_CHOICES)
    headers = ["Código", "Título", "Solicitante", "Setor", "Categoria", "Prioridade",
               "Status", "Responsável", "Criado em", "Resolvido em"]
    rows = []
    for t in items:
        rows.append([
            t.code, t.title, t.requester or "", t.sector or "",
            cat_lbl.get(t.category, t.category), prio_lbl.get(t.priority, t.priority),
            status_lbl.get(t.status, t.status),
            t.assigned_to.name if t.assigned_to else "",
            t.created_at.strftime("%d/%m/%Y %H:%M") if t.created_at else "",
            t.resolved_at.strftime("%d/%m/%Y %H:%M") if t.resolved_at else "",
        ])
    audit.record("export", "ticket", None, f"Exportou {len(rows)} chamado(s) para Excel")
    return xlsx_response("Chamados", headers, rows, filename="chamados")


@bp.route("/painel")
@login_required
def dashboard():
    """Painel de indicadores de chamados (somente equipe de TI)."""
    if not current_user.is_admin:
        abort(403)

    cat_labels = dict(CATEGORY_CHOICES)
    prio_labels = dict(PRIORITY_CHOICES)
    status_labels = dict(STATUS_CHOICES)

    # joinedload evita N+1: o loop de distribuição lê t.assigned_to.name.
    all_tickets = Ticket.query.options(joinedload(Ticket.assigned_to)).all()
    open_statuses = ("aberto", "em_andamento")

    counts = {"aberto": 0, "em_andamento": 0, "resolvido": 0, "cancelado": 0}
    for t in all_tickets:
        if t.status in counts:
            counts[t.status] += 1
    counts["total"] = len(all_tickets)
    counts["abertos_total"] = counts["aberto"] + counts["em_andamento"]

    # SLA por prioridade — centralizado no modelo (Ticket.sla_*).
    now = datetime.now()
    overdue = []
    for t in all_tickets:
        if t.sla_overdue:
            idade_h = (now - t.created_at).total_seconds() / 3600.0
            overdue.append((t, idade_h, t.sla_hours))
    overdue.sort(key=lambda x: x[1] - x[2], reverse=True)

    # Tempo médio de resolução (horas) dos resolvidos
    durations = [
        (t.resolved_at - t.created_at).total_seconds() / 3600.0
        for t in all_tickets
        if t.status == "resolvido" and t.resolved_at and t.created_at
    ]
    avg_resolution_h = round(sum(durations) / len(durations), 1) if durations else None

    # Tempo médio de 1ª resposta (horas) e satisfação (CSAT, média das notas 1-5)
    frs = [t.first_response_hours for t in all_tickets if t.first_response_hours is not None]
    avg_first_response_h = round(sum(frs) / len(frs), 1) if frs else None
    ratings = [t.rating for t in all_tickets if t.rating]
    csat = round(sum(ratings) / len(ratings), 1) if ratings else None
    csat_count = len(ratings)

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
        avg_first_response_h=avg_first_response_h,
        csat=csat, csat_count=csat_count,
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
    open_count = Ticket.query.filter(Ticket.status.in_(("aberto", "em_andamento"))).count()
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
        # Resolução já preenchida ao abrir => o chamado nasce RESOLVIDO (a menos
        # que o admin tenha escolhido explicitamente outro status). O resolved_at
        # é carimbado automaticamente pelo repositório.
        if data.get("resolution") and data.get("status") == "aberto":
            data["status"] = "resolvido"
        t = ticket_repo.create_ticket(opened_by_id=current_user.id, **data)
        # Nasceu resolvido? A 1ª resposta é a própria abertura — senão um
        # comentário futuro carimbaria first_response muito depois e poluiria a
        # métrica de tempo de 1ª resposta.
        if t.status == "resolvido" and t.first_response_at is None:
            t.first_response_at = t.created_at
            db.session.commit()
        # Notifica a equipe de TI por e-mail (best-effort)
        _aberto = (f"Aberto por: {t.requester or current_user.name}"
                   f"{(' · ' + t.sector) if t.sector else ''}")
        mailer.notify_ti(
            f"[InvenSync] Novo chamado {t.code} — {t.title}",
            f"{t.code} — {t.title}\n{_aberto}\nPrioridade: {t.priority}\n"
            f"{(t.description or '').strip()}"
        )
        flash(f"Chamado {t.code} aberto!", "success")
        return redirect(url_for("tickets.detail", tid=t.id))
    return render_template("tickets/form.html", form=form, title="Novo Chamado",
                           users_info=_users_info(), is_admin=is_admin)


@bp.route("/<int:tid>")
@login_required
def detail(tid):
    t = ticket_repo.get_ticket(tid)
    if not current_user.is_admin and not _is_participant(current_user, t):
        abort(403)
    comment_form = CommentForm()
    return render_template("tickets/detail.html", t=t, comment_form=comment_form,
                           is_admin=current_user.is_admin,
                           can_rate=_is_requester(current_user, t))


def _notify_requester_resolved(t):
    """E-mail para o solicitante quando o chamado é RESOLVIDO — fecha o ciclo."""
    corpo = f"Seu chamado {t.code} — {t.title} foi marcado como RESOLVIDO."
    if t.resolution:
        corpo += f"\n\nResolução: {t.resolution.strip()}"
    corpo += "\n\nSe o problema persistir, responda no chamado que reabrimos."
    mailer.notify_user(_requester_user(t),
                       f"[InvenSync] Chamado {t.code} resolvido — {t.title}", corpo)


@bp.route("/<int:tid>/comment", methods=["POST"])
@login_required
def comment(tid):
    t = ticket_repo.get_ticket(tid)
    if not current_user.is_admin and not _is_participant(current_user, t):
        abort(403)
    form = CommentForm()
    if form.validate_on_submit():
        body = form.body.data.strip()
        # Usuário comum não muda status (só a equipe de TI)
        new_status = form.new_status.data if current_user.is_admin else None
        was_resolved = (t.status == "resolvido")
        # Solicitante respondendo num chamado JÁ resolvido? Reabre automaticamente.
        reopened = (not current_user.is_admin) and was_resolved
        if reopened:
            new_status = "em_andamento"
        # 1ª resposta da TI — para a métrica de tempo de resposta.
        if current_user.is_admin and t.first_response_at is None:
            t.first_response_at = datetime.now()
        ticket_repo.add_comment(t, body=body, author_id=current_user.id,
                                new_status=new_status or None)
        # Respostas/andamentos: SEM WhatsApp (economiza a cota do CallMeBot).
        # O WhatsApp fica só na ABERTURA do chamado; aqui mantemos só o e-mail.
        if current_user.is_admin:
            if t.status == "resolvido" and not was_resolved:
                _notify_requester_resolved(t)     # fecha o ciclo pra quem abriu
            else:
                _st = STATUS_LABELS.get(t.status, t.status)
                mailer.notify_user(
                    _requester_user(t),
                    f"[InvenSync] Chamado {t.code} atualizado — {t.title}",
                    f"{t.code} — {t.title}\nAtualizado por {current_user.name}.\n"
                    f"Status: {_st}\n\n{body}"
                )
        else:
            _acao = "REABRIU" if reopened else "respondeu"
            mailer.notify_ti(
                f"[InvenSync] {'Chamado REABERTO' if reopened else 'Resposta'} — {t.code} {t.title}",
                f"{t.requester or current_user.name} {_acao} o chamado {t.code}:\n\n{body}"
            )
        flash("Chamado reaberto — a equipe de TI foi avisada." if reopened
              else "Andamento adicionado.", "success")
    else:
        flash("Escreva o andamento antes de enviar.", "warning")
    return redirect(url_for("tickets.detail", tid=t.id))


@bp.route("/<int:tid>/assumir", methods=["POST"])
@login_required
def assume(tid):
    """Analista de TI assume o chamado, atribuindo-o a si mesmo."""
    if not current_user.is_admin:
        abort(403)
    t = ticket_repo.get_ticket(tid)
    # Atribui a mim e, se ainda estava só aberto, passa para "em andamento".
    t.assigned_to_id = current_user.id
    new_status = "em_andamento" if t.status == "aberto" else None
    if t.first_response_at is None:      # assumir conta como 1ª resposta da TI
        t.first_response_at = datetime.now()
    ticket_repo.add_comment(
        t, body=f"Chamado assumido por {current_user.name}.",
        author_id=current_user.id, new_status=new_status,
    )
    audit.record("update", "ticket", t.id, f"Assumiu o chamado {t.code}")
    # Sem WhatsApp aqui — o CallMeBot fica só na abertura do chamado.
    flash(f"Você assumiu o chamado {t.code}.", "success")
    return redirect(request.referrer or url_for("tickets.list_view"))


@bp.route("/<int:tid>/rate", methods=["POST"])
@login_required
def rate(tid):
    """Avaliação de satisfação — só o solicitante, e só com o chamado resolvido
    (evita a própria TI auto-avaliar quando registra o chamado por terceiros)."""
    t = ticket_repo.get_ticket(tid)
    if not _is_requester(current_user, t):
        abort(403)
    if t.status != "resolvido":
        flash("Só é possível avaliar chamados resolvidos.", "warning")
        return redirect(url_for("tickets.detail", tid=t.id))
    try:
        nota = int(request.form.get("rating") or 0)
    except ValueError:
        nota = 0
    if not (1 <= nota <= 5):
        flash("Escolha uma nota de 1 a 5.", "warning")
        return redirect(url_for("tickets.detail", tid=t.id))
    t.rating = nota
    t.rated_at = datetime.now()
    db.session.commit()
    audit.record("update", "ticket", t.id, f"Avaliou o chamado {t.code}: {nota}/5")
    flash("Obrigado pela avaliação!", "success")
    return redirect(url_for("tickets.detail", tid=t.id))


ALLOWED_ATTACH_EXT = {
    "png", "jpg", "jpeg", "gif", "webp", "bmp", "pdf", "txt", "log",
    "doc", "docx", "xls", "xlsx", "csv", "zip", "rar",
}


def _save_attachment(file_storage, ticket: Ticket) -> TicketAttachment:
    folder = current_app.config["ATTACH_FOLDER"]
    os.makedirs(folder, exist_ok=True)
    safe = secure_filename(file_storage.filename or "arquivo")
    ext = (safe.rsplit(".", 1)[-1] if "." in safe else "").lower()
    if ext not in ALLOWED_ATTACH_EXT:
        return None
    fname = f"t{ticket.id}_{int(time.time()*1000)}_{safe}"
    path = os.path.join(folder, fname)
    file_storage.save(path)
    size = os.path.getsize(path) if os.path.exists(path) else None
    att = TicketAttachment(
        ticket_id=ticket.id, uploaded_by_id=current_user.id,
        filename=fname, original_name=safe,
        content_type=file_storage.mimetype, size=size,
    )
    db.session.add(att)
    return att


@bp.route("/<int:tid>/attach", methods=["POST"])
@login_required
def attach(tid):
    t = ticket_repo.get_ticket(tid)
    if not current_user.is_admin and t.opened_by_id != current_user.id:
        abort(403)
    files = request.files.getlist("files")
    saved, rejected = 0, 0
    for f in files:
        if not f or not f.filename:
            continue
        if _save_attachment(f, t):
            saved += 1
        else:
            rejected += 1
    if saved:
        db.session.commit()
        audit.record("create", "ticket_attachment", t.id, f"Anexou {saved} arquivo(s) ao chamado {t.code}")
        flash(f"{saved} anexo(s) enviado(s).", "success")
    if rejected:
        flash(f"{rejected} arquivo(s) ignorado(s) (tipo não permitido).", "warning")
    if not saved and not rejected:
        flash("Selecione um arquivo para anexar.", "warning")
    return redirect(url_for("tickets.detail", tid=t.id))


@bp.route("/<int:tid>/attach/<int:aid>/delete", methods=["POST"])
@login_required
def attach_delete(tid, aid):
    t = ticket_repo.get_ticket(tid)
    att = TicketAttachment.query.filter_by(id=aid, ticket_id=t.id).first_or_404()
    # Quem pode remover: admin ou quem enviou
    if not current_user.is_admin and att.uploaded_by_id != current_user.id:
        abort(403)
    try:
        path = os.path.join(current_app.config["ATTACH_FOLDER"], att.filename)
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass
    db.session.delete(att)
    db.session.commit()
    flash("Anexo removido.", "success")
    return redirect(url_for("tickets.detail", tid=t.id))


@bp.route("/<int:tid>/attach/<int:aid>/file")
@login_required
def attach_file(tid, aid):
    """Baixa/abre um anexo. Fica FORA de /static: exige login + ser participante
    do chamado (o que a rota estática pública não garantia)."""
    t = ticket_repo.get_ticket(tid)
    if not current_user.is_admin and not _is_participant(current_user, t):
        abort(403)
    att = TicketAttachment.query.filter_by(id=aid, ticket_id=t.id).first_or_404()
    return send_from_directory(
        current_app.config["ATTACH_FOLDER"], att.filename,
        as_attachment=False, download_name=att.original_name or att.filename,
    )


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
        form.requester.data = t.requester or ""
    if form.validate_on_submit():
        was_resolved = (t.status == "resolvido")
        ticket_repo.update_ticket(t, **_to_kwargs(form))
        if t.status == "resolvido" and not was_resolved:
            _notify_requester_resolved(t)     # avisa o solicitante da resolução
        flash("Chamado atualizado!", "success")
        return redirect(url_for("tickets.detail", tid=t.id))
    return render_template("tickets/form.html", form=form, title=f"Editar {t.code}",
                           users_info=_users_info())


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
