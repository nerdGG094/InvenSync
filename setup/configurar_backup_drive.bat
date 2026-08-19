@echo off
REM ============================================================
REM  Configura o backup offsite do InvenSync no Google Drive (rclone).
REM
REM  Roda UMA vez. Abre o assistente do rclone; o unico passo que
REM  precisa de gente e autorizar no navegador com a conta Google que
REM  vai guardar os backups. Chrome ja esta neste servidor, entao a
REM  autorizacao acontece aqui mesmo.
REM
REM  Depois disto, ponha no .env:
REM    BACKUP_UPLOAD_CMD=C:\tools\rclone\rclone.exe copy "{path}" jaboti-cripto:InvenSync --config C:\tools\rclone\rclone.conf
REM  (a linha exata sai impressa no fim.)
REM ============================================================
setlocal
set RCLONE=C:\tools\rclone\rclone.exe
set CONF=C:\tools\rclone\rclone.conf

if not exist "%RCLONE%" goto :sem_rclone
goto :passo1
:sem_rclone
echo [ERRO] rclone nao encontrado em %RCLONE%.
pause
exit /b 1
:passo1

echo.
echo ============================================================
echo  PASSO 1 de 2 - Conta Google (remote "jaboti")
echo ============================================================
echo  No assistente que vai abrir:
echo    n) New remote
echo    name^> jaboti
echo    Storage^> digite:  drive
echo    client_id / client_secret^> deixe em branco (Enter)
echo    scope^> 1  (acesso total)
echo    Edit advanced config^> n
echo    Use web browser to authenticate^> y   ^<== abre o Chrome, faca login e autorize
echo    Configure this as a Shared Drive^> n
echo    y) Yes this is OK
echo    q) Quit config
echo.
pause
"%RCLONE%" config --config "%CONF%"

echo.
echo ============================================================
echo  PASSO 2 de 2 - Camada de CRIPTOGRAFIA (remote "jaboti-cripto")
echo ============================================================
echo  O dump vai em texto claro (inventario, chamados). Esta camada
echo  cifra os arquivos ANTES de subir - no Drive eles ficam
echo  ilegiveis, e o rclone decifra sozinho quando voce baixa de volta.
echo.
echo  No assistente:
echo    n) New remote
echo    name^> jaboti-cripto
echo    Storage^> digite:  crypt
echo    remote^> jaboti:InvenSync    (a pasta no Drive que sera cifrada)
echo    filename_encryption^> 1 (standard)   directory_name_encryption^> y
echo    Password^> g (gera uma forte) - ou defina uma; ANOTE em local seguro
echo    Password2 (salt)^> g tambem, ou Enter
echo    y) Yes this is OK
echo    q) Quit config
echo.
echo  [IMPORTANTE] A senha desta camada mora no proprio rclone.conf.
echo  Se o servidor for perdido, voce precisa do rclone.conf (ou da senha
echo  anotada) para decifrar os backups. GUARDE UMA COPIA FORA DAQUI.
echo.
pause
"%RCLONE%" config --config "%CONF%"

echo.
echo ============================================================
echo  Pronto. Ponha esta linha no .env do InvenSync:
echo.
echo  BACKUP_UPLOAD_CMD=%RCLONE% copy "{path}" jaboti-cripto: --config %CONF%
echo.
echo  Depois rode setup\testar_backup_drive.bat para um envio de teste.
echo ============================================================
pause
endlocal
