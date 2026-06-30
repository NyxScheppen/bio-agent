@echo off
setlocal EnableDelayedExpansion

echo ======================================
echo  BioAI Agent Portable Start
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

echo [INFO] Project root: %PROJECT_ROOT%
echo.

echo ==> Checking backend files...
if not exist "%PROJECT_ROOT%\backend\app\main.py" (
    echo [ERROR] Missing backend entry: %PROJECT_ROOT%\backend\app\main.py
    pause
    exit /b 1
)

if not exist "%PROJECT_ROOT%\backend\static\index.html" (
    echo [ERROR] Missing frontend static: %PROJECT_ROOT%\backend\static\index.html
    pause
    exit /b 1
)

if not exist "%PROJECT_ROOT%\requirements.txt" (
    echo [ERROR] Missing requirements.txt
    pause
    exit /b 1
)

if not exist "%PROJECT_ROOT%\env\r_libs" (
    echo [ERROR] Missing R private library: %PROJECT_ROOT%\env\r_libs
    pause
    exit /b 1
)
echo [OK] Project files checked.
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

if not defined SYS_PYTHON (
    echo [ERROR] Python not found.
    echo Please install Python 3.10/3.11/3.12 first and add it to PATH.
    pause
    exit /b 1
)

echo [OK] Using system Python: %SYS_PYTHON%
%SYS_PYTHON% --version
echo.

echo ==> Preparing virtual environment...
set "PYTHON_CMD=%PROJECT_ROOT%\.venv\Scripts\python.exe"

if not exist "%PYTHON_CMD%" (
    echo [INFO] .venv not found, creating...
    %SYS_PYTHON% -m venv "%PROJECT_ROOT%\.venv"
    if errorlevel 1 (
        echo [ERROR] Failed to create .venv
        pause
        exit /b 1
    )
)

if not exist "%PYTHON_CMD%" (
    echo [ERROR] Virtual environment python still not found:
    echo         %PYTHON_CMD%
    pause
    exit /b 1
)

echo [OK] Virtual environment ready: %PYTHON_CMD%
"%PYTHON_CMD%" --version
echo.

echo ==> Installing Python dependencies...
"%PYTHON_CMD%" -m pip install --upgrade pip
if errorlevel 1 (
    echo [ERROR] Failed to upgrade pip
    pause
    exit /b 1
)

"%PYTHON_CMD%" -m pip install -r "%PROJECT_ROOT%\requirements.txt"
if errorlevel 1 (
    echo [ERROR] Failed to install Python dependencies
    echo [INFO] Please inspect network / wheel compatibility / requirements.txt
    pause
    exit /b 1
)
echo [OK] Python dependencies installed.
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
if not defined RSCRIPT_CMD (
    echo [ERROR] Rscript not found.
    echo Please install R 4.2+ or add Rscript to PATH.
    pause
    exit /b 1
)

echo [OK] Using Rscript: %RSCRIPT_CMD%
"%RSCRIPT_CMD%" --version
echo.

if not exist "%PROJECT_ROOT%\logs" mkdir "%PROJECT_ROOT%\logs"
if not exist "%PROJECT_ROOT%\runtime" mkdir "%PROJECT_ROOT%\runtime"
if not exist "%PROJECT_ROOT%\backend\uploads" mkdir "%PROJECT_ROOT%\backend\uploads"
if not exist "%PROJECT_ROOT%\backend\generated" mkdir "%PROJECT_ROOT%\backend\generated"

set "BACKEND_ROOT=%PROJECT_ROOT%\backend"
set "UPLOAD_DIR=%BACKEND_ROOT%\uploads"
set "GENERATED_DIR=%BACKEND_ROOT%\generated"
set "R_LIBS_USER=%PROJECT_ROOT%\env\r_libs"

for %%I in ("%RSCRIPT_CMD%") do set "R_BIN=%%~dpI"

set "HOST=127.0.0.1"
set "PORT=8000"
set "RUN_BAT=%PROJECT_ROOT%\runtime\run_backend.bat"

echo [INFO] HOST=%HOST%
echo [INFO] PORT=%PORT%
echo [INFO] R_LIBS_USER=%R_LIBS_USER%
echo [INFO] RSCRIPT_CMD=%RSCRIPT_CMD%
echo.

(
    echo @echo off
    echo cd /d "%BACKEND_ROOT%"
    echo set "PROJECT_ROOT=%PROJECT_ROOT%"
    echo set "BACKEND_ROOT=%BACKEND_ROOT%"
    echo set "UPLOAD_DIR=%UPLOAD_DIR%"
    echo set "GENERATED_DIR=%GENERATED_DIR%"
    echo set "R_LIBS_USER=%R_LIBS_USER%"
    echo set "RSCRIPT_CMD=%RSCRIPT_CMD%"
    echo set "RSCRIPT_PATH=%RSCRIPT_CMD%"
    echo set "PYTHONIOENCODING=utf-8"
    echo set "PATH=%R_BIN%;%%PATH%%"
    echo echo PROJECT_ROOT=%%PROJECT_ROOT%%
    echo echo BACKEND_ROOT=%%BACKEND_ROOT%%
    echo echo UPLOAD_DIR=%%UPLOAD_DIR%%
    echo echo GENERATED_DIR=%%GENERATED_DIR%%
    echo echo R_LIBS_USER=%%R_LIBS_USER%%
    echo echo RSCRIPT_PATH=%%RSCRIPT_PATH%%
    echo "%PYTHON_CMD%" -m uvicorn app.main:app --host %HOST% --port %PORT% ^> "%PROJECT_ROOT%\logs\backend.log" 2^>^&1
) > "%RUN_BAT%"

echo [INFO] Starting backend service...
start "BioAI-Agent-Backend" "%RUN_BAT%"

echo [INFO] Waiting for backend to start...
timeout /t 6 /nobreak >nul

echo [INFO] Opening browser...
start http://%HOST%:%PORT%

echo.
echo ======================================
echo  BioAI Agent start command issued
echo ======================================
echo URL: http://%HOST%:%PORT%
echo Health: http://%HOST%:%PORT%/api/health
echo Log: %PROJECT_ROOT%\logs\backend.log
echo.
echo If page is not available, check:
echo   1. logs\backend.log
echo   2. backend\.env
echo   3. Python dependency install output
echo   4. whether your backend imports call R correctly
echo.

pause
exit /b 0