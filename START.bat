@echo off
REM START.bat - start de GPS Tracker stack.
REM Eerste keer? Dubbelklik dan eerst op SETUP.bat.

powershell -ExecutionPolicy Bypass -File "%~dp0start_all.ps1"
pause
