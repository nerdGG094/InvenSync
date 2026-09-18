"""Abre TODA página GET sem parâmetro e exige que nenhuma estoure.

Por que varrer o `url_map` em vez de manter uma lista à mão: a maior causa
isolada de erro no log de produção, depois da colisão de cookie, foi
`Could not build url for endpoint '...'` -- template novo referenciando um
endpoint que o processo em execução não tinha. São 12 das 42 entradas. Uma
lista escrita à mão só cobre o que alguém lembrou de acrescentar; é justamente
a tela que ninguém abre no dia a dia que quebra sem ninguém ver.

O critério é **não estourar** (nada de 5xx). Redirecionar, negar ou não achar
são respostas legítimas dependendo da rota; explodir não é.
"""
import pytest

# Rotas deixadas de fora, com o motivo. Não é "não testar": é que abri-las por
# HTTP aqui faria outra coisa que não renderizar uma página.
PULAR = {
    "auth.logout": "derrubaria a sessão do próprio cliente de teste",
    "auth.login_2fa": "só existe no meio do fluxo de login, com estado na sessão",
    "auth.login_cancel": "limpa o 2FA pendente da sessão",
    "rede.scan": "dispara varredura ARP/ping de verdade na rede",
    "machines.rede_ativos": "lê a tabela ARP do sistema operacional",
    "dvr.go2rtc_page": "sonda o serviço go2rtc pela rede",
    "dvr.go2rtc_status": "sonda o serviço go2rtc pela rede",
    "kiox.apk": "serve um APK que pode nem estar na máquina",
    "static": "arquivo estático, não é página",
}


def _paginas(app):
    """Endpoints GET sem parâmetro de URL, fora os pulados."""
    for regra in app.url_map.iter_rules():
        if regra.arguments or "GET" not in regra.methods:
            continue
        if regra.endpoint in PULAR:
            continue
        yield regra.endpoint, str(regra)


def test_a_lista_de_excecoes_nao_envelhece(app):
    """Endpoint pulado que não existe mais = cobertura desligada em silêncio."""
    conhecidos = {r.endpoint for r in app.url_map.iter_rules()}
    fantasmas = [e for e in PULAR if e not in conhecidos]
    assert not fantasmas, (
        f"Estes endpoints estão na lista de exceções mas não existem mais: "
        f"{fantasmas}. Tire-os da lista -- senão ela vira desculpa para não testar."
    )


def test_toda_pagina_de_admin_abre(app, auth_client):
    quebradas = []
    for endpoint, url in _paginas(app):
        try:
            r = auth_client.get(url, follow_redirects=False)
        except Exception as e:  # noqa: BLE001 — exceção não tratada é falha igual
            quebradas.append(f"{endpoint} ({url}) -> exceção: {type(e).__name__}: {e}")
            continue
        if r.status_code >= 500:
            quebradas.append(f"{endpoint} ({url}) -> HTTP {r.status_code}")
    assert not quebradas, "Páginas que estouraram:\n  " + "\n  ".join(quebradas)


def test_toda_pagina_responde_ao_anonimo_sem_estourar(app, client):
    """Sem login, o esperado é redirecionar para o login -- nunca um 500."""
    quebradas = []
    for endpoint, url in _paginas(app):
        r = client.get(url, follow_redirects=False)
        if r.status_code >= 500:
            quebradas.append(f"{endpoint} ({url}) -> HTTP {r.status_code}")
    assert not quebradas, "Páginas que estouraram para anônimo:\n  " + "\n  ".join(quebradas)


def test_usuario_comum_nao_leva_500_em_pagina_de_admin(app, common_client):
    """O portão de não-admin precisa redirecionar/negar, não quebrar."""
    quebradas = []
    for endpoint, url in _paginas(app):
        r = common_client.get(url, follow_redirects=False)
        if r.status_code >= 500:
            quebradas.append(f"{endpoint} ({url}) -> HTTP {r.status_code}")
    assert not quebradas, "Páginas que estouraram para usuário comum:\n  " + "\n  ".join(quebradas)


@pytest.mark.parametrize("endpoint", ["dashboard.index", "tickets.list_view",
                                      "announcements.list_view", "dev.board"])
def test_paginas_centrais_respondem_200(app, auth_client, endpoint):
    """Um punhado de telas onde 'não estourou' é pouco: têm de abrir mesmo."""
    url = next(str(r) for r in app.url_map.iter_rules() if r.endpoint == endpoint)
    r = auth_client.get(url, follow_redirects=False)
    assert r.status_code == 200, f"{endpoint} -> {r.status_code}"
