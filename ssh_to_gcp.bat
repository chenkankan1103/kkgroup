@echo off
REM KKGroup GCP SSH 連線腳本 - 使用原生 OpenSSH 避免 plink 衝突
REM 版本: 1.0
REM 日期: 2026-02-08

echo ========================================
echo KKGroup GCP SSH 連線工具
echo ========================================
echo.

REM 設定變數
set INSTANCE_NAME=instance-20250501-142333
set ZONE=us-central1-c
set USERNAME=e193752468

echo [1/3] 獲取實例外部 IP...
for /f %%i in ('gcloud compute instances describe %INSTANCE_NAME% --zone=%ZONE% --format="value(networkInterfaces[0].accessConfigs[0].natIP)"') do set GCP_IP=%%i

if "%GCP_IP%"=="" (
    echo 錯誤：無法獲取 GCP 實例 IP
    pause
    exit /b 1
)

echo 實例 IP: %GCP_IP%
echo.

echo [2/3] 檢查 SSH 金鑰...
if not exist "%USERPROFILE%\.ssh\google_compute_engine" (
    echo 警告：SSH 金鑰不存在，正在生成...
    gcloud compute config-ssh --ssh-key-file="%USERPROFILE%\.ssh\google_compute_engine"
)

echo.

echo [3/3] 連線到 GCP 實例...
echo 使用原生 OpenSSH 連線 (避免 plink TCP 衝突)
echo 命令: ssh -o StrictHostKeyChecking=no -o ConnectTimeout=30 %USERNAME%@%GCP_IP%
echo.

REM 使用原生 SSH 連線，避免 plink 參數解析問題
ssh -o StrictHostKeyChecking=no -o ConnectTimeout=30 %USERNAME%@%GCP_IP%

echo.
echo SSH 連線已結束。
pause