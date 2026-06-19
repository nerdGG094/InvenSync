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

bp = Blueprint("colaboradores", __name__)


@bp.before_request
@login_required
def _only_admin():
    if not current_user.is_admin:
        abort(403)


def _clean(v):
    v = (v or "").strip()
    return v or None


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
    return render_template("colaboradores/list.html", items=items, q=q,
                           asset_counts=_asset_counts())


@bp.route("/new", methods=["GET", "POST"])
def new():
    form = ColaboradorForm()
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
    person = User.query.get_or_404(cid)
    form = ColaboradorForm(obj=person)
    if request.method == "GET":
        # `department` no form mapeia para `sector` no modelo.
        form.department.data = person.sector
    if form.validate_on_submit():
        nome = form.name.data.strip()
        if _name_taken(nome, ignore_id=person.id):
            flash("Já existe uma pessoa com esse nome.", "warning")
        else:
            person.name = nome
            person.sector = _clean(form.department.data)
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
                db.session.commit()
                flash("Pessoa atualizada!", "success")
                return redirect(url_for("colaboradores.list_view"))
            except IntegrityError:
                db.session.rollback()
                flash("Não foi possível salvar (e-mail ou nome duplicado).", "danger")
    return render_template("colaboradores/form.html", form=form, title="Editar Pessoa")


@bp.route("/<int:cid>/toggle-active", methods=["POST"])
def toggle_active(cid):
    person = User.query.get_or_404(cid)
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
    person = User.query.get_or_404(cid)
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
    person = User.query.get_or_404(cid)
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
