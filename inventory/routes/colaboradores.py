# inventory/routes/colaboradores.py — cadastro central de pessoas (admin)
#
# Uma pessoa = um registro na tabela `user`. O acesso ao sistema (login) é
# OPCIONAL: marque "Tem acesso ao sistema" e informe e-mail + senha. Quem não
# tem login serve apenas como "responsável" em Máquinas, Celulares, Chamados,
# Movimentações, etc.
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models.user import User
from ..forms.colaborador import ColaboradorForm
from ..services import people

bp = Blueprint("colaboradores", __name__)


@bp.before_request
@login_required
def _only_admin():
    if not current_user.is_admin:
        abort(403)


def _clean(v):
    v = (v or "").strip()
    return v or None


def _dept_choices(current=None):
    """Opções do seletor de departamento — ver services.people.department_choices."""
    from ..services import people
    return people.department_choices(current)


def _asset_counts() -> dict:
    """{ nome_em_minúsculas: nº de equipamentos vinculados (máquinas + celulares) }."""
    from ..models.machine import Machine
    from ..models.mobile import MobileDevice
    counts = {}
    for m in Machine.query.all():
        n = (m.assigned_user or "").strip().lower()
        if n:
            counts[n] = counts.get(n, 0) + 1
    for d in MobileDevice.query.all():
        n = (d.assigned_employee or "").strip().lower()
        if n:
            counts[n] = counts.get(n, 0) + 1
    return counts


def _name_taken(nome, ignore_id=None):
    q = User.query.filter(db.func.lower(User.name) == nome.lower())
    if ignore_id is not None:
        q = q.filter(User.id != ignore_id)
    return q.first() is not None


def _email_taken(email, ignore_id=None):
    if not email:
        return False
    q = User.query.filter(db.func.lower(User.email) == email.lower())
    if ignore_id is not None:
        q = q.filter(User.id != ignore_id)
    return q.first() is not None


def _apply_login_fields(person, form, is_new):
    """Aplica a seção de login. Retorna (ok, mensagem_de_erro)."""
    want_login = bool(form.can_login.data)
    email = (form.email.data or "").strip().lower() or None

    if want_login:
        if not email:
            return False, "Para ter acesso ao sistema é necessário informar um e-mail."
        if _email_taken(email, ignore_id=None if is_new else person.id):
            return False, "E-mail já em uso por outra pessoa."
        if is_new and not form.password.data:
            return False, "Defina uma senha para o acesso ao sistema."
        person.can_login = True
        person.is_admin = bool(form.is_admin.data)
        if form.password.data:
            person.set_password(form.password.data)
    else:
        # Sem login: zera as credenciais para manter o invariante senha⇔login.
        person.can_login = False
        person.is_admin = False
        person.password_hash = None
        person.totp_secret = None
        person.is_2fa_enabled = False

    person.email = email
    return True, None


@bp.route("")
def list_view():
    q = (request.args.get("q") or "").strip()
    query = User.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            (User.name.ilike(like))
            | (User.sector.ilike(like))
            | (User.email.ilike(like))
        )
    items = query.order_by(User.name).all()

    # Agrupa por setor (alfabético; "Sem setor" por último).
    grupos_map = {}
    for p in items:
        setor = (p.sector or "").strip()
        grupos_map.setdefault(setor, []).append(p)
    nomeados = sorted((s for s in grupos_map if s), key=lambda s: s.lower())
    ordem = nomeados + ([""] if "" in grupos_map else [])
    grupos = [{"name": s or None, "items": grupos_map[s]} for s in ordem]

    return render_template("colaboradores/list.html", items=items, q=q,
                           grupos=grupos, asset_counts=_asset_counts(),
                           orfaos_count=len(_orphan_asset_names()))


@bp.route("/export")
def export():
    from ..services.exports import xlsx_response
    q = (request.args.get("q") or "").strip()
    query = User.query
    if q:
        like = f"%{q}%"
        query = query.filter((User.name.ilike(like)) | (User.sector.ilike(like)) | (User.email.ilike(like)))
    items = query.order_by(User.name).all()
    headers = ["Nome", "E-mail", "Setor", "Acesso", "Ativo", "2FA", "WhatsApp"]
    rows = []
    for p in items:
        acesso = "Admin" if (p.can_login and p.is_admin) else ("Login" if p.can_login else "Sem login")
        rows.append([
            p.name, p.email or "", p.sector or "", acesso,
            "Sim" if p.is_active else "Não",
            "Sim" if p.is_2fa_enabled else "Não",
            p.whatsapp or "",
        ])
    return xlsx_response("Colaboradores", headers, rows, filename="colaboradores")


def _orphan_asset_names() -> dict:
    """Nomes em ativos SEM vínculo (user_id nulo) que não existem no cadastro.
    -> { nome_original: {'machines': n, 'mobiles': n} }."""
    from ..models.machine import Machine
    from ..models.mobile import MobileDevice
    out = {}
    for m in Machine.query.filter(Machine.user_id.is_(None),
                                  Machine.assigned_user.isnot(None)).all():
        nm = (m.assigned_user or "").strip()
        if nm:
            out.setdefault(nm, {"machines": 0, "mobiles": 0})["machines"] += 1
    for d in MobileDevice.query.filter(MobileDevice.user_id.is_(None),
                                       MobileDevice.assigned_employee.isnot(None)).all():
        nm = (d.assigned_employee or "").strip()
        if nm:
            out.setdefault(nm, {"machines": 0, "mobiles": 0})["mobiles"] += 1
    return out


def _link_assets(nome_antigo: str, target: User):
    """Vincula (user_id) e normaliza o nome nos ativos que usam `nome_antigo`."""
    from ..models.machine import Machine
    from ..models.mobile import MobileDevice
    low = nome_antigo.strip().lower()
    Machine.query.filter(db.func.lower(db.func.btrim(Machine.assigned_user)) == low).update(
        {Machine.user_id: target.id, Machine.assigned_user: target.name}, synchronize_session=False)
    MobileDevice.query.filter(db.func.lower(db.func.btrim(MobileDevice.assigned_employee)) == low).update(
        {MobileDevice.user_id: target.id, MobileDevice.assigned_employee: target.name}, synchronize_session=False)


@bp.route("/reconciliar", methods=["GET", "POST"])
def reconciliar():
    """Fecha a cobertura da normalização: para cada nome de ativo sem vínculo,
    permite CRIAR a pessoa ou VINCULAR a uma existente (renomeando o ativo)."""
    if request.method == "POST":
        acao = request.form.get("acao")
        nome = (request.form.get("nome") or "").strip()
        if not nome:
            flash("Nome inválido.", "warning")
            return redirect(url_for("colaboradores.reconciliar"))
        if acao == "criar":
            target = User.query.filter(db.func.lower(User.name) == nome.lower()).first()
            if target is None:
                target = User(name=nome, is_active=True, is_admin=False, can_login=False)
                db.session.add(target)
                db.session.flush()   # garante o id para vincular
            _link_assets(nome, target)
            db.session.commit()
            people.invalidate_people_cache()
            flash(f"Pessoa “{nome}” criada e ativos vinculados.", "success")
        elif acao == "vincular":
            target = db.session.get(User, request.form.get("user_id", type=int))
            if not target:
                flash("Selecione uma pessoa para vincular.", "warning")
                return redirect(url_for("colaboradores.reconciliar"))
            _link_assets(nome, target)
            db.session.commit()
            people.invalidate_people_cache()
            flash(f"Ativos de “{nome}” vinculados a {target.name}.", "success")
        return redirect(url_for("colaboradores.reconciliar"))

    orfaos = _orphan_asset_names()
    pessoas = User.query.filter_by(is_active=True).order_by(User.name).all()
    return render_template("colaboradores/reconciliar.html",
                           orfaos=sorted(orfaos.items(), key=lambda kv: kv[0].lower()),
                           pessoas=pessoas)


@bp.route("/new", methods=["GET", "POST"])
def new():
    form = ColaboradorForm()
    form.department.choices = _dept_choices(form.department.data)
    if form.validate_on_submit():
        nome = form.name.data.strip()
        if _name_taken(nome):
            flash("Já existe uma pessoa com esse nome.", "warning")
        else:
            person = User(
                name=nome,
                sector=_clean(form.department.data),
                whatsapp=_clean(form.whatsapp.data),
                is_active=bool(form.is_active.data),
            )
            ok, err = _apply_login_fields(person, form, is_new=True)
            if not ok:
                flash(err, "warning")
                return render_template("colaboradores/form.html", form=form, title="Nova Pessoa")
            try:
                db.session.add(person)
                db.session.commit()
                flash("Pessoa cadastrada!", "success")
                return redirect(url_for("colaboradores.list_view"))
            except IntegrityError:
                db.session.rollback()
                flash("Não foi possível salvar (e-mail ou nome duplicado).", "danger")
    return render_template("colaboradores/form.html", form=form, title="Nova Pessoa")


@bp.route("/<int:cid>/edit", methods=["GET", "POST"])
def edit(cid):
    person = db.get_or_404(User, cid)
    form = ColaboradorForm(obj=person)
    form.department.choices = _dept_choices(person.sector)
    if request.method == "GET":
        # `department` no form mapeia para `sector` no modelo.
        form.department.data = person.sector or ""
    if form.validate_on_submit():
        nome = form.name.data.strip()
        if _name_taken(nome, ignore_id=person.id):
            flash("Já existe uma pessoa com esse nome.", "warning")
        else:
            old_name = person.name
            person.name = nome
            person.sector = _clean(form.department.data)
            person.department_id = people.department_id_for(form.department.data)
            person.whatsapp = _clean(form.whatsapp.data)
            # Protege a própria conta: não pode se desativar nem remover o
            # próprio acesso (senão se trancaria para fora do sistema).
            if person.id == current_user.id and not form.is_active.data:
                flash("Você não pode desativar a si mesmo.", "warning")
                return render_template("colaboradores/form.html", form=form, title="Editar Pessoa")
            if person.id == current_user.id and not form.can_login.data:
                flash("Você não pode remover o seu próprio acesso ao sistema.", "warning")
                return render_template("colaboradores/form.html", form=form, title="Editar Pessoa")
            person.is_active = bool(form.is_active.data)
            ok, err = _apply_login_fields(person, form, is_new=False)
            if not ok:
                flash(err, "warning")
                return render_template("colaboradores/form.html", form=form, title="Editar Pessoa")
            try:
                if nome != old_name:
                    people.propagate_person_rename(old_name, nome)
                db.session.commit()
                flash("Pessoa atualizada!", "success")
                return redirect(url_for("colaboradores.list_view"))
            except IntegrityError:
                db.session.rollback()
                flash("Não foi possível salvar (e-mail ou nome duplicado).", "danger")
    return render_template("colaboradores/form.html", form=form, title="Editar Pessoa")


@bp.route("/<int:cid>/toggle-active", methods=["POST"])
def toggle_active(cid):
    person = db.get_or_404(User, cid)
    if person.id == current_user.id:
        flash("Você não pode desativar a si mesmo.", "warning")
        return redirect(url_for("colaboradores.list_view"))
    person.is_active = not bool(person.is_active)
    db.session.commit()
    flash(f"“{person.name}” {'ativado' if person.is_active else 'inativado'}.", "success")
    return redirect(url_for("colaboradores.list_view"))


@bp.route("/<int:cid>/reset-2fa", methods=["POST"])
def reset_2fa(cid):
    """Desativa o 2FA de uma pessoa (resgate quando perde o autenticador)."""
    person = db.get_or_404(User, cid)
    if not person.is_2fa_enabled and not person.totp_secret:
        flash(f"“{person.name}” não tem 2FA ativo.", "info")
        return redirect(url_for("colaboradores.list_view"))
    person.is_2fa_enabled = False
    person.totp_secret = None
    db.session.commit()
    flash(f"2FA de “{person.name}” resetado.", "success")
    return redirect(url_for("colaboradores.list_view"))


@bp.route("/<int:cid>/delete", methods=["POST"])
def delete(cid):
    person = db.get_or_404(User, cid)
    if person.id == current_user.id:
        flash("Você não pode excluir a si mesmo.", "warning")
        return redirect(url_for("colaboradores.list_view"))
    # Preserva a trilha de auditoria (mantém o nome registrado, solta a FK).
    from ..models.audit import AuditLog
    AuditLog.query.filter_by(user_id=person.id).update({"user_id": None})
    db.session.delete(person)
    db.session.commit()
    flash("Pessoa excluída.", "success")
    return redirect(url_for("colaboradores.list_view"))
