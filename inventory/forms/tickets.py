from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, SubmitField
from wtforms.validators import DataRequired, Length, Optional

CATEGORY_CHOICES = [
    ("hardware", "Hardware"),
    ("software", "Software"),
    ("rede", "Rede"),
    ("impressora", "Impressora"),
    ("acesso", "Acesso / Senha"),
    ("outro", "Outro"),
]

PRIORITY_CHOICES = [
    ("baixa", "Baixa"),
    ("media", "Média"),
    ("alta", "Alta"),
    ("urgente", "Urgente"),
]

STATUS_CHOICES = [
    ("aberto", "Aberto"),
    ("em_andamento", "Em andamento"),
    ("resolvido", "Resolvido"),
    ("cancelado", "Cancelado"),
]


class TicketForm(FlaskForm):
    title = StringField("Título / Assunto", validators=[DataRequired(), Length(min=2, max=200)])
    # choices são preenchidas na rota com os usuários cadastrados em Máquinas
    requester = SelectField("Solicitante", validators=[Optional()], choices=[])
    sector = StringField("Setor", validators=[Optional(), Length(max=120)])
    category = SelectField("Categoria", choices=CATEGORY_CHOICES, validators=[DataRequired()])
    priority = SelectField("Prioridade", choices=PRIORITY_CHOICES, validators=[DataRequired()])
    status = SelectField("Status", choices=STATUS_CHOICES, validators=[DataRequired()])
    assigned_to_id = SelectField("Responsável (atendente)", coerce=int, validators=[Optional()])
    machine_id = SelectField("Máquina relacionada", coerce=int, validators=[Optional()])
    description = TextAreaField("Descrição", validators=[Optional()])
    resolution = TextAreaField("Resolução (o que foi feito)", validators=[Optional()])
    submit = SubmitField("Salvar")


class CommentForm(FlaskForm):
    body = TextAreaField("Andamento", validators=[DataRequired(), Length(min=1)])
    new_status = SelectField("Mudar status para", choices=[("", "— manter —")] + STATUS_CHOICES,
                             validators=[Optional()])
    submit = SubmitField("Adicionar andamento")
