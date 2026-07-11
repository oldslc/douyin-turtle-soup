@echo off
REM 授权码生成器 — 快捷启动
REM 如果 dist\keygen.exe 存在则使用 EXE，否则使用 Python 脚本

set "TOOL_DIR=%~dp0"

if exist "%TOOL_DIR%dist\keygen.exe" (
    "%TOOL_DIR%dist\keygen.exe" %*
) else (
    python "%TOOL_DIR%keygen.py" %*
)
