# inventory/routes/domains.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from ..repositories import domain_repo
from ..forms.domain import DomainForm, REGISTRAR_CHOICES
from ..services import audit, whatsapp
from ..services.exports import xlsx_response

bp = Blueprint("domains", __name__)

REG_LABELS = dict(REGISTRAR_CHOICES)


@bp.before_request
@login_required
def _only_admin():
    if not current_user.is_admin:
        abort(403)


def _to_kwargs(form: DomainForm) -> dict:
    def s(v):
        v = (v or "").strip()
        return v or None
    return dict(
        name=(form.name.data or "").strip().lower(),
        company=s(form.company.data),
        registrar=form.registrar.data or "registro_br",
        expiry_date=form.expiry_date.data,
        auto_renew=bool(form.auto_renew.data),
        notes=s(form.notes.data),
    )


@bp.route("")
def list_view():
    q = (request.args.get("q") or "").strip()
    company = (request.args.get("company") or "").strip()
    registrar = (request.args.get("registrar") or "").strip()
    items = domain_repo.list_domains(q or None, company or None, registrar or None)
    counts = {"vencido": 0, "vencendo": 0, "vigente": 0, "sem_data": 0}
    for d in items:
        counts[d.status] = counts.get(d.status, 0) + 1
    return render_template("domains/list.html", items=items, q=q, company=company,
                           registrar=registrar, counts=counts,
                           companies=domain_repo.companies(),
                           registrars=REGISTRAR_CHOICES)


@bp.route("/new", methods=["GET", "POST"])
def new():
    form = DomainForm()
    if form.validate_on_submit():
        d = domain_repo.create_domain(**_to_kwargs(form))
        audit.record("create", "domain", d.id, f"Cadastrou domínio '{d.name}'")
        flash("Domínio cadastrado!", "success")
        return redirect(url_for("domains.list_view"))
    return render_template("domains/form.html", form=form, title="Novo Domínio")


@bp.route("/<int:did>/edit", methods=["GET", "POST"])
def edit(did):
    d = domain_repo.get_domain(did)
    form = DomainForm(obj=d)
    if form.validate_on_submit():
        domain_repo.update_domain(d, **_to_kwargs(form))
        flash("Domínio atualizado!", "success")
        return redirect(url_for("domains.list_view"))
    return render_template("domains/form.html", form=form, title="Editar Domínio")


@bp.route("/<int:did>/delete", methods=["POST"])
def delete(did):
    d = domain_repo.get_domain(did)
    audit.record("delete", "domain", d.id, f"Excluiu domínio '{d.name}'")
    domain_repo.delete_domain(d)
    flash("Domínio excluído.", "success")
    return redirect(url_for("domains.list_view"))


@bp.route("/export")
def export():
    q = (request.args.get("q") or "").strip()
    company = (request.args.get("company") or "").strip()
    registrar = (request.args.get("registrar") or "").strip()
    items = domain_repo.list_domains(q or None, company or None, registrar or None)
    st_lbl = {"vencido": "Vencido", "vencendo": "Vence em breve", "vigente": "Vigente", "sem_data": "Sem data"}
    headers = ["Domínio", "Empresa", "Registrador", "Vencimento", "Dias restantes",
               "Status", "Renovação automática"]
    rows = []
    for d in items:
        rows.append([
            d.name, d.company or "", REG_LABELS.get(d.registrar, d.registrar),
            d.expiry_date.strftime("%d/%m/%Y") if d.expiry_date else "",
            d.days_left if d.days_left is not None else "",
            st_lbl.get(d.status, d.status), "Sim" if d.auto_renew else "Não",
        ])
    audit.record("export", "domain", None, f"Exportou {len(rows)} domínio(s)")
    return xlsx_response("Dominios", headers, rows, filename="dominios")


@bp.route("/alert", methods=["POST"])
def alert():
    days = request.form.get("days", type=int) or 60
    itens = domain_repo.expiring_within(days)
    if not itens:
        flash("Nenhum domínio vencendo no período. Nada a notificar.", "info")
        return redirect(url_for("domains.list_view"))
    linhas = []
    for d in itens:
        dl = d.days_left
        quando = "VENCIDO" if dl is not None and dl < 0 else f"vence em {dl}d"
        emp = f" [{d.company}]" if d.company else ""
        linhas.append(f"• {d.name}{emp} — {d.expiry_date.strftime('%d/%m/%Y')} ({quando})")
    msg = "🌐 *Domínios a vencer*\n" + "\n".join(linhas)
    whatsapp.notify_ti(msg)
    audit.record("export", "domain", None, f"Disparou alerta de {len(itens)} domínio(s) por WhatsApp")
    if whatsapp.configured() and whatsapp._enabled():
        flash(f"Alerta enviado à TI ({len(itens)} domínio(s)).", "success")
    else:
        flash("WhatsApp não está ativo no .env — o alerta foi montado, mas não enviado.", "warning")
    return redirect(url_for("domains.list_view"))
