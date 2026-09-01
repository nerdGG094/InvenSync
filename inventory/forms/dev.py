from flask_wtf import FlaskForm
from wtforms import (StringField, TextAreaField, SelectField, DateField, SubmitField)
from wtforms.validators import DataRequired, Length, Optional

STATUS_CHOICES = [
    ("backlog", "Backlog"), ("todo", "A fazer"), ("doing", "Fazendo"),
    ("review", "Revisão"), ("done", "Concluído"),
]
PRIORITY_CHOICES = [
    ("baixa", "Baixa"), ("media", "Média"), ("alta", "Alta"), ("critica", "Crítica"),
]
SPRINT_STATUS_CHOICES = [
    ("planejada", "Planejada"), ("ativa", "Ativa"), ("concluida", "Concluída"),
]


class DevTaskForm(FlaskForm):
    title = StringField("Título", validators=[DataRequired(), Length(min=1, max=200)])
    description = TextAreaField("Descrição", validators=[Optional()])
    status = SelectField("Status", choices=STATUS_CHOICES, validators=[DataRequired()])
    priority = SelectField("Prioridade", choices=PRIORITY_CHOICES, validators=[DataRequired()])
    # choices preenchidas na rota (0 = nenhum)
    sprint_id = SelectField("Sprint", coerce=int, choices=[], validate_choice=False,
                            validators=[Optional()])
    assignee_id = SelectField("Responsável", coerce=int, choices=[], validate_choice=False,
                              validators=[Optional()])
    tags = StringField("Tags", validators=[Optional(), Length(max=200)])
    code_ref = StringField("Código (commit/branch/PR/link)", validators=[Optional(), Length(max=300)])
    due_date = DateField("Prazo", validators=[Optional()])
    # choices preenchidas na rota (0 = nenhum); vincula a tarefa a um chamado
    ticket_id = SelectField("Chamado de origem", coerce=int, choices=[],
                            validate_choice=False, validators=[Optional()])
    submit = SubmitField("Salvar")


class DevSprintForm(FlaskForm):
    name = StringField("Nome da sprint", validators=[DataRequired(), Length(min=1, max=120)])
    goal = TextAreaField("Objetivo", validators=[Optional()])
    start_date = DateField("Início", validators=[Optional()])
    end_date = DateField("Fim", validators=[Optional()])
    status = SelectField("Status", choices=SPRINT_STATUS_CHOICES, validators=[DataRequired()])
    submit = SubmitField("Salvar")
