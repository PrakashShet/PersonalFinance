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

REM Ensure writable data folders exist beside the .exe
if not exist "%OUTDIR%\data\store" mkdir "%OUTDIR%\data\store"
if not exist "%OUTDIR%\data\cache" mkdir "%OUTDIR%\data\cache"
if not exist "%OUTDIR%\data\user\backups" mkdir "%OUTDIR%\data\user\backups"
if not exist "%OUTDIR%\logs" mkdir "%OUTDIR%\logs"

echo.
echo [SUCCESS] Build complete.
echo.
echo   Run:  "%EXE%"
echo.
echo   User data is stored next to the .exe:
echo     %OUTDIR%\data\store\
echo     %OUTDIR%\logs\
echo.
echo   Copy the whole folder "dist\PersonalFinanceManager" to distribute the app.
echo.

endlocal & exit /b 0
