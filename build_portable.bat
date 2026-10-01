@echo off
setlocal EnableDelayedExpansion
set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
if exist "%SCRIPT_DIR%\backend" (
    set "PROJECT_ROOT=%SCRIPT_DIR%"
) else (
    if exist "%SCRIPT_DIR%\..\backend" (
        for %%I in ("%SCRIPT_DIR%\..") do set "PROJECT_ROOT=%%~fI"
    ) else (
        echo [ERROR] Cannot locate project root.
        exit /b 1
    )
)
set "RELEASE_DIR=%PROJECT_ROOT%\release\portable"
cd /d "%PROJECT_ROOT%"
echo [INFO] Project root : %PROJECT_ROOT%

set "HAS_ERROR=0"

if not exist "%PROJECT_ROOT%\backend" (
    echo [FAIL] Missing: backend\
    set "HAS_ERROR=1"
)

if not exist "%PROJECT_ROOT%\backend\app\main.py" (
    echo [FAIL] Missing: main.py
    set "HAS_ERROR=1"
)

if not exist "%PROJECT_ROOT%\backend\static\index.html" (
    echo [FAIL] Missing: index.html
    set "HAS_ERROR=1"
)

if not exist "%PROJECT_ROOT%\requirements.txt" (
    echo [FAIL] Missing: requirements.txt
    set "HAS_ERROR=1"
)

if not exist "%PROJECT_ROOT%\env\r_libs" (
    echo [FAIL] Missing: env\r_libs
    set "HAS_ERROR=1"
)

if not exist "%PROJECT_ROOT%\start_app.bat" (
    echo [FAIL] Missing: start_app.bat
    set "HAS_ERROR=1"
)

if not exist "%PROJECT_ROOT%\check_env.bat" (
    echo [FAIL] Missing: check_env.bat
    set "HAS_ERROR=1"
)

if "%HAS_ERROR%"=="1" (
    echo.
    echo [ERROR] One or more required files are missing. Aborting.
    pause
    exit /b 1
)

echo [OK] All required files present.
echo.

REM -- Step 2: Warn if .env contains real keys ----------------
echo ---- Step 2: Checking for sensitive data...

if exist "%PROJECT_ROOT%\backend\.env" (
    echo [WARN] backend\.env found - it may contain real API keys.
    echo [WARN] It will NOT be copied to the portable build.
    echo [WARN] Only backend\.env_example will be included.
) else (
    echo [INFO] No backend\.env found - nothing to exclude.
)
echo.

REM -- Step 3: Recreate release directory ---------------------
echo ---- Step 3: Recreate release directory...

if exist "%RELEASE_DIR%" (
    echo [INFO] Removing old release directory...
    rmdir /s /q "%RELEASE_DIR%"
)

mkdir "%RELEASE_DIR%"
if errorlevel 1 (
    echo [ERROR] Failed to create: %RELEASE_DIR%
REM [skipped] pause
    exit /b 1
)

mkdir "%RELEASE_DIR%\logs"
mkdir "%RELEASE_DIR%\runtime"
mkdir "%RELEASE_DIR%\env"

echo [OK] Release directories created.
echo.

REM -- Step 4: Copy backend (excluding runtime artifacts) -----
echo ---- Step 4: Copy backend...

robocopy "%PROJECT_ROOT%\backend" "%RELEASE_DIR%\backend" /E /NFL /NDL /NJH /NJS ^
    /XD "__pycache__" "storage" "db_data" "tests" ".git" ^
    /XF "*.pyc" "*.pyo" ".env" ".env.*" "*.db" "*.sqlite" "*.sqlite3" ^
        "*.pem" "*.key" "*.pfx" "*.p12" "*.ppk" "*.jks" "*.keystore" "*.kdbx" ^
        "id_rsa" "id_ed25519" ".npmrc" ".pypirc" "*secret*" "*credential*" "service-account*.json"

set "ROBO_ERR=%ERRORLEVEL%"
if %ROBO_ERR% GEQ 8 (
    echo [ERROR] robocopy failed with exit code %ROBO_ERR%
REM [skipped] pause
    exit /b 1
)

echo [OK] backend copied (runtime data, local env files, credentials, and private keys excluded^).
echo.

REM -- Step 5: Create storage and db_data dirs in release -----
echo ---- Step 5: Create runtime directories in release...

mkdir "%RELEASE_DIR%\backend\storage"
mkdir "%RELEASE_DIR%\backend\storage\uploads"
mkdir "%RELEASE_DIR%\backend\storage\generated"
mkdir "%RELEASE_DIR%\backend\storage\temp"
mkdir "%RELEASE_DIR%\backend\db_data"

echo [OK] Runtime directories created.
echo.

REM -- Step 6: Copy R private library -------------------------
echo ---- Step 6: Copy R private library...

robocopy "%PROJECT_ROOT%\env\r_libs" "%RELEASE_DIR%\env\r_libs" /E /NFL /NDL /NJH /NJS ^
    /XD "__pycache__"

set "ROBO_ERR=%ERRORLEVEL%"
if %ROBO_ERR% GEQ 8 (
    echo [ERROR] robocopy failed with exit code %ROBO_ERR%
REM [skipped] pause
    exit /b 1
)

echo [OK] env\r_libs copied.
echo.

REM -- Step 7: Copy scripts and root files --------------------
echo ---- Step 7: Copy scripts and root files...

copy /Y "%PROJECT_ROOT%\start_app.bat"   "%RELEASE_DIR%\start_app.bat"   >nul
copy /Y "%PROJECT_ROOT%\check_env.bat"   "%RELEASE_DIR%\check_env.bat"   >nul
copy /Y "%PROJECT_ROOT%\requirements.txt" "%RELEASE_DIR%\requirements.txt" >nul
copy /Y "%PROJECT_ROOT%\README.md"       "%RELEASE_DIR%\README.md"       >nul

if exist "%PROJECT_ROOT%\install_r_packages.R" (
    copy /Y "%PROJECT_ROOT%\install_r_packages.R" "%RELEASE_DIR%\install_r_packages.R" >nul
    echo [OK] install_r_packages.R copied.
) else (
    echo [WARN] install_r_packages.R not found - R packages won't be installable.
)

if exist "%PROJECT_ROOT%\TECHNICAL_DOCUMENTATION.md" (
    copy /Y "%PROJECT_ROOT%\TECHNICAL_DOCUMENTATION.md" "%RELEASE_DIR%\TECHNICAL_DOCUMENTATION.md" >nul
    echo [OK] TECHNICAL_DOCUMENTATION.md copied.
)

if exist "%PROJECT_ROOT%\backend\.env_example" (
    copy /Y "%PROJECT_ROOT%\backend\.env_example" "%RELEASE_DIR%\backend\.env_example" >nul
    echo [OK] backend\.env_example copied.
) else (
    echo [WARN] backend\.env_example not found.
)

echo [OK] Root-level files copied.
echo.

REM -- Step 8: Copy docs --------------------------------------
echo ---- Step 8: Copy docs...

if exist "%PROJECT_ROOT%\docs" (
    robocopy "%PROJECT_ROOT%\docs" "%RELEASE_DIR%\docs" /E /NFL /NDL /NJH /NJS
    set "ROBO_ERR=!ERRORLEVEL!"
    if !ROBO_ERR! GEQ 8 (
        echo [ERROR] robocopy docs failed with exit code !ROBO_ERR!
REM [skipped] pause
        exit /b 1
    )
    echo [OK] docs\ copied.
) else (
    echo [INFO] docs\ not found - skipping.
)
echo.

REM -- Step 9: Generate VERSION file --------------------------
echo ---- Step 9: Generate VERSION...

(
    echo BioAI Agent Portable
    echo Build Date: %date% %time%
    echo Platform: Windows
    echo Python: 3.11 / 3.12 (install on target machine^)
    echo R: R 4.2+ (install on target machine^)
    echo.
    echo Included directories:
    echo   backend\        - FastAPI application
    echo   env\r_libs\     - R private package library
    echo   docs\           - Development documentation
    echo.
    echo Setup instructions:
    echo   1. Run check_env.bat to verify environment
    echo   2. Copy backend\.env_example to backend\.env and edit API keys
    echo   3. Run install_r_packages.R if R packages are missing:
    echo       Rscript install_r_packages.R
    echo   4. Run start_app.bat to launch
) > "%RELEASE_DIR%\VERSION.txt"

echo [OK] VERSION.txt generated.
echo.

REM -- Step 10: Build summary ---------------------------------
echo ---- Step 10: Build summary...

echo.
echo Directories in release:
dir /b /ad "%RELEASE_DIR%"
echo.
echo Files in release root:
dir /b /a:-d "%RELEASE_DIR%"
echo.

echo ======================================
echo  Portable build completed
echo ======================================
echo Output:
echo   %RELEASE_DIR%
echo.
echo Next steps for distribution:
echo   1. Zip the folder: release\portable
echo   2. Send to recipient
echo   3. Recipient should:
echo      a. Run check_env.bat
echo      b. Copy backend\.env_example to backend\.env and configure
echo      c. Run: Rscript install_r_packages.R  (if R packages missing^)
echo      d. Run start_app.bat
echo.
echo (Tip: run "powershell Compress-Archive -Path release\portable\*"
echo        -DestinationPath release\BioAI_Agent_Portable.zip" to zip^)
echo.

REM [skipped] pause
exit /b 0
