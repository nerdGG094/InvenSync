"""
Launcher PyQt5 do servidor InvenSync.

Inicia/para o servidor (waitress via serve.py) como subprocesso, exibe
status e logs em tempo real, fica na bandeja do sistema e oferece atalho
para abrir no navegador.

Execução:
    python launcher.py          (com console)
    pythonw launcher.py         (sem console — usado pelos atalhos)
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from PyQt5.QtCore import QThread, Qt, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import (
    QBrush, QColor, QDesktopServices, QFont, QFontDatabase, QIcon, QPainter,
    QPixmap,
)
from PyQt5.QtWidgets import (
    QAction, QApplication, QFrame, QGraphicsDropShadowEffect, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
    QPushButton, QSizePolicy, QStyle, QSystemTrayIcon, QVBoxLayout, QWidget,
)

PROJECT_ROOT = Path(__file__).resolve().parent
SERVE_SCRIPT = PROJECT_ROOT / "serve.py"
ICON_PATH = PROJECT_ROOT / "inventory" / "static" / "favicon.ico"

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = "5090"
APP_NAME = "InvenSync"

# ---------- Paleta (dark, acento verde InvenSync) ----------
C_BG          = "#0f1115"
C_SURFACE     = "#171a21"
C_SURFACE_2   = "#1d212a"
C_BORDER      = "#262b36"
C_BORDER_2    = "#2f3543"
C_TEXT        = "#e7e9ee"
C_TEXT_DIM    = "#9ba3b4"
C_TEXT_MUTED  = "#6b7388"
C_PRIMARY     = "#00c853"
C_PRIMARY_HV  = "#00e676"
C_SUCCESS     = "#22c55e"
C_SUCCESS_HV  = "#16a34a"
C_DANGER      = "#ef4444"
C_DANGER_HV   = "#dc2626"
C_WARNING     = "#f59e0b"

QSS = f"""
* {{
    color: {C_TEXT};
    font-family: "Segoe UI Variable", "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}}
QMainWindow, QWidget#root {{ background: {C_BG}; }}
QLabel#title {{ font-size: 20px; font-weight: 600; color: #f4f6fa; }}
QLabel#subtitle {{ color: {C_TEXT_MUTED}; font-size: 12px; }}
QLabel#sectionLabel {{
    color: {C_TEXT_MUTED}; font-size: 11px; letter-spacing: 0.10em;
    font-weight: 600; text-transform: uppercase;
}}
QLabel#fieldLabel {{ color: {C_TEXT_DIM}; font-size: 12px; font-weight: 500; }}
QLabel#urlLabel {{ color: {C_TEXT_DIM}; font-size: 13px; }}
QLabel#urlLabel a {{ color: #6ee7a0; text-decoration: none; }}
QLabel#urlLabel a:hover {{ color: #b6f5cf; text-decoration: underline; }}
QLabel#statusText {{ font-size: 14px; font-weight: 600; }}
QLabel#uptime {{ color: {C_TEXT_MUTED}; font-size: 12px; }}

QFrame#card {{ background: {C_SURFACE}; border: 1px solid {C_BORDER}; border-radius: 12px; }}
QFrame#sep {{ background: {C_BORDER}; max-height: 1px; min-height: 1px; }}

QLineEdit {{
    background: {C_BG}; border: 1px solid {C_BORDER}; border-radius: 8px;
    padding: 7px 11px; color: {C_TEXT}; selection-background-color: {C_PRIMARY};
}}
QLineEdit:focus {{ border: 1px solid {C_PRIMARY}; }}
QLineEdit:disabled {{ color: {C_TEXT_MUTED}; background: #13161c; }}

QPushButton {{
    background: {C_SURFACE_2}; border: 1px solid {C_BORDER_2}; color: #d8dde6;
    border-radius: 8px; padding: 8px 16px; font-weight: 500;
}}
QPushButton:hover {{ background: #242a36; border-color: #3a4150; }}
QPushButton:pressed {{ background: #1a1e27; }}
QPushButton:disabled {{ color: #535a6c; background: #161921; border-color: #1f232c; }}

QPushButton#btnStart {{ background: {C_SUCCESS}; border-color: {C_SUCCESS}; color: #062512; }}
QPushButton#btnStart:hover {{ background: {C_SUCCESS_HV}; border-color: {C_SUCCESS_HV}; }}
QPushButton#btnStart:disabled {{ background: #11321f; border-color: #11321f; color: #4a6b56; }}

QPushButton#btnStop {{ background: {C_DANGER}; border-color: {C_DANGER}; color: #2a0707; }}
QPushButton#btnStop:hover {{ background: {C_DANGER_HV}; border-color: {C_DANGER_HV}; }}
QPushButton#btnStop:disabled {{ background: #2e1414; border-color: #2e1414; color: #6b4949; }}

QPushButton#btnRestart {{ background: transparent; border-color: {C_PRIMARY}; color: #6ee7a0; }}
QPushButton#btnRestart:hover {{ background: rgba(0,200,83,0.12); }}
QPushButton#btnRestart:disabled {{ background: transparent; border-color: #1d3a28; color: #4a785c; }}

QPushButton#btnTest {{ background: transparent; border-color: {C_WARNING}; color: #fbbf24; }}
QPushButton#btnTest:hover {{ background: rgba(245,158,11,0.12); }}
QPushButton#btnTest:disabled {{ background: transparent; border-color: #3a2e10; color: #6b5a30; }}

QPushButton#btnOpen {{ background: {C_PRIMARY}; border-color: {C_PRIMARY}; color: #062512; }}
QPushButton#btnOpen:hover {{ background: {C_PRIMARY_HV}; border-color: {C_PRIMARY_HV}; }}

QPlainTextEdit#log {{
    background: #0a0c10; border: 1px solid {C_BORDER}; border-radius: 10px;
    padding: 12px; color: #c8d1de;
    font-family: "Cascadia Mono", "Consolas", "Courier New", monospace;
    font-size: 12px; selection-background-color: {C_PRIMARY};
}}
QPlainTextEdit#log:focus {{ border-color: #3a4150; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: #2a3040; border-radius: 5px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: #3a4150; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QToolTip {{
    background: {C_SURFACE_2}; color: {C_TEXT}; border: 1px solid {C_BORDER_2};
    padding: 6px 10px; border-radius: 6px;
}}
QMessageBox, QDialog {{ background: {C_SURFACE}; color: {C_TEXT}; }}
QMessageBox QLabel, QDialog QLabel {{ color: {C_TEXT}; background: transparent; font-size: 13px; }}
QMessageBox QPushButton, QDialog QPushButton {{
    background: {C_SURFACE_2}; border: 1px solid {C_BORDER_2}; color: {C_TEXT};
    border-radius: 7px; padding: 6px 18px; min-width: 80px; font-weight: 500;
}}
QMessageBox QPushButton:hover, QDialog QPushButton:hover {{ background: #242a36; border-color: #3a4150; }}
QMessageBox QPushButton:default, QDialog QPushButton:default {{
    background: {C_PRIMARY}; border-color: {C_PRIMARY}; color: #062512;
}}
"""


def _local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 53))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _port_in_use(host: str, port: int, timeout: float = 0.5) -> bool:
    test_host = "127.0.0.1" if host in ("0.0.0.0", "") else host
    try:
        with socket.create_connection((test_host, int(port)), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def _dot_pixmap(color: str, size: int = 12) -> QPixmap:
    pix = QPixmap(size * 2, size * 2)
    pix.setDevicePixelRatio(2)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    glow = QColor(color)
    glow.setAlpha(70)
    p.setBrush(QBrush(glow))
    p.setPen(Qt.NoPen)
    p.drawEllipse(0, 0, size * 2, size * 2)
    p.setBrush(QBrush(QColor(color)))
    p.drawEllipse(size // 2, size // 2, size, size)
    p.end()
    return pix


def _format_uptime(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60:02d}s"
    h, rem = divmod(s, 3600)
    return f"{h}h {rem // 60:02d}m"


class ServerReader(QThread):
    line = pyqtSignal(str)
    finished_with_code = pyqtSignal(int)

    def __init__(self, proc: subprocess.Popen):
        super().__init__()
        self.proc = proc

    def run(self):
        try:
            assert self.proc.stdout is not None
            for raw in self.proc.stdout:
                self.line.emit(raw.rstrip("\n"))
        except Exception as e:
            self.line.emit(f"[reader] erro: {e}")
        finally:
            code = self.proc.wait()
            self.finished_with_code.emit(code)


class HealthChecker(QThread):
    result = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, url: str, timeout: float = 20.0):
        super().__init__()
        self.url = url
        self.timeout = timeout

    def run(self):
        try:
            req = urllib.request.Request(self.url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
                self.result.emit(data)
        except urllib.error.HTTPError as e:
            try:
                data = json.loads(e.read().decode("utf-8"))
                self.result.emit(data)
            except Exception:
                self.failed.emit(f"HTTP {e.code}: {e.reason}")
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")


class Card(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setFrameShape(QFrame.NoFrame)


class LauncherWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — Servidor")
        self.resize(900, 620)
        self.setMinimumSize(720, 520)

        self.proc: subprocess.Popen | None = None
        self.reader: ServerReader | None = None
        self._intentional_stop = False
        self._url = ""
        self._started_at: float | None = None
        self._status_kind = "parado"

        self._build_ui()
        self._build_tray()
        self._uptime_timer = QTimer(self)
        self._uptime_timer.setInterval(1000)
        self._uptime_timer.timeout.connect(self._tick_uptime)
        self._uptime_timer.start()

        self._set_status("parado")
        self._update_url_label()

        # Auto-inicia o servidor ao abrir (útil para o atalho da Inicialização,
        # deixando o InvenSync rodando sozinho após o login). Desative com a
        # variável de ambiente INVENSYNC_NO_AUTOSTART=1.
        if os.environ.get("INVENSYNC_NO_AUTOSTART", "0") not in ("1", "true", "True"):
            QTimer.singleShot(600, self.start_server)

    # ---------- UI ----------
    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(22, 20, 22, 20)
        outer.setSpacing(16)

        header = QHBoxLayout()
        header.setSpacing(12)
        header_text = QVBoxLayout()
        header_text.setSpacing(2)
        title = QLabel(f"{APP_NAME} Server")
        title.setObjectName("title")
        subtitle = QLabel("Painel de controle do servidor do almoxarifado")
        subtitle.setObjectName("subtitle")
        header_text.addWidget(title)
        header_text.addWidget(subtitle)
        header.addLayout(header_text)
        header.addStretch()
        outer.addLayout(header)

        # Status card
        status_card = Card()
        sc = QVBoxLayout(status_card)
        sc.setContentsMargins(18, 14, 18, 16)
        sc.setSpacing(10)
        sc_label = QLabel("Status")
        sc_label.setObjectName("sectionLabel")
        sc.addWidget(sc_label)

        sc_row = QHBoxLayout()
        sc_row.setSpacing(10)
        self.status_dot = QLabel()
        self.status_dot.setFixedSize(24, 24)
        self.status_text = QLabel("Parado")
        self.status_text.setObjectName("statusText")
        self.uptime_label = QLabel("")
        self.uptime_label.setObjectName("uptime")
        sc_row.addWidget(self.status_dot)
        sc_row.addWidget(self.status_text)
        sc_row.addSpacing(10)
        sc_row.addWidget(self.uptime_label)
        sc_row.addStretch()

        self.url_label = QLabel("")
        self.url_label.setObjectName("urlLabel")
        self.url_label.setOpenExternalLinks(True)
        self.url_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        sc_row.addWidget(self.url_label)

        self.open_btn = QPushButton("Abrir no Navegador  ↗")
        self.open_btn.setObjectName("btnOpen")
        self.open_btn.setCursor(Qt.PointingHandCursor)
        self.open_btn.clicked.connect(self._open_browser)
        sc_row.addWidget(self.open_btn)
        sc.addLayout(sc_row)
        outer.addWidget(status_card)

        # Config + actions card
        ctrl_card = Card()
        cc = QVBoxLayout(ctrl_card)
        cc.setContentsMargins(18, 14, 18, 16)
        cc.setSpacing(12)
        cc_label = QLabel("Configuração")
        cc_label.setObjectName("sectionLabel")
        cc.addWidget(cc_label)

        cfg_row = QHBoxLayout()
        cfg_row.setSpacing(10)
        host_lbl = QLabel("Host")
        host_lbl.setObjectName("fieldLabel")
        self.host_input = QLineEdit(DEFAULT_HOST)
        self.host_input.setMaximumWidth(180)
        self.host_input.editingFinished.connect(self._update_url_label)
        cfg_row.addWidget(host_lbl)
        cfg_row.addWidget(self.host_input)
        cfg_row.addSpacing(8)
        port_lbl = QLabel("Porta")
        port_lbl.setObjectName("fieldLabel")
        self.port_input = QLineEdit(DEFAULT_PORT)
        self.port_input.setMaximumWidth(90)
        self.port_input.editingFinished.connect(self._update_url_label)
        cfg_row.addWidget(port_lbl)
        cfg_row.addWidget(self.port_input)
        cfg_row.addStretch()
        cc.addLayout(cfg_row)

        sep = QFrame()
        sep.setObjectName("sep")
        sep.setFixedHeight(1)
        cc.addWidget(sep)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.start_btn = QPushButton("▶  Iniciar")
        self.start_btn.setObjectName("btnStart")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.clicked.connect(self.start_server)

        self.stop_btn = QPushButton("■  Parar")
        self.stop_btn.setObjectName("btnStop")
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.clicked.connect(self.stop_server)

        self.restart_btn = QPushButton("↻  Reiniciar")
        self.restart_btn.setObjectName("btnRestart")
        self.restart_btn.setCursor(Qt.PointingHandCursor)
        self.restart_btn.clicked.connect(self.restart_server)

        self.test_btn = QPushButton("🔍  Testar conexão")
        self.test_btn.setObjectName("btnTest")
        self.test_btn.setCursor(Qt.PointingHandCursor)
        self.test_btn.clicked.connect(self.test_health)
        self.test_btn.setToolTip("Chama /health e mostra o status do PostgreSQL.")

        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.stop_btn)
        btn_row.addWidget(self.restart_btn)
        btn_row.addWidget(self.test_btn)
        btn_row.addStretch()

        self.clear_btn = QPushButton("Limpar log")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(lambda: self.log_view.clear())
        btn_row.addWidget(self.clear_btn)
        cc.addLayout(btn_row)
        outer.addWidget(ctrl_card)

        log_label = QLabel("Logs")
        log_label.setObjectName("sectionLabel")
        outer.addWidget(log_label)

        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("log")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        self.log_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        outer.addWidget(self.log_view, 1)

        self.setCentralWidget(root)
        self.setStyleSheet(QSS)

        for card in (status_card, ctrl_card):
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(24)
            shadow.setOffset(0, 4)
            shadow.setColor(QColor(0, 0, 0, 90))
            card.setGraphicsEffect(shadow)

    def _build_tray(self):
        self.tray = QSystemTrayIcon(self)
        if ICON_PATH.exists():
            app_icon = QIcon(str(ICON_PATH))
        else:
            app_icon = self.style().standardIcon(QStyle.SP_ComputerIcon)
        self.tray.setIcon(app_icon)
        self.tray.setToolTip(f"{APP_NAME} — Servidor")

        menu = QMenu()
        menu.addAction(QAction("Mostrar Janela", self, triggered=self._restore_window))
        menu.addAction(QAction("Abrir no Navegador", self, triggered=self._open_browser))
        menu.addSeparator()
        menu.addAction(QAction("Iniciar", self, triggered=self.start_server))
        menu.addAction(QAction("Parar", self, triggered=self.stop_server))
        menu.addSeparator()
        menu.addAction(QAction("Sair", self, triggered=self._real_quit))
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()
        self.setWindowIcon(self.tray.icon())

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.isVisible():
                self.hide()
            else:
                self._restore_window()

    def _restore_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # ---------- Status ----------
    def _set_status(self, kind: str):
        self._status_kind = kind
        meta = {
            "parado":    (C_TEXT_MUTED, "Parado"),
            "iniciando": (C_WARNING,    "Iniciando…"),
            "rodando":   (C_SUCCESS,    "Rodando"),
            "parando":   (C_WARNING,    "Parando…"),
            "erro":      (C_DANGER,     "Erro"),
        }
        color, text = meta.get(kind, (C_TEXT_MUTED, kind))
        self.status_dot.setPixmap(_dot_pixmap(color, 12))
        self.status_text.setText(text)
        self.status_text.setStyleSheet(f"color: {color};")

        if kind == "rodando":
            if self._started_at is None:
                self._started_at = time.time()
        else:
            self._started_at = None
            self.uptime_label.setText("")

        running = kind in ("rodando", "iniciando")
        transitioning = kind == "parando"
        self.start_btn.setEnabled(not running and not transitioning)
        self.stop_btn.setEnabled(running)
        self.restart_btn.setEnabled(running)
        self.test_btn.setEnabled(kind == "rodando")
        self.host_input.setEnabled(not running and not transitioning)
        self.port_input.setEnabled(not running and not transitioning)

    def _tick_uptime(self):
        if self._status_kind == "rodando" and self._started_at is not None:
            self.uptime_label.setText(f"· ativo há {_format_uptime(time.time() - self._started_at)}")

    def _update_url_label(self):
        host = self.host_input.text().strip() or DEFAULT_HOST
        port = self.port_input.text().strip() or DEFAULT_PORT
        display_host = _local_ip() if host in ("0.0.0.0", "") else host
        self._url = f"http://{display_host}:{port}"
        self.url_label.setText(f'<a href="{self._url}">{self._url}</a>')

    # ---------- Log ----------
    def _log(self, line: str):
        self.log_view.appendPlainText(line)

    # ---------- Server control ----------
    def start_server(self):
        if self.proc and self.proc.poll() is None:
            return
        host = self.host_input.text().strip() or DEFAULT_HOST
        port = self.port_input.text().strip() or DEFAULT_PORT
        try:
            int(port)
        except ValueError:
            QMessageBox.warning(self, "Porta inválida", "A porta deve ser um número inteiro.")
            return
        if not SERVE_SCRIPT.exists():
            QMessageBox.critical(self, "serve.py não encontrado", f"Não encontrei:\n{SERVE_SCRIPT}")
            return
        if _port_in_use(host, int(port)):
            r = QMessageBox.warning(
                self, "Porta já em uso",
                f"A porta {port} em {host} já está sendo usada por outro processo.\n\n"
                "Pode ser uma instância anterior do servidor.\n"
                "Recomendado: cancelar e rodar no PowerShell:\n"
                "    Get-Process python, pythonw | Stop-Process -Force\n\n"
                "Iniciar mesmo assim?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if r != QMessageBox.Yes:
                self._log(f">>> abortado: porta {port} já em uso")
                self._set_status("parado")
                return

        self._update_url_label()
        env = os.environ.copy()
        env["SERVE_HOST"] = host
        env["SERVE_PORT"] = port
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"

        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

        self._intentional_stop = False
        self._set_status("iniciando")
        self._log(f'>>> iniciando: "{sys.executable}" "{SERVE_SCRIPT}" (host={host} port={port})')

        try:
            self.proc = subprocess.Popen(
                [sys.executable, str(SERVE_SCRIPT)],
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                creationflags=creationflags,
            )
        except Exception as e:
            self._log(f"[ERRO] falha ao iniciar processo: {e}")
            self._set_status("erro")
            self.proc = None
            return

        self.reader = ServerReader(self.proc)
        self.reader.line.connect(self._on_server_line)
        self.reader.finished_with_code.connect(self._on_server_exited)
        self.reader.start()
        QTimer.singleShot(1500, self._maybe_mark_running)

    def _maybe_mark_running(self):
        if self.proc and self.proc.poll() is None:
            self._set_status("rodando")

    def _on_server_line(self, line: str):
        self._log(line)

    def _on_server_exited(self, code: int):
        self._log(f">>> servidor encerrou (exit code={code})")
        if self._intentional_stop:
            self._set_status("parado")
        else:
            kind = "parado" if code == 0 else "erro"
            self._set_status(kind)
            if kind == "erro" and not self.isVisible():
                self.tray.showMessage(
                    APP_NAME, f"Servidor parou inesperadamente (code={code}).",
                    QSystemTrayIcon.Warning, 4000,
                )
        self.proc = None
        self.reader = None

    def stop_server(self):
        if not self.proc or self.proc.poll() is not None:
            self._set_status("parado")
            return
        self._intentional_stop = True
        self._set_status("parando")
        self._log(">>> parando servidor (terminate)...")
        try:
            self.proc.terminate()
        except Exception as e:
            self._log(f"[ERRO] terminate: {e}")
        QTimer.singleShot(5000, self._force_kill_if_needed)

    def _force_kill_if_needed(self):
        if self.proc and self.proc.poll() is None:
            self._log(">>> processo ainda vivo após 5s, forçando kill...")
            try:
                self.proc.kill()
            except Exception as e:
                self._log(f"[ERRO] kill: {e}")

    def restart_server(self):
        if not self.proc:
            self.start_server()
            return
        self._log(">>> reiniciando...")
        self._intentional_stop = True
        self._set_status("parando")
        try:
            self.proc.terminate()
        except Exception:
            pass

        def _after():
            if self.proc and self.proc.poll() is None:
                QTimer.singleShot(300, _after)
                return
            self.start_server()

        QTimer.singleShot(300, _after)

    def _open_browser(self):
        self._update_url_label()
        QDesktopServices.openUrl(QUrl(self._url))

    # ---------- Health check ----------
    def test_health(self):
        if not (self.proc and self.proc.poll() is None):
            QMessageBox.warning(self, "Servidor parado", "Inicie o servidor antes de testar a conexão.")
            return
        port = self.port_input.text().strip() or DEFAULT_PORT
        url = f"http://127.0.0.1:{port}/health"
        self._log(f">>> testando conexão: GET {url}")
        self.test_btn.setEnabled(False)
        self.test_btn.setText("Testando...")
        self._health_thread = HealthChecker(url)
        self._health_thread.result.connect(self._on_health_result)
        self._health_thread.failed.connect(self._on_health_failed)
        self._health_thread.finished.connect(self._on_health_done)
        self._health_thread.start()

    def _on_health_result(self, data: dict):
        status = (data.get("status") or "?").upper()
        uptime = data.get("uptime", "?")
        checks = data.get("checks") or {}
        self._log(f">>> /health: {status} (uptime={uptime})")

        rows = []
        for name, info in checks.items():
            st = (info.get("status") or "?").lower()
            lat = info.get("latency_ms")
            err = info.get("error")
            color = "#22c55e" if st == "ok" else "#ef4444"
            rows.append(
                f'<tr><td style="padding:3px 14px 3px 0;color:{color};">●</td>'
                f'<td style="padding:3px 14px 3px 0;font-weight:600;">{name}</td>'
                f'<td style="padding:3px 14px 3px 0;color:{color};">{st.upper()}</td>'
                f'<td style="padding:3px 0;color:#9ba3b4;">{lat}ms</td></tr>'
            )
            if err:
                rows.append(
                    f'<tr><td colspan="4" style="padding:0 0 6px 24px;'
                    f'color:#ff8b8b;font-size:11px;">{err}</td></tr>'
                )

        all_ok = status == "OK"
        header_color = "#22c55e" if all_ok else "#f59e0b"
        html = (
            f'<div style="font-family:Segoe UI,sans-serif;">'
            f'<div style="font-size:14px;font-weight:600;color:{header_color};margin-bottom:8px;">'
            f"Status geral: {status}</div>"
            f'<div style="font-size:12px;color:#9ba3b4;margin-bottom:12px;">Uptime: {uptime}</div>'
            f'<table style="border-collapse:collapse;">{"".join(rows)}</table></div>'
        )
        box = QMessageBox(self)
        box.setWindowTitle("Resultado /health")
        box.setIcon(QMessageBox.Information if all_ok else QMessageBox.Warning)
        box.setTextFormat(Qt.RichText)
        box.setText(html)
        box.exec_()

    def _on_health_failed(self, msg: str):
        self._log(f">>> /health falhou: {msg}")
        QMessageBox.critical(
            self, "Erro ao consultar /health",
            f"Não consegui chamar /health.\n\n{msg}\n\nConfira se o servidor subiu corretamente.")

    def _on_health_done(self):
        self.test_btn.setText("🔍  Testar conexão")
        self.test_btn.setEnabled(self._status_kind == "rodando")

    # ---------- Window lifecycle ----------
    def closeEvent(self, event):
        if self.proc and self.proc.poll() is None:
            event.ignore()
            self.hide()
            self.tray.showMessage(
                APP_NAME,
                "Servidor continua rodando em segundo plano. "
                "Use o ícone na bandeja para restaurar ou sair.",
                QSystemTrayIcon.Information, 3000,
            )
        else:
            event.accept()
            self.tray.hide()
            QApplication.quit()

    def _real_quit(self):
        if self.proc and self.proc.poll() is None:
            r = QMessageBox.question(
                self, "Sair", "O servidor está rodando. Encerrar e sair?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if r != QMessageBox.Yes:
                return
            self._intentional_stop = True
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        self.tray.hide()
        QApplication.quit()


def main():
    if not SERVE_SCRIPT.exists():
        print(f"ERRO: {SERVE_SCRIPT} não encontrado.", file=sys.stderr)
        sys.exit(1)

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    families = set(QFontDatabase().families())
    for f in ("Segoe UI Variable", "Segoe UI", "Inter"):
        if f in families:
            app.setFont(QFont(f, 10))
            break

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.warning(
            None, "Bandeja indisponível",
            "A bandeja do sistema não está disponível. "
            "O launcher continuará funcionando, mas sem ícone na bandeja.")

    win = LauncherWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
