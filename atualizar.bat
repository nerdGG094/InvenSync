@echo off
REM ============================================================
REM  InvenSync - Atualizar (deploy):
REM  puxa o codigo novo, atualiza dependencias, valida o boot e
REM  REINICIA o app sozinho.
REM
REM  O restart deixou de ser um lembrete e virou um passo do script
REM  porque o lembrete falhava: os 42 erros do log de producao, em 4
REM  deploys distintos, sao todos "Could not build url for endpoint",
REM  ou seja, template novo rodando no processo antigo. Enquanto o
REM  restart dependia de alguem lembrar, a janela existia.
REM ============================================================
setlocal
cd /d "%~dp0"

echo.
echo === 1/4  Baixando atualizacoes (git pull) ===
git pull --ff-only
if errorlevel 1 (
  echo.
  echo [ERRO] git pull falhou. Resolva antes de continuar (conflitos/rede).
  pause
  exit /b 1
)

echo.
echo === 2/4  Atualizando dependencias ===
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet --disable-pip-version-check
) else (
  echo [aviso] .venv nao encontrado - rode setup\install.bat primeiro.
)

echo.
echo === 3/4  Verificacao rapida de boot ===
REM Roda ANTES de derrubar o que esta no ar: se o codigo novo nao sobe,
REM o app antigo continua servindo em vez de ficar todo mundo sem sistema.
".venv\Scripts\python.exe" -c "from inventory import create_app; create_app(); print('BOOT OK')"
if errorlevel 1 (
  echo.
  echo [ERRO] O app nao subiu apos a atualizacao. Nada foi reiniciado -
  echo        a versao antiga continua no ar. Revise o erro acima.
  pause
  exit /b 1
)

echo.
echo === 4/4  Reiniciando o InvenSync ===
powershell -NoProfile -ExecutionPolicy Bypass -File "setup\reiniciar.ps1"
if errorlevel 1 (
  echo.
  echo [ERRO] A reinicializacao falhou. Abra o painel pelo
  echo        setup\start_invensync.bat e verifique.
  pause
  exit /b 1
)

echo.
echo ============================================================
echo  Atualizado e reiniciado. Codigo e templates subiram juntos.
echo ============================================================
pause
endlocal
