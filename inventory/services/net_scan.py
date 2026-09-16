"""Descoberta de dispositivos na rede via ARP (+ DNS reverso p/ o nome).

Como a rede é L2 plana, a tabela ARP do servidor lista IP+MAC dos aparelhos
ativos (inclusive DHCP e de outras faixas /24 do mesmo switch). O DNS reverso
(PTR) resolve o hostname (ex.: Comercial1.palazzo.local).

Fluxo:
  - `scan(sweep=True)` faz um ping-sweep das /24 conhecidas p/ POPULAR o ARP
    (o ping dispara ARP mesmo em PC que bloqueia ICMP) e então lê a tabela;
  - sem sweep, lê só o cache atual (rápido).

Tudo best-effort: nunca levanta exceção para fora de `scan()`.
"""
import ipaddress
import re
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

from ..extensions import db

# IP + MAC em qualquer formato do `arp -a` (Windows/Linux).
_ARP_RE = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3})[^0-9a-fA-F]+"
                     r"([0-9a-fA-F]{2}(?:[-:][0-9a-fA-F]{2}){5})")


def _read_arp():
    """Lê a tabela ARP -> lista de (ip, mac_normalizado)."""
    try:
        out = subprocess.run(["arp", "-a"], capture_output=True, timeout=15).stdout
    except Exception:  # noqa: BLE001
        return []
    texto = out.decode("latin-1", "replace")
    pares = []
    for ip, mac in _ARP_RE.findall(texto):
        pares.append((ip, mac.lower().replace(":", "-")))
    return pares


def _e_dispositivo(ip, mac):
    """Filtra broadcast/multicast/link-local; mantém só IP privado real."""
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if a.is_loopback or a.is_multicast or a.is_link_local or a.is_unspecified:
        return False
    if ip.endswith(".255") or ip.endswith(".0"):
        return False
    if mac in ("ff-ff-ff-ff-ff-ff", "00-00-00-00-00-00"):
        return False
    if mac.startswith(("01-00-5e", "33-33")):   # MACs de multicast
        return False
    return a.is_private


def _rdns(ip):
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:  # noqa: BLE001
        return ""


_NB_RE = re.compile(r"^\s*([^\s<]+)\s+<00>\s+UNIQUE", re.M)


def _netbios(ip):
    """Nome NetBIOS via nbtstat (pega Windows sem PTR no DNS). Lento -> só no deep."""
    try:
        out = subprocess.run(["nbtstat", "-A", ip], capture_output=True, timeout=3).stdout
    except Exception:  # noqa: BLE001
        return ""
    m = _NB_RE.search(out.decode("latin-1", "replace"))
    nome = m.group(1).strip() if m else ""
    return "" if nome in ("", "__MSBROWSE__") else nome


def _nome(ip, deep=False):
    n = _rdns(ip)
    if not n and deep:
        n = _netbios(ip)
    return n


def active_set():
    """(macs, ips) ativos agora na tabela ARP — sem DNS, rápido. Best-effort."""
    macs, ips = set(), set()
    try:
        for ip, mac in _read_arp():
            if _e_dispositivo(ip, mac):
                macs.add(mac)
                ips.add(ip)
    except Exception:  # noqa: BLE001
        pass
    return macs, ips


def _ping(ip):
    """1 pacote, 400 ms — só p/ disparar o ARP (não importa se ICMP é bloqueado)."""
    try:
        subprocess.run(["ping", "-n", "1", "-w", "400", ip],
                       capture_output=True, timeout=2)
    except Exception:  # noqa: BLE001
        pass


def _subnets_alvo(app):
    """/24 do servidor + /24 de cada máquina cadastrada com IP fixo."""
    subs = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                subs.add(ipaddress.ip_network(ip + "/24", strict=False))
    except Exception:  # noqa: BLE001
        pass
    try:
        from ..models.machine import Machine
        for (ipx,) in db.session.query(Machine.ip_address).all():
            ipx = (ipx or "").strip()
            try:
                ipaddress.ip_address(ipx)
                subs.add(ipaddress.ip_network(ipx + "/24", strict=False))
            except ValueError:
                continue
    except Exception:  # noqa: BLE001
        pass
    return subs


# Teto TOTAL do ping-sweep. No caso típico ele nem é alcançado (1024 alvos / 64
# trabalhadores ≈ 16 levas de ~0,4s), mas no pior caso cada ping vai até 2s e a
# conta dava ~32s de request.
_SWEEP_TETO = 20.0


def _sweep(app):
    """Popula a tabela ARP pingando as /24 conhecidas. Best-effort e com teto.

    Os pings que não couberam no teto **continuam rodando** e ainda populam o
    ARP — só não chegam a tempo desta leitura. Na prática aparecem na varredura
    seguinte, porque o cache ARP dura alguns minutos.
    """
    alvos = [str(h) for net in _subnets_alvo(app) for h in net.hosts()]
    if not alvos:
        return
    limite = time.monotonic() + _SWEEP_TETO
    ex = ThreadPoolExecutor(max_workers=64)
    try:
        futs = [ex.submit(_ping, ip) for ip in alvos[:1024]]   # teto de segurança
        for f in futs:
            try:
                f.result(timeout=max(0.0, limite - time.monotonic()))
            except Exception:  # noqa: BLE001 — inclui o timeout do future
                pass
    finally:
        # Mesmo motivo do `scan()`: `with ThreadPoolExecutor(...)` faria
        # shutdown(wait=True) e esperaria TODOS os pings restantes.
        ex.shutdown(wait=False, cancel_futures=True)


def scan(app, sweep=False):
    """Descobre os dispositivos ativos. Retorna lista de dicts:
    {ip, mac, name} ordenada por IP. Nunca levanta exceção."""
    try:
        if sweep:
            _sweep(app)
        pares = [(ip, mac) for ip, mac in _read_arp() if _e_dispositivo(ip, mac)]
        # dedup por IP, preservando o 1º MAC visto
        vistos, unicos = set(), []
        for ip, mac in pares:
            if ip not in vistos:
                vistos.add(ip)
                unicos.append((ip, mac))
        ips = [ip for ip, _ in unicos]

        nomes = {}
        # Teto TOTAL da resolução de nomes, não por IP: o timeout por future era
        # gasto um a um, então N hosts lentos somavam N × timeout.
        limite = time.monotonic() + (8.0 if sweep else 5.0)
        ex = ThreadPoolExecutor(max_workers=32)
        try:
            futs = {ip: ex.submit(_nome, ip, sweep) for ip in ips}
            for ip, f in futs.items():
                try:
                    nomes[ip] = f.result(timeout=max(0.0, limite - time.monotonic()))
                except Exception:  # noqa: BLE001 — inclui o timeout do future
                    nomes[ip] = ""
        finally:
            # `with ThreadPoolExecutor(...)` fazia shutdown(wait=True) na saída:
            # esperava TODAS as buscas, inclusive as que já haviam estourado o
            # timeout acima — um PTR lento segurava a varredura inteira e o
            # timeout não valia de nada. Aqui a resposta sai na hora; o que
            # sobrou é cancelado (fila) ou morre sozinho (já rodando).
            ex.shutdown(wait=False, cancel_futures=True)

        devs = [{"ip": ip, "mac": mac, "name": nomes.get(ip, "")}
                for ip, mac in unicos]
        devs.sort(key=lambda d: ipaddress.ip_address(d["ip"]))
        return devs
    except Exception:  # noqa: BLE001
        return []
