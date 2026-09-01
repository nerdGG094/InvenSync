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

    due_date = db.Column(db.Date, nullable=True)             # prazo
    # Quando entrou em "done". Existe separado de updated_at porque este muda a
    # cada edição — sem done_at não dá para medir ciclo nem desenhar burndown.
    done_at = db.Column(db.DateTime, nullable=True)
    # Chamado que originou a tarefa (o app já tem helpdesk; fecha o ciclo)
    ticket_id = db.Column(db.Integer, db.ForeignKey("ticket.id", ondelete="SET NULL"),
                          nullable=True, index=True)
    ticket = db.relationship("Ticket", backref=db.backref("dev_tasks", lazy="dynamic"))

    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    @property
    def tag_list(self):
        return [t.strip() for t in (self.tags or "").split(",") if t.strip()]

    @property
    def checklist_total(self) -> int:
        return self.checklist.count()

    @property
    def checklist_feitos(self) -> int:
        return self.checklist.filter_by(done=True).count()

    @property
    def checklist_pct(self) -> int:
        total = self.checklist_total
        return round(self.checklist_feitos * 100 / total) if total else 0

    @property
    def atrasada(self) -> bool:
        """Passou do prazo e ainda não terminou."""
        from datetime import date
        return bool(self.due_date and self.status != "done" and self.due_date < date.today())

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


class DevChecklistItem(db.Model):
    """Subtarefa de um card — é o "%" que aparece no board."""
    __tablename__ = "dev_checklist"

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("dev_task.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    task = db.relationship("DevTask", backref=db.backref(
        "checklist", lazy="dynamic", cascade="all, delete-orphan",
        order_by="DevChecklistItem.position"))
    text = db.Column(db.String(200), nullable=False)
    done = db.Column(db.Boolean, nullable=False, default=False, server_default="false")
    position = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self) -> str:
        return f"<DevChecklistItem id={self.id} task={self.task_id} done={self.done}>"
