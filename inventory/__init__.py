import os
from flask import Flask, render_template, request, redirect, url_for
from flask_login import current_user
from sqlalchemy import text
from .extensions import db, login_manager
from .config import Config


def _run_light_migrations():
    """Ajustes de schema que o db.create_all() não faz em tabelas já existentes.

    Idempotente: usa ADD COLUMN IF NOT EXISTS. "user" é palavra reservada no
    PostgreSQL, por isso vem entre aspas.
    """
    stmts = [
        'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS totp_secret VARCHAR(64)',
        'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS is_2fa_enabled BOOLEAN NOT NULL DEFAULT false',
    ]
    for sql in stmts:
        try:
            db.session.execute(text(sql))
            db.session.commit()
        except Exception:  # noqa: BLE001
            db.session.rollback()


def _seed_colaboradores_from_assets():
    """Importa para a tabela Colaboradores os nomes de responsáveis que já
    existem em Máquinas/Celulares. Idempotente: só insere o que ainda falta."""
    from .models.colaborador import Colaborador
    from .models.machine import Machine
    from .models.mobile import MobileDevice
    try:
        existentes = {(c.name or "").strip().lower() for c in Colaborador.query.all()}
        novos = {}
        for m in Machine.query.all():
            nome = (m.assigned_user or "").strip()
            chave = nome.lower()
            if nome and chave not in existentes and chave not in novos:
                novos[chave] = (nome, (m.sector or "").strip() or None)
        for d in MobileDevice.query.all():
            nome = (d.assigned_employee or "").strip()
            chave = nome.lower()
            if nome and chave not in existentes and chave not in novos:
                novos[chave] = (nome, (d.sector or "").strip() or None)
        for nome, dept in novos.values():
            db.session.add(Colaborador(name=nome, department=dept, is_active=True))
        if novos:
            db.session.commit()
    except Exception:  # noqa: BLE001
        db.session.rollback()

# Endpoints liberados para usuários NÃO administradores (perfil "comum").
# Eles só acessam Chamados, o próprio Perfil, autenticação e estáticos.
NON_ADMIN_PREFIXES = ("tickets.", "profile.", "auth.", "kb.")
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
    from .models.kb import KbArticle
    from .models.domain import Domain
    from .models.colaborador import Colaborador
    from .models.monitor import MonitoredHost

    # Cria tabelas e semente inicial
    with app.app_context():
        db.create_all()
        _run_light_migrations()
        _seed_colaboradores_from_assets()
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
    from .routes.kb import bp as kb_bp  # ⬅️ NOVO: base de conhecimento
    from .routes.domains import bp as domains_bp  # ⬅️ NOVO: domínios por empresa
    from .routes.profile import bp as profile_bp  # ⬅️ NOVO: meu perfil
    from .routes.wpp import bp as wpp_bp  # ⬅️ NOVO: teste de notificações WhatsApp (CallMeBot)
    from .routes.backups import bp as backups_bp  # ⬅️ NOVO: backups do banco (admin)
    from .routes.colaboradores import bp as colaboradores_bp  # ⬅️ NOVO: cadastro central de colaboradores
    from .routes.monitoring import bp as monitoring_bp  # ⬅️ NOVO: monitoramento de uptime

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
    app.register_blueprint(mobile_bp, url_prefix="/machines/mobile")  # ⬅️ celulares (submódulo de Máquinas)
    app.register_blueprint(routers_bp, url_prefix="/routers")  # ⬅️ NOVO: roteadores
    app.register_blueprint(audit_bp, url_prefix="/audit")  # ⬅️ NOVO: auditoria
    app.register_blueprint(assets_bp, url_prefix="/assets")  # ⬅️ NOVO: ativos por colaborador
    app.register_blueprint(labels_bp, url_prefix="/labels")  # ⬅️ NOVO: etiquetas QR
    app.register_blueprint(maintenance_bp, url_prefix="/machines/maintenance")  # ⬅️ NOVO: manutenção
    app.register_blueprint(credentials_bp, url_prefix="/credentials")  # ⬅️ NOVO: cofre de senhas
    app.register_blueprint(licenses_bp, url_prefix="/licenses")  # ⬅️ NOVO: licenças e garantias
    app.register_blueprint(kb_bp, url_prefix="/kb")  # ⬅️ NOVO: base de conhecimento
    app.register_blueprint(domains_bp, url_prefix="/domains")  # ⬅️ NOVO: domínios
    app.register_blueprint(profile_bp, url_prefix="/profile")  # ⬅️ NOVO: meu perfil
    app.register_blueprint(wpp_bp, url_prefix="/wpp")  # ⬅️ NOVO: teste de notificações WhatsApp
    app.register_blueprint(backups_bp, url_prefix="/backups")  # ⬅️ NOVO: backups do banco
    app.register_blueprint(colaboradores_bp, url_prefix="/colaboradores")  # ⬅️ NOVO: colaboradores
    app.register_blueprint(monitoring_bp, url_prefix="/machines/monitoring")  # ⬅️ monitoramento (submódulo de Máquinas)

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

    # Monitoramento de uptime em segundo plano (ping/HTTP + alerta WhatsApp)
    if app.config.get("MONITORING_ENABLED", True):
        try:
            from .services import monitoring
            monitoring.start_scheduler(app)
        except Exception:  # noqa: BLE001
            app.logger.exception("Falha ao iniciar o monitoramento de uptime")

    return app
