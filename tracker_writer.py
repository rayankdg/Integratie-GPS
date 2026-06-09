"""
tracker_writer.py — GPS Puck Tracker
=====================================
Start dit script om pucks te volgen of nieuwe toe te voegen.

Menu bij opstarten:
  1. Start tracking (alle bekende pucks)
  2. Voeg een nieuwe puck toe
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import threading
from datetime import datetime, timezone
from pathlib import Path

# Onderdrukt print-output van tracking threads tijdens menu-interactie
_menu_active = threading.Event()
_menu_active.clear()  # False = tracking mag printen

def _tprint(*args, **kwargs):
    """Print alleen als er geen menu actief is."""
    if not _menu_active.is_set():
        print(*args, **kwargs)

# ─── Paden ────────────────────────────────────────────────────────────────────
PROJECT_DIR = Path(__file__).parent

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

LATEST_FILE   = DATA_DIR / "latest.json"
LATEST_ALL    = DATA_DIR / "latest_all.json"
HISTORY_FILE  = DATA_DIR / "history.jsonl"
DEVICES_FILE  = DATA_DIR / "devices.json"

POLL_INTERVAL = 30  # seconden

# ─── Regex ────────────────────────────────────────────────────────────────────
# Format: "1. Honor Magic V5: 6928dc79-0000-27db-8cf9-089e0825f0e8"
DEVICE_LINE_RE = re.compile(
    r"^\s*(\d+)\.\s+(.+?):\s+([\w-]{8,})\s*$",
    re.MULTILINE
)

LAT_RE    = re.compile(r"Latitude:\s*([+-]?\d+(?:\.\d+)?)")
LON_RE    = re.compile(r"Longitude:\s*([+-]?\d+(?:\.\d+)?)")
ALT_RE    = re.compile(r"Altitude:\s*([+-]?\d+(?:\.\d+)?)")
TIME_RE   = re.compile(r"Time:\s*(.+)")
STATUS_RE = re.compile(r"Status:\s*([+-]?\d+)")
OWN_RE    = re.compile(r"Is Own Report:\s*(True|False)", re.IGNORECASE)
BAT_RE    = re.compile(r"Battery:\s*(\d+)")


# ─── Devices ──────────────────────────────────────────────────────────────────

def load_devices() -> list[dict]:
    if DEVICES_FILE.exists():
        return json.loads(DEVICES_FILE.read_text(encoding="utf-8"))
    return []


def save_devices(devices: list[dict]) -> None:
    DEVICES_FILE.write_text(json.dumps(devices, indent=2, ensure_ascii=False), encoding="utf-8")


# ─── GoogleFindMyTools aanroepen ──────────────────────────────────────────────

def run_main_py(stdin_input: str, timeout: int = 300) -> str:
    result = subprocess.run(
        [sys.executable, "main.py"],
        input=stdin_input,
        text=True,
        capture_output=True,
        cwd=PROJECT_DIR,
        timeout=timeout,
    )
    return (result.stdout or "") + "\n" + (result.stderr or "")


def list_available_pucks() -> list[dict]:
    """
    Haalt de lijst van beschikbare pucks op uit GoogleFindMyTools.
    Verwacht formaat: "1. Naam: uuid"
    """
    print("  Bezig met ophalen van pucklijst van Google Find My…")
    try:
        # Stuur een lege enter zodat het menu getoond wordt en daarna afsluit
        output = run_main_py("\n", timeout=120)
    except Exception as e:
        print(f"  Fout: {e}")
        return []

    found = []
    for match in DEVICE_LINE_RE.finditer(output):
        idx     = match.group(1).strip()
        name    = match.group(2).strip()
        dev_id  = match.group(3).strip()
        found.append({"index": idx, "name": name, "device_id": dev_id})

    return found


# ─── Locatie ophalen & opslaan ────────────────────────────────────────────────

def parse_location_output(text: str, device: dict) -> dict:
    lat    = LAT_RE.search(text)
    lon    = LON_RE.search(text)
    alt    = ALT_RE.search(text)
    ts     = TIME_RE.search(text)
    status = STATUS_RE.search(text)
    own    = OWN_RE.search(text)
    bat    = BAT_RE.search(text)

    if "No locations found." in text:
        raise RuntimeError("GEEN_LOCATIE: tracker tijdelijk niet zichtbaar in het Google Find My-netwerk.")

    if not lat or not lon or not ts:
        raise RuntimeError(f"Locatiedata niet gevonden in output:\n{text[:500]}")

    return {
        "device_id":  device["device_id"],
        "name":       device.get("name", device["device_id"]),
        "latitude":   float(lat.group(1)),
        "longitude":  float(lon.group(1)),
        "altitude":   float(alt.group(1)) if alt else None,
        "timestamp":  ts.group(1).strip(),
        "status":     int(status.group(1)) if status else None,
        "own_report": own.group(1).lower() == "true" if own else None,
        "battery":    int(bat.group(1)) if bat else None,
    }


def fetch_location_for(device: dict) -> dict:
    output = run_main_py(f"{device['index']}\n")
    return parse_location_output(output, device)


def save_payload(payload: dict) -> None:
    """Altijd opslaan — ook als locatie niet veranderd is."""
    p = dict(payload)
    p["received"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # Enkelvoudig latest (achterwaarts compatibel)
    LATEST_FILE.write_text(json.dumps(p, indent=2, ensure_ascii=False), encoding="utf-8")

    # Per-puck latest_all
    all_latest: dict = {}
    if LATEST_ALL.exists():
        try:
            all_latest = json.loads(LATEST_ALL.read_text(encoding="utf-8"))
        except Exception:
            pass
    all_latest[p["device_id"]] = p
    LATEST_ALL.write_text(json.dumps(all_latest, indent=2, ensure_ascii=False), encoding="utf-8")

    # Geschiedenis
    with HISTORY_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(p, ensure_ascii=False) + "\n")

    # MQTT publiceren (best-effort; faalt stil als er geen broker is)
    try:
        from mqtt_publisher import publish_location
        publish_location(p)
    except Exception:
        pass


# ─── Tracking thread per puck ─────────────────────────────────────────────────

def track_device(device: dict) -> None:
    name = device.get("name", device["device_id"])
    _tprint(f"  ▶ [{name}] tracking gestart")

    while True:
        try:
            payload = fetch_location_for(device)
            save_payload(payload)
            lat = payload.get("latitude")
            lon = payload.get("longitude")
            ts  = payload.get("timestamp", "?")
            _tprint(f"  ✓ [{name}] {ts}  {lat}, {lon}")
        except Exception as e:
            _tprint(f"  ✗ [{name}] Fout: {e}")

        time.sleep(POLL_INTERVAL)


# ─── Puck toevoegen ───────────────────────────────────────────────────────────

def add_puck_wizard() -> None:
    _menu_active.set()
    print("""
╔══════════════════════════════════════════════════════╗
║         Nieuwe GPS-puck toevoegen — Stappenplan      ║
╚══════════════════════════════════════════════════════╝

Stap 1 — Zet de puck aan
  Houd de knop 3 seconden ingedrukt tot de led knippert.

Stap 2 — Voeg toe aan Google Find My
  Open de Google Find My app (Android) of findmy.google.com
  en voeg het apparaat toe aan hetzelfde Google-account.
  Wacht tot het apparaat 'Online' toont (±1-2 min).

Stap 3 — We halen de lijst op…
""")
    input("  Druk ENTER als de puck zichtbaar is in Google Find My…")

    pucks = list_available_pucks()

    if not pucks:
        print("""
  ✗ Geen pucks gevonden. Controleer:
    - Is Chrome ingelogd op het juiste Google-account?
    - Staat PROJECT_DIR correct in dit script?
    - Draai eerst chrome_driver.py als authenticatie faalt.
""")
        _menu_active.clear()
        return

    print("\n  Gevonden apparaten in Google Find My:")
    bestaande_ids = {d["device_id"] for d in load_devices()}
    for p in pucks:
        status = "  (al toegevoegd)" if p["device_id"] in bestaande_ids else "  ← nieuw"
        print(f"    {p['index']}. {p['name']}  ({p['device_id']}){status}")

    print()
    keuze = input("  Welk nummer wil je toevoegen? (ENTER = alle nieuwe) ").strip()

    nieuwe = []
    if keuze == "":
        nieuwe = [p for p in pucks if p["device_id"] not in bestaande_ids]
    else:
        gevonden = next((p for p in pucks if p["index"] == keuze), None)
        if not gevonden:
            print(f"  ✗ Nummer {keuze} niet gevonden.")
            return
        if gevonden["device_id"] in bestaande_ids:
            print(f"  ℹ {gevonden['name']} is al toegevoegd.")
            return
        nieuwe = [gevonden]

    if not nieuwe:
        print("  ℹ Geen nieuwe pucks gevonden om toe te voegen.")
        _menu_active.clear()
        return

    devices = load_devices()
    for p in nieuwe:
        devices.append(p)
        print(f"  ✓ Toegevoegd: {p['name']}  ({p['device_id']})")
    save_devices(devices)
    print(f"\n  {len(nieuwe)} puck(s) opgeslagen. Start opnieuw met optie 1 om te tracken.\n")
    _menu_active.clear()


# ─── Hoofdmenu ────────────────────────────────────────────────────────────────

def remove_puck_menu() -> None:
    _menu_active.set()
    devices = load_devices()
    if not devices:
        print("\n  Geen pucks om te verwijderen.\n")
        _menu_active.clear()
        return

    print("\n  Welke puck wil je verwijderen?\n")
    for i, d in enumerate(devices, 1):
        print(f"    {i}. {d['name']}  ({d['device_id']})")
    print("    0. Annuleren")
    print()

    keuze = input("  Nummer: ").strip()
    if keuze == "0" or keuze == "":
        _menu_active.clear()
        return

    try:
        idx = int(keuze) - 1
        if idx < 0 or idx >= len(devices):
            print("  ✗ Ongeldig nummer.")
            return
    except ValueError:
        print("  ✗ Ongeldig nummer.")
        return

    target = devices[idx]
    bevestig = input(f"  Verwijder '{target['name']}' ({target['device_id']})? (j/n): ").strip().lower()
    if bevestig != "j":
        print("  Geannuleerd.")
        _menu_active.clear()
        return

    devices.pop(idx)
    save_devices(devices)
    print(f"  ✓ {target['name']} verwijderd uit devices.json.\n")
    _menu_active.clear()


def main() -> None:
    while True:
        print("""
╔══════════════════════════════════════════════════════╗
║              GPS Puck Tracker — Hoofdmenu            ║
╚══════════════════════════════════════════════════════╝""")

        devices = load_devices()
        if devices:
            print(f"  Bekende pucks ({len(devices)}):")
            for d in devices:
                print(f"    • {d['name']}  ({d['device_id']})")
        else:
            print("  Geen pucks geconfigureerd.")

        print("""
  1.  Start tracking
  2.  Voeg een nieuwe puck toe / ververs lijst
  3.  Verwijder een puck
  0.  Afsluiten
""")
        keuze = input("  Keuze: ").strip()

        if keuze == "1":
            if not devices:
                print("\n  ✗ Geen pucks in devices.json. Gebruik optie 2 eerst.\n")
            else:
                start_tracking(devices)
        elif keuze == "2":
            add_puck_wizard()
        elif keuze == "3":
            remove_puck_menu()
        elif keuze == "0":
            print("  Tot ziens!")
            sys.exit(0)
        else:
            print("  ✗ Ongeldige keuze.\n")


def start_tracking(devices: list[dict]) -> None:
    print(f"\n  Tracking gestart voor {len(devices)} puck(s). Interval: {POLL_INTERVAL}s.")
    print("  Druk Ctrl+C om te stoppen.\n")

    threads = []
    for device in devices:
        t = threading.Thread(target=track_device, args=(device,), daemon=True)
        t.start()
        threads.append(t)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n  Tracking gestopt. Terug naar menu…")


if __name__ == "__main__":
    main()