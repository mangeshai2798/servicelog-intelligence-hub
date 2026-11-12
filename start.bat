@echo off
title ServiceLog Intelligence Hub
echo ============================================================
echo   Starting ServiceLog Intelligence Hub (FastAPI + Web UI)
echo ============================================================
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    echo [Launcher] Using virtual environment (.venv)...
    ".venv\Scripts\python.exe" run_dashboard.py
) else (
    echo [Launcher] Using system python...
    python run_dashboard.py
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Server stopped with error code %ERRORLEVEL%.
    pause
)

