@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 exit /b 1

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Create .venv and install the development dependencies first.
    goto failed
)

".venv\Scripts\python.exe" -c "import platform, struct, sys; sys.exit(0 if sys.platform == 'win32' and platform.machine().upper() == 'AMD64' and struct.calcsize('P') == 8 else 1)"
if errorlevel 1 (
    echo ERROR: Building this package requires Windows and x64 Python.
    goto failed
)

".venv\Scripts\python.exe" -m PyInstaller --version
if errorlevel 1 (
    echo ERROR: Install the development dependencies in .venv first.
    goto failed
)

".venv\Scripts\python.exe" -m PyInstaller ^
    --noconfirm --onedir --console --noupx ^
    --name st-character-card-translate ^
    --paths "%~dp0src" ^
    --add-data "%~dp0src\st_character_card_translate\config.default.toml:st_character_card_translate" ^
    --specpath "%~dp0build\portable" ^
    --workpath "%~dp0build\portable" ^
    --distpath "%~dp0dist" ^
    "%~dp0portable_entry.py"
if errorlevel 1 goto failed

copy /y "src\st_character_card_translate\config.default.toml" "dist\st-character-card-translate\config.toml" >nul
if errorlevel 1 goto failed
copy /y "README.md" "dist\st-character-card-translate\README.md" >nul
if errorlevel 1 goto failed
copy /y "README.en.md" "dist\st-character-card-translate\README.en.md" >nul
if errorlevel 1 goto failed

".venv\Scripts\python.exe" -c "import shutil; shutil.make_archive('dist/st-character-card-translate-windows-x64', 'zip', 'dist', 'st-character-card-translate')"
if errorlevel 1 goto failed

echo.
echo Created: "%~dp0dist\st-character-card-translate-windows-x64.zip"
popd
if not defined CI pause
exit /b 0

:failed
echo.
echo Build failed. See the error above and the build instructions in README.md.
popd
if not defined CI pause
exit /b 1
