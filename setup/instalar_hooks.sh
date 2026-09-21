#!/bin/sh
# InvenSync - instala os hooks de git do projeto no Linux/macOS.
#
# Equivalente de setup/instalar_hooks.ps1, que so roda no Windows. Existe porque
# o board DEV se alimenta dos commits: editando pelo compartilhamento SMB a
# partir do Linux, o hook do Windows nao achava interpretador nenhum, avisava no
# stderr e saia 0 - o commit passava e o card nunca nascia.
#
#     sh setup/instalar_hooks.sh                          # neste repo
#     sh setup/instalar_hooks.sh --repo ~/projetos/outro  # em outro projeto
#     sh setup/instalar_hooks.sh --db-host 192.168.0.54   # banco noutra maquina
#     sh setup/instalar_hooks.sh --sem-venv               # so reinstala o hook
#
# O que ele faz, alem de copiar o hook:
#
#   1. cria uma venv FORA do repo (~/.local/share/invensync/venv) com o
#      subconjunto de requirements.txt que o dev_commit.py usa. Fora do repo
#      porque .venv/ vem pelo SMB e e a do Windows - as duas nao cabem na mesma
#      pasta (pyvenv.cfg e um so);
#   2. grava ~/.config/invensync/dev_commit.env com o que e desta maquina:
#      onde esta o InvenSync, qual o interpretador e, quando preciso, o DB_HOST
#      (o .env do projeto diz 127.0.0.1, que so vale dentro do servidor);
#   3. confere a conexao com o banco - instalacao que nao testa e so esperanca.
#
# .git/hooks nao e versionado: cada clone roda isto uma vez. Para desligar o
# registro sem remover o hook, DEV_COMMIT_ENABLED=0 no .env do InvenSync.

set -e

repo_alvo=""
db_host=""
criar_venv=1

while [ $# -gt 0 ]; do
    case "$1" in
        --repo)      repo_alvo="$2"; shift 2 ;;
        --db-host)   db_host="$2";   shift 2 ;;
        --sem-venv)  criar_venv=0;   shift ;;
        -h|--help)   sed -n '2,30p' "$0"; exit 0 ;;
        *) echo "[ERRO] opcao desconhecida: $1" >&2; exit 1 ;;
    esac
done

aqui="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
invensync="$(dirname -- "$aqui")"
origem="$aqui/hooks"
alvo_repo="${repo_alvo:-$invensync}"
alvo_repo="$(CDPATH= cd -- "$alvo_repo" && pwd)"
destino="$alvo_repo/.git/hooks"

[ -d "$destino" ] || { echo "[ERRO] $destino nao existe. $alvo_repo e um repositorio git?" >&2; exit 1; }

# Caminhos fixos em $HOME, sem XDG_*: o hook roda em qualquer shell, e o snap
# do VS Code aponta XDG_DATA_HOME para dentro do confinamento.
venv="$HOME/.local/share/invensync/venv"
cfg_dir="$HOME/.config/invensync"
cfg="$cfg_dir/dev_commit.env"

echo "Repositorio: $alvo_repo"
echo "InvenSync:   $invensync"

# --- 1. venv da maquina ----------------------------------------------------
if [ "$criar_venv" = "1" ] && [ ! -x "$venv/bin/python" ]; then
    echo "Criando venv em $venv ..."
    python3 -m venv "$venv"
    # As versoes saem de requirements.txt para nao virarem um segundo pino que
    # envelhece sozinho. So o que o dev_commit.py importa: ele monta um app
    # minimo (config + SQLAlchemy + modelos), nao chama create_app().
    deps="$(grep -E '^(Flask|Flask-SQLAlchemy|Flask-Login|Flask-WTF|Flask-Limiter|Werkzeug|psycopg\[binary\]|python-dotenv)==' \
            "$invensync/requirements.txt" || true)"
    [ -n "$deps" ] || { echo "[ERRO] nao achei as dependencias em requirements.txt" >&2; exit 1; }
    echo "$deps" | "$venv/bin/pip" install -q --disable-pip-version-check -r /dev/stdin
    echo "  venv pronta."
elif [ "$criar_venv" = "1" ]; then
    echo "venv ja existe: $venv"
fi

# --- 2. ambiente desta maquina ---------------------------------------------
# Instalar o hook NOUTRO repo nao pode desconfigurar a maquina: sem --db-host,
# vale o que ja estava no arquivo. Rodar duas vezes apagava o host e o hook
# voltava a tentar o 127.0.0.1 do .env, que so existe dentro do servidor.
if [ -z "$db_host" ] && [ -r "$cfg" ]; then
    db_host="$(sed -n 's/^export DB_HOST="\(.*\)"$/\1/p' "$cfg" | tail -1)"
fi

mkdir -p "$cfg_dir"
{
    echo "# InvenSync - ambiente do hook post-commit NESTA maquina."
    echo "# Gerado por setup/instalar_hooks.sh. O hook le este arquivo; o .env do"
    echo "# projeto vem pelo SMB e vale para o servidor, nao para ca."
    echo "export INVENSYNC_DIR=\"$invensync\""
    [ -x "$venv/bin/python" ] && echo "export INVENSYNC_PY=\"$venv/bin/python\""
    [ -n "$db_host" ] && echo "export DB_HOST=\"$db_host\""
    true
} > "$cfg"
echo "Ambiente:    $cfg"

# --- 3. conexao com o banco -------------------------------------------------
py="$venv/bin/python"
[ -x "$py" ] || py="$(command -v python3 || true)"
if [ -n "$py" ]; then
    # shellcheck disable=SC1090
    . "$cfg"
    if "$py" - "$invensync" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
try:
    import psycopg
    from inventory.config import DATABASE_URL
    psycopg.connect(DATABASE_URL.replace("+psycopg", ""), connect_timeout=8).close()
except Exception as e:
    print(f"    {e.__class__.__name__}: {e}".rstrip(), file=sys.stderr)
    sys.exit(1)
PY
    then
        echo "Banco:       conexao OK"
    else
        echo "[AVISO] o banco do board nao respondeu - o hook vai avisar e sair 0." >&2
        [ -n "$db_host" ] || echo "        se o Postgres esta noutra maquina, rode de novo com --db-host <ip>." >&2
    fi
fi

# --- 4. o hook --------------------------------------------------------------
for hook in "$origem"/*; do
    [ -f "$hook" ] || continue
    nome="$(basename -- "$hook")"
    destino_hook="$destino/$nome"
    if [ -f "$destino_hook" ] && ! grep -q dev_commit "$destino_hook" 2>/dev/null; then
        cp "$destino_hook" "$destino_hook.bak"
        echo "  hook existente salvo em $destino_hook.bak"
    fi
    # Barra normal e LF de proposito: quem executa o hook e /bin/sh (ou o sh do
    # Git for Windows), que nao come CRLF na linha do shebang.
    sed -e "s|@INVENSYNC@|$invensync|g" -e 's/\r$//' "$hook" > "$destino_hook"
    chmod +x "$destino_hook" 2>/dev/null || true
    [ -x "$destino_hook" ] || echo "[AVISO] $destino_hook sem permissao de execucao." >&2
    echo "  instalado: .git/hooks/$nome"
done

echo ""
echo "Pronto. A partir do proximo commit, o board DEV recebe:"
echo "  - commit citando #12        -> atualizacao na tarefa 12"
echo "  - demais commits            -> card novo em Revisao"
echo "  - [skip-kanban] no assunto  -> commit ignorado"
echo "  - \"Backup automatico ...\"   -> commit ignorado (rotina)"
