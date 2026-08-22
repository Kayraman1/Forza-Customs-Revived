@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 goto use_python
py -3 forza_customs_adb_patcher.py
goto finished

:use_python
python forza_customs_adb_patcher.py

:finished
if errorlevel 1 pause
