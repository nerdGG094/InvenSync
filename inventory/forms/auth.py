
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired

class LoginForm(FlaskForm):
    class Meta:
        csrf = False  # desabilita CSRF apenas no login
    email = StringField("E-mail", validators=[DataRequired(), ])
    password = PasswordField("Senha", validators=[DataRequired()])
    submit = SubmitField("Entrar")
