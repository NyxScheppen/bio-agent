@echo off
setlocal EnableDelayedExpansion

echo ======================================
echo  BioAI Agent Portable Build
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

set "RELEASE_DIR=%PROJECT_ROOT%\release\portable"

cd /d "%PROJECT_ROOT%"

echo [INFO] Project root: %PROJECT_ROOT%
echo [INFO] Release dir : %RELEASE_DIR%
echo.

echo ==> Step 1: Basic checks...

if not exist "%PROJECT_ROOT%\backend" (
    echo [ERROR] Missing backend folder: %PROJECT_ROOT%\backend
    pause
    exit /b 1
)

if not exist "%PROJECT_ROOT%\backend\static\index.html" (
    echo [ERROR] Missing frontend static: %PROJECT_ROOT%\backend\static\index.html
    pause
    exit /b 1
)

if not exist "%PROJECT_ROOT%\env\r_libs" (
    echo [ERROR] Missing R private library: %PROJECT_ROOT%\env\r_libs
    pause
    exit /b 1
)

if not exist "%PROJECT_ROOT%\requirements.txt" (
    echo [ERROR] Missing requirements.txt
    echo [INFO] Please generate it first, e.g. pip freeze ^> requirements.txt
    pause
    exit /b 1
)

if not exist "%PROJECT_ROOT%\start_app.bat" (
    echo [ERROR] Missing start_app.bat
    pause
    exit /b 1
)

if not exist "%PROJECT_ROOT%\check_env.bat" (
    echo [ERROR] Missing check_env.bat
    pause
    exit /b 1
)

echo [OK] Basic checks passed.
echo.

echo ==> Step 2: Recreate release directory...
if exist "%RELEASE_DIR%" (
    echo [INFO] Removing old release directory...
    rmdir /s /q "%RELEASE_DIR%"
)

mkdir "%RELEASE_DIR%"
if errorlevel 1 (
    echo [ERROR] Failed to create: %RELEASE_DIR%
    pause
    exit /b 1
)

mkdir "%RELEASE_DIR%\logs"
mkdir "%RELEASE_DIR%\runtime"
mkdir "%RELEASE_DIR%\env"
mkdir "%RELEASE_DIR%\scripts"

echo [OK] Release directories created.
echo.

echo ==> Step 3: Copy backend...
xcopy "%PROJECT_ROOT%\backend" "%RELEASE_DIR%\backend\" /E /I /Y >nul
if errorlevel 1 (
    echo [ERROR] Failed to copy backend
    pause
    exit /b 1
)
echo [OK] backend copied.
echo.

echo ==> Step 4: Copy R private library...
xcopy "%PROJECT_ROOT%\env\r_libs" "%RELEASE_DIR%\env\r_libs\" /E /I /Y >nul
if errorlevel 1 (
    echo [ERROR] Failed to copy env\r_libs
    pause
    exit /b 1
)
echo [OK] env\r_libs copied.
echo.

echo ==> Step 5: Copy scripts...
copy /Y "%PROJECT_ROOT%\start_app.bat" "%RELEASE_DIR%\start_app.bat" >nul
if errorlevel 1 (
    echo [ERROR] Failed to copy start_app.bat
    pause
    exit /b 1
)

copy /Y "%PROJECT_ROOT%\check_env.bat" "%RELEASE_DIR%\check_env.bat" >nul
if errorlevel 1 (
    echo [ERROR] Failed to copy check_env.bat
    pause
    exit /b 1
)

if exist "%PROJECT_ROOT%\scripts\install_r_packages.R" (
    copy /Y "%PROJECT_ROOT%\scripts\install_r_packages.R" "%RELEASE_DIR%\scripts\install_r_packages.R" >nul
)

if exist "%PROJECT_ROOT%\scripts\install_r_packages_linux.R" (
    copy /Y "%PROJECT_ROOT%\scripts\install_r_packages_linux.R" "%RELEASE_DIR%\scripts\install_r_packages_linux.R" >nul
)

echo [OK] scripts copied.
echo.

echo ==> Step 6: Copy requirements and docs...
copy /Y "%PROJECT_ROOT%\requirements.txt" "%RELEASE_DIR%\requirements.txt" >nul
if errorlevel 1 (
    echo [ERROR] Failed to copy requirements.txt
    pause
    exit /b 1
)

if exist "%PROJECT_ROOT%\README.md" (
    copy /Y "%PROJECT_ROOT%\README.md" "%RELEASE_DIR%\README.md" >nul
)

(
echo BioAI Agent Portable
echo Build Date: %date% %time%
echo Platform: Windows
echo Python: install locally on target machine ^(recommended 3.10/3.11/3.12 depending on your tested stack^)
echo R: requires R 4.2+ installed on target machine
) > "%RELEASE_DIR%\VERSION"

echo [OK] docs and VERSION generated.
echo.

echo ======================================
echo  Portable build completed
echo ======================================
echo Output:
echo   %RELEASE_DIR%
echo.
echo Next:
echo   1. Zip the folder: release\portable
echo   2. Send it to others
echo   3. Ask them to run check_env.bat
echo   4. Then run start_app.bat
echo.

pause
exit /b 0