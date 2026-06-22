from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, Optional

STATUS_CHOICES = [
    ("em_uso", "Em uso"),
    ("disponivel", "Disponível"),
    ("manutencao", "Manutenção"),
    ("inativo", "Inativo"),
]


class RouterForm(FlaskForm):
    label = StringField("Identificação / Apelido", validators=[Optional(), Length(max=120)])
    brand = StringField("Marca", validators=[Optional(), Length(max=80)])
    model = StringField("Modelo", validators=[DataRequired(), Length(min=1, max=120)])
    location = StringField("Local / Setor", validators=[Optional(), Length(max=150)])
    serial_number = StringField("Nº de Série", validators=[Optional(), Length(max=120)])
    patrimony = StringField("Nº Patrimônio", validators=[Optional(), Length(max=60)])

    # Acesso administrativo
    ip_address = StringField("IP de acesso (admin)", validators=[Optional(), Length(max=45)])
    mac_address = StringField("MAC do roteador", validators=[Optional(), Length(max=20)])
    admin_user = StringField("Usuário admin", validators=[Optional(), Length(max=80)])
    admin_password = StringField("Senha admin", validators=[Optional(), Length(max=120)])

    # Wi-Fi
    ssid = StringField("SSID (rede Wi-Fi)", validators=[Optional(), Length(max=80)])
    wifi_password = StringField("Senha do Wi-Fi", validators=[Optional(), Length(max=120)])
    ssid_guest = StringField("SSID visitantes", validators=[Optional(), Length(max=80)])
    wifi_password_guest = StringField("Senha visitantes", validators=[Optional(), Length(max=120)])

    # Controle por MAC
    mac_filtering = BooleanField("Filtro de MAC ativo (acesso só por aparelho vinculado)")
    linked_macs = TextAreaField("MACs / aparelhos vinculados", validators=[Optional()])

    status = SelectField("Status", choices=STATUS_CHOICES, validators=[DataRequired()])
    notes = TextAreaField("Observações", validators=[Optional()])
    label_applied = BooleanField("Etiqueta QR colada no aparelho", default=False)
    submit = SubmitField("Salvar")
