from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, Email, Optional

class UserForm(FlaskForm):
    name = StringField("Nome", validators=[DataRequired(), Length(min=2, max=120)])
    email = StringField("E-mail", validators=[DataRequired(), Email(check_deliverability=False)])
    password = PasswordField("Senha (deixe em branco para manter)", validators=[Optional(), Length(min=6)])
    sector = StringField("Setor", validators=[Optional(), Length(max=120)])
    whatsapp = StringField("WhatsApp", validators=[Optional(), Length(max=30)])
    is_admin = BooleanField("Administrador (equipe de TI — acesso total)")
    is_active = BooleanField("Ativo", default=True)
    submit = SubmitField("Salvar")
