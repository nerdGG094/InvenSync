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
    from .models.machine import Machine
    from .models.machine_cleaning import MachineCleaning
    from .models.ticket import Ticket, TicketComment

    # Cria tabelas e semente inicial
    with app.app_context():
        db.create_all()
        # Semente de categoria/fornecedor padrão desativada — a base é mantida
        # limpa intencionalmente; cadastre categorias/fornecedores pela interface.
        #
        # Cria o admin padrão APENAS quando não existe NENHUM usuário, evitando
        # recriar "admin@local" caso ele seja renomeado/excluído pela interface.
        if not User.query.first():
            admin = User(name="Administrador", email="admin@local", is_admin=True)
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
    from .routes.health import bp as health_bp  # ⬅️ NOVO: endpoint /health (launcher)
    from .routes.machines import bp as machines_bp  # ⬅️ NOVO: cadastro de máquinas
    from .routes.cleanings import bp as cleanings_bp  # ⬅️ NOVO: limpeza de máquinas
    from .routes.tickets import bp as tickets_bp  # ⬅️ NOVO: controlador de chamados

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(categories_bp, url_prefix="/categories")
    app.register_blueprint(suppliers_bp, url_prefix="/suppliers")
    app.register_blueprint(products_bp, url_prefix="/products")
    app.register_blueprint(movements_bp, url_prefix="/movements")
    app.register_blueprint(reports_bp, url_prefix="/reports")
    app.register_blueprint(users_bp, url_prefix="/users")  # ⬅️ NOVO: rota /users
    app.register_blueprint(kanban_bp, url_prefix="/kanban")  # ⬅️ NOVO: rota /kanban
    app.register_blueprint(health_bp)  # ⬅️ NOVO: /health (sem login, para o launcher)
    app.register_blueprint(machines_bp, url_prefix="/machines")  # ⬅️ NOVO: rota /machines
    app.register_blueprint(cleanings_bp, url_prefix="/machines/cleanings")  # ⬅️ NOVO: limpezas
    app.register_blueprint(tickets_bp, url_prefix="/tickets")  # ⬅️ NOVO: chamados

    # Handlers de erro
    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", title="404", message="Página não encontrada"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("error.html", title="Erro", message="Erro interno no servidor"), 500

    return app
