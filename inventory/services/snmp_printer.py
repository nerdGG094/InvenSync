"""Leitura de impressoras de rede via SNMP (UDP/161).

Busca contador de páginas, nível de toner/cilindro, modelo e nº de série usando o
**Printer-MIB padrão (RFC 3805)**. Quando o fabricante não publica o nível de
toner nesse MIB — caso das Brother, que devolvem -3 ("nível desconhecido") —, cai
para o **MIB privado da Brother**, onde o item 0x81 traz o percentual restante
(validado em campo: reporta em passos de 10%).

Tudo best-effort: erro/timeout nunca levanta, devolve {"ok": False, "error": ...}.
"""
import asyncio

# ===== Printer-MIB padrão =====
OID_SYSDESCR = "1.3.6.1.2.1.1.1.0"
OID_SYSNAME = "1.3.6.1.2.1.1.5.0"
OID_SERIAL = "1.3.6.1.2.1.43.5.1.1.17.1"
OID_PAGES = "1.3.6.1.2.1.43.10.2.1.4.1.1"
OID_SUPPLIES = "1.3.6.1.2.1.43.11.1.1"      # subárvore: .6=desc .8=max .9=nível

# ===== MIB privado Brother (fallback do toner) =====
OID_BROTHER_MAINT = "1.3.6.1.4.1.2435.2.3.9.4.2.1.5.5.8.0"
BROTHER_TONER_ITEM = 0x81                   # % restante de toner

# Obs.: no Printer-MIB, níveis negativos significam "sem leitura numérica"
# (-1 outro, -2 desconhecido, -3 resta algo) — por isso só calculamos % com n >= 0.


def _texto(v) -> str:
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace").strip()
    return str(v).strip() if v is not None else ""


def _decode_brother(blob: bytes) -> dict:
    """<item:1><tipo:1><tam:1><valor:tam> repetido; 0xff encerra."""
    out, i = {}, 0
    while i + 3 <= len(blob):
        item = blob[i]
        if item == 0xFF:
            break
        tam = blob[i + 2]
        out[item] = int.from_bytes(blob[i + 3:i + 3 + tam], "big")
        i += 3 + tam
    return out


async def _coletar(ip: str, community: str, timeout: float) -> dict:
    from puresnmp import Client, V2C, PyWrapper
    cli = PyWrapper(Client(ip, V2C(community)))

    async def get(oid, padrao=None):
        try:
            return await asyncio.wait_for(cli.get(oid), timeout=timeout)
        except Exception:  # noqa: BLE001
            return padrao

    modelo = _texto(await get(OID_SYSDESCR))
    if not modelo:
        raise TimeoutError("sem resposta SNMP")   # impressora fora/sem SNMP

    dados = {
        "ok": True, "error": None,
        "model": modelo,
        "name": _texto(await get(OID_SYSNAME)),
        "serial": _texto(await get(OID_SERIAL)),
        "pages": None, "toner_pct": None, "supplies": [],
    }
    pg = await get(OID_PAGES)
    if isinstance(pg, int):
        dados["pages"] = pg

    # Tabela de suprimentos (toner, cilindro, etc.)
    # OIDs no formato <base>.<coluna>.<entrada>.<índice>. Atenção: NÃO dá para
    # procurar ".6.1." por substring — o próprio prefixo (1.3.6.1.2.1...) contém
    # essa sequência e casaria com tudo.
    desc, nivel, maxc = {}, {}, {}
    base = OID_SUPPLIES + "."
    colunas = {"6": desc, "8": maxc, "9": nivel}
    try:
        async for oid, val in cli.walk(OID_SUPPLIES):
            s = str(oid)
            if not s.startswith(base):
                continue
            partes = s[len(base):].split(".")
            if len(partes) < 3:
                continue
            alvo = colunas.get(partes[0])
            if alvo is None:
                continue
            alvo[partes[-1]] = _texto(val) if partes[0] == "6" else val
    except Exception:  # noqa: BLE001
        pass

    for idx, nome in sorted(desc.items()):
        n, m = nivel.get(idx), maxc.get(idx)
        pct = None
        if isinstance(n, int) and isinstance(m, int) and m > 0 and n >= 0:
            pct = max(0, min(100, round(n / m * 100)))
        dados["supplies"].append({"desc": nome, "level": n, "max": m, "pct": pct})
        if pct is not None and "toner" in nome.lower() and dados["toner_pct"] is None:
            dados["toner_pct"] = pct

    # Toner sem percentual no MIB padrão (Brother): usa o MIB privado.
    if dados["toner_pct"] is None:
        blob = await get(OID_BROTHER_MAINT)
        if isinstance(blob, bytes):
            item = _decode_brother(blob).get(BROTHER_TONER_ITEM)
            if isinstance(item, int) and 0 <= item <= 100:
                dados["toner_pct"] = item
    return dados


def query(ip: str, community: str = "public", timeout: float = 3.0) -> dict:
    """Consulta uma impressora. Nunca levanta: em falha devolve ok=False."""
    if not (ip or "").strip():
        return {"ok": False, "error": "sem IP"}
    try:
        return asyncio.run(_coletar(ip.strip(), community, timeout))
    except Exception as e:  # noqa: BLE001
        nome = type(e).__name__
        msg = "sem resposta (SNMP desligado, impressora fora ou community errada)" \
            if nome in ("TimeoutError", "asyncio.TimeoutError") else f"{nome}"
        return {"ok": False, "error": msg}
