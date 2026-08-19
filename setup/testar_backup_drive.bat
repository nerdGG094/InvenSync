@echo off
REM ============================================================
REM  Prova que o backup offsite funciona de PONTA A PONTA:
REM  sobe um arquivo de teste, confirma que ele chegou (cifrado) e o
REM  apaga. Rode depois de configurar_backup_drive.bat.
REM ============================================================
setlocal
set RCLONE=C:\tools\rclone\rclone.exe
set CONF=C:\tools\rclone\rclone.conf
set REMOTE=jaboti-cripto:

if not exist "%CONF%" goto :sem_conf
goto :inicio
:sem_conf
echo [ERRO] rclone.conf nao existe. Rode configurar_backup_drive.bat primeiro.
pause
exit /b 1
:inicio

set TESTE=%TEMP%\invensync_teste_offsite.txt
echo Teste de backup offsite do InvenSync em %DATE% %TIME% > "%TESTE%"

echo.
echo === 1/4  Enviando arquivo de teste (cifrado no Drive) ===
"%RCLONE%" copy "%TESTE%" %REMOTE% --config "%CONF%" -v
if errorlevel 1 goto :falhou

echo.
echo === 2/4  Conferindo que chegou ===
"%RCLONE%" ls %REMOTE% --config "%CONF%" | findstr /i "invensync_teste_offsite"
if errorlevel 1 goto :falhou

echo.
echo === 3/4  Baixando de volta para provar que decifra ===
"%RCLONE%" cat %REMOTE%invensync_teste_offsite.txt --config "%CONF%"
if errorlevel 1 goto :falhou

echo.
echo === 4/4  Limpando o arquivo de teste ===
"%RCLONE%" delete %REMOTE%invensync_teste_offsite.txt --config "%CONF%"

echo.
echo ============================================================
echo  OK. O caminho ate o Drive funciona. Ative no .env:
echo    BACKUP_UPLOAD_CMD=%RCLONE% copy "{path}" %REMOTE% --config %CONF%
echo  e reinicie o InvenSync (atualizar.bat ou reiniciar.ps1).
echo  A pagina Backups passa a mostrar o status do envio.
echo ============================================================
del "%TESTE%" 2>nul
pause
goto :eof

:falhou
echo.
echo [ERRO] O envio falhou. Verifique a saida acima. Causas comuns:
echo   - autorizacao do Google expirou (rode configurar_backup_drive.bat)
echo   - sem internet / firewall bloqueando
del "%TESTE%" 2>nul
pause
endlocal
