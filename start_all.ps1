# start_all.ps1 - start de volledige GPS-Tracker stack
# Volgorde:
#   1. InfluxDB 3 Core   (poort 8181)
#   2. Mosquitto broker  (poort 1883 + 9001 websockets)
#   3. MQTT -> InfluxDB bridge
#   4. Website-backend   (uvicorn, poort 8000)

$ErrorActionPreference = "Continue"
$ProjectDir = $PSScriptRoot

# Machine-specifieke config laden (aangemaakt door setup.ps1)
$LocalConfig = Join-Path $PSScriptRoot "local.ps1"
if (Test-Path $LocalConfig) {
    . $LocalConfig
} else {
    Write-Host ""
    Write-Host "  Setup is nog niet uitgevoerd." -ForegroundColor Red
    Write-Host "  Dubbelklik eerst op SETUP.bat en doorloop de installatie." -ForegroundColor Yellow
    Write-Host ""
    Read-Host "  Druk ENTER om af te sluiten"
    exit 1
}

# Python: venv eerst, daarna systeem-Python
if (-not $PyExe -or -not (Test-Path $PyExe)) {
    $venvCandidate = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
    if (Test-Path $venvCandidate) {
        $PyExe = $venvCandidate
    } else {
        $PyExe = (Get-Command python -ErrorAction SilentlyContinue).Source
        if (-not $PyExe) {
            Write-Host "Python niet gevonden. Draai SETUP.bat opnieuw." -ForegroundColor Red
            Read-Host "Druk ENTER om af te sluiten"
            exit 1
        }
    }
}

# InfluxDB: zoek op bekende locaties als local.ps1 het pad kwijt is
if (-not $InfluxExe -or -not (Test-Path $InfluxExe)) {
    foreach ($p in @(
        (Join-Path $PSScriptRoot "influxdb3\influxdb3.exe"),
        "$env:LOCALAPPDATA\influxdb3\influxdb3.exe",
        "$env:ProgramFiles\InfluxData\InfluxDB\influxdb3.exe"
    )) {
        if (Test-Path $p) { $InfluxExe = $p; break }
    }
    if (-not $InfluxExe) {
        $InfluxExe = (Get-Command influxdb3 -ErrorAction SilentlyContinue).Source
    }
}

# Mosquitto: zoek op standaard installatiepad
if (-not $MosqExe -or -not (Test-Path $MosqExe)) {
    foreach ($p in @(
        "$env:ProgramFiles\Mosquitto\mosquitto.exe",
        "C:\Program Files\Mosquitto\mosquitto.exe"
    )) {
        if (Test-Path $p) { $MosqExe = $p; break }
    }
}

if (-not $InfluxData)  { $InfluxData  = "$env:USERPROFILE\.influxdb" }
if (-not $InfluxNode)  { $InfluxNode  = "$env:COMPUTERNAME-node" }
if (-not $InfluxToken) { $InfluxToken = "" }
$MosqConf = Join-Path $ProjectDir "mosquitto.conf"

function Test-Port($port) {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $c.Connect("127.0.0.1", $port)
        $c.Close()
        return $true
    } catch { return $false }
}

function Wait-Port($port, $name, $timeout = 30) {
    Write-Host ("  wachten op {0} (poort {1})..." -f $name, $port) -NoNewline
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

# 1. InfluxDB
if (-not $InfluxExe) {
    Write-Host "[1/4] InfluxDB overgeslagen (niet gevonden - draai SETUP.bat)." -ForegroundColor Yellow
} elseif (Test-Port 8181) {
    Write-Host "[1/4] InfluxDB draait al op poort 8181." -ForegroundColor Yellow
} else {
    Write-Host "[1/4] InfluxDB starten..." -ForegroundColor Green
    $cmd = "`$env:INFLUXDB3_OPERATOR_TOKEN='$InfluxToken'; & '$InfluxExe' serve --node-id $InfluxNode --object-store file --data-dir '$InfluxData' --http-bind '127.0.0.1:8181'"
    Start-InWindow "InfluxDB" $cmd
    Wait-Port 8181 "InfluxDB" | Out-Null
}

# 2. Mosquitto
if (-not $MosqExe) {
    Write-Host "[2/4] Mosquitto overgeslagen (niet gevonden - draai SETUP.bat)." -ForegroundColor Yellow
} elseif (Test-Port 9001) {
    Write-Host "[2/4] Mosquitto draait al (poort 9001)." -ForegroundColor Yellow
} else {
    $svc = Get-Service mosquitto -ErrorAction SilentlyContinue
    if ($svc -and $svc.Status -eq "Running") {
        try {
            Stop-Service mosquitto -ErrorAction Stop
            Write-Host "[2/4] Mosquitto-service gestopt om te herstarten met websockets." -ForegroundColor Green
            Start-Sleep -Seconds 1
        } catch {
            Write-Host "[2/4] LET OP: kon Mosquitto-service niet stoppen (admin nodig)." -ForegroundColor Red
        }
    }
    if (-not (Test-Port 1883)) {
        Write-Host "[2/4] Mosquitto starten (poorten 1883 + 9001)..." -ForegroundColor Green
        Start-InWindow "Mosquitto" "& '$MosqExe' -c '$MosqConf' -v"
        Wait-Port 1883 "Mosquitto" | Out-Null
    } else {
        Write-Host "[2/4] Poort 1883 bezet - websockets mogelijk niet actief." -ForegroundColor Yellow
    }
}

# 3. MQTT -> InfluxDB bridge
Write-Host "[3/4] Bridge starten..." -ForegroundColor Green
Start-InWindow "Bridge MQTT-InfluxDB" "Set-Location '$ProjectDir'; & '$PyExe' mqtt_influx_bridge.py"
Start-Sleep -Seconds 2

# 4. Website-backend
if (Test-Port 8000) {
    Write-Host "[4/4] Backend draait al op poort 8000." -ForegroundColor Yellow
} else {
    Write-Host "[4/4] Website-backend starten..." -ForegroundColor Green
    Start-InWindow "Website uvicorn" "Set-Location '$ProjectDir'; & '$PyExe' -m uvicorn app:app --port 8000 --reload"
    Wait-Port 8000 "uvicorn" | Out-Null
}

Write-Host ""
Write-Host "=== Klaar! Open http://localhost:8000 en klik 'Start tracking'. ===" -ForegroundColor Cyan
Write-Host ""
Start-Process "http://localhost:8000"
