@echo off
title 海龟汤 · 独立集成版（无需 3010）
chcp 65001 >nul

echo ===========================================
echo    海龟汤 🐢 独立集成版
echo    控制面板 + 投屏端
echo    无需启动 3010 后端
echo ===========================================
echo.

cd /d "%~dp0"
set "PORT=3090"

:: 检查参数
if not "%1"=="" set "PORT=%1"

echo  端口: %PORT%
echo  控制面板: http://localhost:%PORT%/
echo  投屏端:   http://localhost:%PORT%/overlay
echo.

:: 启动
set "VENV_DIR=%~dp0..\venv"
call "%VENV_DIR%\Scripts\python.exe" "%~dp0standalone_app.py" --port %PORT%

pause
