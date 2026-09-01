# InvenSync - instala os hooks de git do projeto.
#
# Hoje ha um so: post-commit, que joga cada commit no board DEV (kanban).
# .git/hooks nao e versionado, entao cada clone precisa rodar isto uma vez:
#
#     powershell -ExecutionPolicy Bypass -File setup\instalar_hooks.ps1
#
# Para desligar o registro automatico sem remover o hook, ponha
# DEV_COMMIT_ENABLED=0 no .env.
#
# ATENCAO: mantenha este arquivo em ASCII puro. O Windows PowerShell 5.1 le o
# .ps1 como ANSI; um travessao em UTF-8 vira aspa inteligente e quebra o parser.

$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot
$origem = Join-Path $PSScriptRoot 'hooks'
$destino = Join-Path $raiz '.git\hooks'

if (-not (Test-Path $destino)) {
    Write-Host "[ERRO] $destino nao existe. Isto e um repositorio git?" -ForegroundColor Red
    exit 1
}

foreach ($hook in Get-ChildItem -Path $origem -File) {
    $alvo = Join-Path $destino $hook.Name
    if (Test-Path $alvo) {
        $backup = "$alvo.bak"
        Copy-Item $alvo $backup -Force
        Write-Host "  hook existente salvo em $backup" -ForegroundColor DarkYellow
    }
    Copy-Item $hook.FullName $alvo -Force
    Write-Host "  instalado: .git/hooks/$($hook.Name)" -ForegroundColor Green
}

Write-Host ''
Write-Host 'Pronto. A partir do proximo commit, o board DEV recebe:' -ForegroundColor Cyan
Write-Host '  - commit citando #12        -> atualizacao na tarefa 12'
Write-Host '  - demais commits            -> card novo em Revisao'
Write-Host '  - [skip-kanban] na mensagem -> commit ignorado'
