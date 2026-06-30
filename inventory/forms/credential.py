from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, SubmitField
from wtforms.validators import DataRequired, Length, Optional

CATEGORY_CHOICES = [
    ("servidor", "Servidor"),
    ("email", "E-mail"),
    ("sistema", "Sistema / Aplicação"),
    ("site", "Site / Portal"),
    ("banco", "Banco de Dados"),
    ("rede", "Rede / Equipamento"),
    ("outro", "Outro"),
]


class CredentialForm(FlaskForm):
    name = StringField("Identificação", validators=[DataRequired(), Length(min=2, max=150)])
    category = SelectField("Categoria", choices=CATEGORY_CHOICES, validators=[DataRequired()])
    url = StringField("Host / URL", validators=[Optional(), Length(max=255)])
    username = StringField("Usuário", validators=[Optional(), Length(max=150)])
    password = StringField("Senha", validators=[Optional(), Length(max=255)])
    # Setor escolhido do cadastro de Departamentos (choices preenchidas na rota).
    sector = SelectField("Setor / Dono", choices=[], validate_choice=False,
                         validators=[Optional(), Length(max=120)])
    notes = TextAreaField("Observações", validators=[Optional()])
    submit = SubmitField("Salvar")
