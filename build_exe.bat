@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"
echo ==============================================
echo TextHunter EXE Builder
echo ==============================================

if not exist "venv\Scripts\python.exe" (
    echo [1/5] Creating virtual environment...
    py -3 -m venv venv
    if errorlevel 1 goto :error
) else (
    echo [1/5] Using existing virtual environment...
)

echo [2/5] Activating virtual environment...
call "venv\Scripts\activate.bat"
if errorlevel 1 goto :error

echo [3/5] Installing dependencies and PyInstaller...
python -m pip install --disable-pip-version-check -r requirements.txt pyinstaller
if errorlevel 1 goto :error

echo [4/5] Cleaning old build output...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist TextHunter.spec del /q TextHunter.spec

set ICON_ARG=
if exist "icon.ico" set ICON_ARG=--icon icon.ico

echo [5/5] Building executable...
pyinstaller --noconfirm --clean --onefile --windowed --name "TextHunter" --add-data "sounds;sounds" --add-data "texthunter_config.example.json;." %ICON_ARG% text_hunter.py
if errorlevel 1 goto :error

echo.
echo Build complete!
echo Output: dist\TextHunter.exe
echo.
pause
exit /b 0

:error
echo.
echo Build failed. Check errors above.
echo.
pause
exit /b 1
