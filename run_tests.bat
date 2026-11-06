@echo off
setlocal

REM ============================================================
REM  Personal Finance Manager - Test Runner
REM  Runs unit tests + smoke tests via pytest.
REM ============================================================

cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found. Please run "run_setup.bat" first.
    exit /b 1
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment.
    exit /b 1
)

echo [INFO] Running test suite ...
python -m pytest %*
set EXITCODE=%ERRORLEVEL%

if %EXITCODE%==0 (
    echo.
    echo [SUCCESS] All tests passed.
) else (
    echo.
    echo [FAILED] Some tests failed. Exit code: %EXITCODE%
)

endlocal & exit /b %EXITCODE%
