# inventory/services/patrimony.py
"""Geração automática de números de patrimônio para os ativos.

Numeração única em toda a empresa: máquinas e celulares compartilham a mesma
sequência (PAT-0001, PAT-0002, ...). O número é apenas SUGERIDO no cadastro —
o usuário pode editá-lo livremente. Ao gerar/backfill, calculamos o próximo
número a partir do maior sufixo numérico já existente nas duas tabelas.
"""
import re

from ..extensions import db
from ..models.machine import Machine
from ..models.mobile import MobileDevice

PREFIX = "PAT"
_PAD = 4
_RE = re.compile(r"^\s*" + PREFIX + r"-(\d+)\s*$", re.IGNORECASE)


def format_seq(n: int) -> str:
    """Formata um número de sequência como patrimônio (ex.: 1 -> 'PAT-0001')."""
    return f"{PREFIX}-{n:0{_PAD}d}"


def current_max_seq() -> int:
    """Maior sufixo numérico já usado entre máquinas e celulares (0 se nenhum)."""
    maxn = 0
    for Model in (Machine, MobileDevice):
        rows = db.session.query(Model.patrimony).filter(
            Model.patrimony.isnot(None)
        ).all()
        for (val,) in rows:
            m = _RE.match(val or "")
            if m:
                maxn = max(maxn, int(m.group(1)))
    return maxn


def next_patrimony() -> str:
    """Próximo número de patrimônio sugerido (continua a sequência da empresa)."""
    return format_seq(current_max_seq() + 1)
