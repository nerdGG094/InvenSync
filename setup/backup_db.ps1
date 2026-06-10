# backup_db.ps1 — Backup completo do banco PostgreSQL do InvenSync (inventario_almox).
#
# Faz pg_dump no formato custom (-Fc, comprimido), com carimbo de data/hora,
# e mantém apenas os últimos N dumps (rotação). As credenciais são lidas do
# .env do projeto em tempo de execução — NUNCA gravadas em script/log/disco.
#
# Executado pela Tarefa Agendada 'Backup PostgreSQL - InvenSync'.
# Uso manual:  powershell -ExecutionPolicy Bypass -File setup\backup_db.ps1

$ErrorActionPreference = 'Continue'

$repo    = Split-Path $PSScriptRoot -Parent
$envFile = Join-Path $repo '.env'
$outDir  = 'C:\Backups\invensync_db'
$pgDump  = 'C:\Program Files\PostgreSQL\17\bin\pg_dump.exe'
$keep    = 30          # quantos dumps manter (1/dia ≈ 1 mês)
$log     = Join-Path $outDir 'backup_db.log'

function Write-Log($msg) {
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }
    "$ts  $msg" | Out-File -FilePath $log -Append -Encoding utf8
}

# --- Lê o .env (KEY=VALUE) ---
if (-not (Test-Path $envFile)) { Write-Log "ERRO: .env nao encontrado em $envFile"; exit 1 }
$cfg = @{}
foreach ($line in Get-Content $envFile) {
    if ($line -match '^\s*#') { continue }
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
        $cfg[$matches[1]] = $matches[2].Trim().Trim('"').Trim("'")
    }
}
$pgHost = if ($cfg['DB_HOST']) { $cfg['DB_HOST'] } else { '127.0.0.1' }
$pgPort = if ($cfg['DB_PORT']) { $cfg['DB_PORT'] } else { '5432' }
$pgDb   = if ($cfg['DB_NAME']) { $cfg['DB_NAME'] } else { 'inventario_almox' }
$pgUser = if ($cfg['DB_USER']) { $cfg['DB_USER'] } else { 'postgres' }

if (-not $cfg['DB_PASSWORD']) { Write-Log 'ERRO: DB_PASSWORD ausente no .env'; exit 1 }
if (-not (Test-Path $pgDump))  { Write-Log "ERRO: pg_dump nao encontrado em $pgDump"; exit 1 }
if (-not (Test-Path $outDir))  { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }

# --- Dump (formato custom, comprimido) ---
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$file  = Join-Path $outDir "invensync_$stamp.dump"
$env:PGPASSWORD = $cfg['DB_PASSWORD']
$code = 1
try {
    & $pgDump -h $pgHost -p $pgPort -U $pgUser -d $pgDb -Fc -f $file
    $code = $LASTEXITCODE
} finally {
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
}

if ($code -ne 0 -or -not (Test-Path $file)) {
    Write-Log "pg_dump FALHOU (exit $code)."
    if (Test-Path $file) { Remove-Item $file -Force }   # remove dump parcial
    exit 1
}
$sizeKB = [math]::Round((Get-Item $file).Length / 1KB, 1)
Write-Log "dump OK: $(Split-Path $file -Leaf) ($sizeKB KB)"

# --- Rotação: mantém os $keep mais recentes ---
$old = Get-ChildItem $outDir -Filter 'invensync_*.dump' |
       Sort-Object LastWriteTime -Descending | Select-Object -Skip $keep
foreach ($f in $old) { Remove-Item $f.FullName -Force; Write-Log "rotacao: removido $($f.Name)" }

Write-Output "Backup OK: $file ($sizeKB KB)"
exit 0
