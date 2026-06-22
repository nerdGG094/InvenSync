from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length

LEVEL_CHOICES = [
    ("info", "Informativo"),
    ("aviso", "Atenção"),
    ("urgente", "Urgente"),
]


class AnnouncementForm(FlaskForm):
    title = StringField("Título", validators=[DataRequired(), Length(min=2, max=160)])
    body = TextAreaField("Mensagem", validators=[DataRequired(), Length(min=2)])
    level = SelectField("Nível", choices=LEVEL_CHOICES, default="info")
    is_pinned = BooleanField("Fixar no topo do mural")
    is_active = BooleanField("Publicado (visível para todos)", default=True)
    submit = SubmitField("Salvar")
