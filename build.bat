@echo off
REM Builds LAN-Share.exe (single file, no Python needed to run it).
REM Output: release\LAN-Share.exe
cd /d "%~dp0"
pip install -r requirements.txt pyinstaller || exit /b 1
pyinstaller --noconfirm --onefile --console --name LAN-Share ^
  --add-data "%~dp0templates;templates" ^
  --add-data "%~dp0static\style.css;static" ^
  --add-data "%~dp0static\script.js;static" ^
  --distpath release --workpath build --specpath build ^
  server.py || exit /b 1
echo.
echo Built release\LAN-Share.exe
