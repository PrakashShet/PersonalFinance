@echo off
setlocal

REM ============================================================
REM  Personal Finance Manager - Smoke Test Runner
REM  E2E session + UI launch tests (pytest -m smoke).
REM ============================================================

cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found. Please run "setup.bat" first.
    exit /b 1
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment.
    exit /b 1
)

echo [INFO] Running smoke tests ...
python -m pytest -m smoke -v %*
set EXITCODE=%ERRORLEVEL%

if %EXITCODE%==0 (
    echo.
    echo [SUCCESS] All smoke tests passed.
) else (
    echo.
    echo [FAILED] Some smoke tests failed. Exit code: %EXITCODE%
)

endlocal & exit /b %EXITCODE%
