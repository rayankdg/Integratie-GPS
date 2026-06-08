# stop_all.ps1 - stopt de volledige GPS-Tracker stack (reset bij wijzigingen).
# ===========================================================================
# Gebruik:
#   powershell -ExecutionPolicy Bypass -File .\stop_all.ps1
#
# Opties:
#   -ResetData         wist ook de locatiedata (latest/latest_all/history),
#                      maar behoudt je pucks (devices.json).
#   -RestartService    herstart daarna de standaard Mosquitto-service (1883).
#
# Voorbeeld - alles stoppen en locatiedata wissen:
#   powershell -ExecutionPolicy Bypass -File .\stop_all.ps1 -ResetData

param(
    [switch]$ResetData,
    [switch]$RestartService
)

$ProjectDir = "C:\Users\rayan\Downloads\IoT\GoogleFindMyTools-main\GoogleFindMyTools-main"

function Stop-ByCmd($procName, $match) {
    $procs = Get-CimInstance Win32_Process -Filter "Name='$procName'" |
             Where-Object { $_.CommandLine -like "*$match*" }
    foreach ($p in $procs) {
        Write-Host ("  stop {0} (PID {1}) - {2}" -f $procName, $p.ProcessId, $match) -ForegroundColor Green
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

Write-Host ""
Write-Host "=== GPS Tracker stack stoppen ===" -ForegroundColor Cyan
Write-Host ""

# 1. Website (uvicorn) - meestal 2 processen door --reload
Stop-ByCmd "python.exe" "uvicorn"
Stop-ByCmd "python.exe" "app:app"
Stop-ByCmd "uvicorn.exe" "app:app"
# Wat er ook op poort 8000 luistert hard afsluiten (robuust tegen vastzittende processen)
$lines = netstat -ano | Select-String ":8000\s.*LISTENING"
foreach ($l in $lines) {
    $procid = ($l -split '\s+')[-1]
    Write-Host ("  stop poort-8000 proces PID {0}" -f $procid) -ForegroundColor Green
    taskkill /PID $procid /F /T 2>&1 | Out-Null
}

# 2. Bridge
Stop-ByCmd "python.exe" "mqtt_influx_bridge"

# 3. Terminal-tracker (indien gebruikt)
Stop-ByCmd "python.exe" "tracker_writer"

# 4. Onze Mosquitto-instantie (de Windows-service kan enkel met admin gestopt worden)
$mq = Get-Process mosquitto -ErrorAction SilentlyContinue
if ($mq) {
    foreach ($m in $mq) {
        Write-Host ("  stop mosquitto (PID {0})" -f $m.Id) -ForegroundColor Green
        Stop-Process -Id $m.Id -Force -ErrorAction SilentlyContinue
    }
} else {
    Write-Host "  geen losse mosquitto-instantie" -ForegroundColor DarkGray
}

# 5. InfluxDB
$ix = Get-Process influxdb3 -ErrorAction SilentlyContinue
if ($ix) {
    foreach ($i in $ix) {
        Write-Host ("  stop influxdb3 (PID {0})" -f $i.Id) -ForegroundColor Green
        Stop-Process -Id $i.Id -Force -ErrorAction SilentlyContinue
    }
} else {
    Write-Host "  influxdb3 draaide niet" -ForegroundColor DarkGray
}

# 6. (optioneel) locatiedata wissen
if ($ResetData) {
    Write-Host ""
    Write-Host "  Locatiedata wissen (pucks blijven behouden)..." -ForegroundColor Yellow
    $data = Join-Path $ProjectDir "data"
    foreach ($f in "latest.json", "latest_all.json", "history.jsonl") {
        $path = Join-Path $data $f
        if (Test-Path $path) {
            Remove-Item $path -Force
            Write-Host ("    verwijderd: {0}" -f $f) -ForegroundColor Green
        }
    }
}

# 7. (optioneel) standaard Mosquitto-service herstarten
if ($RestartService) {
    try {
        Start-Service mosquitto -ErrorAction Stop
        Write-Host "  Mosquitto-service (1883) herstart." -ForegroundColor Green
    } catch {
        Write-Host "  Kon Mosquitto-service niet herstarten (admin nodig)." -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "=== Gestopt. Start opnieuw met START.bat of start_all.ps1 ===" -ForegroundColor Cyan
Write-Host ""
