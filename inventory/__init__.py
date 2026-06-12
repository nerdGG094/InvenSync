import os
from flask import Flask, render_template, request, redirect, url_for
from flask_login import current_user
from .extensions import db, login_manager
from .config import Config

# Endpoints liberados para usuários NÃO administradores (perfil "comum").
# Eles só acessam Chamados, o próprio Perfil, autenticação e estáticos.
NON_ADMIN_PREFIXES = ("tickets.", "profile.", "auth.")
NON_ADMIN_ENDPOINTS = ("static", "health.health")

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
    from .models.machine_maintenance import MachineMaintenance
    from .models.ticket import Ticket, TicketComment
    from .models.ticket_attachment import TicketAttachment
    from .models.mobile import MobileDevice
    from .models.router import Router
    from .models.audit import AuditLog
    from .models.credential import Credential
    from .models.license import License

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
    from .routes.mobile import bp as mobile_bp  # ⬅️ NOVO: cadastro de celulares
    from .routes.routers import bp as routers_bp  # ⬅️ NOVO: cadastro de roteadores
    from .routes.audit import bp as audit_bp  # ⬅️ NOVO: trilha de auditoria
    from .routes.assets import bp as assets_bp  # ⬅️ NOVO: ativos por colaborador
    from .routes.labels import bp as labels_bp  # ⬅️ NOVO: etiquetas QR
    from .routes.maintenance import bp as maintenance_bp  # ⬅️ NOVO: manutenção de máquinas
    from .routes.credentials import bp as credentials_bp  # ⬅️ NOVO: cofre de senhas
    from .routes.licenses import bp as licenses_bp  # ⬅️ NOVO: licenças e garantias
    from .routes.profile import bp as profile_bp  # ⬅️ NOVO: meu perfil
    from .routes.wpp import bp as wpp_bp  # ⬅️ NOVO: conexão WhatsApp (admin)

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
    app.register_blueprint(mobile_bp, url_prefix="/mobile")  # ⬅️ NOVO: celulares
    app.register_blueprint(routers_bp, url_prefix="/routers")  # ⬅️ NOVO: roteadores
    app.register_blueprint(audit_bp, url_prefix="/audit")  # ⬅️ NOVO: auditoria
    app.register_blueprint(assets_bp, url_prefix="/assets")  # ⬅️ NOVO: ativos por colaborador
    app.register_blueprint(labels_bp, url_prefix="/labels")  # ⬅️ NOVO: etiquetas QR
    app.register_blueprint(maintenance_bp, url_prefix="/machines/maintenance")  # ⬅️ NOVO: manutenção
    app.register_blueprint(credentials_bp, url_prefix="/credentials")  # ⬅️ NOVO: cofre de senhas
    app.register_blueprint(licenses_bp, url_prefix="/licenses")  # ⬅️ NOVO: licenças e garantias
    app.register_blueprint(profile_bp, url_prefix="/profile")  # ⬅️ NOVO: meu perfil
    app.register_blueprint(wpp_bp, url_prefix="/wpp")  # ⬅️ NOVO: conexão WhatsApp

    # ===== Controle de acesso por módulo =====
    # Usuários comuns (não-admin) só acessam Chamados e o próprio Perfil.
    @app.before_request
    def _gate_non_admins():
        if not current_user.is_authenticated or current_user.is_admin:
            return
        ep = request.endpoint or ""
        if ep in NON_ADMIN_ENDPOINTS or ep.startswith(NON_ADMIN_PREFIXES):
            return
        # Bloqueia o resto: manda para a área de chamados
        return redirect(url_for("tickets.list_view"))

    # Disponibiliza helper de avatar nos templates
    @app.context_processor
    def _inject_helpers():
        def avatar_url(user):
            if user and getattr(user, "photo", None):
                return url_for("static", filename="uploads/avatars/" + user.photo)
            return None
        return {"avatar_url": avatar_url}

    # Handlers de erro
    @app.errorhandler(403)
    def forbidden(e):
        return render_template("error.html", title="Acesso negado",
                               message="Você não tem permissão para acessar esta página."), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", title="404", message="Página não encontrada"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("error.html", title="Erro", message="Erro interno no servidor"), 500

    return app
