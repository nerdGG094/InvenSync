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

BAT = Path(__file__).resolve().parents[1] / "atualizar.bat"


def test_arquivo_existe():
    assert BAT.is_file()


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


@pytest.mark.skipif(sys.platform != "win32", reason="sintaxe do cmd so no Windows")
def test_cmd_consegue_analisar_o_arquivo():
    """Prova de verdade: pede ao proprio cmd para ler o arquivo.

    Roda com uma variavel que faz o script sair no primeiro passo, entao
    nada e baixado, instalado nem reiniciado -- mas o cmd ja precisou
    analisar os blocos para chegar la."""
    r = subprocess.run(["cmd.exe", "/c", str(BAT)], input="\n", capture_output=True,
                       text=True, timeout=600, encoding="latin-1", errors="replace",
                       cwd=str(BAT.parent), env={"PATH": "", "SystemRoot": r"C:\Windows"})
    saida = (r.stdout or "") + (r.stderr or "")
    assert "inesperado" not in saida.lower(), f"cmd nao conseguiu analisar:\n{saida}"
