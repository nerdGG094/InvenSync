"""Backlog DEV #9 — net_scan travava em DNS lento.

O `with ThreadPoolExecutor(...)` chamava shutdown(wait=True) na saida: esperava
TODAS as buscas de nome, inclusive as que ja haviam estourado o timeout por
future. Na pratica o timeout nao valia de nada e um PTR lento segurava a
varredura inteira.
"""
import time

def test_varredura_nao_espera_dns_lento(app, monkeypatch):
    """Um PTR que nunca responde não pode segurar a varredura inteira."""
    from inventory.services import net_scan

    monkeypatch.setattr(net_scan, "_read_arp",
                        lambda: [(f"192.168.0.{i}", f"aa-bb-cc-dd-ee-{i:02x}")
                                 for i in range(10, 20)])

    def _nome_travado(ip, deep=False):
        time.sleep(30)          # o "DNS lento": nunca responde a tempo
        return "nunca"

    monkeypatch.setattr(net_scan, "_nome", _nome_travado)
    monkeypatch.setattr(net_scan, "_e_dispositivo", lambda ip, mac: True)

    inicio = time.monotonic()
    devs = net_scan.scan(app, sweep=False)
    gasto = time.monotonic() - inicio

    # o teto total é 5s sem sweep; com folga de agendamento, 15s é muito
    assert gasto < 15, f"a varredura levou {gasto:.1f}s — voltou a esperar as futures"
    assert len(devs) == 10                      # devolve os aparelhos mesmo assim
    assert all(d["name"] == "" for d in devs)   # só sem o nome


def test_varredura_usa_teto_total_e_nao_por_ip(app, monkeypatch):
    """O timeout era gasto future a future: N hosts lentos somavam N × timeout."""
    from inventory.services import net_scan

    monkeypatch.setattr(net_scan, "_read_arp",
                        lambda: [(f"10.0.0.{i}", f"aa-bb-cc-dd-ff-{i:02x}")
                                 for i in range(1, 41)])       # 40 hosts
    monkeypatch.setattr(net_scan, "_e_dispositivo", lambda ip, mac: True)
    monkeypatch.setattr(net_scan, "_nome", lambda ip, deep=False: time.sleep(30))

    inicio = time.monotonic()
    net_scan.scan(app, sweep=False)
    gasto = time.monotonic() - inicio
    # com teto por IP seriam 40 × 2,5s = 100s; com teto total, ~5s
    assert gasto < 15, f"levou {gasto:.1f}s — o teto voltou a ser por IP"


def test_varredura_devolve_o_nome_quando_o_dns_responde(app, monkeypatch):
    """A correção não pode ter jogado fora o caso normal."""
    from inventory.services import net_scan
    monkeypatch.setattr(net_scan, "_read_arp",
                        lambda: [("192.168.0.54", "aa-bb-cc-dd-ee-01")])
    monkeypatch.setattr(net_scan, "_e_dispositivo", lambda ip, mac: True)
    monkeypatch.setattr(net_scan, "_nome", lambda ip, deep=False: "servidor.local")
    devs = net_scan.scan(app, sweep=False)
    assert devs == [{"ip": "192.168.0.54", "mac": "aa-bb-cc-dd-ee-01",
                     "name": "servidor.local"}]


# ----- Backlog DEV #31: o mesmo padrao sobrou no _sweep -----
def test_sweep_tem_teto_total(app, monkeypatch):
    """O ping-sweep nao pode segurar o request ate o ultimo ping voltar."""
    from inventory.services import net_scan

    # duas /24 = 508 alvos; cada ping "trava"
    import ipaddress
    monkeypatch.setattr(net_scan, "_subnets_alvo",
                        lambda app: {ipaddress.ip_network("192.168.0.0/24"),
                                     ipaddress.ip_network("10.0.0.0/24")})
    monkeypatch.setattr(net_scan, "_ping", lambda ip: time.sleep(30))
    monkeypatch.setattr(net_scan, "_SWEEP_TETO", 2.0)   # encurta p/ o teste

    inicio = time.monotonic()
    net_scan._sweep(app)
    gasto = time.monotonic() - inicio
    assert gasto < 12, f"_sweep levou {gasto:.1f}s — voltou a esperar todos os pings"


def test_sweep_sem_alvos_nao_faz_nada(app, monkeypatch):
    from inventory.services import net_scan
    monkeypatch.setattr(net_scan, "_subnets_alvo", lambda app: set())
    chamou = []
    monkeypatch.setattr(net_scan, "_ping", lambda ip: chamou.append(ip))
    net_scan._sweep(app)
    assert chamou == []
