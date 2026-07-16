from flask_wtf import FlaskForm
from wtforms import (StringField, TextAreaField, SelectField, BooleanField,
                     PasswordField, SubmitField)
from wtforms.validators import DataRequired, Length, Optional

VERSION_CHOICES = [
    ("3.1", "3.1"),
    ("3.3", "3.3 (padrão)"),
    ("3.4", "3.4"),
    ("3.5", "3.5"),
]


class SmartPlugForm(FlaskForm):
    name = StringField("Nome", validators=[DataRequired(), Length(max=120)])
    location = StringField("Local / Setor", validators=[Optional(), Length(max=120)])
    device_id = StringField("Device ID (Tuya)", validators=[DataRequired(), Length(max=64)])
    ip_address = StringField("IP na rede", validators=[Optional(), Length(max=45)])
    # PasswordField: em branco na edição = mantém a chave já salva.
    local_key = PasswordField("Local key", validators=[Optional(), Length(max=200)])
    version = SelectField("Versão do protocolo", choices=VERSION_CHOICES, default="3.3")
    switch_dp = StringField("DP do relé", validators=[Optional(), Length(max=8)], default="1")
    is_active = BooleanField("Ativa", default=True)
    notes = TextAreaField("Observações", validators=[Optional()])
    submit = SubmitField("Salvar")
