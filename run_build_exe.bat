@echo off
setlocal

REM ============================================================
REM  Personal Finance Manager - Build Windows .exe
REM  Output: dist\PersonalFinanceManager\PersonalFinanceManager.exe
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

echo [INFO] Installing build dependencies ...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-build.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    exit /b 1
)

set "OUTDIR=%~dp0dist\PersonalFinanceManager"
set "KEEP=%~dp0dist\_data_kept_during_build"

REM --- Builds before 1.0 kept their data beside the .exe, in a "data" folder.
REM --- A rebuild replaces the whole output folder and would delete it, so set
REM --- it aside now and put it back afterwards: the new .exe then moves it to
REM --- AppData on its first run.
if exist "%OUTDIR%\data" (
    if exist "%KEEP%" (
        echo [ERROR] "%KEEP%" is left from an earlier build. Check it, move it somewhere safe, then build again.
        exit /b 1
    )
    echo [INFO] Setting aside the data folder beside the old .exe during the build ...
    move "%OUTDIR%\data" "%KEEP%" >nul
    if errorlevel 1 (
        echo [ERROR] Could not move "%OUTDIR%\data" - close the app and try again.
        exit /b 1
    )
)

echo [INFO] Building executable with PyInstaller ...
python -m PyInstaller --noconfirm --clean personal_finance.spec
set EXITCODE=%ERRORLEVEL%

if exist "%KEEP%" (
    if not exist "%OUTDIR%" mkdir "%OUTDIR%"
    move "%KEEP%" "%OUTDIR%\data" >nul
    if errorlevel 1 (
        echo [WARNING] Your old data is safe in "%KEEP%" - move it into "%OUTDIR%\data" by hand.
    ) else (
        echo [INFO] Put the old data back beside the new .exe - it moves to AppData on first run.
    )
)

if %EXITCODE% neq 0 (
    echo.
    echo [FAILED] Build failed. Exit code: %EXITCODE%
    endlocal & exit /b %EXITCODE%
)

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
