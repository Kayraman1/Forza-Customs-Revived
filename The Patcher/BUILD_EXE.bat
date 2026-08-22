@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 goto no_python_launcher

py -3 -m PyInstaller --version >nul 2>nul
if errorlevel 1 goto no_pyinstaller

py -3 -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name ForzaCustomsADBPatcher forza_customs_adb_patcher.py
if errorlevel 1 goto build_failed

echo.
echo Built: dist\ForzaCustomsADBPatcher.exe
pause
exit /b 0

:no_python_launcher
echo Python's py launcher was not found. Install Python 3 from python.org.
pause
exit /b 1

:no_pyinstaller
echo PyInstaller is not installed.
echo Install it with: py -3 -m pip install pyinstaller
pause
exit /b 1

:build_failed
echo The EXE build failed. Review the output above.
pause
exit /b 1
