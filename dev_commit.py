"""
Joga o ultimo commit no board DEV (kanban de desenvolvimento).

Uso:
    .venv\\Scripts\\python.exe dev_commit.py                       # HEAD deste repo
    .venv\\Scripts\\python.exe dev_commit.py <hash>                # outro commit
    .venv\\Scripts\\python.exe dev_commit.py <hash> --repo <pasta> # outro projeto

O board atende varios repositorios (InvenSync, CARREG-LOGI, ...): o hook de cada
um chama ESTE script, que grava sempre no banco do InvenSync. O nome do projeto
vira a primeira tag do card. Instalar o hook:

    setup\\instalar_hooks.ps1                 # neste repo
    setup\\instalar_hooks.ps1 -Repo <pasta>   # em outro projeto

Regras (o que vira card, o que e ignorado) ficam em
`inventory/services/dev_commit.py`.

Nunca falha de proposito: um erro aqui nao pode derrubar um `git commit`, entao
qualquer excecao vira aviso no stderr e o processo sai com 0.

Configuracao (.env):
    DEV_COMMIT_ENABLED     0 desliga o registro automatico (default: 1)
    DEV_COMMIT_USER_EMAIL  dono dos cards criados (default: ti@refrigerantesjaboti.com.br)
    DEV_COMMIT_STATUS      coluna onde o card nasce (default: review)
    DEV_COMMIT_PROJETO     forca o nome do projeto (default: nome da pasta)
    DEV_COMMIT_IGNORAR     regex de commits de rotina a ignorar (backup/wip)
"""
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

# Este processo e efemero: nao pode subir monitoramento, alertas, SNMP, tomadas,
# backup nem os listeners de DVR so para gravar uma linha no banco.
for _var in ("MONITORING_ENABLED", "ALERTS_ENABLED", "PRINTER_MONITOR_ENABLED",
             "PLUG_SCHEDULER_ENABLED", "BACKUP_SCHEDULER_ENABLED",
             "DVR_EVENTS_ENABLED", "SECURITY_ALERTS_ENABLED", "MAIL_ENABLED"):
    os.environ[_var] = "0"


def _git(repo: Path, *args) -> str:
    try:
        saida = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=20)
        return (saida.stdout or "").strip()
    except Exception:      # noqa: BLE001 — sem git, sem registro; e so isso
        return ""


def _url_commit(repo: Path, hash_completo: str) -> str:
    """URL do commit no GitHub, quando o remoto for github.com."""
    remoto = _git(repo, "remote", "get-url", "origin")
    if not remoto or "github.com" not in remoto:
        return ""
    caminho = remoto.split("github.com", 1)[1].lstrip(":/").removesuffix(".git")
    return f"https://github.com/{caminho}/commit/{hash_completo}" if caminho else ""


def _projeto(repo: Path) -> str:
    """Nome curto do projeto = primeira tag do card. O board atende varios
    repositorios, entao precisa dar para saber de onde veio o commit."""
    forcado = os.environ.get("DEV_COMMIT_PROJETO")
    if forcado:
        return forcado.strip().lower()
    nome = repo.name.lower()
    # a pasta nem sempre tem o nome pelo qual o projeto e conhecido
    return {"inventarioalmox": "invensync", "kiox-apk": "kiox"}.get(nome, nome)


def _app():
    """App minimo: config + SQLAlchemy, nada mais.

    De proposito NAO usa `create_app()`: ela roda `db.create_all()`, as light
    migrations e todos os seeds a cada boot (4s), e um hook de git nao tem o que
    fazer mexendo no schema do banco a cada commit. Aqui so precisamos gravar
    duas linhas.
    """
    import importlib
    import pkgutil

    from flask import Flask

    from inventory.config import Config
    from inventory.extensions import db
    from inventory import models as pacote_modelos

    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    # Todos os modelos precisam estar importados ou o SQLAlchemy nao consegue
    # resolver os relacionamentos (DevTask -> User -> Department, ...).
    for mod in pkgutil.iter_modules(pacote_modelos.__path__):
        importlib.import_module(f"inventory.models.{mod.name}")
    return app


def main() -> int:
    if (os.environ.get("DEV_COMMIT_ENABLED", "1") or "1").strip() in ("0", "false", "False"):
        return 0

    # dev_commit.py [ref] [--repo <caminho>]   (--repo: outro projeto, ex. CARREG-LOGI)
    args = sys.argv[1:]
    repo = RAIZ
    if "--repo" in args:
        i = args.index("--repo")
        if i + 1 < len(args):
            repo = Path(args[i + 1]).resolve()
        del args[i:i + 2]
    ref = args[0] if args else "HEAD"

    completo = _git(repo, "rev-parse", ref)
    curto = _git(repo, "rev-parse", "--short", ref)
    mensagem = _git(repo, "log", "-1", "--format=%B", ref)
    autor = _git(repo, "log", "-1", "--format=%an <%ae>", ref)
    arquivos = [a for a in _git(repo, "show", "--name-only", "--format=", ref).splitlines()
                if a.strip()]
    if not mensagem:
        print("dev_commit: sem mensagem de commit — nada a registrar.", file=sys.stderr)
        return 0

    sys.path.insert(0, str(RAIZ))
    from inventory.services import dev_commit as servico  # noqa: PLC0415

    with _app().app_context():
        r = servico.registrar(mensagem=mensagem, hash_curto=curto,
                              url_commit=_url_commit(repo, completo), arquivos=arquivos,
                              autor=autor, projeto=_projeto(repo))
    if r.get("acao") == "ignorado":
        print(f"dev_commit: ignorado ({r.get('motivo')})")
    else:
        print(f"dev_commit: {r['acao']} card #{r['task_id']} em {r['status']} — {r['titulo']}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:      # noqa: BLE001 — commit ja foi feito; so avisa
        print(f"dev_commit: falhou ({e.__class__.__name__}: {e})", file=sys.stderr)
        sys.exit(0)
