@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\SteamTracker\runtime\Scripts\python.exe" set "PY=%LOCALAPPDATA%\SteamTracker\runtime\Scripts\python.exe"

if not defined PY (
    echo Creating build environment...
    py -3 -m venv .venv || goto :error
    set "PY=.venv\Scripts\python.exe"
)

echo Installing/updating build requirements...
"%PY%" -m pip install --disable-pip-version-check -r requirements.txt pyinstaller || goto :error

echo.
echo Running tests...
"%PY%" -m unittest discover -s tests -v || goto :error

echo.
echo Building SAM...
"%PY%" -m PyInstaller --noconfirm --clean SAM.spec || goto :error

if not exist "dist\SAM\SAM.exe" goto :missing

echo.
echo Build complete:
echo   %CD%\dist\SAM\SAM.exe
echo.
pause
exit /b 0

:missing
echo.
echo Build finished without producing dist\SAM\SAM.exe
pause
exit /b 1

:error
echo.
echo Build failed. See the error above.
pause
exit /b 1
