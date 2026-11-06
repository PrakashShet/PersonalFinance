@echo off
setlocal

REM ============================================================
REM  Personal Finance Manager - Run
REM  Activates the virtual environment and launches main.py.
REM ============================================================

cd /d "%~dp0"

REM --- Make sure the virtual environment exists ---
if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found. Please run "run_setup.bat" first.
    exit /b 1
)

REM --- Activate the virtual environment ---
call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment.
    exit /b 1
)

REM --- Launch the application ---
echo [INFO] Starting Personal Finance Manager ...
python main.py %*
set EXITCODE=%ERRORLEVEL%

endlocal & exit /b %EXITCODE%
