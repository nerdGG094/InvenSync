
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length

class LoginForm(FlaskForm):
    class Meta:
        csrf = False  # desabilita CSRF apenas no login
    email = StringField("E-mail", validators=[DataRequired(), ])
    password = PasswordField("Senha", validators=[DataRequired()])
    submit = SubmitField("Entrar")


class TwoFactorForm(FlaskForm):
    class Meta:
        csrf = False  # etapa do login (usuário ainda não autenticado)
    code = StringField("Código", validators=[DataRequired(), Length(min=6, max=6)])
    submit = SubmitField("Verificar")
