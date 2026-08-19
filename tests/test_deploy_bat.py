"""O atualizar.bat precisa ser PARSAVEL pelo cmd.

Ele passou meses morrendo logo depois do "git pull" com
"'.' foi inesperado neste momento": um echo dentro de um bloco
`if errorlevel 1 ( ... )` continha "(conflitos/rede)", e o parentese
fechava o bloco antes da hora. O cmd analisa o bloco inteiro assim que o
encontra, entao o script quebrava mesmo quando o passo dava certo -- e o
aviso de reiniciar nunca chegava a ser impresso.
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
BAT = RAIZ / "atualizar.bat"                      # o critico de deploy
# Os .bat que seguem a convencao "sem bloco (), so goto :label". Escritos assim
# de proposito porque tem echos cheios de parenteses (instrucoes: `n) New
# remote`), e um bloco () os tornaria uma bomba. Os pre-existentes install.bat
# e start_invensync.bat usam blocos com conteudo seguro e ficam de fora — um
# parser de cmd por regex para distinguir bloco de prosa e fragil demais; a
# prova de verdade para esses e o teste de cmd vivo abaixo.
BATS_GOTO = [
    RAIZ / "atualizar.bat",
    RAIZ / "setup" / "configurar_backup_drive.bat",
    RAIZ / "setup" / "testar_backup_drive.bat",
]


def test_arquivo_existe():
    assert BAT.is_file()


@pytest.mark.parametrize("bat", BATS_GOTO, ids=lambda p: p.name)
def test_bats_goto_nao_usam_bloco_de_parenteses(bat):
    """Nos .bat de convencao goto, nenhum bloco `( )` — e o que reintroduz o
    bug do parentese-em-echo. Tratamento de erro so com `if ... goto :label`."""
    linhas = bat.read_text(encoding="utf-8", errors="replace").splitlines()
    ofensores = [(i + 1, l) for i, l in enumerate(linhas)
                 if re.search(r"^\s*(if|for)\b.*\(\s*$", l, re.I)]
    assert not ofensores, (
        f"{bat.name}: use `if ... goto :label`, nao bloco (): "
        + "; ".join(f"linha {n}: {l.strip()}" for n, l in ofensores))


def test_sem_bloco_de_parenteses_no_if():
    """A construcao inteira esta banida: e a que permite o erro voltar.
    Tratamento de erro no arquivo e com `if errorlevel 1 goto :label`."""
    linhas = BAT.read_text(encoding="utf-8", errors="replace").splitlines()
    ofensores = [(i + 1, l) for i, l in enumerate(linhas)
                 if re.search(r"^\s*if\b.*\(\s*$", l, re.I)]
    assert not ofensores, (
        "use `if ... goto :label` em vez de bloco entre parenteses: "
        + "; ".join(f"linha {n}: {l.strip()}" for n, l in ofensores))


def test_echo_nao_tem_parentese_solto():
    """Fora de bloco o parentese e inofensivo, mas dentro derruba tudo.
    Como a regra e facil de esquecer, o teste exige ^( e ^) sempre."""
    ruins = []
    for i, l in enumerate(BAT.read_text(encoding="utf-8", errors="replace").splitlines()):
        if not re.match(r"^\s*echo\b", l, re.I):
            continue
        sem_escape = re.sub(r"\^[()]", "", l)
        if "(" in sem_escape or ")" in sem_escape:
            ruins.append((i + 1, l.strip()))
    assert not ruins, ("parenteses precisam de escape ^( ^) no echo: "
                       + "; ".join(f"linha {n}: {t}" for n, t in ruins))


# Prova de verdade: pede ao proprio cmd para ler o arquivo. So os .bat que
# saem cedo sozinhos entram aqui — o atualizar para no `git pull` (PATH vazio =
# git nao existe), o testar para no guard (rclone.conf ausente). O
# configurar_backup_drive fica de fora: ele abre o `rclone config` interativo e
# penduraria o teste; a regra estatica acima ja o cobre.
BATS_CMD_VIVO = [
    RAIZ / "atualizar.bat",
    RAIZ / "setup" / "testar_backup_drive.bat",
]


@pytest.mark.skipif(sys.platform != "win32", reason="sintaxe do cmd so no Windows")
@pytest.mark.parametrize("bat", BATS_CMD_VIVO, ids=lambda p: p.name)
def test_cmd_consegue_analisar_o_arquivo(bat):
    """O cmd analisa o arquivo inteiro ate o ponto de saida — um parentese
    solto em bloco apareceria como "'.' foi inesperado" antes disso."""
    r = subprocess.run(["cmd.exe", "/c", str(bat)], input="\n", capture_output=True,
                       text=True, timeout=600, encoding="latin-1", errors="replace",
                       cwd=str(bat.parent), env={"PATH": "", "SystemRoot": r"C:\Windows"})
    saida = (r.stdout or "") + (r.stderr or "")
    assert "inesperado" not in saida.lower(), f"cmd nao conseguiu analisar:\n{saida}"
