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
- **Latency ceiling of the snapshot:** these DVRs' snapshot.cgi takes ~0.9s → ~1 fps max. Real-time comes from **go2rtc** (below); the snapshot stays as the always-available fallback.

**Real-time video (go2rtc / WebRTC)** — `services/go2rtc.py`, `templates/cftv/go2rtc.html`, `docs/GO2RTC.md`:
- go2rtc is an **external process** (single MIT binary) that reads the DVRs' RTSP (port 554) and serves the browser over **WebRTC in passthrough** (no transcoding → low CPU, nothing on disk). The app never embeds or supervises it.
- `/cftv/go2rtc` (admin) is the control page: live service probe (`/api/streams` + `/api`), masked preview of the config, and a **"Gerar go2rtc.yaml"** button (`POST /cftv/go2rtc/gerar`, audited) that writes one stream per channel — `dvr<id>_ch<N>` — built from the DVR's IP + the vault-decrypted password, percent-encoded. Only **active DVRs with IP and channel count** are included (`go2rtc.eligible`). The generated file holds credentials in plaintext (go2rtc's format) → `go2rtc/` is gitignored; regenerate + restart go2rtc after editing a DVR.
- The camera page keeps the **grid on snapshot** (16-18 WebRTC sessions would be far heavier than 18 JPEGs/3s) and the **enlarged view opens the go2rtc player in an `<iframe>`**, with a button to fall back to snapshot (choice kept in `localStorage`). WebRTC is only offered for channels the probe reports as published; with go2rtc off/down the page degrades silently to the old snapshot behavior.
- **CSP:** `create_app()` adds the `GO2RTC_URL` origin (plus its `ws://`) to `frame-src`/`connect-src` — without it the browser blocks the iframe.
- **What these DVRs actually serve — measured (RTSP `DESCRIBE` + CGI `Encode`), don't guess again:** path is `/cam/realmonitor` (**singular**; `/cams/...` → 404). `subtype=0` (main) = **1280x720 H.265** @15fps; `subtype=1` (sub) = **352x240 CIF H.264** @7fps — and the sub-stream **cannot be raised** (`ExtraFormat.ResolutionTypes=CIF`). So HD only exists as H.265, which WebRTC cannot carry.
- **Transcode on demand** is how HD reaches the browser: each channel is generated with two sources — the main RTSP plus `ffmpeg:<stream>#video=h264`. go2rtc picks by codec negotiation: an H.265-capable browser gets passthrough (zero CPU), everyone else triggers the ffmpeg conversion, **one process per viewer, killed when they close**. Measured on this server (Xeon E5530): HEVC decode alone 19% of a core, full transcode **47% of a core per viewer**. `GO2RTC_TRANSCODE=0` or `GO2RTC_SUBTYPE=1` are the escape hatches if CPU gets tight. Needs `ffmpeg.exe` next to the yaml (declared as `ffmpeg: bin:`).
**Smart detection (human/vehicle)** — `services/dvr_events.py`, `models/dvr_detection.py`:
- The **DVR** does the analysis (Dahua/Intelbras SMD); the app never decodes video or runs a model, so this costs ~0 CPU. One daemon thread per DVR holds `eventManager.cgi?action=attach` open and parses `Code=SmartMotionHuman;action=Start;index=N;data={"object":[{"Rect":[…]}]}`. `index` is 0-based (channel = index+1).
- **Coordinate scale is 1024, measured — do not "fix" it to 8191.** Observed values across samples topped out at X=972 / Y=1021, and only ÷1024 yields sane proportions (people ~5% wide × ~19% tall). The `SizeFilter` in the *config* tree does use 0-8191 — different thing.
- **A channel can hold several objects at once** — `ativos()` returns a *list* per channel. The first version kept one detection per channel, so a `SmartMotionVehicle` event overwrote the `SmartMotionHuman` one on the same channel and people stopped being boxed. Same-object matching uses **IoU ≥ 0.30**, not centre distance: in a crowded room people stand closer than any sane centre threshold and would merge into a single box. `Stop` only clears objects of the type that ended.
- Live state lives in memory (`ativos()`, expires after `DVR_DETECT_TTL` so a dropped connection can't freeze a box on screen); history goes to `DvrDetection` (start/end + rect). `/cftv/<id>/deteccoes` serves the box already converted to %, `/cftv/deteccoes` is the history page.
- **`/cftv/<id>/deteccoes` must never query the database** (a test enforces it). The camera page polls it every 1-3s; the first version did a `get_or_404(Dvr)` per poll, which left connections `idle in transaction`, drained the pool and made the *whole app* crawl while anyone had the camera grid open. The live state is in memory — no DB needed. Same reasoning caps the write side: a repeated `Start` for the same channel+type within `_CONTINUA` (20s) is treated as the same object still on scene, so it refreshes memory instead of inserting another row (the DVR re-sends `Start` every ~5s; without this one person generated 18 rows in 8 minutes).
- The camera page draws the box **only in WebRTC mode**: the stage is forced to 16:9 to match the analysed stream, while the snapshot is ~4:3 and would misplace the rectangle. The grid tiles just get a pulsing outline + label, which is aspect-independent.
- **Firmware support is the catch:** only the **MHDX1232** accepts enabling SMD, and only on channels 1-16. The MHDX 11xx/1216 expose the config tree but reject `Enable` with HTTP 400 (verified across 4 units and several channels, while other writes on the same units return OK). No animal detection at all — SMD is human/vehicle only.
- Config: `DVR_EVENTS_ENABLED`, `DVR_DETECT_TTL`, `DVR_ALERT_ENABLED`/`DVR_ALERT_HOURS` (e.g. `19-6`)/`DVR_ALERT_COOLDOWN` for the off-hours e-mail to TI.

- Grid snapshots stay at whatever the DVR's `Snap` config gives (704x480 on `.134`, 352x240 on `.136`) — no URL parameter changes it (`type=`/`subtype=` are ignored); only the DVR's own config would.
- Config: `GO2RTC_URL` (empty = feature off), `GO2RTC_CONFIG`, `GO2RTC_RTSP_PORT`, `GO2RTC_SUBTYPE` (0=HD), `GO2RTC_TRANSCODE`, `GO2RTC_FFMPEG`, `GO2RTC_RTSP_TEMPLATE`, `GO2RTC_PLAYER_MODE`, `GO2RTC_TIMEOUT`. Install/service/firewall/troubleshooting: `docs/GO2RTC.md`.

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

### Apresentação (`/apresentacao`, todos os perfis)
Landing/welcome page: `routes/intro.py`, `templates/intro/index.html`, `static/css/intro.css`, `static/js/intro.js`.
- **Three.js r185 + GSAP/ScrollTrigger, both from jsdelivr, loaded only on this page** (`extra_js`) — no build step, and the CDN is already allowed by the CSP `script-src`. The JS is an ES module served from `static/` because a static file can't carry the CSP nonce that inline scripts need.
- The background scene lives in **`static/js/bolhas.js`, a shared component** — `criarFundoBolhas(canvas, {densidade})`. It owns its render loop, resize, visibility pause and teardown; `intro.js` only adds the content animations and ties the camera to the scroll.
- **`base.html` runs it on every screen** (`{% block fundo_bolhas %}`, `#fundoBolhas`, density `UI_FUNDO_DENSIDADE`, default 0.3). Two rules that a test enforces: exactly **one scene per page** — the intro overrides the block to empty because it has its own full-density scene, and two scenes would mean two render loops fighting for the GPU — and **`UI_FUNDO_BOLHAS=0` must remove it entirely**, since this is WebGL running all day on whatever machine the user has. On login the gradient `.auth-bg` sits underneath as the fallback: if the CDN is unreachable the module simply doesn't load and the page looks exactly as before.
- **Everything is scoped under `.intro`** — the page uses generic class names (`.card`, `.btn`, `.lead`) that would otherwise fight Bootstrap and the project's design system. A test enforces that no selector escapes the scope.
- The background is a soda-bottle scene: bubbles rise in three depth layers, **animated on the GPU** (the vertex shader integrates an accumulated distance, so changing speed never makes them jump), drawn procedurally in the fragment shader (rim + specular + iridescence), lit from a single shared direction (`DIR_LUZ`). A full-screen post-process pass adds the transparent-glass wall (curvature, chromatic aberration, vertical reflections). **Scroll speed accelerates the bubbles** — the velocity is measured per frame from `scrollY`, not from a ScrollTrigger callback (callbacks stop firing when scrolling stops and the last value sticks).
- Note `gl_PointCoord` has **Y pointing down**, opposite to screen space — the light direction is flipped before use, or the lighting comes from below for no visible reason.
- **First-entry behaviour:** `User.intro_visto` (light migration) starts false; `auth._home_for` sends the user here once, and opening the page marks it seen. After that it's reachable from the menu (first item, above Painel). `intro.` is in `NON_ADMIN_PREFIXES` so common users aren't gated out.

### Domain modules (Blueprints)
Estoque (products/movements/kanban/reports/categories/suppliers), Máquinas & submódulos (machines + cleanings/maintenance/mobile/chips/monitoring/routers/labels, all under `/machines/...` or related prefixes), Colaboradores/departments/assets, **Chamados** (`tickets` — helpdesk with comments timeline, attachments, status workflow, e-mail notifications), **Central de Avisos** (`announcements` — internal bulletin board; admins post, everyone reads), KB, Admin tools (credentials vault, audit, docs, **kiox**, **tomadas** smart plugs, **cotações** ML price deep-links, **rede** ARP discovery, **cftv** DVRs + live cameras, e-mail test at `/wpp`, error log at `/errors`, DB backups), profile, auth (with optional 2FA/TOTP). **Nav layout** (`base.html`): the rail holds **12 module icons + the `…` drawer**. It used to silently drop whatever didn't fit the viewport height; now it **survives short screens on its own** — two `max-height` tiers (800px / 660px) shrink icon size and spacing, and the icon list scrolls as the last resort. The scroll only works because `.navbar-collapse > .navbar-nav` carries `min-height: 0`: a flex item defaults to `min-height: auto` and refuses to shrink below its content, which is exactly why the extra icons used to spill off-screen instead of scrolling. Only the list scrolls — brand band and profile stay pinned — and the submenu drawer is `position: fixed`, so the list's `overflow` never clips it. Adding more icons is still a design call (they get smaller for everyone), but it no longer breaks reachability. Admin order: Apresentação, Painel, Estoque, Cadastros, Máquinas, Colaboradores, Buscar, Avisos, Chamados, Base, Cotações, CFTV. Everything else lives in a **`…` drawer** (`bi-three-dots`, id `ddMais`): Tomadas, Kiox, Rede, then an `Administração` group (`.dd-sub` subtitle) with Cofre/Auditoria/Backups/e-mail/Erros/Docs. **Adding a module to the rail means moving another one into `…`.** The `…` toggle's `active` condition must list exactly the prefixes inside it (forget one and the icon never lights on that page). Common users see only 4 items and no `…`. The profile menu is just Perfil + Sair.

The **kiox** module (`routes/kiox.py`) serves a self-contained fleet-tracking map (`inventory/kiox/RASTREIO-mapa.html`, Leaflet + Firebase) raw via `send_file` (bypassing Jinja); it's a copied snapshot — if the original under the external `KioX/` folder changes, the copy must be re-synced.

### Module map (blueprint → URL prefix)
Quick navigation aid; for fields/endpoints read the module itself. Several "Máquinas" submodules live under `/machines/...`.

| Prefix | Module | | Prefix | Module |
|---|---|---|---|---|
| `/apresentacao` | intro (boas-vindas, todos) | | | |
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
- Dark theme. On desktop (≥992px) the navbar becomes a fixed **icon-only left rail** (labels become tooltips); keep an `<i class="bi ...">` icon on every nav item. Dropdowns open as a **full-height drawer** beside the rail (SeniorX pattern): CSS pins the `.dropdown-menu.show` to `left: var(--rail-w)` with `position: fixed; top: 0; bottom: 0` and a fixed `--drawer-w`, overriding Popper via `!important`. Anchoring to the icon (the old behavior) made items at the end of the rail — Admin, Perfil — open half off-screen; starting at the top always fits, and the drawer scrolls if it ever outgrows the viewport. Each drawer starts with a `<li class="dd-title">` naming the module (the rail hides the icon's label); it sticks to the top and a script in `base.html` injects the ✕ close button into it, so no template repeats that markup. The drawer **overlays** the content — it does not push it like SeniorX does. Icons are Bootstrap Icons; CSS is Bootstrap 5 via CDN plus `static/style.css` and `:root` brand vars (`--brand: #00c853`).
- Reusable patterns: `.page-header`/`.ph-title`, `.table-card`, `.stat-card`, `.empty-state`, `.section-label`, `.kpi`, `badge bg-{color}-subtle text-{color}-emphasis`.

### Charts — the palette is validated, not chosen
Both dashboards (`dashboard.html`, `tickets/dashboard.html`) declare the **same 8-slot categorical palette**, plus a reserved status palette and a single-hue ordinal ramp. It is measured, not picked: it clears the lightness band, chroma floor, colorblind separation, normal-vision floor and 3:1 contrast against **both** surfaces this app renders on (`#15211a` dark, `#ffffff` light). The previous palette failed — brand green `#00c853` and amber `#ffb020` sit at **ΔE 2.9 under protanopia**, and they were the two series of the Entradas × Saídas chart, i.e. indistinguishable for red-green colorblind users.

Rules that are load-bearing, not taste:
- **The slot ORDER is the safety mechanism** — adjacent pairs are what get measured. Don't reorder, don't add a 9th color, without re-running the validator (`dataviz` skill, `scripts/validate_palette.js`, against both surfaces).
- **The brand green is not a series color** — it's too light for the dark-theme band. It identifies the UI, not the data.
- **Color by entity, never by rank or index.** Ticket status is colored from a name→color map because the query sorts by count; a single series gets *one* color for every bar (cycling the palette double-encodes bar length as hue and invents categories).
- **Ordered scales use the ordinal ramp** (priority), identity uses categorical, state uses the status palette (with the label always beside it).
- Every chart has a **table-view twin** via `static/js/chart-tabela.js` (the "Dados" button, built from `chart.data`). It's not optional decoration: three light-mode slots sit below 3:1, which obliges a non-color path to the values.

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
### Câmeras em tempo real (go2rtc) — no ar; falta reiniciar o InvenSync
Implantado neste servidor: serviço **`go2rtc`** (NSSM, início automático, log em
`go2rtc\go2rtc.log` rotacionando em 5 MB) rodando o go2rtc v1.9.14 + ffmpeg 8.1.2
em `InventarioAlmox\go2rtc\`; `go2rtc.yaml` com **34 câmeras** em **720p**;
regras de firewall 1984/TCP e 8555/TCP+UDP restritas a `192.168.0.0/24`;
`GO2RTC_URL` no `.env`.

Pendências:
1. **Reiniciar o InvenSync** para ele ler o `GO2RTC_URL` (o serviço go2rtc já está no ar).
2. Regerar o `go2rtc.yaml` (CFTV → Tempo real) e `Restart-Service go2rtc` sempre que
   cadastrar/alterar um DVR.
3. Opcional: subir a resolução dos **snapshots** da grade mexendo na config `Snap`
   dos DVRs (hoje 704x480 no `.134` e 352x240 no `.136`) — mexe no aparelho, não no app.
