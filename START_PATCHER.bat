:: yk i still hate that batchfile is prolly the most useful thing out there
:: i think this is revision 8 dunno its like friggin 5am
:: one day im going to acutally get a proper sleep scheduele lawl
:: anyway lemme explain u how thisll work
:: the guy at hutch acutally had a full on oflline mode the game didnt even have ads
:: tho it seems like they were thinkn abt it also if u can check the files in the files
:: there are remaining models and acutal logic for the M1 see if you can bind that in
:: anyway so basically the game will on first startup check for servers
:: and the patch will basically rule out that
:: all you need to understand you can void the exsisting server chekup and it works
:: tested on a fold 5 and echo5 by yours truly
:: so you need to make it into a apk (idealy) whichll void that auto
:: have fun sufferin

@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if not errorlevel 1 (
    py -3 forza_customs_adb_patcher.py
    goto done
)

where python >nul 2>nul
if not errorlevel 1 (
    python forza_customs_adb_patcher.py
    goto done
)

echo.
echo Python was not found.
echo Install Python 3 and make sure it is added to PATH.
pause
exit /b 1

:done
if errorlevel 1 pause
exit /b %errorlevel%