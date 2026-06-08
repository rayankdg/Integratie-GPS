from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from pydantic import BaseModel, Field
import json
import threading
import requests

from tracking_service import tracking_service
from auth_service import auth_service
import admin_auth
from google_findmy_bridge import discover_devices

app = FastAPI()


def require_admin(authorization: str | None = Header(default=None)) -> bool:
    """Dependency die wijzig-endpoints beschermt: vereist een geldig admin-token."""
    token = admin_auth.token_from_header(authorization)
    if not admin_auth.validate(token):
        raise HTTPException(status_code=401, detail="Admin-login vereist")
    return True

# CORS voor Live Server / frontend hosting
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent
HTML_FILE = BASE_DIR / "webapp" / "gps_tracker_webapp.html"
DATA_DIR = BASE_DIR / "data"
LATEST_FILE = DATA_DIR / "latest.json"
HISTORY_FILE = DATA_DIR / "history.jsonl"
DEVICES_FILE = DATA_DIR / "devices.json"
LATEST_ALL_FILE = DATA_DIR / "latest_all.json"
GEOCODE_CACHE_FILE = DATA_DIR / "geocode_cache.json"

_geo_lock = threading.Lock()
_geo_cache: dict | None = None


class DeviceIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    device_id: str = Field(min_length=3, max_length=200)
    index: str | None = Field(default=None, max_length=10)
    category: str | None = Field(default=None, max_length=60)


class AdminLogin(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class TokenIn(BaseModel):
    oauth_token: str = Field(min_length=10, max_length=8000)


def _read_json_file(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json_file(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_devices() -> list[dict]:
    data = _read_json_file(DEVICES_FILE, [])
    return data if isinstance(data, list) else []


def save_devices(devices: list[dict]) -> None:
    _write_json_file(DEVICES_FILE, devices)


def upsert_device(new_device: dict) -> tuple[list[dict], bool]:
    devices = load_devices()
    for i, device in enumerate(devices):
        if device.get("device_id") == new_device["device_id"]:
            devices[i] = new_device
            save_devices(devices)
            return devices, False
    devices.append(new_device)
    save_devices(devices)
    return devices, True


def delete_device(device_id: str) -> bool:
    devices = load_devices()
    filtered = [d for d in devices if d.get("device_id") != device_id]
    if len(filtered) == len(devices):
        return False
    save_devices(filtered)
    return True


def purge_device_data(device_id: str) -> dict:
    """Verwijder alle locatiedata van een puck uit latest/latest_all/history.

    Maakt de puck 'echt volledig weg': niet enkel uit devices.json, maar ook
    de laatste positie en de volledige geschiedenis.
    """
    removed = {"latest_all": False, "latest": False, "history": 0}

    # latest_all.json — verwijder de sleutel voor deze puck
    all_latest = _read_json_file(LATEST_ALL_FILE, {})
    if isinstance(all_latest, dict) and device_id in all_latest:
        all_latest.pop(device_id, None)
        _write_json_file(LATEST_ALL_FILE, all_latest)
        removed["latest_all"] = True

    # latest.json — wis als dit bestand net deze puck beschrijft
    latest = _read_json_file(LATEST_FILE, None)
    if isinstance(latest, dict) and latest.get("device_id") == device_id:
        if LATEST_FILE.exists():
            LATEST_FILE.unlink()
        removed["latest"] = True

    # history.jsonl — herschrijf zonder de regels van deze puck
    if HISTORY_FILE.exists():
        kept = []
        dropped = 0
        for line in HISTORY_FILE.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                kept.append(line)
                continue
            if row.get("device_id") == device_id:
                dropped += 1
            else:
                kept.append(line)
        if dropped:
            HISTORY_FILE.write_text(
                ("\n".join(kept) + "\n") if kept else "", encoding="utf-8"
            )
        removed["history"] = dropped

    return removed


@app.get("/", response_class=HTMLResponse)
def home():
    return HTML_FILE.read_text(encoding="utf-8")


@app.get("/api/latest")
def api_latest():
    """Laatste locatie van alle pucks, geïndexeerd op device_id."""
    if not LATEST_FILE.exists():
        return {}
    return _read_json_file(LATEST_FILE, {})


@app.get("/api/all")
def api_all():
    """Alle pucks hun laatste bekende locatie."""
    if LATEST_ALL_FILE.exists():
        payload = _read_json_file(LATEST_ALL_FILE, {})
        if isinstance(payload, dict):
            return payload
    if LATEST_FILE.exists():
        payload = _read_json_file(LATEST_FILE, {})
        if isinstance(payload, dict) and payload.get("device_id"):
            return {payload.get("device_id", "unknown"): payload}
    return {}


@app.get("/api/history")
def api_history():
    """Laatste 50 locatiepunten van alle pucks."""
    if not HISTORY_FILE.exists():
        return []
    rows = []
    for line in HISTORY_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows[-50:]


def _geo_store() -> dict:
    global _geo_cache
    if _geo_cache is None:
        data = _read_json_file(GEOCODE_CACHE_FILE, {})
        _geo_cache = data if isinstance(data, dict) else {}
    return _geo_cache


def _short_address(payload: dict) -> str:
    a = payload.get("address", {}) if isinstance(payload, dict) else {}
    road = a.get("road") or a.get("pedestrian") or a.get("footway") or a.get("cycleway")
    num = a.get("house_number")
    city = a.get("city") or a.get("town") or a.get("village") or a.get("municipality") or a.get("hamlet")
    postcode = a.get("postcode")
    parts = []
    if road:
        parts.append(f"{road} {num}".strip() if num else road)
    locality = " ".join(x for x in [postcode, city] if x)
    if locality:
        parts.append(locality)
    return ", ".join(parts) or payload.get("display_name", "") if isinstance(payload, dict) else ""


@app.get("/api/geocode")
def api_geocode(lat: float, lon: float):
    """Reverse-geocode (adres bij coördinaten) via OpenStreetMap, met cache."""
    key = f"{round(lat, 4)},{round(lon, 4)}"
    with _geo_lock:
        cache = _geo_store()
        if key in cache:
            return {"address": cache[key], "cached": True}

    address = None
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"format": "jsonv2", "lat": lat, "lon": lon, "zoom": 18, "addressdetails": 1},
            headers={"User-Agent": "GPS-Puck-Tracker/1.0 (zelf-gehost)"},
            timeout=8,
        )
        resp.raise_for_status()
        address = _short_address(resp.json()) or None
    except Exception:
        address = None

    if address:
        with _geo_lock:
            cache = _geo_store()
            cache[key] = address
            _write_json_file(GEOCODE_CACHE_FILE, cache)
    return {"address": address, "cached": False}


@app.get("/api/devices")
def api_devices():
    """Lijst van bekende pucks."""
    devices = load_devices()
    return devices


@app.get("/api/admin/status")
def api_admin_status(authorization: str | None = Header(default=None)):
    """Is de huidige bezoeker ingelogd als admin? Is er een wachtwoord ingesteld?"""
    token = admin_auth.token_from_header(authorization)
    return {"is_admin": admin_auth.validate(token), "configured": admin_auth.is_configured()}


@app.post("/api/admin/login")
def api_admin_login(payload: AdminLogin):
    """Login met het gedeelde admin-wachtwoord. Geeft een sessie-token terug."""
    token = admin_auth.login(payload.password)
    if not token:
        raise HTTPException(status_code=401, detail="Verkeerd wachtwoord")
    return {"ok": True, "token": token}


@app.post("/api/admin/logout")
def api_admin_logout(authorization: str | None = Header(default=None)):
    admin_auth.logout(admin_auth.token_from_header(authorization))
    return {"ok": True}


@app.get("/api/auth/status", dependencies=[Depends(require_admin)])
def api_auth_status():
    """Is er een Google-account verbonden, en welk? (enkel admin)"""
    return auth_service.status()


@app.post("/api/auth/login", dependencies=[Depends(require_admin)])
def api_auth_login():
    """Start het Google-loginproces (opent Chrome op de server-machine)."""
    started = auth_service.login()
    return {"ok": True, "started": started, "status": auth_service.status()}


@app.post("/api/auth/keys", dependencies=[Depends(require_admin)])
def api_auth_keys():
    """Haal de E2EE-ontsleutelsleutels op (opent browser via subprocess)."""
    started = auth_service.retrieve_keys()
    return {"ok": True, "started": started, "status": auth_service.status()}


@app.post("/api/auth/token", dependencies=[Depends(require_admin)])
def api_auth_token(payload: TokenIn):
    """Login met een handmatig geplakt Google oauth_token (geen server-Chrome)."""
    ok, info = auth_service.login_with_token(payload.oauth_token)
    if not ok:
        raise HTTPException(status_code=400, detail=info)
    return {"ok": True, "username": info, "status": auth_service.status()}


@app.post("/api/auth/logout", dependencies=[Depends(require_admin)])
def api_auth_logout():
    """Wis de tokens zodat een ander Google-account verbonden kan worden."""
    ok = auth_service.logout()
    return {"ok": ok, "status": auth_service.status()}


@app.get("/api/discover", dependencies=[Depends(require_admin)])
def api_discover_devices():
    """Scan Google Find My en geef de gevonden pucks terug.

    Zelfde bron als de terminal-wizard (tracker_writer.py): markeert per puck
    of die al in devices.json staat.
    """
    try:
        found = discover_devices()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Kon Google Find My niet bereiken: {e}")
    known_ids = {d.get("device_id") for d in load_devices()}
    pucks = [
        {
            "index": p["index"],
            "name": p["name"],
            "device_id": p["device_id"],
            "already_added": p["device_id"] in known_ids,
        }
        for p in found
    ]
    return {"ok": True, "pucks": pucks}


@app.post("/api/devices", status_code=201, dependencies=[Depends(require_admin)])
def api_add_device(payload: DeviceIn):
    device = {"name": payload.name.strip(), "device_id": payload.device_id.strip()}
    if payload.index:
        device["index"] = payload.index.strip()
    if payload.category is not None:
        device["category"] = payload.category.strip()
    devices, created = upsert_device(device)
    return {"ok": True, "created": created, "device": device, "devices": devices}


@app.delete("/api/devices/{device_id}", dependencies=[Depends(require_admin)])
def api_delete_device(device_id: str):
    """Verwijder een puck volledig: uit devices.json én alle locatiedata."""
    removed = delete_device(device_id)
    purged = purge_device_data(device_id)
    had_data = purged["latest_all"] or purged["latest"] or purged["history"] > 0
    if not removed and not had_data:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"ok": True, "deleted": device_id, "removed_from_devices": removed, "purged": purged}


@app.put("/api/devices/{device_id}", dependencies=[Depends(require_admin)])
def api_rename_device(device_id: str, payload: DeviceIn):
    devices = load_devices()
    updated = None
    for i, device in enumerate(devices):
        if device.get("device_id") == device_id:
            device["name"] = payload.name.strip()
            if payload.category is not None:
                device["category"] = payload.category.strip()
            devices[i] = device          # behoudt index en andere velden
            updated = device
            break
    if updated is None:
        raise HTTPException(status_code=404, detail="Device not found")
    save_devices(devices)
    return {"ok": True, "device": updated, "devices": devices}


# ─── Tracking (zelfde functionaliteit als tracker_writer.py) ──────────────────


@app.post("/api/tracking/start", dependencies=[Depends(require_admin)])
def api_tracking_start():
    """Start de achtergrond-tracking voor alle bekende pucks."""
    try:
        started = tracking_service.start()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "started": started, "status": tracking_service.status()}


@app.post("/api/tracking/stop", dependencies=[Depends(require_admin)])
def api_tracking_stop():
    """Stop de achtergrond-tracking."""
    stopped = tracking_service.stop()
    return {"ok": True, "stopped": stopped, "status": tracking_service.status()}


@app.get("/api/tracking/status")
def api_tracking_status():
    """Huidige trackingstatus, per-puck-status en recente log."""
    return tracking_service.status()
