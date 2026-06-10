from ..extensions import db


class Machine(db.Model):
    """Cadastro de máquinas: computadores, notebooks e impressoras."""
    __tablename__ = "machine"

    id = db.Column(db.Integer, primary_key=True)

    # Tipo: 'computador' | 'notebook' | 'impressora'
    kind = db.Column(db.String(20), nullable=False, default="computador",
                     server_default="computador", index=True)

    name = db.Column(db.String(120), nullable=True)          # identificação/hostname
    brand = db.Column(db.String(120), nullable=True)         # marca (Dell, HP...)
    model = db.Column(db.String(150), nullable=True)         # modelo do PC/notebook/impressora
    assigned_user = db.Column(db.String(150), nullable=True, index=True)  # usuário/responsável
    ip_address = db.Column(db.String(45), nullable=True, index=True)      # IP (IPv4/IPv6)
    sector = db.Column(db.String(120), nullable=True)        # setor/localização
    patrimony = db.Column(db.String(60), nullable=True, index=True)
    serial_number = db.Column(db.String(120), nullable=True, index=True)
    notes = db.Column(db.Text, nullable=True)

    is_active = db.Column(db.Boolean, nullable=False, default=True,
                          server_default=db.text("true"))    # em uso / ativo
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self) -> str:
        return f"<Machine id={self.id} kind={self.kind!r} model={self.model!r} ip={self.ip_address!r}>"
