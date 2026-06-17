from flask_wtf import FlaskForm
from wtforms import StringField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, Email


class ColaboradorForm(FlaskForm):
    name = StringField("Nome", validators=[DataRequired(), Length(min=2, max=150)])
    department = StringField("Departamento / Setor", validators=[Optional(), Length(max=120)])
    email = StringField("E-mail", validators=[Optional(), Email(check_deliverability=False), Length(max=255)])
    is_active = BooleanField("Ativo", default=True)
    submit = SubmitField("Salvar")
