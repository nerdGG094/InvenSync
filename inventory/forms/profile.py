from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, Email, Optional, EqualTo


class ProfileForm(FlaskForm):
    name = StringField("Nome", validators=[DataRequired(), Length(min=2, max=120)])
    email = StringField("E-mail", validators=[DataRequired(), Email(check_deliverability=False)])
    sector = StringField("Setor", validators=[Optional(), Length(max=120)])
    photo = FileField("Foto de perfil", validators=[
        Optional(),
        FileAllowed(["png", "jpg", "jpeg", "gif", "webp"], "Apenas imagens (png, jpg, gif, webp)."),
    ])
    new_password = PasswordField("Nova senha", validators=[Optional(), Length(min=6)])
    confirm = PasswordField("Confirmar nova senha", validators=[
        Optional(), EqualTo("new_password", message="As senhas não conferem."),
    ])
    submit = SubmitField("Salvar alterações")
