from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, Email


class ColaboradorForm(FlaskForm):
    name = StringField("Nome", validators=[DataRequired(), Length(min=2, max=150)])
    department = StringField("Departamento / Setor", validators=[Optional(), Length(max=120)])
    email = StringField("E-mail", validators=[Optional(), Email(check_deliverability=False), Length(max=255)])
    is_active = BooleanField("Ativo (pode ser selecionado como responsável)", default=True)

    # ===== Acesso ao sistema (login) — opcional =====
    can_login = BooleanField("Tem acesso ao sistema (login)")
    password = PasswordField("Senha (deixe em branco para manter)", validators=[Optional(), Length(min=6)])
    is_admin = BooleanField("Administrador (equipe de TI — acesso total)")
    whatsapp = StringField("WhatsApp (notificações)", validators=[Optional(), Length(max=30)])

    submit = SubmitField("Salvar")
