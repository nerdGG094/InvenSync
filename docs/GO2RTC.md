# Câmeras em tempo real (go2rtc / WebRTC)

O módulo CFTV mostra as câmeras de duas formas:

| Modo | Como funciona | Latência | Quando é usado |
|---|---|---|---|
| **Snapshot** | `snapshot.cgi` do DVR, proxy em memória (`services/dvr_cam.py`) | ~1 quadro/s | grade de miniaturas (sempre) e reserva da ampliada |
| **Tempo real** | **go2rtc** lê o RTSP do DVR e entrega por **WebRTC** | sub-segundo | câmera ampliada, quando o go2rtc está no ar |

O teto de ~1 fps do snapshot é do próprio DVR (o CGI leva ~0,9 s por foto), não
do InvenSync. Para vídeo fluido é preciso um "media gateway": o **go2rtc**.

- Custo: **R$ 0** (open-source, licença MIT), binário único de ~20 MB.
- CPU: baixa — o InvenSync usa o **sub-stream H.264** dos DVRs e o go2rtc faz
  **passthrough** (não transcodifica). Só há tráfego enquanto alguém assiste.
- Disco: **nada** é gravado (a gravação continua sendo do DVR).
- Ônus: mais um processo para manter no ar. Se ele cair, a página volta sozinha
  para o snapshot.

---

## Instalação (uma vez)

### 1. Baixar o binário

Baixe `go2rtc_win64.zip` em <https://github.com/AlexxIT/go2rtc/releases> e
extraia o `go2rtc.exe` para a pasta do arquivo de configuração. Para o HD, o
**ffmpeg** também precisa estar ali (<https://www.gyan.dev/ffmpeg/builds/> —
build "release essentials"). No fim a pasta fica assim:

```
InventarioAlmox\go2rtc\go2rtc.exe     (~19 MB)
InventarioAlmox\go2rtc\ffmpeg.exe     (~97 MB — só para o transcode do H.265)
InventarioAlmox\go2rtc\nssm.exe       (~0,3 MB — só para registrar o serviço)
InventarioAlmox\go2rtc\go2rtc.yaml    (gerado pelo InvenSync; contém senhas)
InventarioAlmox\go2rtc\go2rtc.log     (log do serviço, rotaciona em 5 MB)
```

(A pasta `go2rtc/` está no `.gitignore`: binários grandes + arquivo com senhas.)

### 2. Gerar o `go2rtc.yaml`

No InvenSync: **CFTV → Tempo real → Gerar go2rtc.yaml**.

A tela monta um stream por canal de cada DVR **ativo, com IP e nº de canais**,
usando a senha guardada cifrada no cadastro (VAULT_KEY). O nome de cada stream é
`dvr<ID>_ch<CANAL>` — estável, é o que a página de câmeras usa no player.

```yaml
streams:
  # PRODUÇÃO — 192.168.0.134 · 16 canais
  dvr1_ch1: "rtsp://admin:senha@192.168.0.134:554/cam/realmonitor?channel=1&subtype=1"
  ...
```

### O que estes DVRs entregam (conferido por `DESCRIBE` em 554 e pelo CGI `Encode`)

| | Principal (`subtype=0`) | Sub-stream (`subtype=1`) |
|---|---|---|
| Resolução | **1280x720** (alguns canais 960x1080) | **352x240 (CIF)** |
| Codec | **H.265** | H.264 |
| Taxa | 512-1024 kbps · 15 fps | 80-160 kbps · **7 fps** |
| Serve para | é o **HD** | é a imagem "SD" ruim |

Caminho: `/cam/realmonitor` — **singular**; `/cams/...` devolve `404 Not Found`.

**O sub-stream não pode melhorar:** o próprio DVR responde
`ExtraFormat.ResolutionTypes=CIF` — 352x240 é o teto dele. Ou seja, HD só existe
no stream principal, que é **H.265** — e o **WebRTC não transporta H.265**.

### Como o HD chega ao navegador (transcode sob demanda)

Cada canal é gerado com **duas fontes**:

```yaml
  dvr1_ch1:
    - "rtsp://admin:senha@192.168.0.134:554/cam/realmonitor?channel=1&subtype=0"
    - "ffmpeg:dvr1_ch1#video=h264"
```

O go2rtc escolhe pela negociação de codec:

- navegador que decodifica **H.265** → assiste a fonte 1 direto (**CPU zero**);
- navegador sem H.265 (a maioria) → entra a fonte 2, que converte para H.264.

O ffmpeg **só roda enquanto alguém está com aquele canal aberto** e morre quando
a pessoa fecha — um processo por espectador.

**Custo medido neste servidor** (Xeon E5530 2,4 GHz, 4 núcleos), 720p @ 15 fps:

| | CPU |
|---|---|
| só decodificar o H.265 (piso inevitável) | 19% de um núcleo |
| decodificar + recodificar p/ H.264 (o que roda) | **47% de um núcleo por espectador** |

Ou seja: 2 pessoas assistindo ≈ 1 núcleo. Se apertar, `GO2RTC_TRANSCODE=0`
desliga a conversão (só quem tem H.265 vê) ou `GO2RTC_SUBTYPE=1` volta ao
CIF leve.

> ⚠️ O arquivo contém **usuário e senha dos DVRs em texto puro** — é o formato
> que o go2rtc entende. Trate a pasta com o mesmo cuidado do `.env` (fora do Git,
> acesso restrito no Windows).

### 3. Testar

```bat
cd InventarioAlmox\go2rtc
go2rtc.exe -config go2rtc.yaml
```

Abra `http://IP-DO-SERVIDOR:1984` — o painel do go2rtc lista os streams; clique
em `stream` num deles para ver o vídeo. Se abrir aí, abre no InvenSync.

### 4. Deixar rodando como serviço do Windows

O go2rtc é um executável comum (não fala com o Gerenciador de Serviços), então
precisa de um "envelope": o [NSSM](https://nssm.cc/). Foi assim que ficou aqui:

```bat
nssm install go2rtc "C:\...\InventarioAlmox\go2rtc\go2rtc.exe" -config go2rtc.yaml
nssm set go2rtc AppDirectory  "C:\...\InventarioAlmox\go2rtc"
nssm set go2rtc DisplayName   "go2rtc (CFTV InvenSync)"
nssm set go2rtc Start         SERVICE_AUTO_START
nssm set go2rtc AppStdout     "C:\...\InventarioAlmox\go2rtc\go2rtc.log"
nssm set go2rtc AppStderr     "C:\...\InventarioAlmox\go2rtc\go2rtc.log"
nssm set go2rtc AppRotateFiles 1
nssm set go2rtc AppRotateBytes 5242880
nssm start go2rtc
```

Depois de regerar o `go2rtc.yaml`: `Restart-Service go2rtc` (ou
`nssm restart go2rtc`). Para conferir: `Get-Service go2rtc`.

### 4b. Firewall

O navegador fala **direto** com o go2rtc, então as portas precisam estar abertas
para a rede interna (aqui foram criadas restritas a `192.168.0.0/24`):

```powershell
New-NetFirewallRule -DisplayName "go2rtc - painel/sinalizacao (InvenSync CFTV)" `
  -Direction Inbound -Action Allow -Protocol TCP -LocalPort 1984 -RemoteAddress 192.168.0.0/24
New-NetFirewallRule -DisplayName "go2rtc - midia WebRTC TCP (InvenSync CFTV)" `
  -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8555 -RemoteAddress 192.168.0.0/24
New-NetFirewallRule -DisplayName "go2rtc - midia WebRTC UDP (InvenSync CFTV)" `
  -Direction Inbound -Action Allow -Protocol UDP -LocalPort 8555 -RemoteAddress 192.168.0.0/24
```

Sem a **8555** o painel lista o stream mas o vídeo não abre — é a porta da mídia.

### 5. Ligar no InvenSync

No `.env`:

```
GO2RTC_URL=http://192.168.0.54:1984
```

**Reinicie o InvenSync** (mudança de `.py`/config exige restart). A câmera
ampliada passa a abrir em WebRTC; um chip **AO VIVO** aparece nas miniaturas dos
canais que o go2rtc publica.

### 6. Depois de cadastrar/alterar um DVR

Gere o `go2rtc.yaml` de novo e **reinicie o serviço go2rtc** — ele lê a
configuração só na partida.

---

## Configuração (`.env`)

| Variável | Padrão | Para que serve |
|---|---|---|
| `GO2RTC_URL` | *(vazio)* | Endereço do go2rtc. **Vazio = tempo real desligado** (só snapshot). É o **navegador** que acessa esta URL, então use o IP do servidor, não `localhost`. |
| `GO2RTC_CONFIG` | `<repo>\go2rtc\go2rtc.yaml` | Onde gravar o arquivo gerado. |
| `GO2RTC_RTSP_PORT` | `554` | Porta RTSP dos DVRs. |
| `GO2RTC_SUBTYPE` | `0` | `0` = principal (720p HD, H.265), `1` = sub-stream (CIF, leve). |
| `GO2RTC_TRANSCODE` | `1` | Converte o H.265 para H.264 sob demanda (é o que faz o HD abrir em qualquer navegador). `0` desliga. |
| `GO2RTC_FFMPEG` | *(vazio)* | Caminho do `ffmpeg.exe`; vazio = procura ao lado do `go2rtc.yaml` e depois no PATH. |
| `GO2RTC_RTSP_TEMPLATE` | `/cam/realmonitor?channel={channel}&subtype={subtype}` | Molde da URL RTSP. Campos: `{user} {password} {host} {port} {channel} {subtype}`. |
| `GO2RTC_PLAYER_MODE` | `webrtc,mse` | Modo do player embutido; `mse` é a reserva quando o WebRTC não serve (ex.: canal H.265). |
| `GO2RTC_TIMEOUT` | `3` | Timeout (s) da sondagem do serviço. |
| `DVR_SNAP_TTL` / `DVR_SNAP_TTL_LIVE` | `3` / `0.4` | Cache do snapshot (grade / ampliada) — o modo de reserva. |

---

## Como o InvenSync usa

- `services/go2rtc.py` — nomes/URLs dos streams, geração do `go2rtc.yaml`,
  URL do player e sondagem (`probe`, com cache curto).
- `routes/dvr.py` — `/cftv/go2rtc` (painel + prévia), `/cftv/go2rtc/gerar` (POST,
  auditado), `/cftv/go2rtc/status` (JSON).
- `templates/cftv/cameras.html` — a ampliada abre num `<iframe>` do player do
  go2rtc; um botão alterna para snapshot e a escolha fica no `localStorage`.
  Sem go2rtc (ou com ele fora do ar) a página nem oferece o botão.
- CSP: a origem do `GO2RTC_URL` é liberada em `frame-src`/`connect-src`
  (`inventory/__init__.py`) — sem isso o navegador bloqueia o `<iframe>`.

A grade **continua em snapshot de propósito**: 16-18 sessões WebRTC simultâneas
num monitor de parede seriam muito mais caras que 18 JPEGs a cada 3 s.

---

## Problemas comuns

**A página diz "o serviço go2rtc não respondeu".**
O processo está no ar? `http://IP:1984` abre no navegador do servidor? A porta
1984 está liberada no firewall do Windows para a rede interna?

**"O go2rtc está no ar, mas não conhece as câmeras deste DVR".**
Falta gerar o `go2rtc.yaml` (ou reiniciar o go2rtc depois de gerar).

**O painel do go2rtc mostra o stream, mas o vídeo não abre no navegador.**
É a negociação WebRTC: libere a porta **8555 (TCP e UDP)** no firewall. Em
servidor com várias placas de rede, fixe o candidato no `go2rtc.yaml`:

```yaml
webrtc:
  listen: ":8555"
  candidates:
    - 192.168.0.54:8555
```

**Um canal fica preto (ou só ele não abre).** O HD é H.265 e depende do
transcode: confira se o `ffmpeg.exe` está na pasta e se o `go2rtc.yaml` tem a
seção `ffmpeg: bin:`. No `go2rtc.log` aparece o erro do ffmpeg daquele canal.

**A CPU do servidor dispara com várias pessoas assistindo.** Cada espectador
custa ~47% de um núcleo (veja a tabela acima). Alternativas: `GO2RTC_SUBTYPE=1`
(volta ao CIF leve, sem transcode) ou `GO2RTC_TRANSCODE=0`.

**As miniaturas da grade continuam pequenas.** Elas vêm do `snapshot.cgi`, cuja
resolução é fixada no próprio DVR (config `Snap`): hoje 704x480 no `.134` e
352x240 no `.136`. Não há parâmetro de URL que mude isso — só alterando a
configuração do DVR. Como são miniaturas de ~240 px, costuma não valer a pena.

**Erro de autenticação no stream.** A senha mudou no DVR: atualize o cadastro em
CFTV, gere o `go2rtc.yaml` de novo e reinicie o go2rtc.

**Qualquer pessoa da rede abre `http://IP:1984` e vê as câmeras.** É verdade — o
go2rtc não tem login por padrão e o navegador precisa alcançá-lo direto (por isso
não dá para escondê-lo atrás do InvenSync). Restrinja a porta 1984 no firewall às
faixas de IP que devem enxergar o CFTV.
