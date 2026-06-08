@echo off
REM START.bat — start de GPS Tracker stack.
REM Draai SETUP.bat eerst als je dit project net gecloned hebt.

if not exist "%~dp0local.ps1" (
    echo.
    echo  Setup nog niet uitgevoerd. Setup wordt nu automatisch gestart...
    echo.
    powershell -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
)

powershell -ExecutionPolicy Bypass -File "%~dp0start_all.ps1"
echo.
echo (Dit venster mag je sluiten - de services draaien in hun eigen vensters.)
pause
