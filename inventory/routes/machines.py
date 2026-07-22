# inventory/routes/machines.py
import io

from flask import (Blueprint, render_template, request, redirect, url_for, flash,
                   Response, jsonify, current_app)
from flask_login import login_required
from sqlalchemy import func

from ..extensions import db
from ..repositories import machine_repo
from ..forms.machines import MachineForm
from ..models.machine import Machine
from ..services import people, patrimony, imports, audit, snmp_printer

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


def _supply_choices():
    """Materiais de suprimento (toner/cilindro) do Estoque, para os comboboxes."""
    from ..models.product import Product
    sup = (Product.query.filter(Product.segment == "suprimento")
           .order_by(Product.name.asc()).all())
    return [(0, "— nenhum —")] + [(p.id, f"{p.name} ({p.sku})") for p in sup]


def _fill_supply_choices(form: MachineForm, m: "Machine | None" = None):
    choices = _supply_choices()
    form.toner_product_id.choices = list(choices)
    form.drum_product_id.choices = list(choices)
    # Garante que o material atual apareça mesmo se deixar de ser 'suprimento'.
    if m is not None:
        from ..models.product import Product
        for fld, pid in (("toner_product_id", m.toner_product_id),
                         ("drum_product_id", m.drum_product_id)):
            if pid and pid not in [c[0] for c in getattr(form, fld).choices]:
                p = db.session.get(Product, pid)
                if p:
                    getattr(form, fld).choices.append((p.id, f"{p.name} ({p.sku})"))


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
        user_id=people.user_id_for(form.assigned_user.data),   # mantém a FK em dia
        ip_address=s(form.ip_address.data),
        sector=sector,
        patrimony=s(form.patrimony.data),
        serial_number=s(form.serial_number.data),
        notes=s(form.notes.data),
        # Só faz sentido em impressora; 0 (= nenhum) vira None.
        toner_product_id=(form.toner_product_id.data or None),
        drum_product_id=(form.drum_product_id.data or None),
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
    _fill_supply_choices(form)
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
    _fill_supply_choices(form, m)
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


@bp.route("/<int:mid>/snmp")
@login_required
def snmp_status(mid):
    """Status ao vivo de uma impressora de rede (páginas, toner, cilindro).
    Consumido por AJAX no card — a consulta é de rede e não pode travar a página."""
    m = machine_repo.get_machine(mid)
    if m.kind != "impressora" or not (m.ip_address or "").strip():
        return jsonify(ok=False, error="não é impressora de rede"), 400
    dados = snmp_printer.query(
        m.ip_address,
        community=current_app.config.get("SNMP_COMMUNITY", "public"),
        timeout=float(current_app.config.get("SNMP_TIMEOUT", 3)),
    )
    return jsonify(dados)


@bp.route("/impressoras/consumo")
@login_required
def printers_report():
    """Consumo de impressão por impressora/setor num período (páginas = leitura
    do fim − leitura do início), a partir do histórico SNMP. O período pode ser
    'últimos N dias' ou um intervalo de datas exato (de/até)."""
    from datetime import datetime, timedelta
    from ..models.printer_reading import PrinterReading

    de_s = (request.args.get("de") or "").strip()
    ate_s = (request.args.get("ate") or "").strip()
    dias = None
    if de_s or ate_s:
        # Intervalo de datas: 'de' 00:00 até 'ate' 23:59:59.
        try:
            desde = datetime.strptime(de_s, "%Y-%m-%d") if de_s else datetime.now() - timedelta(days=30)
        except ValueError:
            desde = datetime.now() - timedelta(days=30)
        try:
            ate = (datetime.strptime(ate_s, "%Y-%m-%d") + timedelta(days=1) - timedelta(seconds=1)
                   ) if ate_s else datetime.now()
        except ValueError:
            ate = datetime.now()
    else:
        try:
            dias = max(1, min(3650, int(request.args.get("dias", 30))))
        except (TypeError, ValueError):
            dias = 30
        desde, ate = datetime.now() - timedelta(days=dias), datetime.now()

    label = (f"{desde.strftime('%d/%m/%Y')} a {ate.strftime('%d/%m/%Y')}"
             if dias is None else f"últimos {dias} dias")

    impressoras = (Machine.query.filter_by(kind="impressora")
                   .filter(Machine.ip_address.isnot(None)).all())
    linhas = []
    for m in impressoras:
        leituras = (PrinterReading.query
                    .filter(PrinterReading.machine_id == m.id,
                            PrinterReading.taken_at >= desde,
                            PrinterReading.taken_at <= ate,
                            PrinterReading.pages.isnot(None))
                    .order_by(PrinterReading.taken_at).all())
        paginas = None
        primeira = ultima = None
        if len(leituras) >= 2:
            primeira, ultima = leituras[0], leituras[-1]
            paginas = max(0, (ultima.pages or 0) - (primeira.pages or 0))
        elif leituras:
            ultima = leituras[-1]
        linhas.append({
            "machine": m, "sector": (m.sector or "").strip() or "Sem setor",
            "pages_period": paginas,
            "pages_total": ultima.pages if ultima else None,
            "toner_pct": ultima.toner_pct if ultima else None,
            "drum_pct": ultima.drum_pct if ultima else None,
            "de_at": primeira.taken_at if primeira else None,
            "ate_at": ultima.taken_at if ultima else None,
            "amostras": len(leituras),
        })

    # Agrupa por setor (só o que teve consumo mensurável)
    setores = {}
    for ln in linhas:
        if ln["pages_period"] is not None:
            setores[ln["sector"]] = setores.get(ln["sector"], 0) + ln["pages_period"]
    por_setor = sorted(setores.items(), key=lambda kv: kv[1], reverse=True)
    total = sum(setores.values())
    linhas.sort(key=lambda x: (x["pages_period"] is None, -(x["pages_period"] or 0)))
    return render_template("machines/printers_report.html", linhas=linhas,
                           por_setor=por_setor, total=total, dias=dias, label=label,
                           de=de_s, ate=ate_s)


@bp.route("/import", methods=["GET", "POST"])
@login_required
def import_view():
    """Importa máquinas em massa via CSV/XLSX (upsert por patrimônio/nº série)."""
    if request.method == "POST":
        f = request.files.get("file")
        if not f or not f.filename:
            flash("Selecione um arquivo CSV ou XLSX.", "warning")
            return redirect(url_for("machines.import_view"))
        if not f.filename.lower().endswith((".csv", ".xlsx")):
            flash("Formato não suportado: use .csv ou .xlsx.", "warning")
            return redirect(url_for("machines.import_view"))
        try:
            rows = imports.parse_table(f, imports.MACHINE_ALIASES)
        except Exception:  # noqa: BLE001
            flash("Não consegui ler o arquivo. Confira o formato/planilha.", "danger")
            return redirect(url_for("machines.import_view"))
        res = imports.import_machines(rows)
        audit.record("import", "machine", None,
                     f"Importou máquinas: {res['created']} criadas, {res['updated']} atualizadas")
        flash(f"Importação concluída: {res['created']} criada(s), {res['updated']} atualizada(s).",
              "success" if not res["errors"] else "warning")
        for err in res["errors"][:12]:
            flash(err, "warning")
        if len(res["errors"]) > 12:
            flash(f"... e mais {len(res['errors']) - 12} erro(s).", "warning")
        return redirect(url_for("machines.list_view"))
    return render_template("machines/import.html", headers=imports.MACHINE_TEMPLATE_HEADERS)


@bp.route("/import/template")
@login_required
def import_template():
    """CSV modelo com os cabeçalhos aceitos e uma linha de exemplo."""
    buf = io.StringIO()
    buf.write(";".join(imports.MACHINE_TEMPLATE_HEADERS) + "\r\n")
    buf.write("notebook;NB-FINANCEIRO-01;Dell;Latitude 3420;PAT-0123;SN123456;"
              "192.168.0.50;Financeiro;Maria Silva\r\n")
    return Response(
        buf.getvalue().encode("utf-8-sig"), mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=modelo_maquinas.csv"})


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
