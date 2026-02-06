@echo off
REM KK Garden Bot 启动脚本（Windows）
REM 确保使用虚拟环境中的 Python

echo ==========================================
echo  🤖 KK Garden Bot 启动脚本
echo ==========================================
echo.

REM 获取脚本所在目录
setlocal enabledelayedexpansion
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM 检查虚拟环境
if not exist ".venv\Scripts\python.exe" (
    echo ❌ 虚拟环境未找到！
    echo 请先运行: python -m venv .venv
    echo 然后运行: .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

echo ✅ 虚拟环境已找到
echo.

REM 验证依赖
echo 检查依赖...
.venv\Scripts\python.exe verify_dependencies.py
if errorlevel 1 (
    echo.
    echo ❌ 部分依赖缺失！
    echo 正在安装依赖...
    .venv\Scripts\pip install -r requirements.txt
    echo.
)

echo.
echo ==========================================
echo  🚀 启动 Bot...
echo ==========================================
echo.

REM 启动 BOT
.venv\Scripts\python.exe bot.py

REM 如果 BOT 意外停止
if errorlevel 1 (
    echo.
    echo ❌ Bot 崩溃了！错误代码: %errorlevel%
    echo.
    pause
)
