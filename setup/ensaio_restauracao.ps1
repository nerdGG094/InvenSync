# setup\ensaio_restauracao.ps1 — restaura um dump num banco DESCARTAVEL e diz se prestou.
#
# Existe porque backup que nunca foi restaurado e hipotese, nao backup. Este
# ensaio responde, em minutos e sem risco, as tres perguntas que ninguem quer
# descobrir durante uma queda: o arquivo abre? o pg_restore instalado le o
# formato? quanto tempo demora?
#
# SEGURANCA: o banco de ensaio e sempre outro. O script se recusa a rodar se o
# nome do ensaio for igual ao da producao, e nenhum comando aqui escreve no
# banco de producao -- as unicas consultas a ele sao SELECT count(*).
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File setup\ensaio_restauracao.ps1
#   ... -Dump backups\inventario_almox_20260820_020810.dump   # arquivo especifico
#   ... -Manter                                               # nao apaga o banco no fim

param(
    [string]$Dump = "",
    [string]$Ensaio = "inventario_almox_ensaio",
    [switch]$Manter
)

$ErrorActionPreference = 'Stop'
$raiz = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

# ---- 1. Configuracao: le o .env do projeto --------------------------------
$envPath = Join-Path $raiz '.env'
if (-not (Test-Path $envPath)) { throw "Nao achei o .env em $raiz" }

$cfg = @{}
foreach ($linha in Get-Content $envPath) {
    $t = $linha.Trim()
    if ($t -eq '' -or $t.StartsWith('#') -or -not $t.Contains('=')) { continue }
    $i = $t.IndexOf('=')
    $valor = $t.Substring($i + 1).Trim()
    # aspas ao redor do valor nao fazem parte dele (senao a senha vai errada)
    if ($valor.Length -ge 2 -and
        (($valor.StartsWith('"') -and $valor.EndsWith('"')) -or
         ($valor.StartsWith("'") -and $valor.EndsWith("'")))) {
        $valor = $valor.Substring(1, $valor.Length - 2)
    }
    $cfg[$t.Substring(0, $i).Trim()] = $valor
}

$dbHost = if ($cfg['DB_HOST']) { $cfg['DB_HOST'] } else { '127.0.0.1' }
$dbPort = if ($cfg['DB_PORT']) { $cfg['DB_PORT'] } else { '5432' }
$dbName = if ($cfg['DB_NAME']) { $cfg['DB_NAME'] } else { 'inventario_almox' }
$dbUser = if ($cfg['DB_USER']) { $cfg['DB_USER'] } else { 'postgres' }
$env:PGPASSWORD = $cfg['DB_PASSWORD']

if ($Ensaio -ieq $dbName) {
    throw "RECUSADO: o banco de ensaio ('$Ensaio') e o mesmo da producao ('$dbName')."
}

# ---- 2. Binarios do PostgreSQL (a maior versao instalada) -----------------
# Se o .env aponta o PG_DUMP, os outros binarios estao na mesma pasta -- e essa
# e a instalacao que gerou os dumps, que e o que importa: pg_restore mais ANTIGO
# que o pg_dump nao le o formato.
if ($cfg['PG_DUMP'] -and (Test-Path $cfg['PG_DUMP'])) {
    $bin = Split-Path $cfg['PG_DUMP'] -Parent
} else {
    # Ordenar pelo Name nao serviria: o Name de toda pasta 'bin' e "bin". E
    # ordenar texto poria "9.6" na frente de "17"; por isso compara versao.
    $inst = Get-ChildItem 'C:\Program Files\PostgreSQL' -Directory -ErrorAction SilentlyContinue |
            Where-Object { Test-Path (Join-Path $_.FullName 'bin\pg_restore.exe') } |
            Sort-Object { try { [version]($_.Name + '.0') } catch { [version]'0.0' } } -Descending |
            Select-Object -First 1
    if (-not $inst) { throw "Nao achei o PostgreSQL em C:\Program Files\PostgreSQL\<versao>\bin" }
    $bin = Join-Path $inst.FullName 'bin'
}
$psql       = Join-Path $bin 'psql.exe'
$pgRestore  = Join-Path $bin 'pg_restore.exe'
$createdb   = Join-Path $bin 'createdb.exe'
$dropdb     = Join-Path $bin 'dropdb.exe'

# ---- 3. O dump a ensaiar --------------------------------------------------
if ($Dump) {
    $arquivo = Get-Item (Join-Path $raiz $Dump) -ErrorAction SilentlyContinue
    if (-not $arquivo) { $arquivo = Get-Item $Dump }
} else {
    $pasta = if ($cfg['BACKUP_DIR']) { $cfg['BACKUP_DIR'] } else { Join-Path $raiz 'backups' }
    $arquivo = Get-ChildItem (Join-Path $pasta '*.dump') | Sort-Object LastWriteTime -Descending |
               Select-Object -First 1
    if (-not $arquivo) { throw "Nenhum .dump em $pasta" }
}

Write-Host ""
Write-Host "=== Ensaio de restauracao ===" -ForegroundColor Cyan
Write-Host ("  dump      : {0}" -f $arquivo.Name)
Write-Host ("  gerado em : {0}" -f $arquivo.LastWriteTime)
Write-Host ("  tamanho   : {0:N1} MB" -f ($arquivo.Length / 1MB))
Write-Host ("  destino   : {0} (descartavel)" -f $Ensaio)
Write-Host ("  binarios  : {0}" -f $bin)
Write-Host ""

# ---- 4. Restaura ----------------------------------------------------------
& $dropdb   -h $dbHost -p $dbPort -U $dbUser --if-exists $Ensaio | Out-Null
& $createdb -h $dbHost -p $dbPort -U $dbUser $Ensaio
if ($LASTEXITCODE -ne 0) { throw "Falhou ao criar o banco de ensaio." }

$cronometro = [Diagnostics.Stopwatch]::StartNew()
& $pgRestore -h $dbHost -p $dbPort -U $dbUser -d $Ensaio --no-owner --no-privileges $arquivo.FullName
$saidaRestore = $LASTEXITCODE
$cronometro.Stop()
$segundos = [math]::Round($cronometro.Elapsed.TotalSeconds, 1)

# pg_restore devolve != 0 tambem por AVISO (owner/extensao). Quem decide se
# prestou sao as contagens abaixo, nao so o codigo de saida.
if ($saidaRestore -ne 0) {
    Write-Host ""
    Write-Host "pg_restore terminou com codigo $saidaRestore (pode ser so aviso de owner)." -ForegroundColor Yellow
}

# ---- 5. Confere: mesmas tabelas, producao x restaurado --------------------
$tabelas = @('"user"', 'product', 'stock_movement', 'machine', 'ticket', 'audit_log', 'dvr_detection')
$sql = ($tabelas | ForEach-Object { "SELECT '$_' AS t, count(*) AS n FROM $_" }) -join ' UNION ALL '

function Contar($banco) {
    $saida = & $psql -h $dbHost -p $dbPort -U $dbUser -d $banco -At -F '|' -c $sql 2>$null
    $mapa = @{}
    foreach ($l in $saida) { $p = $l -split '\|'; if ($p.Count -ge 2) { $mapa[$p[0]] = [int]$p[1] } }
    return $mapa
}

$prod = Contar $dbName          # somente leitura
$rest = Contar $Ensaio

Write-Host ""
Write-Host ("{0,-16} {1,12} {2,12}   {3}" -f 'tabela', 'producao', 'restaurado', 'situacao')
$problemas = 0
foreach ($t in $tabelas) {
    $chave = $t.Trim('"')
    $a = if ($prod.ContainsKey($chave)) { $prod[$chave] } else { -1 }
    $b = if ($rest.ContainsKey($chave)) { $rest[$chave] } else { -1 }
    # O dump e de ate ontem: producao com MAIS linhas e o esperado. Menos, nao.
    if ($b -lt 0)      { $situacao = 'FALTA no restaurado'; $problemas++ }
    elseif ($b -eq 0 -and $a -gt 0) { $situacao = 'VAZIA (suspeito)'; $problemas++ }
    elseif ($b -gt $a) { $situacao = 'ok (producao ja expurgou depois do dump)' }
    else               { $situacao = 'ok' }
    Write-Host ("{0,-16} {1,12} {2,12}   {3}" -f $chave, $a, $b, $situacao)
}

$ultimo = & $psql -h $dbHost -p $dbPort -U $dbUser -d $Ensaio -At -c "SELECT max(created_at) FROM audit_log" 2>$null
Write-Host ""
Write-Host ("Evento mais recente dentro do dump: {0}" -f $ultimo)
Write-Host ("Tempo de restauracao: {0}s" -f $segundos)

# ---- 6. Limpeza -----------------------------------------------------------
if ($Manter) {
    Write-Host ""
    Write-Host "Banco '$Ensaio' MANTIDO (use -Manter apenas enquanto precisar; depois:" -ForegroundColor Yellow
    Write-Host "  `"$dropdb`" -U $dbUser --if-exists $Ensaio)" -ForegroundColor Yellow
} else {
    & $dropdb -h $dbHost -p $dbPort -U $dbUser --if-exists $Ensaio | Out-Null
    Write-Host "Banco de ensaio removido."
}

Write-Host ""
if ($problemas -eq 0) {
    Write-Host "VEREDITO: o dump restaura e as tabelas vieram completas." -ForegroundColor Green
    exit 0
} else {
    Write-Host "VEREDITO: $problemas tabela(s) com problema -- NAO confie neste backup ainda." -ForegroundColor Red
    exit 1
}
