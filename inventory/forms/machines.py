from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, Regexp

# IPv4 simples ou vazio (também aceita hostname curto). Validação leve.
IP_REGEX = r"^$|^(\d{1,3}\.){3}\d{1,3}$|^[A-Za-z0-9.\-:]+$"

KIND_CHOICES = [
    ("computador", "Computador"),
    ("notebook", "Notebook"),
    ("impressora", "Impressora"),
]


class MachineForm(FlaskForm):
    kind = SelectField("Tipo", choices=KIND_CHOICES, validators=[DataRequired()])
    name = StringField("Identificação / Hostname", validators=[Optional(), Length(max=120)])
    brand = StringField("Marca", validators=[Optional(), Length(max=120)])
    model = StringField("Modelo", validators=[DataRequired(), Length(min=1, max=150)])
    assigned_user = StringField("Usuário / Responsável", validators=[Optional(), Length(max=150)])
    ip_address = StringField("IP da máquina", validators=[Optional(), Length(max=45),
                                                          Regexp(IP_REGEX, message="IP inválido.")])
    sector = StringField("Setor / Localização", validators=[Optional(), Length(max=120)])
    patrimony = StringField("Nº Patrimônio", validators=[Optional(), Length(max=60)])
    serial_number = StringField("Nº de Série", validators=[Optional(), Length(max=120)])
    notes = TextAreaField("Observações", validators=[Optional()])
    is_active = BooleanField("Em uso / ativo", default=True)
    submit = SubmitField("Salvar")
