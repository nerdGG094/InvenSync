import os
from flask import Flask, render_template
from .extensions import db, login_manager
from .config import Config

def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)

    # Garante a pasta instance
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    # Extensões
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = None
    login_manager.needs_refresh_message = None

    # Importa modelos para o SQLAlchemy conhecer
    from .models.user import User
    from .models.category import Category
    from .models.supplier import Supplier
    from .models.product import Product
    from .models.movement import StockMovement

    # Cria tabelas e semente inicial
    with app.app_context():
        db.create_all()
        if not Category.query.first():
            db.session.add(Category(name="Geral", description="Categoria padrão"))
        if not Supplier.query.first():
            db.session.add(Supplier(name="Fornecedor Padrão"))
        admin = User.query.filter_by(email="admin@local").first()
        if not admin:
            admin = User(name="Administrador", email="admin@local")
            admin.set_password("admin")
            db.session.add(admin)
        db.session.commit()

    # Loader do usuário
    @login_manager.user_loader
    def load_user(user_id):
        try:
            return User.query.get(int(user_id))
        except Exception:
            return None

    # Blueprints
    from .routes.auth import bp as auth_bp
    from .routes.dashboard import bp as dashboard_bp
    from .routes.categories import bp as categories_bp
    from .routes.suppliers import bp as suppliers_bp
    from .routes.products import bp as products_bp
    from .routes.movements import bp as movements_bp
    from .routes.reports import bp as reports_bp
    from .routes.users import bp as users_bp  # ⬅️ NOVO: blueprint de usuários
    from .routes.kanban import bp as kanban_bp  # ⬅️ NOVO: board kanban de estoque

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(categories_bp, url_prefix="/categories")
    app.register_blueprint(suppliers_bp, url_prefix="/suppliers")
    app.register_blueprint(products_bp, url_prefix="/products")
    app.register_blueprint(movements_bp, url_prefix="/movements")
    app.register_blueprint(reports_bp, url_prefix="/reports")
    app.register_blueprint(users_bp, url_prefix="/users")  # ⬅️ NOVO: rota /users
    app.register_blueprint(kanban_bp, url_prefix="/kanban")  # ⬅️ NOVO: rota /kanban

    # Handlers de erro
    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", title="404", message="Página não encontrada"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("error.html", title="Erro", message="Erro interno no servidor"), 500

    return app
