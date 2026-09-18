@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "BUILD_ENV=%~dp0.build-venv"
set "PY=%BUILD_ENV%\Scripts\python.exe"

if not exist "%PY%" (
    echo [SAM] Creating build environment...
    py -3.12 -m venv "%BUILD_ENV%" 2>nul
    if errorlevel 1 py -3 -m venv "%BUILD_ENV%"
    if errorlevel 1 goto :python_error
)

echo [SAM] Installing/updating build dependencies...
"%PY%" -m pip install --disable-pip-version-check --upgrade -r requirements.txt pyinstaller pillow
if errorlevel 1 goto :build_error

echo [SAM] Running tests...
"%PY%" -m unittest discover -s tests -v
if errorlevel 1 goto :test_error

echo [SAM] Generating Windows icon...\n"%PY%" tools\\build_icon.py\nif errorlevel 1 goto :build_error\n\necho [SAM] Building Windows app...
if exist build rmdir /s /q build
if exist dist\SAM rmdir /s /q dist\SAM
"%PY%" -m PyInstaller --noconfirm --clean SAM.spec
if errorlevel 1 goto :build_error

if not exist "dist\SAM\SAM.exe" goto :missing_exe

echo.
echo [SAM] Build complete:
echo %CD%\dist\SAM\SAM.exe
echo.
echo You can zip the whole dist\SAM folder for distribution.
pause
exit /b 0

:python_error
echo.
echo [SAM] Python 3 was not found. Install Python 3.12 or newer and enable the py launcher.
pause
exit /b 1

:test_error
echo.
echo [SAM] Tests failed. Build stopped so a broken release is not produced.
pause
exit /b 1

:missing_exe
echo.
echo [SAM] PyInstaller finished but dist\SAM\SAM.exe was not created.
pause
exit /b 1

:build_error
echo.
echo [SAM] Build failed. Run this file again and copy the error shown above if you need help.
pause
exit /b 1
