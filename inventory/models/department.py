from ..extensions import db


class Department(db.Model):
    """Cadastro de departamentos / setores da empresa.

    Fonte da verdade dos setores usados no cadastro de colaboradores (campo
    `User.sector`). Antes o setor era digitado livremente em cada pessoa, o que
    gerava divergências ("Compras", "compras", "Setor de Compras"...). Agora o
    setor é escolhido a partir desta lista, padronizando os nomes.
    """
    __tablename__ = "department"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True,
                          server_default=db.text("true"))
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self) -> str:
        return f"<Department id={self.id} name={self.name!r}>"
