import os
import secrets
from flask import (Flask, render_template, request, redirect, url_for, flash,
                   send_from_directory, make_response, current_app, g)
from flask_login import current_user
from sqlalchemy import text
from .extensions import db, login_manager, csrf, limiter
from .config import Config
from .seguranca import voltar


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
        'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS intro_visto BOOLEAN NOT NULL DEFAULT false',
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
        # ===== Normalização (fase 1): colunas FK ADITIVAS + backfill por nome =====
        # Colunas novas (todas NULL) — não quebram nada; as strings legadas seguem.
        'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS department_id INTEGER REFERENCES department(id)',
        'ALTER TABLE machine ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES "user"(id)',
        'ALTER TABLE mobile_device ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES "user"(id)',
        # Impressoras: material de toner/cilindro (Estoque) p/ baixa automática na troca.
        'ALTER TABLE machine ADD COLUMN IF NOT EXISTS toner_product_id INTEGER REFERENCES product(id)',
        'ALTER TABLE machine ADD COLUMN IF NOT EXISTS drum_product_id INTEGER REFERENCES product(id)',
        # Identidade de rede estável (DHCP): MAC + hostname p/ o módulo Rede/ARP.
        'ALTER TABLE machine ADD COLUMN IF NOT EXISTS mac_address VARCHAR(20)',
        'ALTER TABLE machine ADD COLUMN IF NOT EXISTS hostname VARCHAR(120)',
        'ALTER TABLE mobile_device ADD COLUMN IF NOT EXISTS mac_address VARCHAR(20)',
        # Uptime: hosts auto-gerados a partir de impressoras/DVRs/routers.
        'ALTER TABLE monitored_host ADD COLUMN IF NOT EXISTS auto_source VARCHAR(30)',
        # Senhas cifradas dos routers: alarga p/ 255 (token Fernet de senha longa
        # estourava VARCHAR(120) e truncava). Idempotente (no-op se já é 255).
        'ALTER TABLE router ALTER COLUMN admin_password TYPE VARCHAR(255)',
        'ALTER TABLE router ALTER COLUMN wifi_password TYPE VARCHAR(255)',
        'ALTER TABLE router ALTER COLUMN wifi_password_guest TYPE VARCHAR(255)',
        # Backfill idempotente (só onde ainda está NULL), casando por nome normalizado.
        'UPDATE "user" u SET department_id = d.id FROM department d '
        'WHERE u.department_id IS NULL AND u.sector IS NOT NULL '
        "AND lower(btrim(u.sector)) = lower(btrim(d.name))",
        'UPDATE machine m SET user_id = u.id FROM "user" u '
        'WHERE m.user_id IS NULL AND m.assigned_user IS NOT NULL '
        "AND lower(btrim(m.assigned_user)) = lower(btrim(u.name))",
        'UPDATE mobile_device md SET user_id = u.id FROM "user" u '
        'WHERE md.user_id IS NULL AND md.assigned_employee IS NOT NULL '
        "AND lower(btrim(md.assigned_employee)) = lower(btrim(u.name))",
        # ===== Métricas de chamados: 1ª resposta da TI + avaliação do solicitante =====
        'ALTER TABLE ticket ADD COLUMN IF NOT EXISTS first_response_at TIMESTAMP',
        'ALTER TABLE ticket ADD COLUMN IF NOT EXISTS rating INTEGER',
        'ALTER TABLE ticket ADD COLUMN IF NOT EXISTS rated_at TIMESTAMP',
        # Backfill da 1ª resposta: menor comentário de autor diferente de quem abriu.
        'UPDATE ticket t SET first_response_at = sub.first_at FROM ('
        '  SELECT tc.ticket_id, MIN(tc.created_at) AS first_at FROM ticket_comment tc'
        '  JOIN ticket tk ON tk.id = tc.ticket_id'
        '  WHERE tc.author_id IS DISTINCT FROM tk.opened_by_id GROUP BY tc.ticket_id'
        ') sub WHERE t.id = sub.ticket_id AND t.first_response_at IS NULL',
        # Apoio ao "última limpeza por máquina" (DISTINCT ON) do dashboard.
        'CREATE INDEX IF NOT EXISTS ix_machine_cleaning_machine_started '
        'ON machine_cleaning (machine_id, started_at DESC)',
        # Segurança: solicitante do chamado por id estável (autorização não pode
        # depender do nome, que o usuário edita livremente no perfil).
        'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS last_totp_code VARCHAR(10)',
        # Tomadas: estado de disponibilidade para o aviso de "offline".
        'ALTER TABLE smart_plug ADD COLUMN IF NOT EXISTS last_seen TIMESTAMP',
        'ALTER TABLE smart_plug ADD COLUMN IF NOT EXISTS offline_since TIMESTAMP',
        'ALTER TABLE smart_plug ADD COLUMN IF NOT EXISTS offline_alerted BOOLEAN NOT NULL DEFAULT false',
        'ALTER TABLE ticket ADD COLUMN IF NOT EXISTS requester_id INTEGER REFERENCES "user"(id)',
        'UPDATE ticket t SET requester_id = u.id FROM "user" u '
        'WHERE t.requester_id IS NULL AND t.requester IS NOT NULL '
        "AND lower(btrim(t.requester)) = lower(btrim(u.name))",
    ]
    for sql in stmts:
        try:
            db.session.execute(text(sql))
            db.session.commit()
        except Exception as e:  # noqa: BLE001
            db.session.rollback()
            # Idempotente por design, mas uma falha real (lock, tipo incompatível)
            # não pode passar em silêncio — deixa rastro para diagnóstico.
            try:
                current_app.logger.warning("migração leve falhou [%s]: %s",
                                           (sql[:60] + "…") if len(sql) > 60 else sql, e)
            except Exception:  # noqa: BLE001
                pass


def _migrate_private_uploads(app):
    """Correção de segurança: anexos de chamados e NFs ficavam em
    static/uploads/{tickets,nf} (servidos pela rota pública /static, sem login).
    Move os arquivos existentes para uploads_private/... uma vez. Idempotente."""
    import shutil
    pares = [
        (os.path.join(app.static_folder, "uploads", "tickets"), app.config["ATTACH_FOLDER"]),
        (os.path.join(app.static_folder, "uploads", "nf"), app.config["NF_FOLDER"]),
    ]
    for antigo, novo in pares:
        try:
            if not os.path.isdir(antigo):
                continue
            os.makedirs(novo, exist_ok=True)
            for fn in os.listdir(antigo):
                src, dst = os.path.join(antigo, fn), os.path.join(novo, fn)
                if os.path.isfile(src) and not os.path.exists(dst):
                    shutil.move(src, dst)
        except Exception:  # noqa: BLE001
            pass


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


def _encrypt_router_secrets():
    """Cifra as senhas dos roteadores (admin + Wi-Fi) ainda em texto puro.

    Mesma estratégia idempotente do cofre: `looks_encrypted` (estrutural) impede
    re-cifrar um valor que já é token, mesmo que a chave atual não o decifre."""
    from .models.router import Router
    from .services import crypto
    fields = ("admin_password", "wifi_password", "wifi_password_guest")
    try:
        changed = False
        for r in Router.query.all():
            for f in fields:
                v = getattr(r, f)
                if v and not crypto.looks_encrypted(v):
                    setattr(r, f, crypto.encrypt(v))
                    changed = True
        if changed:
            db.session.commit()
    except Exception:  # noqa: BLE001
        db.session.rollback()


# Endpoints liberados para usuários NÃO administradores (perfil "comum").
# Eles só acessam Chamados, o próprio Perfil, autenticação e estáticos.
NON_ADMIN_PREFIXES = ("tickets.", "profile.", "auth.", "kb.", "announcements.", "intro.")
NON_ADMIN_ENDPOINTS = ("static", "health.health", "service_worker", "manifest")

_WEAK_SECRETS = {"", "dev-secret-key", "troque-por-uma-chave-secreta", "changeme"}


def _guard_secrets(app):
    """Recusa iniciar em produção com SECRET_KEY placeholder/fraco (senão o cookie
    de sessão é forjável → login como admin). VAULT_KEY vazio apenas alerta (por
    compat: deriva do SECRET_KEY em instalações antigas)."""
    import sys
    if app.config.get("TESTING") or "pytest" in sys.modules:
        return
    sk = (app.config.get("SECRET_KEY") or "").strip()
    if sk in _WEAK_SECRETS or len(sk) < 16:
        raise RuntimeError(
            "SECRET_KEY inseguro/placeholder. Defina um SECRET_KEY forte no .env "
            "(ex.: python -c \"import secrets;print(secrets.token_urlsafe(48))\").")
    if not (app.config.get("VAULT_KEY") or "").strip():
        try:
            app.logger.warning("VAULT_KEY vazio: o Cofre deriva a chave do "
                               "SECRET_KEY. Defina um VAULT_KEY dedicado no .env.")
        except Exception:  # noqa: BLE001
            pass


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    _guard_secrets(app)

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
        # Esta e a mensagem que o usuario relata ao "perder a sessao". O CSRF
        # so falha quando o token do formulario nao casa com o csrf_token da
        # SESSAO — ou seja, a pagina foi montada com uma sessao e enviada com
        # outra. Registrar o estado permite ligar (ou nao) este erro a mesma
        # causa dos registros de 'sessao_perdida'.
        from flask import session
        from .services import errorlog
        errorlog.record(
            "csrf", level="warning",
            message=("{} em {} | logado: {} | chaves na sessao: {} | {} | ip: {}").format(
                getattr(e, "description", "falha de CSRF"),
                request.endpoint or request.path,
                getattr(current_user, "is_authenticated", False),
                sorted(session.keys()) or "VAZIA",
                _diagnostico_cookie(),
                request.remote_addr))
        flash("Sessão expirada ou formulário inválido. Tente novamente.", "warning")
        return voltar(url_for("auth.login"))

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
    from .models.credential_photo import CredentialPhoto
    from .models.license import License
    from .models.kb import KbArticle
    from .models.domain import Domain
    from .models.colaborador import Colaborador
    from .models.monitor import MonitoredHost
    from .models.department import Department
    from .models.chip import SimChip
    from .models.announcement import Announcement
    from .models.error_log import ErrorLog
    from .models.asset_signature import AssetSignature
    from .models.asset_termo import AssetTermo
    from .models.smart_plug import SmartPlug
    from .models.smart_plug_schedule import SmartPlugSchedule
    from .models.printer_reading import PrinterReading
    from .models.dvr import Dvr
    from .models.dvr_detection import DvrDetection

    # Cria tabelas e semente inicial
    with app.app_context():
        db.create_all()
        _run_light_migrations()
        _migrate_private_uploads(app)   # move anexos/NFs p/ fora de /static
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
        # Cifra senhas dos roteadores (admin/Wi-Fi) ainda em texto puro.
        _encrypt_router_secrets()
        db.session.commit()

    # Loader do usuário
    @login_manager.user_loader
    def load_user(user_id):
        """Resolve o cookie de sessão no usuário.

        Devolver None aqui equivale a "não está logado", e o Flask-Login manda
        para a tela de login SEM MENSAGEM (login_message = None). Por isso cada
        motivo é registrado: antes, um `except Exception` mudo transformava
        qualquer soluço do banco em logout invisível, e não havia como
        distinguir isso de cookie expirado, token trocado ou sessão de outra
        instância. Quem relata "voltou para o login do nada" não deixava rastro
        nenhum para investigar."""
        from .services import errorlog
        raw = str(user_id)
        uid, _, tok = raw.partition(":")
        try:
            u = db.session.get(User, int(uid))
        except Exception as e:  # noqa: BLE001 — banco fora, pool esgotado, etc.
            errorlog.record("user_loader", exc=e,
                            message=f"falha ao carregar a sessão do usuário {uid}")
            return None
        if u is None:
            errorlog.record("user_loader", level="warning",
                            message=f"sessão apontava para usuário inexistente ({uid})")
            return None
        # O token é obrigatório quando o usuário tem session_token (todos têm,
        # via backfill): cookie sem token (formato legado) é rejeitado — força
        # um novo login e garante que "sair de todas as sessões" invalide
        # cookies antigos de fato.
        if (u.session_token or "") and tok != u.session_token:
            errorlog.record(
                "user_loader", level="warning",
                message=("token de sessão não confere para {} — cookie antigo, "
                         "'sair de todas as sessões', ou cookie gerado por outra "
                         "instância/SECRET_KEY").format(u.email or u.id))
            return None
        return u

    @login_manager.unauthorized_handler
    def _sem_sessao():
        """Mesmo destino de sempre (a tela de login), mas registrando o motivo.

        Só registra quando havia ALGUM cookie de autenticação: sem isso, toda
        visita anônima a uma página protegida viraria ruído no log."""
        from flask import session
        from .services import errorlog
        tinha_sessao = bool(request.cookies.get(app.config["SESSION_COOKIE_NAME"]))
        tinha_lembrete = bool(request.cookies.get(app.config["REMEMBER_COOKIE_NAME"]))
        if tinha_sessao or tinha_lembrete:
            # As CHAVES da sessão (nunca os valores) sao o dado decisivo:
            #   vazio       -> o cookie chegou mas nao decodificou (assinatura /
            #                  SECRET_KEY diferente) ou expirou
            #   sem _user_id-> decodificou, mas ninguem esta logado nele
            # O host distingue o caso de abrir o sistema por dois enderecos
            # (IP e nome), que sao potes de cookie separados no navegador.
            errorlog.record(
                "sessao_perdida", level="warning",
                message=("mandado ao login em {} — chaves na sessao: {} | {} | {}"
                         " | host: {} | ip: {}").format(
                    request.endpoint or request.path,
                    sorted(session.keys()) or "VAZIA",
                    _diagnostico_cookie(),
                    _diagnostico_lembrete(),
                    request.host,
                    request.remote_addr))
        return redirect(url_for("auth.login"))

    def _diagnostico_cookie():
        """Sessao VAZIA tem duas causas muito diferentes, e o log precisa
        separa-las: ou o cookie nao passa na assinatura (chave diferente,
        valor corrompido/truncado — o Flask entrega sessao vazia calado), ou
        ele assina certo e realmente esta vazio (foi sobrescrito). Tamanho
        entra junto porque acima de ~4093 bytes o navegador corta o cookie, e
        cortado ele sempre falha na assinatura."""
        bruto = request.cookies.get(app.config["SESSION_COOKIE_NAME"])
        if not bruto:
            return "cookie sessao: AUSENTE"
        s = app.session_interface.get_signing_serializer(app)
        if s is None:
            return f"cookie sessao: {len(bruto)}b (sem serializador)"
        try:
            dados = s.loads(bruto)
            return (f"cookie sessao: {len(bruto)}b, assinatura OK, "
                    f"conteudo={sorted(dados.keys()) or 'vazio de verdade'}")
        except Exception as e:  # noqa: BLE001
            return f"cookie sessao: {len(bruto)}b, ASSINATURA FALHOU ({type(e).__name__})"

    def _diagnostico_lembrete():
        """O 'lembrar-me' deveria restaurar a sessao sozinho. Se ele existe e
        mesmo assim caiu no login, e porque tambem nao validou."""
        bruto = request.cookies.get(app.config["REMEMBER_COOKIE_NAME"])
        if not bruto:
            return "lembrar-me: AUSENTE"
        try:
            from flask_login.utils import decode_cookie
            valor = decode_cookie(bruto)
            return ("lembrar-me: valido" if valor
                    else "lembrar-me: presente mas NAO VALIDA")
        except Exception as e:  # noqa: BLE001
            return f"lembrar-me: erro ao ler ({type(e).__name__})"

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
    from .routes.wpp import bp as wpp_bp  # teste de notificações por e-mail (SMTP)
    from .routes.backups import bp as backups_bp  # ⬅️ NOVO: backups do banco (admin)
    from .routes.colaboradores import bp as colaboradores_bp  # ⬅️ NOVO: cadastro central de colaboradores
    from .routes.monitoring import bp as monitoring_bp  # ⬅️ NOVO: monitoramento de uptime
    from .routes.departments import bp as departments_bp  # ⬅️ NOVO: cadastro de departamentos
    from .routes.chips import bp as chips_bp  # ⬅️ NOVO: controle de chips (linhas/SIM)
    from .routes.docs import bp as docs_bp  # ⬅️ NOVO: documentação viva (admin)
    from .routes.announcements import bp as announcements_bp  # ⬅️ NOVO: central de avisos (mural)
    from .routes.kiox import bp as kiox_bp  # ⬅️ NOVO: Kiox — mapa de rastreio (admin)
    from .routes.search import bp as search_bp  # ⬅️ NOVO: busca global (Ctrl+K)
    from .routes.errors import bp as errors_bp  # ⬅️ NOVO: log central de erros (admin)
    from .routes.smartplugs import bp as smartplugs_bp  # tomadas inteligentes Tuya/NeoAvant (admin)
    from .routes.cotacoes import bp as cotacoes_bp      # cotações no Mercado Livre (admin)
    from .routes.rede import bp as rede_bp              # descoberta de rede via ARP (admin)
    from .routes.intro import bp as intro_bp            # Apresentação (todos)
    from .routes.dvr import bp as dvr_bp                # CFTV / DVRs (admin)

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
    app.register_blueprint(errors_bp, url_prefix="/errors")  # ⬅️ NOVO: log de erros (admin)
    app.register_blueprint(smartplugs_bp, url_prefix="/tomadas")  # tomadas inteligentes (admin)
    app.register_blueprint(cotacoes_bp, url_prefix="/cotacoes")   # cotações Mercado Livre (admin)
    app.register_blueprint(rede_bp, url_prefix="/rede")          # descoberta de rede (admin)
    app.register_blueprint(intro_bp, url_prefix="/apresentacao")  # Apresentação (todos)
    app.register_blueprint(dvr_bp, url_prefix="/cftv")           # CFTV / DVRs (admin)

    # ===== Controle de acesso por módulo =====
    # Usuários comuns (não-admin) só acessam Chamados e o próprio Perfil.
    @app.before_request
    def _gate_non_admins():
        if not current_user.is_authenticated or current_user.is_admin:
            return
        ep = request.endpoint or ""
        # URL inexistente (sem endpoint): deixa seguir para virar 404, em vez de
        # redirecionar para os avisos (mascararia o 404 como "acesso negado").
        if not ep:
            return
        if ep in NON_ADMIN_ENDPOINTS or ep.startswith(NON_ADMIN_PREFIXES):
            return
        # Bloqueia o resto: manda para a tela inicial do perfil comum (avisos)
        return redirect(url_for("announcements.list_view"))

    # ===== 2FA obrigatório para administradores =====
    # Admin sem verificação em duas etapas é levado à configuração e só navega
    # depois de ativar (libera apenas as rotas de 2FA, logout, auth e estáticos).
    _2FA_ALLOWED = ("profile.twofa_setup", "profile.twofa_enable", "profile.twofa_qr",
                    "static", "service_worker", "health.health")

    @app.before_request
    def _force_admin_2fa():
        if app.config.get("TESTING") or not app.config.get("FORCE_ADMIN_2FA", True):
            return
        u = current_user
        if (not u.is_authenticated or not getattr(u, "is_admin", False)
                or getattr(u, "is_2fa_enabled", False)):
            return
        ep = request.endpoint or ""
        if ep in _2FA_ALLOWED or ep.startswith("auth."):
            return
        flash("Como administrador, ative a verificação em duas etapas (2FA) para continuar.", "warning")
        return redirect(url_for("profile.twofa_setup"))

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

    # ===== CSP com nonce =====
    # Cada resposta ganha um nonce aleatório; os <script> inline dos templates o
    # declaram (nonce="{{ csp_nonce() }}"). Assim o script-src dispensa
    # 'unsafe-inline' — um XSS injetado não consegue adivinhar o nonce e não roda.
    # (style-src mantém 'unsafe-inline': são atributos style=... espalhados pelos
    # templates, risco muito menor e nonce não se aplica a atributos.)
    @app.before_request
    def _gerar_csp_nonce():
        g.csp_nonce = secrets.token_urlsafe(16)

    @app.context_processor
    def _csp_nonce_ctx():
        return {"csp_nonce": lambda: getattr(g, "csp_nonce", "")}

    # Cabeçalhos de segurança em toda resposta
    if app.config.get("SECURITY_HEADERS", True):
        # Câmeras em tempo real: o player do go2rtc roda num <iframe> apontando
        # para o serviço externo (outra porta) — sem liberar essa origem no
        # frame-src/connect-src o CSP bloqueia o vídeo.
        _g2 = (app.config.get("GO2RTC_URL") or "").strip().rstrip("/")
        if _g2 and "://" not in _g2:
            _g2 = "http://" + _g2
        _g2_srcs = ""
        if _g2:
            _g2_srcs = " " + _g2 + " " + _g2.replace("https://", "wss://").replace("http://", "ws://")

        def _csp(nonce):
            return (
                "default-src 'self'; "
                "img-src 'self' data: https:; "
                f"script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net https://unpkg.com https://www.gstatic.com https://*.firebaseio.com; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; "
                "font-src 'self' data: https://cdn.jsdelivr.net; "
                f"connect-src 'self' https://*.firebaseio.com https://*.googleapis.com wss://*.firebaseio.com{_g2_srcs}; "
                f"frame-src 'self'{' ' + _g2 if _g2 else ''}; "
                "object-src 'none'; "
                "frame-ancestors 'self'; base-uri 'self'; form-action 'self'"
            )

        secure = bool(app.config.get("SESSION_COOKIE_SECURE"))

        @app.after_request
        def _security_headers(resp):
            resp.headers.setdefault("X-Content-Type-Options", "nosniff")
            resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
            resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
            resp.headers.setdefault("Content-Security-Policy",
                                    _csp(getattr(g, "csp_nonce", "")))
            resp.headers.setdefault(
                "Permissions-Policy", "geolocation=(), microphone=(), camera=()")
            # HSTS só faz sentido (e só é seguro) sob HTTPS — ligado junto com o
            # cookie Secure (BEHIND_PROXY + SESSION_COOKIE_SECURE=1).
            if secure:
                resp.headers.setdefault(
                    "Strict-Transport-Security", "max-age=31536000; includeSubDomains")
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
        # Volta para o endpoint que estourou o limite quando faz sentido (ex.: o
        # 2FA tem limite próprio), em vez de sempre jogar para o login.
        ep = request.endpoint or ""
        if ep == "auth.login_2fa":
            return redirect(url_for("auth.login_2fa"))
        if ep == "credentials.reauth":
            return voltar(url_for("credentials.list_view"))
        return redirect(url_for("auth.login"))

    # Log central de erros: captura exceções NÃO tratadas das requisições (5xx).
    from flask import got_request_exception
    from werkzeug.exceptions import HTTPException

    def _log_request_exception(sender, exception, **extra):
        if isinstance(exception, HTTPException) and (exception.code or 500) < 500:
            return  # 4xx não é erro de servidor
        from .services import errorlog
        errorlog.record("request", exc=exception)

    # weak=False: o receiver é uma função local; sem isto o blinker o coleta (GC)
    # e o sinal fica sem receivers.
    got_request_exception.connect(_log_request_exception, app, weak=False)

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

    # Backup automático do banco em segundo plano (agendador interno)
    if app.config.get("BACKUP_SCHEDULER_ENABLED", True):
        try:
            from .services import backup_scheduler
            backup_scheduler.start_scheduler(app)
        except Exception:  # noqa: BLE001
            app.logger.exception("Falha ao iniciar o agendador de backup")

    # Agendamento das tomadas inteligentes (liga/desliga por horário)
    if app.config.get("PLUG_SCHEDULER_ENABLED", True):
        try:
            from .services import plug_scheduler
            plug_scheduler.start_scheduler(app)
        except Exception:  # noqa: BLE001
            app.logger.exception("Falha ao iniciar o agendador de tomadas")

    # Coleta SNMP das impressoras (histórico + alerta de suprimento baixo)
    if app.config.get("PRINTER_MONITOR_ENABLED", True):
        try:
            from .services import printer_monitor
            printer_monitor.start_scheduler(app)
        except Exception:  # noqa: BLE001
            app.logger.exception("Falha ao iniciar o monitoramento de impressoras")

    # Detecção inteligente das câmeras (SMD): escuta os eventos dos DVRs
    if app.config.get("DVR_EVENTS_ENABLED", True):
        try:
            from .services import dvr_events
            dvr_events.start_scheduler(app)
        except Exception:  # noqa: BLE001
            app.logger.exception("Falha ao iniciar a escuta de eventos dos DVRs")

    return app
