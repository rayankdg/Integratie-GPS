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

# ─── Hulpfuncties ─────────────────────────────────────────────────────────────

function Test-WinGet {
    return [bool](Get-Command winget -ErrorAction SilentlyContinue)
}

function Install-ViaWinGet($id, $label) {
    Write-Host "  Installeren via winget: $label..." -ForegroundColor Cyan
    winget install --id $id --accept-package-agreements --accept-source-agreements --silent 2>&1 | Out-Null
    return $LASTEXITCODE -eq 0
}

function Find-Exe($searchPaths, $command) {
    foreach ($p in $searchPaths) {
        if ($p -and (Test-Path $p)) { return $p }
    }
    $found = (Get-Command $command -ErrorAction SilentlyContinue).Source
    return $found
}

# ─── 1. Python ────────────────────────────────────────────────────────────────
Write-Host "[1/6] Python controleren..." -ForegroundColor White

$Python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Python) {
    if (Test-WinGet) {
        Write-Host "  Python niet gevonden, installeren via winget..." -ForegroundColor Yellow
        Install-ViaWinGet "Python.Python.3.12" "Python 3.12" | Out-Null
        # PATH bijwerken na installatie
        $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH","User")
        $Python = (Get-Command python -ErrorAction SilentlyContinue).Source
    }
}

if (-not $Python) {
    Write-Host "  FOUT: Python niet gevonden en kon niet automatisch installeren." -ForegroundColor Red
    Write-Host "  Download handmatig van: https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "  Zet vinkje bij 'Add Python to PATH' tijdens installatie." -ForegroundColor Yellow
    Read-Host "  Druk ENTER om af te sluiten"
    exit 1
}
Write-Host "  OK: $Python" -ForegroundColor Green

# ─── 2. Google Chrome ─────────────────────────────────────────────────────────
Write-Host "[2/6] Google Chrome controleren..." -ForegroundColor White

$chromePaths = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)
$Chrome = Find-Exe $chromePaths "chrome"

if (-not $Chrome) {
    if (Test-WinGet) {
        Write-Host "  Chrome niet gevonden, installeren via winget..." -ForegroundColor Yellow
        Install-ViaWinGet "Google.Chrome" "Google Chrome" | Out-Null
        $Chrome = Find-Exe $chromePaths "chrome"
    }
}

if ($Chrome) {
    Write-Host "  OK: Chrome gevonden." -ForegroundColor Green
} else {
    Write-Host "  LET OP: Chrome niet gevonden." -ForegroundColor Yellow
    Write-Host "  Download van: https://www.google.com/chrome/" -ForegroundColor Yellow
    Write-Host "  Chrome is vereist voor de Google-login." -ForegroundColor Yellow
}

# ─── 3. Mosquitto ─────────────────────────────────────────────────────────────
Write-Host "[3/6] Mosquitto controleren..." -ForegroundColor White

$mosqPaths = @(
    "$env:ProgramFiles\Mosquitto\mosquitto.exe",
    "C:\Program Files\Mosquitto\mosquitto.exe"
)
$MosqExe = Find-Exe $mosqPaths "mosquitto"

if (-not $MosqExe) {
    if (Test-WinGet) {
        Write-Host "  Mosquitto niet gevonden, installeren via winget..." -ForegroundColor Yellow
        Install-ViaWinGet "EclipseFoundation.Mosquitto" "Mosquitto" | Out-Null
        $MosqExe = Find-Exe $mosqPaths "mosquitto"
    }
}

if (-not $MosqExe) {
    Write-Host "  LET OP: Mosquitto niet gevonden na installatie." -ForegroundColor Yellow
    Write-Host "  Download van: https://mosquitto.org/download/" -ForegroundColor Yellow
    $input = Read-Host "  Pad naar mosquitto.exe (leeg = overslaan)"
    if ($input -and (Test-Path $input)) { $MosqExe = $input }
} else {
    Write-Host "  OK: $MosqExe" -ForegroundColor Green
}

# ─── 4. InfluxDB 3 Core ───────────────────────────────────────────────────────
Write-Host "[4/6] InfluxDB 3 Core controleren..." -ForegroundColor White

$influxSearchPaths = @(
    (Join-Path $ProjectDir "influxdb3\influxdb3.exe"),
    (Join-Path (Split-Path $ProjectDir) "influxdb3\influxdb3.exe"),
    "$env:LOCALAPPDATA\influxdb3\influxdb3.exe",
    "$env:ProgramFiles\InfluxData\InfluxDB\influxdb3.exe"
)
$InfluxExe = Find-Exe $influxSearchPaths "influxdb3"

if (-not $InfluxExe) {
    Write-Host "  InfluxDB niet gevonden, automatisch downloaden..." -ForegroundColor Yellow
    $InfluxDir = Join-Path $ProjectDir "influxdb3"

    try {
        Write-Host "  Laatste versie opzoeken via GitHub..." -ForegroundColor Cyan
        $releases = Invoke-RestMethod "https://api.github.com/repos/influxdata/influxdb/releases?per_page=30" -TimeoutSec 15
        $v3 = $releases | Where-Object { $_.tag_name -match "^v3\." -and -not $_.prerelease } | Select-Object -First 1
        $asset = $null
        if ($v3) {
            $asset = $v3.assets | Where-Object { $_.name -match "windows" -and $_.name -match "amd64" -and $_.name -match "\.zip$" } | Select-Object -First 1
        }

        if ($asset) {
            $zipPath = Join-Path $env:TEMP "influxdb3.zip"
            Write-Host ("  Downloaden: {0} ({1:N0} MB)..." -f $asset.name, ($asset.size / 1MB)) -ForegroundColor Cyan
            Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath -TimeoutSec 300
            Write-Host "  Uitpakken naar $InfluxDir..." -ForegroundColor Cyan
            if (-not (Test-Path $InfluxDir)) { New-Item -ItemType Directory -Path $InfluxDir | Out-Null }
            Expand-Archive -Path $zipPath -DestinationPath $InfluxDir -Force
            Remove-Item $zipPath -ErrorAction SilentlyContinue

            # influxdb3.exe kan in een submap zitten na uitpakken
            $found = Get-ChildItem $InfluxDir -Recurse -Filter "influxdb3.exe" | Select-Object -First 1
            if ($found) { $InfluxExe = $found.FullName }
        }
    } catch {
        Write-Host "  Automatisch downloaden mislukt: $_" -ForegroundColor Yellow
    }
}

if (-not $InfluxExe) {
    Write-Host "  LET OP: InfluxDB niet gevonden." -ForegroundColor Yellow
    Write-Host "  Download van: https://www.influxdata.com/downloads/" -ForegroundColor Yellow
    Write-Host "  Kies 'InfluxDB 3 Core' voor Windows." -ForegroundColor Yellow
    $input = Read-Host "  Pad naar influxdb3.exe (leeg = overslaan)"
    if ($input -and (Test-Path $input)) { $InfluxExe = $input }
} else {
    Write-Host "  OK: $InfluxExe" -ForegroundColor Green
}

# ─── 5. Python venv + requirements ────────────────────────────────────────────
Write-Host "[5/6] Virtuele omgeving aanmaken en pakketten installeren..." -ForegroundColor White

$VenvPy = Join-Path $ProjectDir "venv\Scripts\python.exe"
if (-not (Test-Path $VenvPy)) {
    & $Python -m venv "$ProjectDir\venv"
}

if (Test-Path $VenvPy) {
    Write-Host "  Pakketten installeren (dit kan even duren)..." -ForegroundColor Cyan
    & $VenvPy -m pip install -r "$ProjectDir\requirements.txt" --quiet
    Write-Host "  OK: venv en pakketten klaar." -ForegroundColor Green
} else {
    Write-Host "  FOUT: venv aanmaken mislukt." -ForegroundColor Red
}

# ─── 6. Secrets + local.ps1 ───────────────────────────────────────────────────
Write-Host "[6/6] Configuratie opslaan..." -ForegroundColor White

$SecretsH = Join-Path $ProjectDir "secrets.h"
if (-not (Test-Path $SecretsH)) {
    Copy-Item (Join-Path $ProjectDir "secrets.h.example") $SecretsH
    Write-Host "  OK: secrets.h aangemaakt vanuit template." -ForegroundColor Green
} else {
    Write-Host "  OK: secrets.h bestaat al (ongewijzigd)." -ForegroundColor Green
}

$NodeName   = $env:COMPUTERNAME + "-node"
$InfluxData = "$env:USERPROFILE\.influxdb"
$LocalPs1   = Join-Path $ProjectDir "local.ps1"

@"
# local.ps1 — gegenereerd door setup.ps1 (staat in .gitignore)
`$PyExe      = "$VenvPy"
`$InfluxExe  = "$InfluxExe"
`$InfluxData = "$InfluxData"
`$InfluxNode = "$NodeName"
`$MosqExe    = "$MosqExe"
"@ | Out-File -FilePath $LocalPs1 -Encoding utf8

Write-Host "  OK: local.ps1 opgeslagen." -ForegroundColor Green

# ─── Klaar ────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Installatie klaar!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Nog twee stappen (eenmalig):" -ForegroundColor White
Write-Host ""
Write-Host "  1. Open secrets.h en vul in:" -ForegroundColor White
Write-Host "       INFLUX_TOKEN   = jouw InfluxDB API-token" -ForegroundColor Yellow
Write-Host "       ADMIN_PASSWORD = een wachtwoord voor de website" -ForegroundColor Yellow
Write-Host ""
Write-Host "  2. Koppel je Google-account:" -ForegroundColor White
Write-Host "       python do_google_login.py" -ForegroundColor Yellow
Write-Host "       python do_shared_key.py" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Daarna: dubbelklik START.bat" -ForegroundColor Green
Write-Host ""
Read-Host "Druk ENTER om af te sluiten"
