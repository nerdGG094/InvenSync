@echo off
REM Lanca o launcher PyQt5 do InvenSync sem abrir janela de console.
REM Usa pythonw.exe do .venv do projeto.

setlocal
REM Sobe da pasta setup\ para a raiz do projeto.
cd /d "%~dp0.."

if not exist ".venv\Scripts\pythonw.exe" (
    echo [ERRO] .venv nao encontrado em "%CD%\.venv"
    echo Rode setup\install.bat primeiro, ou crie manualmente:
    echo   python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" "launcher.py"
endlocal
