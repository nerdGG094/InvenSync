# InvenSync - instala os hooks de git do projeto.
#
# Hoje ha um so: post-commit, que joga cada commit no board DEV (kanban).
# O board e compartilhado entre os projetos, entao o hook pode ser instalado
# tambem em outros repositorios - ele sempre chama o dev_commit.py do InvenSync:
#
#     powershell -ExecutionPolicy Bypass -File setup\instalar_hooks.ps1
#     powershell -ExecutionPolicy Bypass -File setup\instalar_hooks.ps1 -Repo C:\...\CARREG-LOGI
#
# No Linux/macOS o equivalente e setup/instalar_hooks.sh - o hook em si serve
# aos dois sistemas (escolhe o interpretador pelo uname).
#
# .git/hooks nao e versionado: cada clone precisa rodar isto uma vez.
# Para desligar o registro automatico sem remover o hook, ponha
# DEV_COMMIT_ENABLED=0 no .env do InvenSync.
#
# ATENCAO: mantenha este arquivo em ASCII puro. O Windows PowerShell 5.1 le o
# .ps1 como ANSI; um travessao em UTF-8 vira aspa inteligente e quebra o parser.

param(
    # Repositorio onde instalar. Vazio = o proprio InvenSync.
    [string]$Repo = ''
)

$ErrorActionPreference = 'Stop'
$invensync = Split-Path -Parent $PSScriptRoot
$origem = Join-Path $PSScriptRoot 'hooks'
$alvoRepo = if ($Repo) { (Resolve-Path $Repo).Path } else { $invensync }
$destino = Join-Path $alvoRepo '.git\hooks'

if (-not (Test-Path $destino)) {
    Write-Host "[ERRO] $destino nao existe. $alvoRepo e um repositorio git?" -ForegroundColor Red
    exit 1
}

Write-Host "Repositorio: $alvoRepo"
Write-Host "InvenSync:   $invensync"

# O hook e um modelo: o caminho do InvenSync entra aqui, na instalacao.
# Barra normal de proposito - quem executa o hook e o sh do Git for Windows.
$caminhoSh = $invensync -replace '\\', '/'

foreach ($hook in Get-ChildItem -Path $origem -File) {
    $alvo = Join-Path $destino $hook.Name
    if (Test-Path $alvo) {
        $atual = Get-Content $alvo -Raw
        if ($atual -notmatch 'dev_commit') {
            Copy-Item $alvo "$alvo.bak" -Force
            Write-Host "  hook existente salvo em $alvo.bak" -ForegroundColor DarkYellow
        }
    }
    $conteudo = (Get-Content $hook.FullName -Raw) -replace '@INVENSYNC@', $caminhoSh
    # LF e sem BOM: o sh do Git nao come CRLF nem BOM na linha do shebang.
    $texto = $conteudo -replace "`r`n", "`n"
    [System.IO.File]::WriteAllText($alvo, $texto, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "  instalado: .git/hooks/$($hook.Name)" -ForegroundColor Green
}

Write-Host ''
Write-Host 'Pronto. A partir do proximo commit, o board DEV recebe:' -ForegroundColor Cyan
Write-Host '  - commit citando #12        -> atualizacao na tarefa 12'
Write-Host '  - demais commits            -> card novo em Revisao'
Write-Host '  - [skip-kanban] no assunto  -> commit ignorado'
Write-Host '  - "Backup automatico ..."   -> commit ignorado (rotina)'
