from flask_wtf import FlaskForm
from wtforms import StringField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length


class DepartmentForm(FlaskForm):
    name = StringField("Nome do departamento", validators=[DataRequired(), Length(min=2, max=120)])
    is_active = BooleanField("Ativo (aparece na seleção de colaboradores)", default=True)
    submit = SubmitField("Salvar")
