@echo off
REM KK 群紙娃娃 RPG 遊戲 - 快速啟動腳本 (Windows)
REM 自動啟動 Flask API 和調試伺服器

cd /d "%~dp0"

echo.
echo ╔═══════════════════════════════════════════════╗
echo ║   🎮 KK 群紙娃娃 RPG 遊戲 - 啟動腳本        ║
echo ╚═══════════════════════════════════════════════╝
echo.

REM 檢查 Python 是否安裝
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 錯誤：找不到 Python
    echo 請確保 Python 已安裝並在 PATH 中
    pause
    exit /b 1
)

REM 檢查依賴
echo 📦 檢查依賴...
python -c "import flask; import flask_cors" >nul 2>&1
if errorlevel 1 (
    echo ⚠️  缺少依賴，正在安裝...
    pip install -r requirements.txt
)

REM 啟動 Flask API
echo.
echo 🚀 啟動 Flask API 伺服器...
echo 📍 訪問地址: http://localhost:5000
echo 🎮 遊戲頁面: http://localhost:5000/rpg-game.html?user_id=YOUR_USER_ID
echo.
echo ✅ 伺服器已啟動，請保持此窗口打開
echo.

python unified_api.py

pause
