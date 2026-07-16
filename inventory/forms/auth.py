
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length

class LoginForm(FlaskForm):
    # CSRF habilitado (protege contra login-CSRF); o template emite o token via
    # form.hidden_tag().
    email = StringField("E-mail", validators=[DataRequired(), ])
    password = PasswordField("Senha", validators=[DataRequired()])
    submit = SubmitField("Entrar")


class TwoFactorForm(FlaskForm):
    code = StringField("Código", validators=[DataRequired(), Length(min=6, max=6)])
    submit = SubmitField("Verificar")
