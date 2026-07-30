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
- No linter config and **no build step** (templates are server-rendered Jinja, assets are CDN + `inventory/static/`).
- **Tests** (pytest smoke + feature tests in `tests/`): run with `pytest -q`. A safety guard in `tests/conftest.py` **refuses to run unless the DB looks like a test DB** (`DATABASE_URL`/`DB_NAME` contains `test`) or `INVENSYNC_ALLOW_DB_TESTS=1` is set — the suite creates/mutates rows, so never point it at production. CI runs them on push via `.github/workflows/ci.yml` (Postgres service).
- Quick boot/smoke check: `.venv\Scripts\python.exe -c "from inventory import create_app; create_app()"`.
- `run.py` has `debug=True` so templates reload, but **changes to `.py` files require a server restart** to take effect.

## Architecture

### App factory & boot sequence (`inventory/__init__.py`)
`create_app()` is the spine. On every boot, in order: (optional `ProxyFix` when `BEHIND_PROXY=1`) → init extensions (`db`, `login_manager`, `csrf`, `limiter`) → CSRF error handler → import **all** models → `db.create_all()` → `_run_light_migrations()` → seed/backfill functions (incl. `_encrypt_credentials` + `_encrypt_router_secrets`, which cipher any plaintext secrets at rest) → `user_loader` (parses `id:token`, see session-token below) → register ~35 blueprints → access-control `before_request` → context processors (`avatar_url`, `page_url`) / error handlers (incl. 429 → friendly redirect) → `/sw.js` route → start background schedulers: **monitoring** (uptime), **alerts** (proactive), **printer_monitor** (SNMP), **plug_scheduler** (smart plugs), **backup_scheduler** (DB backups).

Background schedulers each run on their own daemon thread and are guarded by a `_started` flag + `WERKZEUG_RUN_MAIN` (so the Flask reloader doesn't double-start them in dev).

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
- `mailer.py` — **outbound notifications by e-mail (SMTP)**; `notify_ti` / `notify_user`, no-op unless `MAIL_ENABLED=1`. This **replaced the old WhatsApp/CallMeBot** integration (removed). The `/wpp` blueprint is now the e-mail test/diagnostics page (kept the legacy `wpp` name).
- `monitoring.py` — background uptime scheduler started in `create_app()` when `MONITORING_ENABLED`.
- `alerts.py` — proactive-alerts scheduler (`ALERTS_ENABLED`): low stock, expiring licenses/warranties, stuck tickets. **Upserts a single auto-announcement** (title `AUTO_TITLE`) in Central de Avisos + daily **e-mail** digest. `alerts.publish(app)` is also triggerable from the announcements page button.
- `crypto.py` — Fernet symmetric encryption for secrets at rest; key derived from `VAULT_KEY` (falls back to `SECRET_KEY`). `encrypt`/`decrypt` (tolerant of legacy plaintext), `looks_encrypted` (structural check — never re-ciphers a token). Used by the **credentials vault** and the **routers** module. **`VAULT_KEY` must never change** or existing ciphertext is unrecoverable.
- `snmp_printer.py` — reads network printers via **SNMP** (Printer-MIB pages/supplies + Brother private toner OID) with an **IPP fallback** (`pyipp`) for Canon that only exposes state/alerts. `query(ip)` is best-effort → `{"ok": bool, ...}`.
- `printer_monitor.py` — background scheduler (`PRINTER_MONITOR_ENABLED`): scans active network printers, writes `PrinterReading` history, **e-mails TI once per supply-low event**, and **auto-registers a stock OUT movement** when a supply jumps back up (toner/drum swap detected — compares to the last DB reading, robust to restarts).
- `router_ctl.py` — probes a router's admin panel (online/latency + Basic-Auth vs form detection) for the routers control panel; `auth_url`/`base_url` helpers. Best-effort.
- `net_scan.py` — ARP-based network discovery for the `/rede` module: reads `arp -a`, filters, reverse-DNS names in parallel; optional ping-sweep of known /24s; `active_set()` returns current ARP MACs/IPs (no DNS) for the machine-card live status. Best-effort.
- `dvr_cam.py` — snapshot proxy for the CFTV cameras (`/cgi-bin/snapshot.cgi`, Digest); serves the JPEG in-memory (never to disk) with a short per-(dvr,channel) cache. Reuses `router_ctl.probe` for DVR status.
- `tuya.py` / `plug_scheduler.py` — smart-plug (Tuya/NeoAvant LAN) control + scheduled on/off, backing the `/tomadas` module.
- `backup_scheduler.py` — periodic PostgreSQL dumps for the `/backups` module. `errorlog.py` — captured error log for `/errors`.
- `pagination.py` — `paginate(items, per_page=20)` slices an in-memory list using `?page`/`?per_page` (20/50/100) and returns `(slice, meta)`; render with the `pager` macro in `templates/_macros.html` (uses the `page_url` context helper to preserve filters).
- `patrimony.py` — company-wide `PAT-0001` sequence shared by machines & mobiles.
- `exports.py` — `xlsx_response(...)` for Excel downloads. `people.py`, `assets.py`, `docs.py`, `twofa.py` (TOTP), `inventory_service.py`, `imports.py`.

### Printer SNMP monitoring & supply auto-baixa
Network printers (`Machine.kind == "impressora"` with an `ip_address`) are polled via `services/snmp_printer.py`. `services/printer_monitor.py` runs in the background and:
- stores one `PrinterReading` per printer per cycle (pages/toner%/drum%) — the `models/printer_reading.py` history table;
- e-mails TI when a supply crosses `PRINTER_SUPPLY_ALERT_PCT` (re-arms after recovery);
- **auto-registers a stock OUT movement** of 1 unit when a supply level jumps up by ≥ `PRINTER_REPLACE_JUMP` (default 40) and reaches ≥ `PRINTER_REPLACE_PCT` (default 80) — i.e. a physical swap. The printer's linked supply is `Machine.toner_product_id` / `Machine.drum_product_id` (FK → `product.id`, added via light migration; the machine form shows two comboboxes filtered by the "Toner" / "Cilindro/Fotocondutor" **product categories**, only for printers). Emails TI if the material's stock was already ≤ 0.

The consumption report (`/machines/impressoras/consumo`, `routes/machines.py::printers_report`) sums only the **rises** between consecutive readings, so a counter that "drops" mid-period (IP corrected, device swapped) never yields a negative total. It also shows a "Resma de papel" KPI (pages ÷ 500) and a **"Custo de suprimento por setor"** section: it sums OUT stock movements of toner/drum products (Toner/Cilindro categories) × unit cost, grouped by `StockMovement.responsible_sector`. The auto-swap stamps `responsible_sector` (printer's sector) + `unit_cost` (product price) on the movement, so cost accrues per sector over time.

**Brother parts life:** `snmp_printer.query()` also decodes the Brother private "maintenance" blob (`OID_BROTHER_MAINT`) beyond toner (0x81) — items `0x6a/0x6b/0x6c/0x6d/0x6f` are the **remaining-life % of parts** (belt/fuser/laser/PF kits), reported ×100 (÷100 = %; validated because 0x41 matched the standard drum %). Returned as `parts` and shown as bars on the printer card (`_BROTHER_PARTS` labels are best-effort per model).

### Router control panel (`/routers`, admin)
Beyond CRUD, each router card shows a **live status** (AJAX to `routers.status` via `services/router_ctl.py`) and a smart access button. Note the hard constraint: browsers strip URL-embedded credentials, so there is **no reliable one-click auto-login** even for Basic-Auth panels — the button opens `http://IP` and copies the admin password to the clipboard. Router admin/Wi-Fi passwords are **encrypted at rest** (`crypto`, VAULT_KEY); revealed on demand via `routers.senha` with audit — never rendered raw into the page.

### CFTV / DVR module (`/cftv`, admin — `routes/dvr.py`, `models/dvr.py`)
DVRs de câmera (Intelbras/Dahua). Same pattern as routers: encrypted `admin_password` (VAULT_KEY, `String(255)`), live status (`router_ctl.probe`), "Abrir painel" (open + copy password). Plus **live camera view**:
- `services/dvr_cam.py` proxies the **snapshot CGI** (`/cgi-bin/snapshot.cgi?channel=N`, **Digest auth**) — the JPEG is served **in-memory (never written to disk)**, with a short per-(dvr,channel) cache shared across viewers; the Digest opener is reused.
- `dvr.cameras` renders a grid of `Dvr.channels` thumbnails; `dvr.snap/<ch>` is the proxy (accepts `?live=1` → minimal cache for the enlarged view). The camera page refreshes the grid every ~3s and the enlarged view does **chained double-buffered polling** (`?live=1`).
- **Latency ceiling:** these DVRs' snapshot.cgi takes ~0.9s → ~1 fps max. True real-time needs a media gateway (**go2rtc** — see "Próximos passos" at the end; RTSP 554 is open on both DVRs). MJPEG CGI on these units is weak (sub-stream is H.264).

### Admin utility modules
- `/tomadas` (smart plugs) — Tuya/NeoAvant LAN plugs with on/off scheduling (`services/tuya.py` + `plug_scheduler.py`); plug local keys encrypted with `crypto`.
- `/cotacoes` (Cotações) — type a model → **deep-link** to the Mercado Livre listing ordered by lowest price (opens in the admin's browser; ML blocks server-side search, so there is intentionally **no API/scraping**).
- `/rede` (Rede/ARP) — on-demand network discovery via `net_scan`; page opens instantly, scans only on the button (JSON `rede.scan`, CSS "radar" animation). Matches devices → cadastro by **MAC** (certeiro, works with DHCP), then hostname/IP/name; "salvar MAC" bootstraps `Machine.mac_address`/`hostname` from a discovered device. Machines & mobiles now carry `mac_address` (+ `hostname` on machines); the machines list shows a **live online/offline chip** for PCs/notebooks via `machines.rede_ativos` (reads the ARP table only — fast, no DNS).

### Uptime monitoring auto-sync (`/machines/monitoring`)
`services/monitoring.py::_sync_auto_hosts()` (run each `check_all` cycle + on the monitoring page) upserts a `MonitoredHost` (with `auto_source` = `impressora:N`/`dvr:N`/`router:N`) for every active printer/DVR/router that has a fixed IP, so they flow through the existing up/down e-mail alerting. Auto hosts are read-only in the UI (edit/delete blocked); removing/inactivating the device drops its monitor.

### Auth hardening
- **Rate limiting** (`extensions.limiter`, Flask-Limiter, memory store): `auth.login` POST `10/min;40/h`, `auth.login_2fa` POST `10/min`. 429 → friendly flash + redirect.
- **Remember-me**: login uses `login_user(user, remember=True)` + `session.permanent = True`.
- **Session token / "logout everywhere"**: `User.get_id()` returns `"id:token"`; `user_loader` rejects a mismatching token. `profile.logout_others` rotates `User.session_token` (invalidates other devices' session + remember cookies; legacy `id`-only cookies still accepted until next login). New column added via light migration with backfill.
- Password min length 8 on login accounts; admins without 2FA see a dismissible nudge banner. Optional inactivity logout via `INACTIVITY_MINUTES`.

### Global search (`routes/search.py`, `/busca`)
Admin-only JSON endpoint scanning products/machines/mobiles/chips/tickets/users/licenses (≥2 chars, capped per category, returns ready `url`s). UI is a Ctrl+K modal in `base.html` (admin only).

### PWA
`static/manifest.webmanifest` + `static/sw.js` (cache-first for `/static/` only) + `icon-192/512.png`. The service worker is served from root via the `/sw.js` route (scope `/`); registration + manifest link live in `base.html`.

### Domain modules (Blueprints)
Estoque (products/movements/kanban/reports/categories/suppliers), Máquinas & submódulos (machines + cleanings/maintenance/mobile/chips/monitoring/routers/labels, all under `/machines/...` or related prefixes), Colaboradores/departments/assets, **Chamados** (`tickets` — helpdesk with comments timeline, attachments, status workflow, e-mail notifications), **Central de Avisos** (`announcements` — internal bulletin board; admins post, everyone reads), KB, Admin tools (credentials vault, audit, docs, **kiox**, **tomadas** smart plugs, **cotações** ML price deep-links, **rede** ARP discovery, **cftv** DVRs + live cameras, e-mail test at `/wpp`, error log at `/errors`, DB backups), profile, auth (with optional 2FA/TOTP). The Admin dropdown (gear) holds Cofre/Auditoria/Cotações/Rede/CFTV/Kiox/Tomadas + Backups/e-mail/Erros/Docs; the profile menu is just Perfil + Sair.

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
| `/machines/cleanings` | cleanings | | `/wpp` | e-mail test/diagnostics (admin) |
| `/machines/impressoras/consumo` | printer consumption | | `/tomadas` | smart plugs (admin) |
| `/busca` | global search JSON (admin) | | `/cotacoes` | ML price deep-links (admin) |
| `/errors` | error log (admin) | | `/rede` | ARP network discovery (admin) |
| `/cftv` | CFTV / DVRs + câmeras (admin) | | | |
| (no prefix) | `auth` (login/2FA), `health` (/health), `/sw.js` (PWA) | | | |

## UI conventions
- Single `base.html`; child templates `{% extends "base.html" %}` and use `{% block content %}`, `{% block extra_head %}`, `{% block extra_js %}`.
- Dark theme. On desktop (≥992px) the navbar becomes a fixed **icon-only left rail** (labels become tooltips); keep an `<i class="bi ...">` icon on every nav item. Icons are Bootstrap Icons; CSS is Bootstrap 5 via CDN plus `static/style.css` and `:root` brand vars (`--brand: #00c853`).
- Reusable patterns: `.page-header`/`.ph-title`, `.table-card`, `.stat-card`, `.empty-state`, `.section-label`, `.kpi`, `badge bg-{color}-subtle text-{color}-emphasis`.

### Global front-end behaviors (all in `base.html`, automatic — no per-page wiring)
These are driven by markup conventions + global scripts; reuse them instead of reinventing:
- **Flash → toasts**: flash messages render as auto-dismissing toasts (top-right).
- **Confirm modal**: any `onsubmit="return confirm('…')"` is intercepted and shown as a styled modal (CSRF unaffected — tokens are injected at load).
- **Collapsible filters**: any `.table-card-tools` containing fields gets a "Filtros" toggle (starts hidden; auto-opens if a filter is active).
- **Department pills**: lists grouped by sector render a `dept-tabs` bar (`data-dept-tabs="#gridId"` + cards with `data-dept`); the bar collapses behind a "Departamentos" button, starts with nothing shown (or auto-shows all when a search filter is active). Cards are a CSS grid of equal width.
- **Pagination**: `{% from "_macros.html" import pager %}` then `{{ pager(pag) }}` (the route provides `pag` from `paginate(...)`).
- **Ctrl+K** opens global search (admin).

## Configuration
All secrets/config come from `.env` (see `.env.example`), loaded in `inventory/config.py`. DB is PostgreSQL via `psycopg` 3 (`postgresql+psycopg://...`); `DATABASE_URL` overrides the discrete `DB_*` vars. Timestamps use server-local time (`db.func.now()`), not UTC. Uploads (avatars, ticket attachments, NF files) go under `inventory/static/uploads/...` with a 16 MB cap.

Secrets encrypted at rest (credentials vault, router passwords, smart-plug keys) use `VAULT_KEY` — **never change it** or existing ciphertext becomes unrecoverable.

Notable optional toggles:
- **E-mail** (replaces WhatsApp): `MAIL_ENABLED=1` + `SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASSWORD/SMTP_TLS`, `MAIL_FROM`, `MAIL_TI` (TI recipients, comma-separated).
- **Printers/SNMP**: `SNMP_COMMUNITY`, `SNMP_TIMEOUT`, `PRINTER_MONITOR_ENABLED`, `PRINTER_MONITOR_MINUTES`, `PRINTER_SUPPLY_ALERT_PCT`, `PRINTER_REPLACE_PCT`/`PRINTER_REPLACE_JUMP` (swap-detection thresholds).
- **Smart plugs**: `PLUG_SCHEDULER_ENABLED`, `PLUG_OFFLINE_*`.
- **Schedulers/alerts**: `MONITORING_ENABLED`, `ALERTS_ENABLED`/`ALERTS_*`, `INACTIVITY_MINUTES` (0=off).
- **CFTV/DVR cameras**: `DVR_SNAP_TTL` (grid snapshot cache, default 3s), `DVR_SNAP_TTL_LIVE` (enlarged view, default 0.4s).
- **Backups**: `BACKUP_DIR`, `BACKUP_KEEP`, `BACKUP_HOUR`, `BACKUP_SCHEDULER_ENABLED` (app-owned daily dump, self-heals if the server was down). **Offsite** (recommended): `BACKUP_MIRROR_DIR` (2nd folder/NAS/synced Drive) and/or `BACKUP_UPLOAD_CMD` (post-backup command, e.g. rclone to Google Drive — `{path}`/`{name}` placeholders). The Backups page shows the offsite status (off / unreachable / OK). `backup_db.py` at the repo root does the work (`run_backup`, `mirror_status`).
- **HTTPS behind a reverse proxy**: `BEHIND_PROXY=1` + `SESSION_COOKIE_SECURE=1` (see `docs/HTTPS.md`).

## Deploy
`atualizar.bat` (repo root) is the update flow: `git pull` → `pip install -r requirements.txt` → boot-check (`create_app()`) → **reminder to restart**. Always restart after pulling so `.py` code and templates load together (a template that references a not-yet-registered endpoint/form field errors every page until restart — most historical `/errors` entries were exactly this).

## Próximos passos / TODO
### Câmeras em tempo real via go2rtc (WebRTC) — HANDOFF para novo chat
**Estado atual:** o módulo CFTV mostra câmeras por **snapshot** (`services/dvr_cam.py` + `templates/cftv/cameras.html`), com teto de **~1 fps** (snapshot.cgi do DVR leva ~0,9s). Isso NÃO é tempo real.

**Objetivo:** vídeo fluido sub-segundo no navegador, sem transcodificar.

**Fatos já confirmados (deste ambiente):**
- 2 DVRs cadastrados na tabela `dvr`: **INDUSTRIA3** `192.168.0.134` (16 canais) e **MHDX1216** `192.168.0.136` (18 canais). user `admin`, senha cifrada (VAULT_KEY) — decifra com `crypto.decrypt(d.admin_password)`.
- **RTSP porta 554 ABERTA** nos dois. URL padrão Intelbras/Dahua: `rtsp://user:senha@IP:554/cams/realmonitor?channel=N&subtype=0` (main) / `subtype=1` (sub).
- Câmeras analógicas são **H.264** → go2rtc faz **passthrough p/ WebRTC** (CPU baixa). Canais IP (ch17-18 do MHDX) podem ser H.265 → checar (HEVC não passa direto no WebRTC).

**Plano proposto:**
1. Rodar **go2rtc** (binário único, grátis/MIT, ~20-40 MB) no mesmo servidor, como serviço. Download: github.com/AlexxIT/go2rtc.
2. **Gerar `go2rtc.yaml`** a partir da tabela `dvr` (um stream por canal, com a URL RTSP montada da credencial decifrada). Cuidar da permissão do arquivo (leva user:senha em texto).
3. Na página `cftv/cameras.html`, trocar (ou dar opção) o `<img>` snapshot pelo **player WebRTC do go2rtc** (iframe `http://SERVIDOR:1984/webrtc.html?src=<cam>` ou o webcomponent do go2rtc). Grade pode seguir em snapshot (leve) e a **ampliada** vira WebRTC.
4. Config sugerida: `GO2RTC_URL` no `.env`; endpoint/rota no InvenSync que devolve a URL do player por DVR/canal.

**Custo:** R$ 0 (open-source), CPU baixa (passthrough, só transmite quando alguém assiste), nada em disco. Único ônus: mais um processo pra manter no ar (se cair, o snapshot ~1s continua de reserva).
