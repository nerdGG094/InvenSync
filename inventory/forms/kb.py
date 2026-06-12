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


class KbForm(FlaskForm):
    title = StringField("Título", validators=[DataRequired(), Length(min=3, max=200)])
    category = SelectField("Categoria", choices=CATEGORY_CHOICES, validators=[DataRequired()])
    problem = TextAreaField("Problema / Sintoma", validators=[Optional()])
    solution = TextAreaField("Solução", validators=[DataRequired(), Length(min=3)])
    tags = StringField("Palavras-chave (separadas por vírgula)", validators=[Optional(), Length(max=255)])
    submit = SubmitField("Salvar")
