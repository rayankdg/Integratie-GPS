# setup.ps1 - eenmalige installatie voor GPS Tracker
# Draai dit een keer na het clonen van de repo.
# Daarna gebruik je gewoon START.bat.

$ErrorActionPreference = "Continue"
$ProjectDir = $PSScriptRoot

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  GPS Tracker - Eerste installatie" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$HasWinGet = [bool](Get-Command winget -ErrorAction SilentlyContinue)

# --- 1. Python ---
Write-Host "[1/6] Python controleren..." -ForegroundColor White

$Python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Python) {
    if ($HasWinGet) {
        Write-Host "  Python niet gevonden, installeren via winget..." -ForegroundColor Yellow
        winget install --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements --silent
        $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("PATH","User")
        $Python = (Get-Command python -ErrorAction SilentlyContinue).Source
    }
}

if (-not $Python) {
    Write-Host "  FOUT: Python niet gevonden." -ForegroundColor Red
    Write-Host "  Download van: https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "  Zet vinkje bij 'Add Python to PATH' tijdens installatie." -ForegroundColor Yellow
    Read-Host "  Druk ENTER om af te sluiten"
    exit 1
}
Write-Host "  OK: $Python" -ForegroundColor Green

# --- 2. Google Chrome ---
Write-Host "[2/6] Google Chrome controleren..." -ForegroundColor White

$Chrome = $null
$chromePaths = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)
foreach ($p in $chromePaths) {
    if (Test-Path $p) { $Chrome = $p; break }
}
if (-not $Chrome) {
    $Chrome = (Get-Command chrome -ErrorAction SilentlyContinue).Source
}

if (-not $Chrome) {
    if ($HasWinGet) {
        Write-Host "  Chrome niet gevonden, installeren via winget..." -ForegroundColor Yellow
        winget install --id Google.Chrome --accept-package-agreements --accept-source-agreements --silent
        foreach ($p in $chromePaths) {
            if (Test-Path $p) { $Chrome = $p; break }
        }
    }
}

if ($Chrome) {
    Write-Host "  OK: Chrome gevonden." -ForegroundColor Green
} else {
    Write-Host "  LET OP: Chrome niet gevonden." -ForegroundColor Yellow
    Write-Host "  Download van: https://www.google.com/chrome/" -ForegroundColor Yellow
}

# --- 3. Mosquitto ---
Write-Host "[3/6] Mosquitto controleren..." -ForegroundColor White

$MosqExe = $null
$mosqPaths = @(
    "$env:ProgramFiles\Mosquitto\mosquitto.exe",
    "C:\Program Files\Mosquitto\mosquitto.exe"
)
foreach ($p in $mosqPaths) {
    if (Test-Path $p) { $MosqExe = $p; break }
}
if (-not $MosqExe) {
    $MosqExe = (Get-Command mosquitto -ErrorAction SilentlyContinue).Source
}

if (-not $MosqExe) {
    if ($HasWinGet) {
        Write-Host "  Mosquitto niet gevonden, installeren via winget..." -ForegroundColor Yellow
        winget install --id EclipseFoundation.Mosquitto --accept-package-agreements --accept-source-agreements --silent
        foreach ($p in $mosqPaths) {
            if (Test-Path $p) { $MosqExe = $p; break }
        }
        if (-not $MosqExe) {
            $MosqExe = (Get-Command mosquitto -ErrorAction SilentlyContinue).Source
        }
    }
}

if (-not $MosqExe) {
    Write-Host "  LET OP: Mosquitto niet gevonden." -ForegroundColor Yellow
    Write-Host "  Download van: https://mosquitto.org/download/" -ForegroundColor Yellow
    $inp = Read-Host "  Pad naar mosquitto.exe (leeg = overslaan)"
    if ($inp -and (Test-Path $inp)) { $MosqExe = $inp }
} else {
    Write-Host "  OK: $MosqExe" -ForegroundColor Green
}

# --- 4. InfluxDB 3 Core ---
Write-Host "[4/6] InfluxDB 3 Core controleren..." -ForegroundColor White

$InfluxExe = $null

# Vaste paden controleren
$influxPaths = @(
    (Join-Path $ProjectDir "influxdb3\influxdb3.exe"),
    (Join-Path (Split-Path $ProjectDir) "influxdb3\influxdb3.exe"),
    "$env:LOCALAPPDATA\influxdb3\influxdb3.exe",
    "$env:ProgramFiles\InfluxData\InfluxDB\influxdb3.exe"
)
foreach ($p in $influxPaths) {
    if ($p -and (Test-Path $p)) { $InfluxExe = $p; break }
}

# Controleer of het op PATH staat
if (-not $InfluxExe) {
    $InfluxExe = (Get-Command influxdb3 -ErrorAction SilentlyContinue).Source
}

# Zoek in Downloads-map (mensen pakken de ZIP daar vaak uit)
if (-not $InfluxExe) {
    Write-Host "  Zoeken in Downloads-map..." -ForegroundColor Cyan
    $found = Get-ChildItem "$env:USERPROFILE\Downloads" -Recurse -Filter "influxdb3.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { $InfluxExe = $found.FullName }
}

# Zoek in de map naast het project (vaak staat alles in dezelfde IoT-map)
if (-not $InfluxExe) {
    $found = Get-ChildItem (Split-Path $ProjectDir) -Recurse -Filter "influxdb3.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { $InfluxExe = $found.FullName }
}

if (-not $InfluxExe) {
    Write-Host "  InfluxDB niet gevonden, automatisch downloaden..." -ForegroundColor Yellow
    $InfluxDir = Join-Path $ProjectDir "influxdb3"
    $zipPath   = Join-Path $env:TEMP "influxdb3.zip"
    $downloaded = $false

    # Probeer 1: influxdata/influxdb3-core repo
    # Probeer 2: influxdata/influxdb repo met v3-tag
    $repoUrls = @(
        "https://api.github.com/repos/influxdata/influxdb3-core/releases/latest",
        "https://api.github.com/repos/influxdata/influxdb3-core/releases?per_page=5"
    )
    foreach ($url in $repoUrls) {
        if ($downloaded) { break }
        try {
            $data = Invoke-RestMethod $url -TimeoutSec 10 -Headers @{ "User-Agent" = "GPS-Tracker-Setup" }
            $releases = if ($data -is [array]) { $data } else { @($data) }
            foreach ($rel in $releases) {
                $asset = $rel.assets | Where-Object {
                    $_.name -match "windows" -and $_.name -match "amd64" -and $_.name -match "\.zip$"
                } | Select-Object -First 1
                if ($asset) {
                    $sizeMB = [math]::Round($asset.size / 1MB, 0)
                    Write-Host "  Downloaden: $($asset.name) ($sizeMB MB)..." -ForegroundColor Cyan
                    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath -TimeoutSec 300
                    $downloaded = $true
                    break
                }
            }
        } catch { }
    }

    # Probeer 3: directe download-URL van influxdata.com
    if (-not $downloaded) {
        try {
            Write-Host "  GitHub mislukt, directe download proberen..." -ForegroundColor Yellow
            $directUrl = "https://dl.influxdata.com/influxdb/releases/influxdb3-core-latest-windows_amd64.zip"
            Invoke-WebRequest -Uri $directUrl -OutFile $zipPath -TimeoutSec 300
            $downloaded = $true
        } catch { }
    }

    if ($downloaded -and (Test-Path $zipPath)) {
        Write-Host "  Uitpakken naar $InfluxDir..." -ForegroundColor Cyan
        if (-not (Test-Path $InfluxDir)) { New-Item -ItemType Directory -Path $InfluxDir | Out-Null }
        Expand-Archive -Path $zipPath -DestinationPath $InfluxDir -Force
        Remove-Item $zipPath -ErrorAction SilentlyContinue
        $found = Get-ChildItem $InfluxDir -Recurse -Filter "influxdb3.exe" | Select-Object -First 1
        if ($found) { $InfluxExe = $found.FullName }
    }
}

if (-not $InfluxExe) {
    Write-Host ""
    Write-Host "  Automatisch downloaden is mislukt." -ForegroundColor Yellow
    Write-Host "  Volg deze stappen om InfluxDB handmatig toe te voegen:" -ForegroundColor White
    Write-Host ""
    Write-Host "    1. Ga naar: https://docs.influxdata.com/influxdb3/core/install/" -ForegroundColor Cyan
    Write-Host "    2. Klik op de dropdown en kies: Windows (AMD64, x86_64) binary" -ForegroundColor Cyan
    Write-Host "    3. Download het .zip bestand" -ForegroundColor Cyan
    Write-Host "    4. Pak het uit naar deze map:" -ForegroundColor Cyan
    Write-Host "       $(Join-Path $ProjectDir 'influxdb3\')" -ForegroundColor Yellow
    Write-Host "    5. Zorg dat influxdb3.exe in die map staat" -ForegroundColor Cyan
    Write-Host ""
    $inp = Read-Host "  Druk ENTER als je klaar bent (of voer het pad naar influxdb3.exe in)"
    if ($inp -and (Test-Path $inp)) {
        $InfluxExe = $inp
    } else {
        $autoFound = Join-Path $ProjectDir "influxdb3\influxdb3.exe"
        if (Test-Path $autoFound) { $InfluxExe = $autoFound }
    }
} else {
    Write-Host "  OK: $InfluxExe" -ForegroundColor Green
}

# --- 5. Python venv + requirements ---
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

# --- 6. Secrets + local.ps1 ---
Write-Host "[6/6] Configuratie opslaan..." -ForegroundColor White

$SecretsH = Join-Path $ProjectDir "secrets.h"
if (-not (Test-Path $SecretsH)) {
    Copy-Item (Join-Path $ProjectDir "secrets.h.example") $SecretsH
    Write-Host "  OK: secrets.h aangemaakt vanuit template." -ForegroundColor Green
} else {
    Write-Host "  OK: secrets.h bestaat al." -ForegroundColor Green
}

$NodeName   = $env:COMPUTERNAME + "-node"
$InfluxData = "$env:USERPROFILE\.influxdb"
$LocalPs1   = Join-Path $ProjectDir "local.ps1"

$localContent = @"
# local.ps1 - gegenereerd door setup.ps1 (staat in .gitignore)
`$PyExe      = "$VenvPy"
`$InfluxExe  = "$InfluxExe"
`$InfluxData = "$InfluxData"
`$InfluxNode = "$NodeName"
`$MosqExe    = "$MosqExe"
"@
$localContent | Out-File -FilePath $LocalPs1 -Encoding utf8
Write-Host "  OK: local.ps1 opgeslagen." -ForegroundColor Green

# --- Klaar ---
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
