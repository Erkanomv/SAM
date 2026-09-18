@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem Fast path: reuse an already-working environment. This avoids recreating a
rem venv every time a new tracker zip is extracted.
set "PYCON="
set "PYWIN="

call :try_runtime "%~dp0.venv"
if defined PYCON goto :launch

call :try_runtime "%LOCALAPPDATA%\SteamTracker\runtime"
if defined PYCON goto :launch

rem Reuse the environment from an older side-by-side release when possible.
for /d %%D in ("%~dp0..\steam_account_tracker_v*") do (
    call :try_runtime "%%~fD\.venv"
    if defined PYCON goto :launch
)

rem First run only. Keep this runtime outside the extracted app folder so future
rem versions launch immediately without reinstalling the same dependencies.
set "RUNTIME=%LOCALAPPDATA%\SteamTracker\runtime"
if not exist "%RUNTIME%\Scripts\python.exe" (
    echo First launch setup - creating the shared Steam Tracker runtime...
    py -3 -m venv "%RUNTIME%" || goto :error
)

set "PYCON=%RUNTIME%\Scripts\python.exe"
set "PYWIN=%RUNTIME%\Scripts\pythonw.exe"

set "NEED_INSTALL="
if not exist "%RUNTIME%\Lib\site-packages\webview\__init__.py" set "NEED_INSTALL=1"
if not exist "%RUNTIME%\Lib\site-packages\httpx\__init__.py" set "NEED_INSTALL=1"
if not exist "%RUNTIME%\Lib\site-packages\keyring\__init__.py" set "NEED_INSTALL=1"
if not exist "%RUNTIME%\Lib\site-packages\psutil\__init__.py" set "NEED_INSTALL=1"
if not exist "%RUNTIME%\Lib\site-packages\pyperclip\__init__.py" set "NEED_INSTALL=1"
if defined NEED_INSTALL (
    echo First launch setup - installing dependencies...
    "%PYCON%" -m pip install --disable-pip-version-check --no-input -r "%~dp0requirements.txt" || goto :error
)

goto :launch

:try_runtime
if defined PYCON exit /b 0
if not exist "%~1\Scripts\python.exe" exit /b 0
if not exist "%~1\Lib\site-packages\webview\__init__.py" exit /b 0
if not exist "%~1\Lib\site-packages\httpx\__init__.py" exit /b 0
if not exist "%~1\Lib\site-packages\keyring\__init__.py" exit /b 0
if not exist "%~1\Lib\site-packages\psutil\__init__.py" exit /b 0
if not exist "%~1\Lib\site-packages\pyperclip\__init__.py" exit /b 0
set "PYCON=%~1\Scripts\python.exe"
if exist "%~1\Scripts\pythonw.exe" (
    set "PYWIN=%~1\Scripts\pythonw.exe"
) else (
    set "PYWIN=%~1\Scripts\python.exe"
)
exit /b 0

:launch
if /I "%~1"=="--debug" (
    echo Starting Steam Tracker in debug-console mode...
    "%PYCON%" "%~dp0app.py"
    set "CODE=%ERRORLEVEL%"
    if not "%CODE%"=="0" pause
    exit /b %CODE%
)

rem Normal launch is detached and console-free. The .bat window should disappear
rem almost immediately once the runtime exists.
start "" "%PYWIN%" "%~dp0app.py"
exit /b 0

:error
echo.
echo Steam Tracker setup failed. Check Python and your internet connection.
pause
exit /b 1
