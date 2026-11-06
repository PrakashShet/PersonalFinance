@echo off
setlocal

REM ============================================================
REM  Personal Finance Manager - Build Windows .exe
REM  Output: dist\PersonalFinanceManager\PersonalFinanceManager.exe
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

echo [INFO] Installing build dependencies ...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-build.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    exit /b 1
)

echo [INFO] Building executable with PyInstaller ...
python -m PyInstaller --noconfirm --clean personal_finance.spec
set EXITCODE=%ERRORLEVEL%

if %EXITCODE% neq 0 (
    echo.
    echo [FAILED] Build failed. Exit code: %EXITCODE%
    endlocal & exit /b %EXITCODE%
)

set "OUTDIR=%~dp0dist\PersonalFinanceManager"
set "EXE=%OUTDIR%\PersonalFinanceManager.exe"

if not exist "%EXE%" (
    echo [ERROR] Expected executable was not created: %EXE%
    endlocal & exit /b 1
)

echo.
echo [SUCCESS] Build complete.
echo.
echo   Run:  "%EXE%"
echo.
echo   Your data is NOT stored beside the .exe (rebuilding replaces this folder).
echo   It lives in:  %%APPDATA%%\PersonalFinanceManager\data\store
echo   Data from an older build kept beside the .exe is copied there on first run.
echo.
echo   Copy the whole folder "dist\PersonalFinanceManager" to distribute the app.
echo.

endlocal & exit /b 0
