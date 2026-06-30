@echo off
cd /d "D:\Desktop\bio_test\backend"
set "PROJECT_ROOT=D:\Desktop\bio_test"
set "BACKEND_ROOT=D:\Desktop\bio_test\backend"
set "UPLOAD_DIR=D:\Desktop\bio_test\backend\uploads"
set "GENERATED_DIR=D:\Desktop\bio_test\backend\generated"
set "R_LIBS_USER=D:\Desktop\bio_test\env\r_libs"
set "RSCRIPT_CMD=C:\Program Files\R\R-4.5.2\bin\x64\Rscript.exe"
set "RSCRIPT_PATH=C:\Program Files\R\R-4.5.2\bin\x64\Rscript.exe"
set "PYTHONIOENCODING=utf-8"
set "PATH=C:\Program Files\R\R-4.5.2\bin\x64\;%PATH%"
echo PROJECT_ROOT=%PROJECT_ROOT%
echo BACKEND_ROOT=%BACKEND_ROOT%
echo UPLOAD_DIR=%UPLOAD_DIR%
echo GENERATED_DIR=%GENERATED_DIR%
echo R_LIBS_USER=%R_LIBS_USER%
echo RSCRIPT_PATH=%RSCRIPT_PATH%
"D:\Desktop\bio_test\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > "D:\Desktop\bio_test\logs\backend.log" 2>&1
