import os
from flask import (Flask, render_template, request, redirect, url_for, flash,
                   send_from_directory, make_response)
from flask_login import current_user
from sqlalchemy import text
from .extensions import db, login_manager, csrf, limiter
from .config import Config


def _run_light_migrations():
    """Ajustes de schema que o db.create_all() não faz em tabelas já existentes.

    Idempotente: usa ADD COLUMN IF NOT EXISTS. "user" é palavra reservada no
    PostgreSQL, por isso vem entre aspas.
    """
    stmts = [
        'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS totp_secret VARCHAR(64)',
        # Cofre de senhas: armazenado cifrado (token Fernet) — TEXT comporta o tamanho.
        "ALTER TABLE credential ALTER COLUMN password TYPE TEXT",
        # Token de sessão p/ "sair de todas as sessões" (backfill aleatório nos já existentes).
        'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS session_token VARCHAR(32)',
        "UPDATE \"user\" SET session_token = md5(random()::text || id::text) WHERE session_token IS NULL",
        # Bloqueio de conta por tentativas de senha erradas.
        'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS failed_logins INTEGER NOT NULL DEFAULT 0',
        'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP',
        # Preferência de tema (claro/escuro) por usuário.
        "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS theme VARCHAR(10) NOT NULL DEFAULT 'dark'",
        'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS is_2fa_enabled BOOLEAN NOT NULL DEFAULT false',
        'ALTER TABLE stock_movement ADD COLUMN IF NOT EXISTS nf_filename VARCHAR(255)',
        'ALTER TABLE stock_movement ADD COLUMN IF NOT EXISTS nf_original_name VARCHAR(255)',
        # Unificação Colaboradores + Usuários: o login passa a ser opcional.
        'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS can_login BOOLEAN NOT NULL DEFAULT false',
        'ALTER TABLE "user" ALTER COLUMN password_hash DROP NOT NULL',
        'ALTER TABLE "user" ALTER COLUMN email DROP NOT NULL',
        # Quem já tinha senha era um usuário de login — preserva o acesso.
        'UPDATE "user" SET can_login = true WHERE password_hash IS NOT NULL AND can_login = false',
        # Celular compartilhado: até 2 funcionários adicionais no mesmo aparelho.
        'ALTER TABLE mobile_device ADD COLUMN IF NOT EXISTS assigned_employee_2 VARCHAR(150)',
        'ALTER TABLE mobile_device ADD COLUMN IF NOT EXISTS assigned_employee_3 VARCHAR(150)',
        # Etiqueta QR aplicada no aparelho (controle do analista na tela de Etiquetas).
        'ALTER TABLE machine ADD COLUMN IF NOT EXISTS label_applied BOOLEAN NOT NULL DEFAULT false',
        'ALTER TABLE router ADD COLUMN IF NOT EXISTS label_applied BOOLEAN NOT NULL DEFAULT false',
        'ALTER TABLE mobile_device ADD COLUMN IF NOT EXISTS label_applied BOOLEAN NOT NULL DEFAULT false',
        # KioX (app de rastreio) instalado no celular.
        'ALTER TABLE mobile_device ADD COLUMN IF NOT EXISTS kiox_installed BOOLEAN NOT NULL DEFAULT false',
    ]
    for sql in stmts:
        try:
            db.session.execute(text(sql))
            db.session.commit()
        except Exception:  # noqa: BLE001
            db.session.rollback()


def _seed_people_into_users():
    """Migração ÚNICA da antiga tabela `colaborador` para o cadastro central `user`.

    Copia para `user` cada colaborador que ainda não exista lá (casando por nome,
    case-insensitive) como pessoa SEM login (can_login=False) e, em seguida,
    ESVAZIA a tabela `colaborador`. Como a tabela é zerada, isto roda de fato uma
    só vez — em boots seguintes não há nada a importar.

    Importante: NÃO recriamos pessoas a partir de Máquinas/Celulares. Os nomes
    vinculados a ativos continuam aparecendo no seletor de "responsável" via
    `services.people` (união em tempo real), mas não são recriados aqui — assim,
    quem o admin excluir na tela de Colaboradores permanece excluído."""
    from .models.user import User
    from .models.colaborador import Colaborador
    try:
        # Nada legado para migrar? Sai cedo — evita varrer a tabela `user` (duas
        # vezes) a cada boot depois que a migração já ocorreu uma vez.
        if not Colaborador.query.first():
            return
        existentes = {(u.name or "").strip().lower() for u in User.query.all()}
        emails = {(u.email or "").strip().lower() for u in User.query.all() if u.email}
        novos = {}  # chave_nome -> (nome, setor, email)

        for c in Colaborador.query.all():
            nome = (c.name or "").strip()
            chave = nome.lower()
            if nome and chave not in existentes and chave not in novos:
                email = (c.email or "").strip().lower() or None
                if email and email in emails:
                    email = None  # evita violar a unicidade de e-mail
                if email:
                    emails.add(email)
                novos[chave] = (nome, (c.department or "").strip() or None, email)

        for nome, setor, email in novos.values():
            db.session.add(User(
                name=nome, sector=setor, email=email,
                is_active=True, is_admin=False, can_login=False,
            ))

        # Esvazia a tabela antiga: todo colaborador já está representado em `user`
        # (criado acima ou casado por nome). Evita ressurreição em boots futuros.
        migrou_colaboradores = Colaborador.query.count() > 0
        if migrou_colaboradores:
            Colaborador.query.delete()

        if novos or migrou_colaboradores:
            db.session.commit()
    except Exception:  # noqa: BLE001
        db.session.rollback()

def _backfill_patrimony():
    """Gera nº de patrimônio para máquinas/celulares já cadastrados sem o campo.

    Idempotente: só preenche quem está com `patrimony` vazio, continuando a
    sequência única da empresa (PAT-0001, PAT-0002, ...). Ordena por id para
    uma atribuição estável (máquinas primeiro, depois celulares)."""
    from .models.machine import Machine
    from .models.mobile import MobileDevice
    from .services import patrimony
    try:
        # Carrega só quem está SEM patrimônio (filtra no banco), em vez de varrer
        # as tabelas inteiras a cada boot depois que o backfill já foi feito.
        from sqlalchemy import or_, func
        def _sem_patrimonio(model):
            return (model.query
                    .filter(or_(model.patrimony.is_(None),
                                func.trim(model.patrimony) == ""))
                    .order_by(model.id.asc()).all())
        faltantes = _sem_patrimonio(Machine) + _sem_patrimonio(MobileDevice)
        if not faltantes:
            return
        seq = patrimony.current_max_seq()
        for obj in faltantes:
            seq += 1
            obj.patrimony = patrimony.format_seq(seq)
        db.session.commit()
    except Exception:  # noqa: BLE001
        db.session.rollback()


def _seed_departments_from_sectors():
    """Popula a tabela `department` com os setores já existentes nos colaboradores.

    Roda de forma idempotente: cria um Department para cada `User.sector` distinto
    que ainda não exista (casando por nome, case-insensitive). Assim, ao ligar o
    novo seletor de departamentos, todas as pessoas já cadastradas continuam com
    o setor disponível na lista — nada se perde."""
    from .models.user import User
    from .models.department import Department
    try:
        existentes = {(d.name or "").strip().lower() for d in Department.query.all()}
        novos = {}  # chave -> nome original
        # Lê apenas os setores DISTINTOS (uma coluna) em vez de hidratar todos os
        # usuários a cada boot — mesmo resultado, muito menos carga.
        for (sector,) in db.session.query(User.sector).distinct():
            nome = (sector or "").strip()
            chave = nome.lower()
            if nome and chave not in existentes and chave not in novos:
                novos[chave] = nome
        for nome in novos.values():
            db.session.add(Department(name=nome, is_active=True))
        if novos:
            db.session.commit()
    except Exception:  # noqa: BLE001
        db.session.rollback()


def _encrypt_credentials():
    """Cifra senhas do cofre que ainda estejam em texto puro (migração única).

    Idempotente: usa `looks_encrypted` (detecção estrutural) — assim NUNCA
    re-cifra um valor que já é um token, mesmo que a chave atual não o decifre.
    Isso evita o empilhamento de camadas que corrompia o cofre quando a
    SECRET_KEY/VAULT_KEY mudava entre boots."""
    from .models.credential import Credential
    from .services import crypto
    try:
        changed = False
        for c in Credential.query.filter(Credential.password.isnot(None)).all():
            if c.password and not crypto.looks_encrypted(c.password):
                c.password = crypto.encrypt(c.password)
                changed = True
        if changed:
            db.session.commit()
    except Exception:  # noqa: BLE001
        db.session.rollback()


# Endpoints liberados para usuários NÃO administradores (perfil "comum").
# Eles só acessam Chamados, o próprio Perfil, autenticação e estáticos.
NON_ADMIN_PREFIXES = ("tickets.", "profile.", "auth.", "kb.", "announcements.")
NON_ADMIN_ENDPOINTS = ("static", "health.health", "service_worker", "manifest")

def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)

    # Garante a pasta instance
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    # Atrás de proxy reverso HTTPS (IIS/nginx/Caddy): honra X-Forwarded-* para
    # gerar URLs https corretas e respeitar o esquema. Ative com BEHIND_PROXY=1.
    if os.environ.get("BEHIND_PROXY", "0") in ("1", "true", "True"):
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # Extensões
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = None
    login_manager.needs_refresh_message = None
    csrf.init_app(app)
    limiter.init_app(app)

    # Falha de CSRF (token ausente/expirado): mensagem amigável + volta à página.
    from flask_wtf.csrf import CSRFError

    @app.errorhandler(CSRFError)
    def _handle_csrf_error(e):
        flash("Sessão expirada ou formulário inválido. Tente novamente.", "warning")
        return redirect(request.referrer or url_for("auth.login"))

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
    from .models.department import Department
    from .models.chip import SimChip
    from .models.announcement import Announcement

    # Cria tabelas e semente inicial
    with app.app_context():
        db.create_all()
        _run_light_migrations()
        # Semente de categoria/fornecedor padrão desativada — a base é mantida
        # limpa intencionalmente; cadastre categorias/fornecedores pela interface.
        #
        # Cria o admin padrão APENAS quando não existe NENHUM usuário, evitando
        # recriar "admin@local" caso ele seja renomeado/excluído pela interface.
        # (Roda ANTES de importar colaboradores para garantir que sempre exista
        # uma conta de login de administrador.)
        if not User.query.first():
            admin = User(name="Administrador", email="admin@local",
                         is_admin=True, can_login=True)
            admin.set_password("admin")
            db.session.add(admin)
            db.session.commit()
        # Unifica colaboradores/ativos no cadastro central de pessoas (user).
        _seed_people_into_users()
        # Popula os departamentos a partir dos setores já usados nos colaboradores.
        _seed_departments_from_sectors()
        # Gera nº de patrimônio para máquinas/celulares já cadastrados sem o campo.
        _backfill_patrimony()
        # Cifra senhas do cofre que ainda estejam em texto puro.
        _encrypt_credentials()
        db.session.commit()

    # Loader do usuário
    @login_manager.user_loader
    def load_user(user_id):
        try:
            raw = str(user_id)
            uid, _, tok = raw.partition(":")
            u = User.query.get(int(uid))
            if u is None:
                return None
            # Se o id traz token (formato novo), precisa bater com o atual.
            # Cookies legados (só "id") continuam válidos até o próximo login.
            if tok and (u.session_token or "") and tok != u.session_token:
                return None
            return u
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
    from .routes.departments import bp as departments_bp  # ⬅️ NOVO: cadastro de departamentos
    from .routes.chips import bp as chips_bp  # ⬅️ NOVO: controle de chips (linhas/SIM)
    from .routes.docs import bp as docs_bp  # ⬅️ NOVO: documentação viva (admin)
    from .routes.announcements import bp as announcements_bp  # ⬅️ NOVO: central de avisos (mural)
    from .routes.kiox import bp as kiox_bp  # ⬅️ NOVO: Kiox — mapa de rastreio (admin)
    from .routes.search import bp as search_bp  # ⬅️ NOVO: busca global (Ctrl+K)

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(categories_bp, url_prefix="/categories")
    app.register_blueprint(suppliers_bp, url_prefix="/suppliers")
    app.register_blueprint(products_bp, url_prefix="/products")
    app.register_blueprint(movements_bp, url_prefix="/movements")
    app.register_blueprint(reports_bp, url_prefix="/reports")
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
    app.register_blueprint(departments_bp, url_prefix="/departments")  # ⬅️ NOVO: departamentos
    app.register_blueprint(chips_bp, url_prefix="/machines/chips")  # ⬅️ chips (submódulo de Máquinas)
    app.register_blueprint(docs_bp, url_prefix="/docs")  # ⬅️ NOVO: documentação viva (submódulo de Admin)
    app.register_blueprint(announcements_bp, url_prefix="/avisos")  # ⬅️ NOVO: central de avisos (mural)
    app.register_blueprint(kiox_bp, url_prefix="/kiox")  # ⬅️ NOVO: Kiox — mapa de rastreio (submódulo de Admin)
    app.register_blueprint(search_bp, url_prefix="/busca")  # ⬅️ NOVO: busca global (Ctrl+K)

    # ===== Controle de acesso por módulo =====
    # Usuários comuns (não-admin) só acessam Chamados e o próprio Perfil.
    @app.before_request
    def _gate_non_admins():
        if not current_user.is_authenticated or current_user.is_admin:
            return
        ep = request.endpoint or ""
        if ep in NON_ADMIN_ENDPOINTS or ep.startswith(NON_ADMIN_PREFIXES):
            return
        # Bloqueia o resto: manda para a tela inicial do perfil comum (avisos)
        return redirect(url_for("announcements.list_view"))

    # Disponibiliza helper de avatar nos templates
    @app.context_processor
    def _inject_helpers():
        def avatar_url(user):
            if user and getattr(user, "photo", None):
                return url_for("static", filename="uploads/avatars/" + user.photo)
            return None

        def page_url(page):
            """URL da página `page` preservando os filtros atuais da query."""
            args = request.args.to_dict(flat=True)
            args["page"] = page
            return url_for(request.endpoint, **args)

        return {"avatar_url": avatar_url, "page_url": page_url}

    # Cabeçalhos de segurança em toda resposta
    if app.config.get("SECURITY_HEADERS", True):
        csp = (
            "default-src 'self'; "
            "img-src 'self' data: https:; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com https://www.gstatic.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; "
            "font-src 'self' data: https://cdn.jsdelivr.net; "
            "connect-src 'self' https://*.firebaseio.com https://*.googleapis.com wss://*.firebaseio.com; "
            "frame-ancestors 'self'; base-uri 'self'; form-action 'self'"
        )

        @app.after_request
        def _security_headers(resp):
            resp.headers.setdefault("X-Content-Type-Options", "nosniff")
            resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
            resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
            resp.headers.setdefault("Content-Security-Policy", csp)
            return resp

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

    # Excesso de tentativas (rate limit do login)
    @app.errorhandler(429)
    def too_many_requests(e):
        flash("Muitas tentativas em pouco tempo. Aguarde um instante e tente novamente.", "warning")
        return redirect(url_for("auth.login"))

    # PWA: service worker servido da raiz (escopo "/") para controlar todo o app
    @app.route("/sw.js", endpoint="service_worker")
    def _service_worker():
        resp = make_response(send_from_directory(app.static_folder, "sw.js"))
        resp.headers["Content-Type"] = "application/javascript"
        resp.headers["Service-Worker-Allowed"] = "/"
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    # Monitoramento de uptime em segundo plano (ping/HTTP + alerta WhatsApp)
    if app.config.get("MONITORING_ENABLED", True):
        try:
            from .services import monitoring
            monitoring.start_scheduler(app)
        except Exception:  # noqa: BLE001
            app.logger.exception("Falha ao iniciar o monitoramento de uptime")

    # Alertas proativos (estoque/licenças/chamados) em segundo plano
    if app.config.get("ALERTS_ENABLED", True):
        try:
            from .services import alerts
            alerts.start_scheduler(app)
        except Exception:  # noqa: BLE001
            app.logger.exception("Falha ao iniciar os alertas proativos")

    return app
