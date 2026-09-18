"""Troca de celular: a saída do aparelho novo devolve o antigo.

Estoque e Celulares eram dois cadastros que não se falavam. Entregar um
aparelho novo a quem já tinha um exigia dois lançamentos manuais — a saída do
novo no Estoque e, se alguém lembrasse, a atualização do cadastro — e nada
garantia que as duas versões concordassem. Este módulo liga os dois no único
momento em que eles falam da mesma coisa: a troca.

**A troca é confirmada, nunca automática.** Os três desfechos são todos comuns
(voltou ao estoque, foi para manutenção, a pessoa ficou com os dois) e o erro
tem um custo específico: uma entrada automática coloca no estoque um aparelho
que está quebrado ou na gaveta de alguém, e a diferença só aparece no dia do
inventário, quando ninguém lembra mais da movimentação que a criou.
"""
from sqlalchemy import or_

from ..extensions import db
from ..models.category import Category
from ..models.mobile import MobileDevice
from ..models.product import Product

# Como reconhecer "isto é um celular" no Estoque. Mesmo critério já usado para
# toner/cilindro nas impressoras: categoria OU nome do produto, porque cadastro
# antigo costuma estar sem categoria.
_TERMOS = ("celular", "smartphone")

DESTINOS = ("estoque", "manutencao", "nada")


def _cond_celular():
    return or_(*[Category.name.ilike(f"%{t}%") for t in _TERMOS],
               *[Product.name.ilike(f"%{t}%") for t in _TERMOS])


def produtos_celular():
    """Materiais do Estoque que são aparelho celular."""
    return (Product.query.outerjoin(Category, Product.category_id == Category.id)
            .filter(_cond_celular()).order_by(Product.name.asc()).all())


def ids_produtos_celular() -> set:
    return {p.id for p in produtos_celular()}


def _norm(v: str) -> str:
    return " ".join((v or "").lower().split())


def aparelhos_da_pessoa(nome: str) -> list:
    """Aparelhos EM USO no nome da pessoa, elegíveis para devolução.

    Só o titular (`assigned_employee`), e **nunca um aparelho compartilhado**:
    devolver ao estoque um celular que outras duas pessoas também usam tiraria
    o aparelho delas sem ninguém pedir.
    """
    nome = _norm(nome)
    if not nome:
        return []
    itens = (MobileDevice.query
             .filter(MobileDevice.status == "em_uso")
             .order_by(MobileDevice.id.desc()).all())
    return [d for d in itens
            if _norm(d.assigned_employee) == nome and not d.is_shared]


def sugerir_produto(dev: MobileDevice, produtos=None):
    """Qual material do Estoque corresponde a este aparelho.

    Primeiro a memória (`dev.product_id`, gravado na troca anterior); depois um
    palpite por nome. O palpite existe para a primeira vez de cada modelo — a
    escolha do analista é o que fica gravado.
    """
    if dev.product_id:
        p = db.session.get(Product, dev.product_id)
        if p:
            return p
    produtos = produtos if produtos is not None else produtos_celular()
    modelo = _norm(f"{dev.brand or ''} {dev.model or ''}")
    if not modelo:
        return None
    for p in produtos:                      # nome do produto contido no modelo
        n = _norm(p.name)
        if n and (n in modelo or modelo in n):
            return p
    alvo = _norm(dev.model)                  # só o modelo, sem a marca
    for p in produtos:
        n = _norm(p.name)
        if alvo and n and (alvo in n or n in alvo):
            return p
    return None


def resumo(dev: MobileDevice) -> dict:
    """O que a tela precisa mostrar sobre o aparelho atual da pessoa."""
    sug = sugerir_produto(dev)
    rotulo = " ".join(x for x in (dev.brand, dev.model) if x) or "aparelho"
    return {
        "id": dev.id,
        "rotulo": rotulo,
        "patrimony": dev.patrimony or "",
        "imei": dev.imei or "",
        "linha": dev.phone_number or "",
        "setor": dev.sector or "",
        "produto_id": sug.id if sug else 0,
        "produto_nome": f"{sug.name} ({sug.sku})" if sug else "",
    }


def aplicar(dev: MobileDevice, destino: str, produto_id: int, pessoa: str,
            novo_rotulo: str = "", user_id: int = None):
    """Executa a devolução escolhida. Devolve (mensagem, movimento_de_entrada).

    **Não faz commit de propósito**: as alterações ficam pendentes na sessão e
    quem confirma é o commit da saída do aparelho novo, logo em seguida. Saída
    do novo e devolução do antigo são o mesmo fato — se uma falhar, nenhuma
    pode ficar gravada.
    """
    from ..models.movement import StockMovement

    if destino not in DESTINOS or destino == "nada":
        return None, None

    ident = " ".join(x for x in (dev.brand, dev.model) if x) or f"aparelho {dev.id}"
    if dev.patrimony:
        ident += f" ({dev.patrimony})"

    entrada = None
    if destino == "estoque":
        if not produto_id:
            return None, None
        nota = f"Devolução na troca de aparelho: {ident}"
        if pessoa:
            nota += f" — estava com {pessoa}"
        if novo_rotulo:
            nota += f"; recebeu {novo_rotulo}"
        entrada = StockMovement(
            product_id=produto_id, movement_type="IN", quantity=1,
            # `responsible_user` diz "para quem foi o item"; numa devolução não
            # há destinatário, e preenchê-lo com quem devolveu inverteria o
            # sentido do campo em todo relatório. A pessoa fica na observação.
            responsible_user=None,
            responsible_sector=dev.sector or None,
            note=nota,
            user_id=user_id,
        )
        db.session.add(entrada)
        dev.status = "disponivel"
        dev.product_id = produto_id          # memória para a próxima troca
        msg = f"{ident} voltou ao estoque."
    else:                                     # manutencao
        dev.status = "manutencao"
        msg = f"{ident} foi para manutenção."

    # Em ambos os casos o aparelho deixa de estar com a pessoa.
    dev.assigned_employee = None
    dev.assigned_employee_2 = None
    dev.assigned_employee_3 = None
    dev.user_id = None
    return msg, entrada
