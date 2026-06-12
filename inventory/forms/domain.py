from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, DateField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, Optional

REGISTRAR_CHOICES = [
    ("registro_br", "Registro.br"),
    ("godaddy", "GoDaddy"),
    ("outro", "Outro"),
]


class DomainForm(FlaskForm):
    name = StringField("Domínio", validators=[DataRequired(), Length(min=3, max=150)])
    company = StringField("Empresa", validators=[Optional(), Length(max=120)])
    registrar = SelectField("Registrador", choices=REGISTRAR_CHOICES, validators=[DataRequired()])
    expiry_date = DateField("Vencimento", validators=[Optional()])
    auto_renew = BooleanField("Renovação automática ativa")
    notes = TextAreaField("Observações", validators=[Optional()])
    submit = SubmitField("Salvar")
