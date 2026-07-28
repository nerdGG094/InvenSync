from flask_wtf import FlaskForm
from wtforms import (StringField, TextAreaField, SelectField, IntegerField,
                     SubmitField)
from wtforms.validators import DataRequired, Length, Optional, Regexp, NumberRange

IP_REGEX = r"^$|^(\d{1,3}\.){3}\d{1,3}$|^[A-Za-z0-9.\-:]+$"

STATUS_CHOICES = [
    ("em_uso", "Em uso"), ("manutencao", "Manutenção"), ("inativo", "Inativo"),
]


class DvrForm(FlaskForm):
    label = StringField("Apelido / Identificação", validators=[Optional(), Length(max=120)])
    brand = StringField("Marca", validators=[Optional(), Length(max=80)])
    model = StringField("Modelo", validators=[DataRequired(), Length(min=1, max=120)])
    serial_number = StringField("Nº de Série", validators=[Optional(), Length(max=120)])
    patrimony = StringField("Nº Patrimônio", validators=[Optional(), Length(max=60)])

    ip_address = StringField("IP do painel", validators=[Optional(), Length(max=45),
                             Regexp(IP_REGEX, message="IP inválido.")])
    web_port = IntegerField("Porta do painel", validators=[Optional(), NumberRange(min=1, max=65535)])
    mac_address = StringField("MAC", validators=[Optional(), Length(max=20)])
    admin_user = StringField("Usuário admin", validators=[Optional(), Length(max=80)])
    admin_password = StringField("Senha admin", validators=[Optional(), Length(max=120)])

    channels = IntegerField("Nº de canais", validators=[Optional(), NumberRange(min=1, max=256)])
    location = StringField("Local / Setor", validators=[Optional(), Length(max=150)])
    status = SelectField("Status", choices=STATUS_CHOICES, validators=[DataRequired()])
    notes = TextAreaField("Observações", validators=[Optional()])
    submit = SubmitField("Salvar")
