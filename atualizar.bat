@echo off
REM ============================================================
REM  InvenSync - Atualizar (deploy) com disciplina:
REM  puxa o codigo novo, atualiza dependencias e LEMBRA de reiniciar.
REM  Evita a janela de erro "template novo no ar antes do restart".
REM ============================================================
setlocal
cd /d "%~dp0"

echo.
echo === 1/3  Baixando atualizacoes (git pull) ===
git pull --ff-only
if errorlevel 1 (
  echo.
  echo [ERRO] git pull falhou. Resolva antes de continuar (conflitos/rede).
  pause
  exit /b 1
)

echo.
echo === 2/3  Atualizando dependencias ===
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet --disable-pip-version-check
) else (
  echo [aviso] .venv nao encontrado - rode setup\install.bat primeiro.
)

echo.
echo === 3/3  Verificacao rapida de boot ===
".venv\Scripts\python.exe" -c "from inventory import create_app; create_app(); print('BOOT OK')"
if errorlevel 1 (
  echo.
  echo [ERRO] O app nao subiu apos a atualizacao. NAO reinicie ainda; revise o erro acima.
  pause
  exit /b 1
)

echo.
echo ============================================================
echo  Atualizado com sucesso. AGORA REINICIE O INVENSYNC:
echo  feche o painel e abra pelo start_invensync.bat (ou reinicie
echo  o servico), para que codigo e templates subam juntos.
echo ============================================================
pause
endlocal
