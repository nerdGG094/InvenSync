# inventory/routes/assets.py
from datetime import datetime

from flask import Blueprint, render_template, request, abort
from flask_login import login_required, current_user

from ..services import assets

_MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
          "agosto", "setembro", "outubro", "novembro", "dezembro"]

bp = Blueprint("assets", __name__)


@bp.before_request
@login_required
def _only_admin():
    if not current_user.is_admin:
        abort(403)


@bp.route("")
def list_view():
    q = (request.args.get("q") or "").strip().lower()
    people = assets.people_with_assets()
    if q:
        people = [p for p in people if q in p["name"].lower()]
    totals = {
        "pessoas": len(people),
        "maquinas": sum(len(p["machines"]) for p in people),
        "celulares": sum(len(p["mobiles"]) for p in people),
    }
    return render_template("assets/list.html", people=people, totals=totals, q=request.args.get("q") or "")


@bp.route("/<path:name>")
def detail(name):
    data = assets.assets_for(name)
    if data["total"] == 0:
        abort(404)
    return render_template("assets/detail.html", a=data)


@bp.route("/<path:name>/termo")
def termo(name):
    data = assets.assets_for(name)
    if data["total"] == 0:
        abort(404)
    now = datetime.now()
    data_extenso = f"{now.day} de {_MESES[now.month - 1]} de {now.year}"
    return render_template("assets/termo.html", a=data, data_extenso=data_extenso)
