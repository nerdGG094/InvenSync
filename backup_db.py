"""
Backup do banco PostgreSQL do InvenSync via pg_dump (formato custom -Fc).

Uso:
    python backup_db.py            # gera um backup e aplica rotação

Também é importável pelo app (rota admin "Backups"):
    from backup_db import run_backup, list_backups, backup_dir

Configuração (via .env):
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD   (já usados pelo app)
    BACKUP_DIR    pasta de destino (default: <projeto>/backups)
    BACKUP_KEEP   quantos backups manter (default: 30)
    PG_DUMP       caminho do pg_dump.exe (default: autodetecta o PostgreSQL instalado)

Pensado para ser chamado por uma Tarefa Agendada do Windows (diária).
"""
import datetime
import glob
import os
import subprocess
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # noqa: BLE001
    load_dotenv = None

PROJECT_ROOT = Path(__file__).resolve().parent

if load_dotenv:
    load_dotenv(PROJECT_ROOT / ".env")


def _pg_dump_exe() -> str:
    override = os.environ.get("PG_DUMP")
    if override and Path(override).exists():
        return override
    # Autodetecta a maior versão instalada (ex.: PostgreSQL 17 antes da 16).
    found = sorted(glob.glob(r"C:\Program Files\PostgreSQL\*\bin\pg_dump.exe"), reverse=True)
    if found:
        return found[0]
    return "pg_dump"  # confia no PATH


def backup_dir() -> Path:
    d = Path(os.environ.get("BACKUP_DIR") or (PROJECT_ROOT / "backups"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _keep() -> int:
    try:
        return max(1, int(os.environ.get("BACKUP_KEEP", "30")))
    except ValueError:
        return 30


def list_backups():
    """Lista os backups existentes, do mais novo para o mais antigo."""
    items = []
    for p in backup_dir().glob("*.dump"):
        st = p.stat()
        items.append({
            "name": p.name,
            "path": str(p),
            "size": st.st_size,
            "mtime": datetime.datetime.fromtimestamp(st.st_mtime),
        })
    items.sort(key=lambda i: i["mtime"], reverse=True)
    return items


def _rotate():
    files = sorted(backup_dir().glob("*.dump"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[_keep():]:
        try:
            old.unlink()
        except OSError:
            pass


def run_backup(timestamp: str = None):
    """Gera um backup. Retorna (ok: bool, mensagem: str, caminho|None)."""
    host = os.environ.get("DB_HOST", "127.0.0.1")
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ.get("DB_NAME", "inventario_almox")
    user = os.environ.get("DB_USER", "postgres")
    pwd = os.environ.get("DB_PASSWORD", "")

    ts = timestamp or datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = backup_dir() / f"{name}_{ts}.dump"
    exe = _pg_dump_exe()

    cmd = [exe, "-h", host, "-p", str(port), "-U", user, "-d", name, "-Fc", "-f", str(out)]
    env = os.environ.copy()
    env["PGPASSWORD"] = pwd

    try:
        r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=900)
    except FileNotFoundError:
        return False, f"pg_dump não encontrado (PG_DUMP={exe}).", None
    except Exception as e:  # noqa: BLE001
        return False, f"Falha ao executar pg_dump: {e}", None

    if r.returncode != 0:
        if out.exists():
            try:
                out.unlink()
            except OSError:
                pass
        return False, (r.stderr or "erro desconhecido no pg_dump").strip(), None

    _rotate()
    size = out.stat().st_size if out.exists() else 0
    return True, f"Backup gerado: {out.name} ({size/1024/1024:.1f} MB)", str(out)


if __name__ == "__main__":
    ok, msg, _ = run_backup()
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{stamp} {'[OK]' if ok else '[ERRO]'} {msg}")
    sys.exit(0 if ok else 1)
