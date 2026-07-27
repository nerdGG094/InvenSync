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
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FTimeout

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


def _sweep(app):
    alvos = [str(h) for net in _subnets_alvo(app) for h in net.hosts()]
    if not alvos:
        return
    with ThreadPoolExecutor(max_workers=64) as ex:
        list(ex.map(_ping, alvos[:1024]))   # teto de segurança


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
        with ThreadPoolExecutor(max_workers=32) as ex:
            futs = {ip: ex.submit(_nome, ip, sweep) for ip in ips}
            for ip, f in futs.items():
                try:
                    nomes[ip] = f.result(timeout=(4.0 if sweep else 2.5))
                except (FTimeout, Exception):  # noqa: BLE001
                    nomes[ip] = ""

        devs = [{"ip": ip, "mac": mac, "name": nomes.get(ip, "")}
                for ip, mac in unicos]
        devs.sort(key=lambda d: ipaddress.ip_address(d["ip"]))
        return devs
    except Exception:  # noqa: BLE001
        return []
