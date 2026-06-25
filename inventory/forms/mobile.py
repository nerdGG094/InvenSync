from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, DateField, SubmitField, BooleanField
from wtforms.validators import DataRequired, Length, Optional

STATUS_CHOICES = [
    ("em_uso", "Em uso"),
    ("disponivel", "Disponível"),
    ("manutencao", "Manutenção"),
    ("inativo", "Inativo"),
]


class MobileForm(FlaskForm):
    brand = StringField("Marca", validators=[Optional(), Length(max=80)])
    model = StringField("Modelo", validators=[DataRequired(), Length(min=1, max=120)])
    phone_number = StringField("Número / Linha", validators=[Optional(), Length(max=30)])
    carrier = StringField("Operadora", validators=[Optional(), Length(max=40)])
    plan = StringField("Plano / Pacote", validators=[Optional(), Length(max=80)])
    imei = StringField("IMEI", validators=[Optional(), Length(max=40)])
    serial_number = StringField("Nº de Série", validators=[Optional(), Length(max=120)])
    # choices preenchidas na rota com os usuários cadastrados em Máquinas
    assigned_employee = SelectField("Funcionário", validators=[Optional()], choices=[])
    # Aparelho compartilhado: libera 2 funcionários adicionais.
    shared = BooleanField("Compartilhado (mais de um funcionário usa este aparelho)")
    assigned_employee_2 = SelectField("2º funcionário", validators=[Optional()], choices=[])
    assigned_employee_3 = SelectField("3º funcionário", validators=[Optional()], choices=[])
    sector = StringField("Setor", validators=[Optional(), Length(max=120)])
    patrimony = StringField("Nº Patrimônio", validators=[Optional(), Length(max=60)])
    status = SelectField("Status", choices=STATUS_CHOICES, validators=[DataRequired()])
    handed_at = DateField("Data de entrega", validators=[Optional()])
    notes = TextAreaField("Observações", validators=[Optional()])
    label_applied = BooleanField("Etiqueta QR colada no aparelho", default=False)
    kiox_installed = BooleanField("KioX instalado neste aparelho", default=False)
    submit = SubmitField("Salvar")
