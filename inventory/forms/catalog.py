
from flask_wtf import FlaskForm
from wtforms import (
    StringField, TextAreaField, SubmitField, IntegerField, DecimalField,
    SelectField, DateField,
)
from wtforms.validators import DataRequired, Length, Email, Optional, NumberRange

class CategoryForm(FlaskForm):
    name = StringField("Nome", validators=[DataRequired(), Length(min=2, max=120)])
    description = TextAreaField("Descrição", validators=[Optional(), Length(max=500)])
    submit = SubmitField("Salvar")

class SupplierForm(FlaskForm):
    name = StringField("Nome", validators=[DataRequired(), Length(min=2, max=200)])
    email = StringField("E-mail", validators=[Optional(), Email(check_deliverability=False)])
    phone = StringField("Telefone", validators=[Optional(), Length(max=50)])
    notes = TextAreaField("Notas", validators=[Optional(), Length(max=500)])
    submit = SubmitField("Salvar")

class ProductForm(FlaskForm):
    sku = StringField("SKU", validators=[Optional(), Length(min=1, max=120)])
    name = StringField("Nome", validators=[DataRequired(), Length(min=2, max=200)])
    description = TextAreaField("Descrição", validators=[Optional()])
    # novos campos:
    item_type = SelectField("Tipo", validators=[DataRequired()])              # choices vêm da rota
    unit = SelectField("Unidade de medida", validators=[DataRequired()])
    category_id = SelectField("Categoria", coerce=int, validators=[Optional()])
    supplier_id = SelectField("Fornecedor", coerce=int, validators=[Optional()])
    min_stock = IntegerField("Estoque mínimo", validators=[NumberRange(min=0)], default=0)
    price = DecimalField("Preço", places=2, validators=[NumberRange(min=0)], default=0)

    # ===== Campos específicos de TI =====
    brand = StringField("Marca", validators=[Optional(), Length(max=120)])
    model = StringField("Modelo", validators=[Optional(), Length(max=120)])
    patrimony = StringField("Nº Patrimônio", validators=[Optional(), Length(max=60)])
    serial_number = StringField("Nº de Série", validators=[Optional(), Length(max=120)])
    location = StringField("Localização", validators=[Optional(), Length(max=120)])
    compatibility = TextAreaField("Compatibilidade", validators=[Optional()])
    expiry_date = DateField("Validade", validators=[Optional()])

    # Usuário responsável (de Máquinas) + setor automático
    responsible_user = SelectField("Usuário responsável", validators=[Optional()], choices=[])
    responsible_sector = StringField("Setor", validators=[Optional(), Length(max=120)])

    submit = SubmitField("Salvar")

class MovementForm(FlaskForm):
    product_id = SelectField("Produto", coerce=int)
    movement_type = SelectField("Tipo", choices=[("IN","Entrada"),("OUT","Saída")])
    quantity = IntegerField("Quantidade", validators=[DataRequired(), NumberRange(min=1)])
    unit_cost = DecimalField("Custo unitário (opcional)", places=2, validators=[Optional(), NumberRange(min=0)])
    # Usuário responsável (de Máquinas) + setor automático
    responsible_user = SelectField("Usuário responsável", validators=[Optional()], choices=[])
    responsible_sector = StringField("Setor", validators=[Optional(), Length(max=120)])
    note = TextAreaField("Observação", validators=[Optional()])
    submit = SubmitField("Registrar")
