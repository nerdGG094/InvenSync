# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**InvenSync** — internal IT asset/inventory + helpdesk web app for *Refrigerantes Jaboti*. Flask + PostgreSQL, served in production via waitress and wrapped by a PyQt5 desktop launcher. The codebase and UI are in **Brazilian Portuguese**; match that language in user-facing strings, flash messages, comments, and commit messages.

## Commands

```bash
# Development (Flask debug server, auto-reload, binds 192.168.0.54:5090)
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env        # then fill DB_PASSWORD / SECRET_KEY
python run.py

# Production (waitress, binds 0.0.0.0:5090 — env SERVE_HOST/SERVE_PORT override)
python serve.py

# Windows one-click (creates .venv, installs deps, generates .env + shortcuts)
setup\install.bat
setup\start_invensync.bat     # launches PyQt5 panel + waitress
```

- **Always run Python via `.venv\Scripts\python.exe`** — the system Python lacks the dependencies (`pyotp`, `psycopg`, etc.).
- There is **no test suite**, no linter config, and **no build step** (templates are server-rendered Jinja, assets are CDN + `inventory/static/`).
- Quick boot/smoke check: `.venv\Scripts\python.exe -c "from inventory import create_app; create_app()"`.
- `run.py` has `debug=True` so templates reload, but **changes to `.py` files require a server restart** to take effect.

## Architecture

### App factory & boot sequence (`inventory/__init__.py`)
`create_app()` is the spine. On every boot, in order: init extensions (`db`, `login_manager`, `csrf`) → import **all** models → `db.create_all()` → `_run_light_migrations()` → seed functions → register ~34 blueprints → install the access-control `before_request` → context processors / error handlers → start the background monitoring scheduler.

When adding a model: **import it inside `create_app()`** (in the model-import block) or `create_all()` won't see it. When adding a blueprint: import + `register_blueprint(..., url_prefix=...)` in the same file.

### Schema changes — NO Alembic/migrations framework
Tables are created by `db.create_all()`. **New columns on existing tables** must be added as idempotent raw SQL (`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`) inside `_run_light_migrations()`. Note `"user"` is quoted (reserved word in Postgres). One-off data migrations live as `_seed_*` / `_backfill_*` helpers that are written to be safe to run on every boot.

### Layering: routes → repositories → models
- `routes/` — one Blueprint per module; HTTP, forms, flash, access checks.
- `repositories/` — query/sort logic for the **data-heavy** modules (products, machines, tickets, movements, …). Not every module has a repo; simpler CRUD modules (departments, announcements, kiox) query inline in the route. Follow the neighbor module's style.
- `models/` — SQLAlchemy models, one per file.
- `forms/` — Flask-WTF forms. `services/` — cross-cutting logic (see below).

### Access control — two-tier (admin vs. common user)
Defined in `inventory/__init__.py`:
- `_gate_non_admins` (a global `before_request`) blocks non-admin users from every endpoint **except** those whose name starts with a `NON_ADMIN_PREFIXES` entry (`tickets.`, `profile.`, `auth.`, `kb.`, `announcements.`) or is in `NON_ADMIN_ENDPOINTS`. Blocked non-admins are redirected to the **Central de Avisos** (`announcements.list_view`).
- **Post-login landing differs by role** (`routes/auth.py::_home_for`): admins → `dashboard.index`; common users → `announcements.list_view`.
- Admin-only blueprints enforce it with a `@bp.before_request` that `abort(403)`s non-admins (see `departments.py`). Modules that are read-for-all-but-write-for-admins (e.g. `announcements.py`) only require login globally and call a local `_admin_only()` in each mutating route.

To expose a module to common users you must add its blueprint prefix to `NON_ADMIN_PREFIXES` **and** make the routes tolerate non-admins.

### CSRF — global, with JS auto-injection
`CSRFProtect` is enabled app-wide. Rather than editing every one of the ~40 raw `<form method=post>` templates, `base.html` carries a `<meta name="csrf-token">` and a script that injects a hidden `csrf_token` field into every POST form lacking one (also covers dynamically created forms via a capture-phase submit listener). `WTF_CSRF_TIME_LIMIT = None` so tokens last the session. FlaskForm forms still emit their own token via `hidden_tag()`. **Consequence:** raw POST forms rely on JS; if you add an AJAX POST, send the token from the meta tag.

### People model — unified `user` table
There is no separate "employee" table anymore. `models/user.py` is the central registry of people; **login is optional** (`can_login`, nullable `email`/`password_hash`). People without login exist only to be selected as "responsável" on assets/tickets. `services/people.py` builds the responsible-person dropdowns by **unioning, at request time**, the central `user` records with any names still referenced on Machines/Mobile devices. The legacy `colaborador` table is a one-time migration source that `_seed_people_into_users()` drains on first boot.

### Services (`inventory/services/`)
- `audit.py` — `audit.record(action, entity, entity_id, summary)`; best-effort, never raises, used across mutations.
- `whatsapp.py` — outbound notifications via CallMeBot (`notify_user`, `notify_ti`); no-op unless `WHATSAPP_ENABLED=1`.
- `monitoring.py` — background uptime scheduler started in `create_app()` when `MONITORING_ENABLED`.
- `patrimony.py` — company-wide `PAT-0001` sequence shared by machines & mobiles.
- `exports.py` — `xlsx_response(...)` for Excel downloads. `people.py`, `assets.py`, `docs.py`, `twofa.py` (TOTP), `inventory_service.py`.

### Domain modules (Blueprints)
Estoque (products/movements/kanban/reports/categories/suppliers), Máquinas & submódulos (machines + cleanings/maintenance/mobile/chips/monitoring/routers/labels, all under `/machines/...` or related prefixes), Colaboradores/departments/assets, **Chamados** (`tickets` — helpdesk with comments timeline, attachments, status workflow, WhatsApp notifications), **Central de Avisos** (`announcements` — internal bulletin board; admins post, everyone reads), KB, Admin tools (credentials vault, audit, docs, **kiox**), profile, auth (with optional 2FA/TOTP).

The **kiox** module (`routes/kiox.py`) serves a self-contained fleet-tracking map (`inventory/kiox/RASTREIO-mapa.html`, Leaflet + Firebase) raw via `send_file` (bypassing Jinja); it's a copied snapshot — if the original under the external `KioX/` folder changes, the copy must be re-synced.

### Module map (blueprint → URL prefix)
Quick navigation aid; for fields/endpoints read the module itself. Several "Máquinas" submodules live under `/machines/...`.

| Prefix | Module | | Prefix | Module |
|---|---|---|---|---|
| `/` | dashboard (admin home) | | `/machines/maintenance` | maintenance |
| `/avisos` | announcements (common home) | | `/machines/monitoring` | monitoring |
| `/tickets` | tickets (helpdesk) | | `/machines/chips` | chips (SIM/lines) |
| `/kb` | knowledge base | | `/routers` | routers |
| `/profile` | profile (+ 2FA) | | `/labels` | QR labels |
| `/products` | products/materials | | `/colaboradores` | people registry |
| `/movements` | stock movements | | `/departments` | departments |
| `/kanban` | stock kanban | | `/assets` | assets-by-person |
| `/reports` | reports | | `/credentials` | secrets vault (admin) |
| `/categories` `/suppliers` | stock cadastros | | `/audit` | audit trail (admin) |
| `/licenses` `/domains` | licenses/domains | | `/docs` | living docs (admin) |
| `/machines` | machines | | `/kiox` | fleet map (admin) |
| `/machines/mobile` | mobile devices | | `/backups` | DB backups (admin) |
| `/machines/cleanings` | cleanings | | `/wpp` | WhatsApp test |
| (no prefix) | `auth` (login/2FA), `health` (/health) | | | |

## UI conventions
- Single `base.html`; child templates `{% extends "base.html" %}` and use `{% block content %}`, `{% block extra_head %}`, `{% block extra_js %}`.
- Dark theme. On desktop (≥992px) the navbar becomes a fixed **icon-only left rail** (labels become tooltips); keep an `<i class="bi ...">` icon on every nav item. Icons are Bootstrap Icons; CSS is Bootstrap 5 via CDN plus `static/style.css` and `:root` brand vars (`--brand: #00c853`).
- Reusable patterns: `.page-header`/`.ph-title`, `.table-card`, `.stat-card`, `.empty-state`, `badge bg-{color}-subtle text-{color}-emphasis`.

## Configuration
All secrets/config come from `.env` (see `.env.example`), loaded in `inventory/config.py`. DB is PostgreSQL via `psycopg` 3 (`postgresql+psycopg://...`); `DATABASE_URL` overrides the discrete `DB_*` vars. Timestamps use server-local time (`db.func.now()`), not UTC. Uploads (avatars, ticket attachments, NF files) go under `inventory/static/uploads/...` with a 16 MB cap.
