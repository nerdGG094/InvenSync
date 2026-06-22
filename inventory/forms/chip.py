from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, DateField, SubmitField
from wtforms.validators import DataRequired, Length, Optional

USAGE_CHOICES = [
    ("particular", "Celular particular do funcionário"),
    ("aparelho_empresa", "Aparelho da empresa"),
    ("disponivel", "Disponível / em estoque"),
    ("cancelado", "Cancelado / inativo"),
]


class ChipForm(FlaskForm):
    phone_number = StringField("Número / Linha", validators=[DataRequired(), Length(min=3, max=30)])
    carrier = StringField("Operadora", validators=[Optional(), Length(max=40)])
    plan = StringField("Plano / Pacote", validators=[Optional(), Length(max=80)])
    iccid = StringField("ICCID (nº do chip)", validators=[Optional(), Length(max=30)])
    usage = SelectField("Uso", choices=USAGE_CHOICES, validators=[DataRequired()])
    # choices preenchidas na rota (colaboradores cadastrados)
    assigned_employee = SelectField("Responsável", validators=[Optional()], choices=[])
    sector = StringField("Setor", validators=[Optional(), Length(max=120)])
    # choices preenchidas na rota (celulares da empresa); só usado quando o chip
    # está num aparelho da empresa.
    mobile_id = SelectField("Aparelho vinculado (empresa)", validators=[Optional()],
                            choices=[], coerce=str)
    handed_at = DateField("Data de entrega", validators=[Optional()])
    notes = TextAreaField("Observações", validators=[Optional()])
    submit = SubmitField("Salvar")
