@echo off
setlocal
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv || goto :error
)
call .venv\Scripts\activate.bat
pip install -r requirements.txt pyinstaller || goto :error
pyinstaller --noconfirm --clean --windowed --name SteamAccountTracker ^
  --collect-all keyring ^
  --collect-all webview ^
  --add-data "steam_tracker\web;steam_tracker\web" ^
  app.py || goto :error

echo.
echo Built: dist\SteamAccountTracker\SteamAccountTracker.exe
pause
goto :eof

:error
echo Build failed.
pause
exit /b 1
