@echo off
REM GCP 文件傳輸工具 - Windows 批處理腳本
REM 用於快速同步本地代碼到 GCP VM

setlocal enabledelayedexpansion

REM 配置
set GCP_HOST=gcp-kkgroup
set REMOTE_PATH=/home/kankan/kkgroup
set LOCAL_PATH=%cd%

REM 顏色定義 (Windows 10+ 支持 ANSI 顏色)
set "RED=[91m"
set "GREEN=[92m"
set "YELLOW=[93m"
set "CYAN=[96m"
set "RESET=[0m"

echo:
echo %CYAN%╔════════════════════════════════════════╗%RESET%
echo %CYAN%║  GCP 文件傳輸工具                        ║%RESET%
echo %CYAN%╚════════════════════════════════════════╝%RESET%
echo:

REM 檢查參數
if "%1"=="" (
    echo %YELLOW%⚠️  用法:
    echo %YELLOW%  gcp_transfer.bat [選項]
    echo:
    echo %CYAN%選項:%RESET%
    echo   sync      - 同步整個項目 (推薦首次使用)
    echo   upload    - 上傳單個文件
    echo   download  - 下載單個文件
    echo   config    - 顯示配置信息
    echo   test      - 測試連接
    echo:
    goto :eof
)

if "%1"=="test" goto :test
if "%1"=="config" goto :config
if "%1"=="sync" goto :sync
if "%1"=="upload" goto :upload
if "%1"=="download" goto :download

echo %RED%✗ 未知命令: %1%RESET%
goto :eof

REM ===================== 測試連接 =====================
:test
echo %CYAN%🧪 測試 SSH 連接...%RESET%
ssh %GCP_HOST% "echo SSH連接成功"
if errorlevel 1 (
    echo %RED%✗ SSH 連接失敗%RESET%
    echo %YELLOW%請檢查:
    echo   1. SSH 密鑰是否正確配置
    echo   2. GCP 防火牆是否開放 SSH 端口 22
    echo   3. SSH 配置文件是否正確%RESET%
    exit /b 1
)
echo %GREEN%✓ SSH 連接成功%RESET%
goto :eof

REM ===================== 顯示配置 =====================
:config
echo %CYAN%📋 GCP 傳輸配置信息:%RESET%
echo:
echo   GCP Host:        %GCP_HOST%
echo   Remote Path:     %REMOTE_PATH%
echo   Local Path:      %LOCAL_PATH%
echo:
echo %CYAN%SSH 配置檔案位置:%RESET%
echo   %USERPROFILE%\.ssh\config
echo:
echo %CYAN%SSH 密鑰位置:%RESET%
echo   %USERPROFILE%\.ssh\gcp_kankan_key
echo   %USERPROFILE%\.ssh\google_cloud_rsa
echo:
goto :eof

REM ===================== 同步項目 =====================
:sync
echo %CYAN%📤 開始同步項目...%RESET%
echo   源: %LOCAL_PATH%
echo   目標: %GCP_HOST%:%REMOTE_PATH%
echo:

REM 首先創建遠端目錄
echo %YELLOW%正在創建遠端目錄...%RESET%
ssh %GCP_HOST% "mkdir -p %REMOTE_PATH%" >nul 2>&1

REM 排除不需要同步的文件
echo %YELLOW%正在計算同步文件...%RESET%
set EXCLUDE=--exclude=.git --exclude=.venv --exclude=__pycache__ --exclude=*.pyc --exclude=.env --exclude=.DS_Store --exclude=node_modules

REM 使用 SCP 遞歸複製 (仍然是手動，因為 rsync 在 Windows 上不普遍)
REM 為了更好的體驗，我們逐個同步主要文件夾
echo:
echo %CYAN%正在同步文件...%RESET%

echo %YELLOW%  ① 複製 bot.py%RESET%
scp "%LOCAL_PATH%\bot.py" "%GCP_HOST%:%REMOTE_PATH%/" >nul 2>&1 && echo %GREEN%    ✓ bot.py%RESET% || echo %RED%    ✗ bot.py%RESET%

echo %YELLOW%  ② 複製 commands 目錄%RESET%
scp -r "%LOCAL_PATH%\commands" "%GCP_HOST%:%REMOTE_PATH%/" >nul 2>&1 && echo %GREEN%    ✓ commands%RESET% || echo %RED%    ✗ commands%RESET%

echo %YELLOW%  ③ 複製 uicommands 目錄%RESET%
scp -r "%LOCAL_PATH%\uicommands" "%GCP_HOST%:%REMOTE_PATH%/" >nul 2>&1 && echo %GREEN%    ✓ uicommands%RESET% || echo %RED%    ✗ uicommands%RESET%

echo %YELLOW%  ④ 複製 utils 目錄%RESET%
scp -r "%LOCAL_PATH%\utils" "%GCP_HOST%:%REMOTE_PATH%/" >nul 2>&1 && echo %GREEN%    ✓ utils%RESET% || echo %RED%    ✗ utils%RESET%

echo %YELLOW%  ⑤ 複製 requirements.txt%RESET%
scp "%LOCAL_PATH%\requirements.txt" "%GCP_HOST%:%REMOTE_PATH%/" >nul 2>&1 && echo %GREEN%    ✓ requirements.txt%RESET% || echo %RED%    ✗ requirements.txt%RESET%

echo %YELLOW%  ⑥ 複製 database_schema.py%RESET%
scp "%LOCAL_PATH%\database_schema.py" "%GCP_HOST%:%REMOTE_PATH%/" >nul 2>&1 && echo %GREEN%    ✓ database_schema.py%RESET% || echo %RED%    ✗ database_schema.py%RESET%

echo %YELLOW%  ⑦ 複製 gcp_deploy.sh%RESET%
scp "%LOCAL_PATH%\gcp_deploy.sh" "%GCP_HOST%:%REMOTE_PATH%/" >nul 2>&1 && echo %GREEN%    ✓ gcp_deploy.sh%RESET% || echo %RED%    ✗ gcp_deploy.sh%RESET%

echo %YELLOW%  ⑧ 複製 verify_dependencies.py%RESET%
scp "%LOCAL_PATH%\verify_dependencies.py" "%GCP_HOST%:%REMOTE_PATH%/" >nul 2>&1 && echo %GREEN%    ✓ verify_dependencies.py%RESET% || echo %RED%    ✗ verify_dependencies.py%RESET%

echo:
echo %GREEN%✓ 文件同步完成%RESET%
echo:
echo %CYAN%下一步:%RESET%
echo   1. ssh %GCP_HOST%
echo   2. bash /home/kankan/kkgroup/gcp_deploy.sh
echo:
goto :eof

REM ===================== 上傳文件 =====================
:upload
if "%2"=="" (
    echo %RED%✗ 請指定本地文件路徑%RESET%
    echo %YELLOW%用法: gcp_transfer.bat upload ^<本地文件路徑^>%RESET%
    exit /b 1
)

if not exist "%2" (
    echo %RED%✗ 文件不存在: %2%RESET%
    exit /b 1
)

echo %CYAN%📤 上傳文件...%RESET%
echo   源: %2
echo   目標: %GCP_HOST%:%REMOTE_PATH%
echo:

scp "%2" "%GCP_HOST%:%REMOTE_PATH%/"
if errorlevel 1 (
    echo %RED%✗ 上傳失敗%RESET%
    exit /b 1
)

echo %GREEN%✓ 文件上傳成功%RESET%
goto :eof

REM ===================== 下載文件 =====================
:download
if "%2"=="" (
    echo %RED%✗ 請指定遠端文件路徑%RESET%
    echo %YELLOW%用法: gcp_transfer.bat download ^<遠端文件路徑^>%RESET%
    exit /b 1
)

echo %CYAN%📥 下載文件...%RESET%
echo   源: %GCP_HOST%:%2
echo   目標: %LOCAL_PATH%
echo:

scp "%GCP_HOST%:%2" "%LOCAL_PATH%/"
if errorlevel 1 (
    echo %RED%✗ 下載失敗%RESET%
    exit /b 1
)

echo %GREEN%✓ 文件下載成功%RESET%
goto :eof

endlocal
