from ..extensions import db


class DevSprint(db.Model):
    """Uma sprint/iteração do time de desenvolvimento."""
    __tablename__ = "dev_sprint"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    goal = db.Column(db.Text, nullable=True)                 # objetivo da sprint
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    # planejada | ativa | concluida
    status = db.Column(db.String(12), nullable=False, default="planejada",
                       server_default="planejada", index=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self) -> str:
        return f"<DevSprint id={self.id} {self.name!r} {self.status}>"


class DevTask(db.Model):
    """Item de backlog/sprint (card do board) — estilo Monday."""
    __tablename__ = "dev_task"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    # backlog | todo | doing | review | done
    status = db.Column(db.String(12), nullable=False, default="backlog",
                       server_default="backlog", index=True)
    # baixa | media | alta | critica
    priority = db.Column(db.String(10), nullable=False, default="media",
                         server_default="media", index=True)

    sprint_id = db.Column(db.Integer, db.ForeignKey("dev_sprint.id", ondelete="SET NULL"),
                          nullable=True, index=True)
    sprint = db.relationship("DevSprint", backref=db.backref("tasks", lazy="dynamic"))

    # Responsável: FK ao cadastro de pessoas (+ texto legado como reserva).
    assignee_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    assignee = db.relationship("User", foreign_keys=[assignee_id])

    tags = db.Column(db.String(200), nullable=True)          # separadas por vírgula
    code_ref = db.Column(db.String(300), nullable=True)      # commit/branch/PR/link
    position = db.Column(db.Integer, nullable=False, default=0, server_default="0")

    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    @property
    def tag_list(self):
        return [t.strip() for t in (self.tags or "").split(",") if t.strip()]

    def __repr__(self) -> str:
        return f"<DevTask id={self.id} {self.status} {self.title!r}>"


class DevUpdate(db.Model):
    """Atualização/registro num item — é aqui que o dev 'upa' o que editou
    (descrição + link do commit/PR). Timeline do card, estilo Monday."""
    __tablename__ = "dev_update"

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("dev_task.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    task = db.relationship("DevTask", backref=db.backref("updates", lazy="dynamic",
                                                         cascade="all, delete-orphan",
                                                         order_by="DevUpdate.created_at"))
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    user = db.relationship("User")
    body = db.Column(db.Text, nullable=False)
    code_ref = db.Column(db.String(300), nullable=True)      # commit/PR desta atualização
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self) -> str:
        return f"<DevUpdate id={self.id} task={self.task_id}>"
