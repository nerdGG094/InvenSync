@echo off
REM ============================================================
REM  InvenSync - Atualizar (deploy):
REM  puxa o codigo novo, atualiza dependencias, valida o boot e
REM  REINICIA o app sozinho.
REM
REM  ESTILO: erro tratado com "if errorlevel 1 goto :label", NUNCA com
REM  bloco "if errorlevel 1 ( ... )". O cmd analisa o bloco inteiro assim
REM  que o encontra, e um parentese solto dentro de um echo -- ex.:
REM  "Resolva antes de continuar (conflitos/rede)." -- fecha o bloco antes
REM  da hora e derruba o script com "'.' foi inesperado neste momento",
REM  mesmo que o passo tenha dado certo. Foi assim que este arquivo passou
REM  meses morrendo logo depois do git pull, sem nunca chegar a avisar que
REM  faltava reiniciar. Se precisar de parenteses num echo, escreva ^( e ^).
REM ============================================================
setlocal
cd /d "%~dp0"

echo.
echo === 1/4  Baixando atualizacoes ^(git pull^) ===
git pull --ff-only
if errorlevel 1 goto :erro_pull

echo.
echo === 2/4  Atualizando dependencias ===
if not exist ".venv\Scripts\python.exe" goto :sem_venv
".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet --disable-pip-version-check
goto :boot

:sem_venv
echo [aviso] .venv nao encontrado - rode setup\install.bat primeiro.

:boot
echo.
echo === 3/4  Verificacao rapida de boot ===
REM Roda ANTES de derrubar o que esta no ar: se o codigo novo nao sobe,
REM o app antigo continua servindo em vez de ficar todo mundo sem sistema.
".venv\Scripts\python.exe" -c "from inventory import create_app; create_app(); print('BOOT OK')"
if errorlevel 1 goto :erro_boot

echo.
echo === 4/4  Reiniciando o InvenSync ===
powershell -NoProfile -ExecutionPolicy Bypass -File "setup\reiniciar.ps1"
if errorlevel 1 goto :erro_restart

echo.
echo ============================================================
echo  Atualizado e reiniciado. Codigo e templates subiram juntos.
echo ============================================================
goto :fim

:erro_pull
echo.
echo [ERRO] git pull falhou. Resolva antes de continuar - conflito ou rede.
goto :fim

:erro_boot
echo.
echo [ERRO] O app nao subiu apos a atualizacao. Nada foi reiniciado:
echo        a versao antiga continua no ar. Revise o erro acima.
goto :fim

:erro_restart
echo.
echo [ERRO] A reinicializacao falhou. Abra o painel pelo
echo        setup\start_invensync.bat e verifique.
goto :fim

:fim
echo.
pause
endlocal
