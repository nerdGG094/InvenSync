"""Detecção inteligente das câmeras (SMD): escuta os eventos dos DVRs.

Quem faz a análise de vídeo é o **próprio DVR** — o InvenSync não decodifica
nem roda modelo nenhum, então isto custa praticamente zero de CPU. Cada DVR
capaz mantém uma conexão HTTP aberta (`eventManager.cgi?action=attach`) que
empurra os eventos assim que acontecem:

    Code=SmartMotionHuman;action=Start;index=8;data={
       "object" : [ { "Rect" : [ 798, 116, 825, 215 ], "HumanID" : 0 } ]
    }

`index` é o canal (base 0) e `Rect` é [x1,y1,x2,y2] na escala **0-1023**
(conferida nos eventos reais — veja `DvrDetection.ESCALA`), que vira % da
imagem para o navegador desenhar a caixa sobre o vídeo.

Duas saídas:
  - **estado ao vivo** em memória (`ativos()`), consumido pela página de câmeras;
  - **histórico** em `DvrDetection`, para consulta depois.

Nem todo DVR suporta: os Intelbras MHDX 11xx/1216 expõem a configuração mas
recusam ativá-la (HTTP 400); o MHDX1232 aceita nos 16 primeiros canais. Um DVR
que não emite eventos apenas não gera nada — a thread fica ociosa e reconecta.
"""
import json
import os
import re
import threading
import time

from ..extensions import db

_started = False
_lock = threading.Lock()

# Estado ao vivo: (dvr_id, canal) -> [ {"tipo","rect","ts"}, ... ]
# É uma LISTA porque um mesmo canal reporta vários objetos ao mesmo tempo —
# várias pessoas, ou pessoa e veículo juntos. Guardar um só fazia o último
# evento apagar os anteriores (numa sala cheia, ninguém aparecia).
_ativos = {}
_ativos_lock = threading.Lock()

# Code=SmartMotionHuman;action=Start;index=8;data={...}
_CABECALHO = re.compile(r"Code=(\w+);\s*action=(\w+);\s*index=(\d+)(?:;\s*data=)?", re.I)

TIPOS = {"smartmotionhuman": "human", "smartmotionvehicle": "vehicle"}
CODES = "[SmartMotionHuman,SmartMotionVehicle]"

# Segundos dentro dos quais um novo "Start" no mesmo canal/tipo é considerado o
# MESMO objeto ainda em cena (o DVR repete o evento). Medido: repete a cada ~5s.
_CONTINUA = 20.0


# --------------------------------------------------------------------------- #
# Estado ao vivo (o que a página de câmeras lê)
# --------------------------------------------------------------------------- #
def ativos(dvr_id=None, ttl=8.0):
    """Detecções em curso: {canal: [ {"tipo","rect","idade"}, ... ]}.

    É uma LISTA por canal: o DVR reporta vários objetos ao mesmo tempo (várias
    pessoas, ou pessoa e veículo juntos). `ttl` é o prazo de validade (config
    `DVR_DETECT_TTL`): o DVR manda `Stop`, mas se a conexão cair no meio a
    caixa ficaria presa na tela para sempre."""
    agora = time.time()
    out = {}
    with _ativos_lock:
        for (did, ch), lista in list(_ativos.items()):
            # Só descarta de vez depois da janela de continuação; senão o objeto
            # sumiria da memória só porque alguém abriu a tela, e o próximo
            # "Start" repetido viraria um objeto novo no histórico.
            lista[:] = [o for o in lista if agora - o["ts"] <= max(ttl, _CONTINUA)]
            if not lista:
                _ativos.pop((did, ch), None)
                continue
            if dvr_id is not None and did != dvr_id:
                continue
            visiveis = [{"tipo": o["tipo"], "rect": o["rect"],
                         "idade": round(agora - o["ts"], 1)}
                        for o in lista if agora - o["ts"] <= ttl]
            if not visiveis:
                continue
            alvo = out.setdefault(did, {}) if dvr_id is None else out
            alvo[ch] = visiveis
    return out


_cfg_cache = {}          # dvr_id -> (ts, {canais com SMD ligado})


def canais_com_deteccao(d, senha, ttl=300.0):
    """Canais com detecção inteligente LIGADA no DVR (conjunto de nºs 1..N).

    Lê a configuração do aparelho, com cache — serve para a tela avisar quando
    a câmera simplesmente não tem detecção, em vez de deixar o usuário achando
    que a caixa está quebrada. Falhou? Devolve vazio (best-effort)."""
    agora = time.time()
    got = _cfg_cache.get(d.id)
    if got and agora - got[0] < ttl:
        return got[1]
    canais = set()
    try:
        from . import dvr_cam
        op, base = dvr_cam._opener(d, senha)
        texto = op.open(f"{base}/cgi-bin/configManager.cgi?action=getConfig"
                        "&name=SmartMotionDetect", timeout=8).read(400000).decode("latin-1", "replace")
        for linha in texto.splitlines():
            linha = linha.strip()
            if linha.startswith("table.SmartMotionDetect[") and linha.endswith(".Enable=true"):
                try:
                    canais.add(int(linha.split("[", 1)[1].split("]", 1)[0]) + 1)
                except (ValueError, IndexError):
                    pass
    except Exception:  # noqa: BLE001 — DVR fora do ar/sem suporte
        canais = set()
    _cfg_cache[d.id] = (agora, canais)
    return canais


def _mesmo_objeto(a, b, minimo=0.30) -> bool:
    """Mesmo objeto se as caixas se SOBREPÕEM bastante (IoU >= `minimo`).

    Critério por sobreposição, e não por distância entre centros: numa sala
    cheia duas pessoas lado a lado ficam a poucos por cento uma da outra e
    seriam fundidas numa caixa só, sumindo com quase todo mundo. Caixas que não
    se cruzam são objetos diferentes, por mais próximas que estejam; a mesma
    pessoa andando devagar continua se sobrepondo entre um evento e outro."""
    if not a or not b:
        return True                       # sem caixa: trata como o mesmo
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if not inter:
        return False
    area_a = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
    area_b = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
    uniao = area_a + area_b - inter
    return uniao > 0 and (inter / uniao) >= minimo


def _marcar(dvr_id, ch, tipo, rect):
    """Registra o objeto. Devolve True se é NOVO (e não o mesmo se movendo)."""
    agora = time.time()
    with _ativos_lock:
        lista = _ativos.setdefault((dvr_id, ch), [])
        for o in lista:
            if o["tipo"] == tipo and _mesmo_objeto(o["rect"], rect):
                o["rect"], o["ts"] = rect, agora      # mesmo objeto: só atualiza
                return False
        lista.append({"tipo": tipo, "rect": rect, "ts": agora})
        return True


def _desmarcar(dvr_id, ch, tipo=None):
    """Fim do evento: some com os objetos daquele tipo (ou com todos)."""
    with _ativos_lock:
        lista = _ativos.get((dvr_id, ch))
        if not lista:
            return
        if tipo is not None:
            lista[:] = [o for o in lista if o["tipo"] != tipo]
        if tipo is None or not lista:
            _ativos.pop((dvr_id, ch), None)


# --------------------------------------------------------------------------- #
# Leitura do fluxo de eventos
# --------------------------------------------------------------------------- #
def _rects_do_payload(texto):
    """TODAS as caixas do evento — um evento pode trazer vários objetos.

    O bloco lido do multipart traz o corpo do evento e, colado, o cabeçalho do
    evento seguinte; por isso cortamos no delimitador antes de interpretar."""
    corpo = texto.split("--myboundary", 1)[0]
    ini = corpo.find("{")
    if ini < 0:
        return []

    def limpa(r):
        try:
            return [int(v) for v in r[:4]]
        except (ValueError, TypeError):
            return None

    try:
        dados = json.loads(corpo[ini:])
        objetos = dados.get("object") or []
        if isinstance(objetos, dict):
            objetos = [objetos]
        saida = [limpa(o.get("Rect")) for o in objetos
                 if isinstance(o.get("Rect"), list) and len(o.get("Rect")) >= 4]
        saida = [r for r in saida if r]
        if saida:
            return saida
    except (ValueError, TypeError, AttributeError):
        pass
    # Tolerante: o JSON vem com sobra colada, então varre o texto direto.
    achados = [limpa(m.split(",")) for m in
               re.findall(r'"Rect"\s*:\s*\[\s*([\d\s,]+)\]', corpo)]
    return [r for r in achados if r]


def _processar(app, d, bruto):
    """Trata um bloco do multipart. Devolve True se era um evento conhecido."""
    m = _CABECALHO.search(bruto)
    if not m:
        return False
    code, acao, idx = m.group(1).lower(), m.group(2).lower(), int(m.group(3))
    tipo = TIPOS.get(code)
    if not tipo:
        return False
    canal = idx + 1                       # o DVR conta a partir de 0

    if acao == "stop":
        _desmarcar(d.id, canal, tipo)     # só o tipo que terminou
        _encerrar_no_banco(app, d.id, canal, tipo)
        return True

    if acao != "start":
        return True

    # O DVR reenvia "Start" do MESMO objeto enquanto ele continua em cena (a
    # cada ~5s). `_marcar` diz se é objeto novo; se for o mesmo se movendo, só
    # atualiza a caixa na tela e não escreve no banco — senão o histórico enche
    # de duplicatas e o banco leva uma gravação por repetição, à toa.
    for rect in _rects_do_payload(bruto) or [None]:
        if _marcar(d.id, canal, tipo, rect):
            _gravar_no_banco(app, d, canal, tipo, rect)
    return True


def _gravar_no_banco(app, d, canal, tipo, rect):
    from ..models.dvr_detection import DvrDetection
    with app.app_context():
        try:
            det = DvrDetection(dvr_id=d.id, channel=canal, object_type=tipo)
            if rect:
                det.rect_x1, det.rect_y1, det.rect_x2, det.rect_y2 = rect
            db.session.add(det)
            db.session.commit()
        except Exception:  # noqa: BLE001 — histórico nunca derruba a escuta
            db.session.rollback()
            return
    _talvez_avisar(app, d, canal, tipo)


def _encerrar_no_banco(app, dvr_id, canal, tipo):
    from ..models.dvr_detection import DvrDetection
    with app.app_context():
        try:
            det = (DvrDetection.query
                   .filter_by(dvr_id=dvr_id, channel=canal, object_type=tipo, ended_at=None)
                   .order_by(DvrDetection.id.desc()).first())
            if det:
                det.ended_at = db.func.now()
                db.session.commit()
        except Exception:  # noqa: BLE001
            db.session.rollback()


# --------------------------------------------------------------------------- #
# Aviso por e-mail fora do expediente (desligado por padrão)
# --------------------------------------------------------------------------- #
_ultimo_aviso = {}     # (dvr_id, canal) -> timestamp


def _fora_do_expediente(app) -> bool:
    """True se a hora atual está na janela de vigilância (ex.: 19-6)."""
    faixa = (app.config.get("DVR_ALERT_HOURS") or "").strip()
    if not faixa:
        return False
    try:
        ini, fim = [int(x) for x in faixa.split("-", 1)]
    except (ValueError, TypeError):
        return False
    h = time.localtime().tm_hour
    return (ini <= h or h < fim) if ini > fim else (ini <= h < fim)


def _talvez_avisar(app, d, canal, tipo):
    """E-mail à TI quando detecta gente fora do expediente. Só com DVR_ALERT_ENABLED=1."""
    if not app.config.get("DVR_ALERT_ENABLED"):
        return
    if tipo != "human" or not _fora_do_expediente(app):
        return
    espera = float(app.config.get("DVR_ALERT_COOLDOWN", 900) or 900)
    chave = (d.id, canal)
    agora = time.time()
    if agora - _ultimo_aviso.get(chave, 0) < espera:
        return          # evita enxurrada: 1 aviso por canal a cada X segundos
    _ultimo_aviso[chave] = agora
    from . import mailer
    local = d.location or d.label or d.model
    try:
        with app.app_context():
            mailer.notify_ti(
                f"CFTV: movimento humano em {local} (canal {canal})",
                f"O DVR '{local}' detectou uma pessoa no canal {canal} às "
                f"{time.strftime('%d/%m/%Y %H:%M:%S')}, fora do horário comercial.")
    except Exception:  # noqa: BLE001 — aviso é best-effort
        pass


# --------------------------------------------------------------------------- #
# Thread de escuta (uma por DVR)
# --------------------------------------------------------------------------- #
def _dados(app, dvr_id):
    """Lê o DVR e devolve uma cópia SOLTA dos campos que a thread usa.

    A thread vive fora do contexto da aplicação; segurar a instância do
    SQLAlchemy daria DetachedInstanceError quando a sessão fosse encerrada."""
    from types import SimpleNamespace
    from ..models.dvr import Dvr
    from . import crypto
    with app.app_context():
        d = db.session.get(Dvr, dvr_id)
        if not d or d.status == "inativo" or not d.ip_address:
            return None, ""
        senha = crypto.decrypt(d.admin_password) or ""
        return SimpleNamespace(id=d.id, ip_address=d.ip_address, web_port=d.web_port,
                               admin_user=d.admin_user, location=d.location,
                               label=d.label, model=d.model), senha


def _escutar(app, dvr_id):
    """Mantém a conexão de eventos aberta, reconectando quando cair."""
    from . import dvr_cam

    espera = 5
    while True:
        try:
            copia, senha = _dados(app, dvr_id)
            if copia is None:
                return                              # DVR removido/inativado
            dvr_cam._openers.pop(dvr_id, None)      # negocia digest do zero
            op, base = dvr_cam._opener(copia, senha)
            resp = op.open(f"{base}/cgi-bin/eventManager.cgi?action=attach&codes={CODES}",
                           timeout=None)
            espera = 5                              # conectou: zera o recuo
            buf = b""
            while True:
                pedaco = resp.read(512)
                if not pedaco:
                    break                            # DVR encerrou: reconecta
                buf += pedaco
                while b"\r\n\r\n" in buf:
                    bloco, _, buf = buf.partition(b"\r\n\r\n")
                    texto = bloco.decode("latin-1", "replace")
                    if "Code=" in texto:
                        _processar(app, copia, texto)
                if len(buf) > 65536:                 # lixo sem delimitador
                    buf = b""
        except Exception:  # noqa: BLE001 — queda de rede, DVR reiniciando, etc.
            pass
        time.sleep(espera)
        espera = min(espera * 2, 300)                # recuo exponencial até 5 min


def alvos(app):
    """DVRs que valem escutar: ativos, com IP e senha."""
    from ..models.dvr import Dvr
    with app.app_context():
        return [d.id for d in Dvr.query.filter(Dvr.status != "inativo").all()
                if d.ip_address and d.admin_password]


def start_scheduler(app):
    global _started
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return
    if not app.config.get("DVR_EVENTS_ENABLED", True):
        return
    with _lock:
        if _started:
            return
        _started = True

    def iniciar():
        time.sleep(25)          # deixa o servidor subir antes de abrir conexões
        for dvr_id in alvos(app):
            threading.Thread(target=_escutar, args=(app, dvr_id), daemon=True,
                             name=f"dvr-eventos-{dvr_id}").start()

    threading.Thread(target=iniciar, daemon=True, name="dvr-eventos").start()
