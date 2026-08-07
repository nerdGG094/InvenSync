# setup\reiniciar.ps1 — para e sobe o InvenSync, e confirma que voltou.
#
# Existe por causa de uma falha real e repetida: o atualizar.bat puxava o
# codigo novo e apenas PEDIA para reiniciar. Quando o passo era pulado, os
# templates novos rodavam no processo antigo e toda pagina quebrava com
# "Could not build url for endpoint '...'" — os 42 erros do log de producao,
# em 4 deploys distintos, sao todos desse tipo. Automatizando o restart, a
# janela deixa de existir.
#
# CUIDADO AO MEXER: este servidor roda outros apps Python (CARREG-LOGI, entre
# outros). Filtrar por nome de processo, ou pela linha de comando, derrubaria
# os vizinhos — o launcher do CARREG-LOGI aparece como
#   ".venv\Scripts\pythonw.exe" "launcher.py"
# exatamente igual ao deste projeto. O unico discriminador confiavel e o
# ExecutablePath, que o Windows resolve para caminho absoluto. Por isso o
# filtro abaixo e por caminho, e nao por nome.

$ErrorActionPreference = 'Stop'
$raiz = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$prefixo = $raiz.TrimEnd('\') + '\'

Write-Host "InvenSync em: $raiz"

function Processos-Do-Projeto {
    Get-CimInstance Win32_Process -Filter "name='pythonw.exe' or name='python.exe'" |
        Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($prefixo, 'OrdinalIgnoreCase') }
}

# ---- 1. Parar -------------------------------------------------------------
$alvos = @(Processos-Do-Projeto)
if (-not $alvos) {
    Write-Host "Nada rodando deste projeto (primeira subida?)."
} else {
    foreach ($p in $alvos) { Write-Host ("  parando PID {0}  {1}" -f $p.ProcessId, $p.ExecutablePath) }
    # Filhos primeiro (o serve.py e filho do launcher): matar o pai antes
    # deixaria o waitress orfao segurando a porta 5090.
    $ordenado = $alvos | Sort-Object -Property ParentProcessId -Descending
    foreach ($p in $ordenado) {
        $proc = Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue
        if (-not $proc) { continue }
        try { [void]$proc.CloseMainWindow() } catch {}   # tenta fechar com educacao
    }
    Start-Sleep -Seconds 3
    foreach ($p in $ordenado) {
        $proc = Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue
        if ($proc) { try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop } catch {} }
    }
    # Espera os processos sumirem antes de subir de novo
    for ($i = 0; $i -lt 15; $i++) {
        if (-not (Processos-Do-Projeto)) { break }
        Start-Sleep -Seconds 1
    }
    $sobrou = @(Processos-Do-Projeto)
    if ($sobrou) {
        Write-Host "[ERRO] Estes processos nao encerraram:" -ForegroundColor Red
        $sobrou | ForEach-Object { Write-Host ("  PID {0}" -f $_.ProcessId) }
        exit 1
    }
    Write-Host "Parado."
}

# ---- 2. Subir -------------------------------------------------------------
Write-Host "Subindo..."
Start-Process -FilePath (Join-Path $PSScriptRoot 'start_invensync.bat') -WorkingDirectory $raiz

# ---- 3. Provar que voltou -------------------------------------------------
# Sem esta checagem o deploy continuaria "no escuro": o script diria OK mesmo
# se o app nao tivesse subido.
$porta = if ($env:SERVE_PORT) { $env:SERVE_PORT } else { '5090' }
$url = "http://127.0.0.1:$porta/health"
Write-Host "Aguardando $url ..."
for ($i = 1; $i -le 40; $i++) {
    Start-Sleep -Seconds 2
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5
        if ($r.StatusCode -eq 200) {
            Write-Host "InvenSync no ar (~$($i*2)s)." -ForegroundColor Green
            exit 0
        }
    } catch { }
}
Write-Host "[ERRO] O app nao respondeu em /health apos ~80s. Abra o painel e veja o log." -ForegroundColor Red
exit 1
