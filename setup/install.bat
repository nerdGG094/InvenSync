@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
REM Sobe da pasta setup\ para a raiz do projeto.
cd /d "%~dp0.."

echo ============================================================
echo  InvenSync - Instalador
echo ============================================================
echo.
echo Pasta do projeto: %CD%
echo.

REM ---------- 1. Python no PATH ----------
where python >nul 2>nul
if errorlevel 1 (
    echo [ERRO] Python nao encontrado no PATH.
    echo Instale Python 3.12 de https://www.python.org/downloads/
    goto :fim_erro
)

REM ---------- 2. .venv ----------
if not exist ".venv\Scripts\python.exe" (
    echo [1/5] Criando ambiente virtual .venv...
    python -m venv .venv || goto :fim_erro
) else (
    echo [1/5] .venv ja existe, pulando criacao.
)

REM ---------- 3. dependencias ----------
echo [2/5] Instalando dependencias (pode demorar)...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet || goto :fim_erro
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :fim_erro

REM ---------- 4. .env ----------
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [3/5] .env criado a partir de .env.example.
        echo       *** EDITE .env COM AS SENHAS REAIS ANTES DE INICIAR ***
    ) else (
        echo [AVISO] .env e .env.example ausentes. Crie .env manualmente.
    )
) else (
    echo [3/5] .env ja existe, pulando.
)

REM ---------- 5. atalhos .lnk (Desktop + Startup) ----------
echo [4/5] Criando atalhos InvenSync.lnk (Desktop + Inicializacao)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d='%CD%'; $py=Join-Path $d '.venv\Scripts\pythonw.exe'; $ln=Join-Path $d 'launcher.py'; $ic=Join-Path $d 'inventory\static\favicon.ico'; if (-not (Test-Path $py)) { Write-Error 'pythonw.exe nao encontrado'; exit 1 }; if (-not (Test-Path $ln)) { Write-Error 'launcher.py nao encontrado'; exit 1 }; $sh=New-Object -ComObject WScript.Shell; foreach ($p in @((Join-Path ([Environment]::GetFolderPath('Desktop')) 'InvenSync.lnk'),(Join-Path ([Environment]::GetFolderPath('Startup')) 'InvenSync.lnk'))) { $s=$sh.CreateShortcut($p); $s.TargetPath=$py; $s.Arguments='\"' + $ln + '\"'; $s.WorkingDirectory=$d; if (Test-Path $ic) { $s.IconLocation=$ic + ',0' }; $s.Description='InvenSync - Servidor Flask'; $s.WindowStyle=1; $s.Save(); Write-Output ('Criado: ' + $p) }"
if errorlevel 1 (
    echo [ERRO] Falha ao criar atalhos.
    goto :fim_erro
)

REM ---------- 6. Detectar processos Python orfaos do projeto ----------
echo.
echo [5/5] Verificando processos Python orfaos do projeto...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$root = (Resolve-Path .).Path; $procs = Get-Process python, pythonw -ErrorAction SilentlyContinue | Where-Object { try { $_.Path -and ($_.Path.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) } catch { $false } }; if ($procs) { Write-Host '      [AVISO] Existem processos Python rodando deste projeto:' -ForegroundColor Yellow; $procs | Format-Table Id, ProcessName, StartTime -AutoSize | Out-String | Write-Host } else { Write-Host '      [OK] Nenhum processo Python orfao detectado.' }"

echo.
echo ============================================================
echo  Instalacao concluida com sucesso!
echo ============================================================
echo.
echo Proximos passos:
echo   1. Edite .env com as senhas reais (se ainda nao editou).
echo   2. Use o atalho "InvenSync" na area de trabalho para iniciar.
echo      O atalho da Inicializacao sobe automaticamente no proximo login.
echo.
pause
exit /b 0

:fim_erro
echo.
echo ============================================================
echo  Instalacao FALHOU. Verifique a mensagem de erro acima.
echo ============================================================
pause
exit /b 1
