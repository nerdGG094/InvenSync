from flask_wtf import FlaskForm
from wtforms import (StringField, TextAreaField, SelectField, DateField,
                     IntegerField, DecimalField, SubmitField)
from wtforms.validators import DataRequired, Length, Optional, NumberRange

KIND_CHOICES = [
    ("licenca", "Licença de Software"),
    ("garantia", "Garantia"),
    ("contrato", "Contrato / Assinatura"),
    ("certificado", "Certificado Digital"),
    ("outro", "Outro"),
]


class LicenseForm(FlaskForm):
    name = StringField("Nome / Descrição", validators=[DataRequired(), Length(min=2, max=150)])
    kind = SelectField("Tipo", choices=KIND_CHOICES, validators=[DataRequired()])
    vendor = StringField("Fornecedor / Fabricante", validators=[Optional(), Length(max=120)])
    license_key = StringField("Chave / Serial", validators=[Optional(), Length(max=255)])
    seats = IntegerField("Qtd. de licenças", validators=[Optional(), NumberRange(min=0)])
    assigned_to = StringField("Vinculado a (máquina/setor/pessoa)", validators=[Optional(), Length(max=150)])
    start_date = DateField("Início / Compra", validators=[Optional()])
    expiry_date = DateField("Vencimento", validators=[Optional()])
    cost = DecimalField("Custo (R$)", places=2, validators=[Optional(), NumberRange(min=0)])
    notes = TextAreaField("Observações", validators=[Optional()])
    submit = SubmitField("Salvar")
