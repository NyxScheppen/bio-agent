@echo off
setlocal EnableDelayedExpansion

echo ======================================
echo  BioAI Agent Portable Env Check
echo ======================================

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

if exist "%SCRIPT_DIR%\backend" (
    set "PROJECT_ROOT=%SCRIPT_DIR%"
) else (
    if exist "%SCRIPT_DIR%\..\backend" (
        for %%I in ("%SCRIPT_DIR%\..") do set "PROJECT_ROOT=%%~fI"
    ) else (
        echo [ERROR] Cannot locate project root.
        echo [ERROR] SCRIPT_DIR=%SCRIPT_DIR%
        pause
        exit /b 1
    )
)

cd /d "%PROJECT_ROOT%"
set "HAS_ERROR=0"

echo [INFO] Project root: %PROJECT_ROOT%
echo.

echo ==> Checking backend files...
if exist "%PROJECT_ROOT%\backend\app\main.py" (
    echo [OK] Found: backend\app\main.py
) else (
    echo [FAIL] Missing: backend\app\main.py
    set "HAS_ERROR=1"
)

if exist "%PROJECT_ROOT%\backend\static\index.html" (
    echo [OK] Found: backend\static\index.html
) else (
    echo [FAIL] Missing: backend\static\index.html
    set "HAS_ERROR=1"
)

if exist "%PROJECT_ROOT%\requirements.txt" (
    echo [OK] Found: requirements.txt
) else (
    echo [FAIL] Missing: requirements.txt
    set "HAS_ERROR=1"
)

if exist "%PROJECT_ROOT%\env\r_libs" (
    echo [OK] Found: env\r_libs
) else (
    echo [FAIL] Missing: env\r_libs
    set "HAS_ERROR=1"
)
echo.

echo ==> Locating Python...
set "SYS_PYTHON="

where python >nul 2>nul
if not errorlevel 1 (
    set "SYS_PYTHON=python"
)

if not defined SYS_PYTHON (
    py -3.12 --version >nul 2>nul
    if not errorlevel 1 set "SYS_PYTHON=py -3.12"
)

if not defined SYS_PYTHON (
    py -3.11 --version >nul 2>nul
    if not errorlevel 1 set "SYS_PYTHON=py -3.11"
)

if not defined SYS_PYTHON (
    py -3.10 --version >nul 2>nul
    if not errorlevel 1 set "SYS_PYTHON=py -3.10"
)

if defined SYS_PYTHON (
    echo [OK] Python found: %SYS_PYTHON%
    %SYS_PYTHON% --version
) else (
    echo [FAIL] Python not found.
    echo [INFO] Please install Python 3.10/3.11/3.12 and add it to PATH.
    set "HAS_ERROR=1"
)
echo.

echo ==> Locating Rscript...
set "RSCRIPT_CMD="
set "R_HOME="

for /f "tokens=2,*" %%A in ('reg query "HKLM\SOFTWARE\R-core\R" /v InstallPath 2^>nul ^| find /i "InstallPath"') do (
    set "R_HOME=%%B"
)

if not defined R_HOME (
    for /f "tokens=2,*" %%A in ('reg query "HKLM\SOFTWARE\WOW6432Node\R-core\R" /v InstallPath 2^>nul ^| find /i "InstallPath"') do (
        set "R_HOME=%%B"
    )
)

if defined R_HOME (
    if exist "%R_HOME%\bin\Rscript.exe" set "RSCRIPT_CMD=%R_HOME%\bin\Rscript.exe"
    if exist "%R_HOME%\bin\x64\Rscript.exe" set "RSCRIPT_CMD=%R_HOME%\bin\x64\Rscript.exe"
)

if not defined RSCRIPT_CMD (
    where Rscript >nul 2>nul
    if not errorlevel 1 set "RSCRIPT_CMD=Rscript"
)

if not defined RSCRIPT_CMD (
    for /f "delims=" %%F in ('dir /b /ad "C:\Program Files\R" 2^>nul ^| sort /r') do (
        if exist "C:\Program Files\R\%%F\bin\x64\Rscript.exe" (
            set "RSCRIPT_CMD=C:\Program Files\R\%%F\bin\x64\Rscript.exe"
            goto r_found
        )
        if exist "C:\Program Files\R\%%F\bin\Rscript.exe" (
            set "RSCRIPT_CMD=C:\Program Files\R\%%F\bin\Rscript.exe"
            goto r_found
        )
    )
)

if not defined RSCRIPT_CMD (
    for /f "delims=" %%F in ('dir /b /ad "D:\R-*" 2^>nul ^| sort /r') do (
        if exist "D:\%%F\bin\x64\Rscript.exe" (
            set "RSCRIPT_CMD=D:\%%F\bin\x64\Rscript.exe"
            goto r_found
        )
        if exist "D:\%%F\bin\Rscript.exe" (
            set "RSCRIPT_CMD=D:\%%F\bin\Rscript.exe"
            goto r_found
        )
    )
)

:r_found
if defined RSCRIPT_CMD (
    echo [OK] Rscript found: %RSCRIPT_CMD%
    "%RSCRIPT_CMD%" --version
) else (
    echo [FAIL] Rscript not found
    echo [INFO] Please install R 4.2+ and ensure Rscript is available.
    set "HAS_ERROR=1"
)
echo.

if "%HAS_ERROR%"=="0" (
    echo ======================================
    echo  Environment check passed
    echo ======================================
) else (
    echo ======================================
    echo  Environment check failed
    echo ======================================
)

pause
exit /b %HAS_ERROR%