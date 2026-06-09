from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, Email, Optional

class UserForm(FlaskForm):
    name = StringField("Nome", validators=[DataRequired(), Length(min=2, max=120)])
    email = StringField("E-mail", validators=[DataRequired(), Email(check_deliverability=False)])
    password = PasswordField("Senha (deixe em branco para manter)", validators=[Optional(), Length(min=6)])
    is_admin = BooleanField("Administrador")
    is_active = BooleanField("Ativo", default=True)
    submit = SubmitField("Salvar")
