# start_all.ps1 - start de volledige GPS-Tracker stack in de juiste volgorde
# ==========================================================================
#   1. InfluxDB 3 Core   (poort 8181)
#   2. Mosquitto broker  (poort 1883 + 9001 websockets)
#   3. MQTT -> InfluxDB bridge
#   4. Website-backend   (uvicorn, poort 8000)
#
# Gebruik:
#   powershell -ExecutionPolicy Bypass -File .\start_all.ps1
#
# Tip: draai als Administrator zodat de Mosquitto-service met websockets
#      herstart kan worden (anders werkt de live kaart in de browser niet).

$ErrorActionPreference = "Stop"

# --- Paden (pas aan indien je iets verplaatst) ---
$ProjectDir = "C:\Users\rayan\Downloads\IoT\GoogleFindMyTools-main\GoogleFindMyTools-main"
# Expliciete Python uit de venv (heeft alle modules: nodriver, paho, influxdb3, ...).
# Zo hangt het niet af van wat er toevallig op PATH staat.
$PyExe      = "C:\Users\rayan\Downloads\IoT\GoogleFindMyTools\venv\Scripts\python.exe"
$InfluxExe  = "C:\Users\rayan\Downloads\IoT\influxdb3-core-3.9.2-windows_amd64\influxdb3.exe"
$InfluxData = "C:\Users\rayan\.influxdb"
$InfluxNode = "LaptopSahbi-node"
$MosqExe    = "C:\Program Files\Mosquitto\mosquitto.exe"
$MosqConf   = Join-Path $ProjectDir "mosquitto.conf"

function Test-Port($port) {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $c.Connect("127.0.0.1", $port)
        $c.Close()
        return $true
    } catch {
        return $false
    }
}

function Wait-Port($port, $name, $timeout = 30) {
    Write-Host ("  wachten tot {0} (poort {1}) luistert..." -f $name, $port) -NoNewline
    for ($i = 0; $i -lt $timeout; $i++) {
        if (Test-Port $port) { Write-Host " OK"; return $true }
        Start-Sleep -Seconds 1
        Write-Host "." -NoNewline
    }
    Write-Host " TIMEOUT"
    return $false
}

function Start-InWindow($title, $command) {
    $inner = "`$host.UI.RawUI.WindowTitle = '$title'; $command"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $inner
}

Write-Host ""
Write-Host "=== GPS Tracker stack starten ===" -ForegroundColor Cyan
Write-Host ""

# --- 1. InfluxDB ---
if (Test-Port 8181) {
    Write-Host "[1/4] InfluxDB draait al op 8181 - overslaan." -ForegroundColor Yellow
} else {
    Write-Host "[1/4] InfluxDB starten..." -ForegroundColor Green
    $cmd = "& '$InfluxExe' serve --node-id $InfluxNode --object-store file --data-dir '$InfluxData' --http-bind '127.0.0.1:8181'"
    Start-InWindow "InfluxDB" $cmd
    Wait-Port 8181 "InfluxDB" | Out-Null
}

# --- 2. Mosquitto (1883 + 9001) ---
if (Test-Port 9001) {
    Write-Host "[2/4] Mosquitto met websockets draait al (9001) - overslaan." -ForegroundColor Yellow
} else {
    $svc = Get-Service mosquitto -ErrorAction SilentlyContinue
    if ($svc -and $svc.Status -eq "Running") {
        try {
            Stop-Service mosquitto -ErrorAction Stop
            Write-Host "[2/4] Mosquitto-service gestopt (om met websockets te herstarten)." -ForegroundColor Green
            Start-Sleep -Seconds 1
        } catch {
            Write-Host "[2/4] LET OP: kon de Mosquitto-service niet stoppen (admin nodig)." -ForegroundColor Red
            Write-Host "      Bridge + InfluxDB werken wel, maar de LIVE KAART (9001) niet." -ForegroundColor Red
            Write-Host "      Draai dit script als Administrator voor de volledige live kaart." -ForegroundColor Red
        }
    }
    if (-not (Test-Port 1883)) {
        Write-Host "[2/4] Mosquitto starten met onze config (1883 + 9001)..." -ForegroundColor Green
        $cmd = "& '$MosqExe' -c '$MosqConf' -v"
        Start-InWindow "Mosquitto" $cmd
        Wait-Port 1883 "Mosquitto" | Out-Null
    } else {
        Write-Host "[2/4] Poort 1883 is bezet (service draait nog) - geen websockets." -ForegroundColor Yellow
    }
}

# --- 3. MQTT -> InfluxDB bridge ---
Write-Host "[3/4] Bridge starten..." -ForegroundColor Green
Start-InWindow "Bridge MQTT-InfluxDB" "Set-Location '$ProjectDir'; & '$PyExe' mqtt_influx_bridge.py"
Start-Sleep -Seconds 2

# --- 4. Website-backend (uvicorn) ---
if (Test-Port 8000) {
    Write-Host "[4/4] Backend draait al op 8000 - overslaan." -ForegroundColor Yellow
} else {
    Write-Host "[4/4] Website-backend (uvicorn) starten..." -ForegroundColor Green
    Start-InWindow "Website uvicorn" "Set-Location '$ProjectDir'; & '$PyExe' -m uvicorn app:app --port 8000 --reload"
    Wait-Port 8000 "uvicorn" | Out-Null
}

Write-Host ""
Write-Host "=== Klaar. Open http://localhost:8000 en klik 'Start tracking'. ===" -ForegroundColor Cyan
Write-Host ""
Start-Process "http://localhost:8000"
