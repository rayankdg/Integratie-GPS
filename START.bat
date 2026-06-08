@echo off
REM START.bat - start de hele GPS-Tracker stack als GEWONE gebruiker.
REM
REM BELANGRIJK: dit draait bewust NIET als administrator. De Google-login
REM opent een Chrome via nodriver, en dat werkt niet vanuit een admin-proces
REM ("Failed to connect to browser"). Daarom geen self-elevation meer.
REM
REM Eenmalig vooraf (in een ADMIN-terminal) de Mosquitto-service uitschakelen,
REM zodat poort 1883 vrij is zonder admin:
REM     Stop-Service mosquitto
REM     Set-Service mosquitto -StartupType Disabled

powershell -ExecutionPolicy Bypass -File "%~dp0start_all.ps1"
echo.
echo (Dit venster mag je sluiten - de services draaien in hun eigen vensters.)
pause
