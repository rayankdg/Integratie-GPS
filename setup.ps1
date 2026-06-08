# setup.ps1 — eenmalige installatie voor GPS Tracker
# =====================================================
# Draai dit één keer na het clonen van de repo.
# Daarna gebruik je gewoon START.bat om alles op te starten.

$ErrorActionPreference = "Continue"
$ProjectDir = $PSScriptRoot

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  GPS Tracker — Eerste installatie" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ─── 1. Python ────────────────────────────────────────────────────────────────
Write-Host "[1/6] Python controleren..." -ForegroundColor White
$Python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Python) {
    Write-Host "  FOUT: Python niet gevonden." -ForegroundColor Red
    Write-Host "  Download van: https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "  Zorg dat 'Add Python to PATH' aangevinkt staat tijdens installatie." -ForegroundColor Yellow
    Read-Host "  Druk ENTER om af te sluiten"
    exit 1
}
Write-Host "  OK: $Python" -ForegroundColor Green

# ─── 2. Venv aanmaken + requirements installeren ──────────────────────────────
Write-Host "[2/6] Virtuele omgeving aanmaken..." -ForegroundColor White
$VenvPy = Join-Path $ProjectDir "venv\Scripts\python.exe"
if (-not (Test-Path $VenvPy)) {
    & $Python -m venv "$ProjectDir\venv"
    if (-not (Test-Path $VenvPy)) {
        Write-Host "  FOUT: venv aanmaken mislukt." -ForegroundColor Red
        Read-Host "  Druk ENTER om af te sluiten"
        exit 1
    }
}
Write-Host "  OK: venv klaar." -ForegroundColor Green

Write-Host "[3/6] Python-pakketten installeren (kan even duren)..." -ForegroundColor White
& $VenvPy -m pip install -r "$ProjectDir\requirements.txt" --quiet
Write-Host "  OK: pakketten geinstalleerd." -ForegroundColor Green

# ─── 3. secrets.h aanmaken ────────────────────────────────────────────────────
Write-Host "[4/6] Configuratiebestand controleren..." -ForegroundColor White
$SecretsH  = Join-Path $ProjectDir "secrets.h"
$SecretsEx = Join-Path $ProjectDir "secrets.h.example"
if (-not (Test-Path $SecretsH)) {
    Copy-Item $SecretsEx $SecretsH
    Write-Host "  OK: secrets.h aangemaakt vanuit template." -ForegroundColor Green
} else {
    Write-Host "  OK: secrets.h bestaat al (ongewijzigd)." -ForegroundColor Green
}

# ─── 4. InfluxDB zoeken ───────────────────────────────────────────────────────
Write-Host "[5/6] InfluxDB zoeken..." -ForegroundColor White
$InfluxExe = $null
$influxSearchPaths = @(
    (Join-Path $ProjectDir "influxdb3\influxdb3.exe"),
    (Join-Path (Split-Path $ProjectDir) "influxdb3\influxdb3.exe"),
    "$env:LOCALAPPDATA\influxdb3\influxdb3.exe",
    "$env:ProgramFiles\InfluxData\InfluxDB\influxdb3.exe",
    "$env:ProgramW6432\InfluxData\InfluxDB\influxdb3.exe"
)
foreach ($p in $influxSearchPaths) {
    if (Test-Path $p) { $InfluxExe = (Resolve-Path $p).Path; break }
}
if (-not $InfluxExe) {
    $found = (Get-Command influxdb3 -ErrorAction SilentlyContinue).Source
    if ($found) { $InfluxExe = $found }
}

if ($InfluxExe) {
    Write-Host "  Gevonden: $InfluxExe" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "  InfluxDB niet automatisch gevonden." -ForegroundColor Yellow
    Write-Host "  Download 'InfluxDB 3 Core' van: https://www.influxdata.com/downloads/" -ForegroundColor Yellow
    Write-Host "  Pak het ZIP-bestand uit en voer het pad naar influxdb3.exe in." -ForegroundColor Yellow
    Write-Host "  (Leeg laten = InfluxDB-opslag overslaan, locatiedata gaat enkel naar JSON)" -ForegroundColor Gray
    Write-Host ""
    $input = Read-Host "  Pad naar influxdb3.exe"
    if ($input -and (Test-Path $input)) {
        $InfluxExe = $input
        Write-Host "  OK: $InfluxExe" -ForegroundColor Green
    } else {
        Write-Host "  Overgeslagen — InfluxDB niet geconfigureerd." -ForegroundColor Yellow
    }
}

# ─── 5. Mosquitto zoeken ──────────────────────────────────────────────────────
Write-Host "[6/6] Mosquitto zoeken..." -ForegroundColor White
$MosqExe = $null
$mosqSearchPaths = @(
    "$env:ProgramFiles\Mosquitto\mosquitto.exe",
    "${env:ProgramFiles(x86)}\Mosquitto\mosquitto.exe",
    "C:\Program Files\Mosquitto\mosquitto.exe"
)
foreach ($p in $mosqSearchPaths) {
    if (Test-Path $p) { $MosqExe = $p; break }
}
if (-not $MosqExe) {
    $found = (Get-Command mosquitto -ErrorAction SilentlyContinue).Source
    if ($found) { $MosqExe = $found }
}

if ($MosqExe) {
    Write-Host "  Gevonden: $MosqExe" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "  Mosquitto niet gevonden." -ForegroundColor Yellow
    Write-Host "  Download van: https://mosquitto.org/download/" -ForegroundColor Yellow
    Write-Host "  Kies de Windows installer (.exe)." -ForegroundColor Yellow
    Write-Host ""
    $input = Read-Host "  Pad naar mosquitto.exe (leeg = overslaan)"
    if ($input -and (Test-Path $input)) {
        $MosqExe = $input
        Write-Host "  OK: $MosqExe" -ForegroundColor Green
    } else {
        Write-Host "  Overgeslagen." -ForegroundColor Yellow
    }
}

# ─── 6. local.ps1 opslaan ─────────────────────────────────────────────────────
$NodeName   = $env:COMPUTERNAME + "-node"
$InfluxData = "$env:USERPROFILE\.influxdb"
$LocalPs1   = Join-Path $ProjectDir "local.ps1"

@"
# local.ps1 — gegenereerd door setup.ps1
# Pas dit bestand NIET aan in Git (staat in .gitignore).
# Draai setup.ps1 opnieuw als je paden zijn gewijzigd.
`$PyExe      = "$VenvPy"
`$InfluxExe  = "$InfluxExe"
`$InfluxData = "$InfluxData"
`$InfluxNode = "$NodeName"
`$MosqExe    = "$MosqExe"
"@ | Out-File -FilePath $LocalPs1 -Encoding utf8

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Installatie klaar!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Nog te doen (eenmalig):" -ForegroundColor White
Write-Host "  1. Open secrets.h en vul in:" -ForegroundColor White
Write-Host "       INFLUX_TOKEN   = jouw InfluxDB API-token" -ForegroundColor Yellow
Write-Host "       ADMIN_PASSWORD = een sterk wachtwoord voor de website" -ForegroundColor Yellow
Write-Host ""
Write-Host "  2. Google-account koppelen:" -ForegroundColor White
Write-Host "       python do_google_login.py" -ForegroundColor Yellow
Write-Host "       python do_shared_key.py" -ForegroundColor Yellow
Write-Host ""
Write-Host "  3. Dubbelklik START.bat om alles op te starten." -ForegroundColor White
Write-Host ""
Read-Host "Druk ENTER om af te sluiten"
