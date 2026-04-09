@echo off
REM KK 群紙娃娃 RPG 遊戲 - 增強啟動腳本 (Windows)
REM 功能: 自動啟動 Flask API、依賴檢查、診斷功能

setlocal enabledelayedexpansion
cd /d "%~dp0"

REM 顏色和符號定義
set "SUCCESS=✅"
set "ERROR=❌"
set "WARNING=⚠️"
set "INFO=ℹ️"
set "ROCKET=🚀"

echo.
echo ╔═══════════════════════════════════════════════════════════╗
echo ║   %ROCKET% KK 群紙娃娃 RPG 遊戲 - 啟動腳本            ║
echo ║   KKCoin Unified API v2.0                                 ║
echo ╚═══════════════════════════════════════════════════════════╝
echo.
echo 日期: %date% %time%
echo 位置: %cd%
echo.

REM ========== 步驟 1: 檢查 Python ==========
echo %INFO% 步驟 1: 檢查 Python 環境...
python --version >nul 2>&1
if errorlevel 1 (
    echo %ERROR% 錯誤：找不到 Python
    echo.
    echo 解決方案:
    echo   1. 安裝 Python 3.8+ (https://python.org)
    echo   2. 在安裝時勾選 "Add Python to PATH"
    echo   3. 重新啟動此腳本
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version') do set "PYTHON_VERSION=%%i"
echo %SUCCESS% Python 已安裝: %PYTHON_VERSION%
echo.

REM ========== 步驟 2: 檢查 requirements.txt ==========
echo %INFO% 步驟 2: 檢查依賴文件...
if not exist "requirements.txt" (
    echo %ERROR% 錯誤：找不到 requirements.txt
    echo.
    pause
    exit /b 1
)
echo %SUCCESS% requirements.txt 已找到
echo.

REM ========== 步驟 3: 檢查依賴 ==========
echo %INFO% 步驟 3: 驗證 Python 依賴...
python -c "import flask, flask_cors" >nul 2>&1
if errorlevel 1 (
    echo %WARNING% 發現缺少依賴，正在安裝...
    echo.
    pip install -r requirements.txt
    if errorlevel 1 (
        echo %ERROR% 依賴安裝失敗
        echo.
        pause
        exit /b 1
    )
    echo %SUCCESS% 依賴已安裝
) else (
    echo %SUCCESS% 所有依賴已存在
)
echo.

REM ========== 步驟 4: 檢查主要模塊 ==========
echo %INFO% 步驟 4: 驗證主要模塊...
if not exist "unified_api.py" (
    echo %ERROR% 錯誤：找不到 unified_api.py
    pause
    exit /b 1
)
echo %SUCCESS% unified_api.py 已找到
if not exist "game_api.py" (
    echo %ERROR% 錯誤：找不到 game_api.py
    pause
    exit /b 1
)
echo %SUCCESS% game_api.py 已找到
echo.

REM ========== 步驟 5: 檢查資料庫 ==========
echo %INFO% 步驟 5: 驗證數據資源...
if not exist "user_data.db" (
    echo %WARNING% user_data.db 不存在，首次運行時將自動建立
) else (
    echo %SUCCESS% user_data.db 已找到
)
if not exist ".env" (
    echo %WARNING% .env 不存在，使用預設環境變數
) else (
    echo %SUCCESS% .env 已找到
)
echo.

REM ========== 啟動伺服器 ==========
echo.
echo ╔═══════════════════════════════════════════════════════════╗
echo ║  %ROCKET% 啟動 Flask API 伺服器                        ║
echo ╚═══════════════════════════════════════════════════════════╝
echo.
echo 📍 訪問地址:
echo    主頁: http://localhost:5000
echo    健康檢查: http://localhost:5000/api/health
echo    遊戲頁面: http://localhost:5000/rpg-game.html?user_id=YOUR_USER_ID
echo.
echo 💡 提示: 第一次啟動可能需要 2-3 秒
echo.
echo 🔴 按 Ctrl+C 停止伺服器
echo.

set "START_TIME=%time%"

python unified_api.py

if errorlevel 1 (
    echo.
    echo %ERROR% 伺服器啟動失敗
    echo.
    echo 診斷信息:
    echo   - 檢查 Python 是否正常
    echo   - 檢查依賴是否完整
    echo   - 檢查 unified_api.py 是否存在語法錯誤
    echo.
    echo 嘗試手動運行此命令以查看詳細錯誤:
    echo   python -m py_compile unified_api.py
    echo.
) else (
    echo.
    echo %SUCCESS% 伺服器已停止
    echo.
)

pause
