from flask_wtf import FlaskForm
from wtforms import (StringField, TextAreaField, SelectField, DateField,
                     DecimalField, SubmitField)
from wtforms.validators import DataRequired, Length, Optional, NumberRange

KIND_CHOICES = [
    ("preventiva", "Preventiva"),
    ("corretiva", "Corretiva"),
    ("upgrade", "Upgrade / Melhoria"),
    ("formatacao", "Formatação / Reinstalação"),
    ("troca_peca", "Troca de peça"),
    ("outro", "Outro"),
]


class MaintenanceForm(FlaskForm):
    machine_id = SelectField("Máquina", coerce=int, validators=[DataRequired()])
    date = DateField("Data", validators=[DataRequired()])
    kind = SelectField("Tipo", choices=KIND_CHOICES, validators=[DataRequired()])
    description = TextAreaField("O que foi feito", validators=[DataRequired(), Length(min=2)])
    parts = TextAreaField("Peças trocadas / utilizadas", validators=[Optional()])
    performed_by = StringField("Executado por (técnico/empresa)", validators=[Optional(), Length(max=150)])
    cost = DecimalField("Custo (R$)", places=2, validators=[Optional(), NumberRange(min=0)])
    submit = SubmitField("Salvar")
