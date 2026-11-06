@echo off
setlocal

REM ============================================================
REM  Personal Finance Manager - Setup
REM  Creates a virtual environment and installs dependencies.
REM ============================================================

cd /d "%~dp0"

REM --- Check for Python ---
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found on PATH. Please install Python 3.10+ and try again.
    exit /b 1
)

REM --- Create virtual environment if it doesn't already exist ---
if not exist ".venv\Scripts\activate.bat" (
    echo [INFO] Creating virtual environment in .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        exit /b 1
    )
) else (
    echo [INFO] Virtual environment already exists. Skipping creation.
)

REM --- Activate the virtual environment ---
echo [INFO] Activating virtual environment ...
call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment.
    exit /b 1
)

REM --- Upgrade pip and install dependencies ---
echo [INFO] Upgrading pip ...
python -m pip install --upgrade pip

echo [INFO] Installing dependencies from requirements.txt ...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    exit /b 1
)

echo.
echo [SUCCESS] Setup complete. Run "run.bat" to start the application.
endlocal
