@echo off
title AI Multi-Agent Data Analysis Studio Launcher

echo =======================================================
echo   AI Multi-Agent Data Analysis Studio Launcher (Windows)
echo =======================================================
echo.

:: Check for python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python was not found on your system PATH.
    echo Please install Python 3.10 or higher and make sure it is added to PATH.
    pause
    exit /b 1
)

:: Create virtual env if it does not exist
if not exist ".venv" (
    echo [INFO] Creating Python virtual environment in .venv folder...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

:: Activate virtual env
echo [INFO] Activating virtual environment...
call .venv\Scripts\activate
if %errorlevel% neq 0 (
    echo [ERROR] Failed to activate virtual environment.
    pause
    exit /b 1
)

:: Install dependencies
set INSTALL_DEPS=1
if exist ".venv\sentinel" (
    powershell -Command "if ((Get-Item '.venv\sentinel').LastWriteTime -ge (Get-Item 'requirements.txt').LastWriteTime) { exit 0 } else { exit 1 }" >nul 2>&1
    if %errorlevel% equ 0 (
        set INSTALL_DEPS=0
        echo [INFO] Dependencies are up to date. Skipping installation.
    )
)

if %INSTALL_DEPS% equ 1 (
    echo [INFO] Installing dependencies from requirements.txt...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install requirements.
        pause
        exit /b 1
    )
    echo. > ".venv\sentinel"
)

:: Launch uvicorn
echo.
echo [INFO] Launching FastAPI Backend Server...
echo [INFO] The application will open automatically in your default browser.
echo [INFO] Keep this command window open to keep the application running.
echo =======================================================
echo.

python -m uvicorn backend.main:app --port 8000 --host 127.0.0.1

if %errorlevel% neq 0 (
    echo.
    echo [WARNING] Server stopped with error code %errorlevel%.
    pause
)
