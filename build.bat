@echo off
setlocal enabledelayedexpansion
set ROOT=%~dp0

echo ================================
echo   DitingVeritas - Build Release
echo ================================
echo.

echo [1/2] Build backend EXE...
cd /d "%ROOT%backend"
if exist ".venv\Scripts\activate.bat" call .venv\Scripts\activate.bat
pyinstaller --onefile --console --name diting-backend main.py ^
    --distpath dist --workpath build\pyinstaller --specpath build\pyinstaller -y ^
    --exclude-module datasets ^
    --exclude-module torchvision ^
    --exclude-module gradio ^
    --exclude-module onnxruntime ^
    --collect-submodules faster_whisper ^
    --collect-submodules ctranslate2 ^
    --collect-submodules silero_vad ^
    --collect-data silero_vad
if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller failed
    pause
    exit /b 1
)
echo       -> backend\dist\diting-backend.exe

echo.
echo [2/2] Build frontend + pack...
cd /d "%ROOT%frontend"
if not exist "node_modules\" call npm install
call npm run electron:build
if %errorlevel% neq 0 (
    echo [ERROR] Electron build failed
    pause
    exit /b 1
)

echo.
echo ================================
echo   Build complete!
echo   Release: frontend\release\
echo ================================
cd /d "%ROOT%"
pause
