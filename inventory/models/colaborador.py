from ..extensions import db


class Colaborador(db.Model):
    """Cadastro central de colaboradores (pessoas) da empresa.

    Fonte da verdade do "usuário responsável" usado pelos demais módulos
    (Máquinas, Celulares, Chamados, Movimentações...). Antes esse nome ficava
    preso em cada ativo; agora a pessoa é cadastrada aqui uma única vez.
    """
    __tablename__ = "colaborador"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, unique=True, index=True)  # nome
    department = db.Column(db.String(120), nullable=True)   # departamento / setor
    email = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True,
                          server_default=db.text("true"))
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self) -> str:
        return f"<Colaborador id={self.id} name={self.name!r} dept={self.department!r}>"
