"""
tracking_service.py — achtergrond-tracking voor de website
===========================================================
Brengt de "Start tracking" functionaliteit naar de FastAPI-app: per puck een
achtergrondlus die elke POLL_INTERVAL seconden de locatie ophaalt bij Google
Find My en wegschrijft naar latest.json / latest_all.json / history.jsonl.

Een supervisor leest elke RELOAD_INTERVAL seconden devices.json opnieuw in:
  • nieuw toegevoegde pucks worden automatisch mee getrackt (zonder herstart);
  • verwijderde pucks stoppen automatisch.

Hergebruikt de bestaande parse-/opslaglogica uit tracker_writer.py en de
Google-Find-My-aanroepen uit google_findmy_bridge.py.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from google_findmy_bridge import discover_devices, fetch_location_for_index
from tracker_writer import (
    POLL_INTERVAL,
    load_devices,
    parse_location_output,
    save_payload,
)

RELOAD_INTERVAL = 15  # seconden tussen het opnieuw inlezen van devices.json


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class TrackingService:
    """Beheert de achtergrond-tracking met automatische herlaad van de pucklijst."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._run_event: threading.Event | None = None   # stop-signaal van de huidige run
        self._running = False
        self._started_at: str | None = None
        self._statuses: dict[str, dict] = {}
        self._log: list[dict] = []
        self._workers: dict[str, dict] = {}     # device_id -> {thread, stop, device}
        self._index_by_id: dict[str, str] = {}  # device_id -> menu-index

    # ─── Status & logging ────────────────────────────────────────────────────

    def _add_log(self, message: str, level: str = "info") -> None:
        entry = {
            "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            "level": level,
            "message": message,
        }
        with self._lock:
            self._log.append(entry)
            if len(self._log) > 200:
                self._log = self._log[-200:]

    def _set_status(self, device_id: str, **fields) -> None:
        with self._lock:
            cur = self._statuses.setdefault(device_id, {"device_id": device_id})
            cur.update(fields)

    # ─── Start / stop ────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Start tracking. De supervisor leest devices.json (telkens opnieuw)."""
        with self._lock:
            if self._running:
                return False
            devices = load_devices()
            if not devices:
                raise RuntimeError("Geen pucks geconfigureerd (devices.json is leeg).")
            run_event = threading.Event()        # eigen stop-signaal voor deze run
            self._run_event = run_event
            self._running = True
            self._started_at = _now()
            self._statuses = {}
            self._workers = {}
            self._index_by_id = {}

        self._add_log(
            f"Tracking gestart ({len(devices)} puck(s)). Interval {POLL_INTERVAL}s, "
            f"pucklijst-herlaad elke {RELOAD_INTERVAL}s."
        )
        threading.Thread(target=self._supervise, args=(run_event,), daemon=True).start()
        return True

    def stop(self) -> bool:
        """Stop tracking. Geeft de UI meteen 'gestopt' terug; threads die nog in
        een ophaalcyclus zitten, ronden op de achtergrond af."""
        with self._lock:
            if not self._running:
                return False
            self._running = False                # meteen zichtbaar in de UI
            if self._run_event:
                self._run_event.set()
            self._workers = {}                   # signaleert lopende workers te stoppen
        self._add_log("Tracking gestopt.")
        return True

    def status(self) -> dict:
        with self._lock:
            return {
                "running": self._running,
                "started_at": self._started_at,
                "poll_interval": POLL_INTERVAL,
                "reload_interval": RELOAD_INTERVAL,
                "devices": list(self._statuses.values()),
                "log": self._log[-50:],
            }

    # ─── Index-ontdekking ────────────────────────────────────────────────────

    def _refresh_indices(self, devices: list[dict]) -> None:
        """Haal menu-indexen op bij Google Find My, maar enkel als er een puck
        is waarvan we de index (nog) niet kennen — zo vermijden we onnodige calls.
        """
        unknown = [d["device_id"] for d in devices if d["device_id"] not in self._index_by_id]
        if not unknown:
            return
        try:
            self._add_log("Pucklijst ophalen van Google Find My…")
            discovered = discover_devices()
            self._index_by_id = {d["device_id"]: d["index"] for d in discovered}
            self._add_log(f"{len(discovered)} puck(s) gevonden bij Google Find My.")
        except Exception as e:  # noqa: BLE001
            self._add_log(f"Kon pucklijst niet ophalen: {e}.", "error")

    # ─── Supervisor: houdt de set workers gelijk aan devices.json ────────────

    def _supervise(self, run_event: threading.Event) -> None:
        while not run_event.is_set():
            devices = load_devices()
            by_id = {d["device_id"]: d for d in devices}
            self._refresh_indices(devices)
            if run_event.is_set():
                break

            # Workers stoppen voor pucks die niet meer in devices.json staan.
            for device_id in list(self._workers):
                if device_id not in by_id:
                    self._workers[device_id]["stop"].set()
                    del self._workers[device_id]
                    with self._lock:
                        self._statuses.pop(device_id, None)
                    self._add_log(f"[{device_id}] verwijderd uit devices.json — tracking gestopt.")

            # Workers starten voor nieuwe pucks; bestaande hun device-info verversen.
            for device_id, device in by_id.items():
                if device_id in self._workers:
                    self._workers[device_id]["device"] = device
                    continue
                stop = threading.Event()
                self._workers[device_id] = {"thread": None, "stop": stop, "device": device}
                t = threading.Thread(
                    target=self._track_device, args=(device_id, stop, run_event), daemon=True
                )
                self._workers[device_id]["thread"] = t
                self._add_log(f"[{device.get('name', device_id)}] tracking gestart.")
                t.start()

            run_event.wait(RELOAD_INTERVAL)

        with self._lock:
            if self._run_event is run_event:     # alleen als dit nog de actieve run is
                self._running = False

    # ─── Worker per puck ─────────────────────────────────────────────────────

    def _track_device(self, device_id: str, stop: threading.Event, run_event: threading.Event) -> None:
        while not run_event.is_set() and not stop.is_set():
            worker = self._workers.get(device_id)
            if worker is None:
                break
            device = worker["device"]
            name = device.get("name", device_id)
            index = self._index_by_id.get(device_id) or device.get("index")

            if not index:
                self._set_status(device_id, name=name, state="error",
                                 message="Geen index gevonden bij Google Find My.",
                                 last_update=_now())
                stop.wait(POLL_INTERVAL)
                continue

            try:
                output = fetch_location_for_index(index)
                payload = parse_location_output(output, {**device, "index": index})
                save_payload(payload)
                self._set_status(
                    device_id,
                    name=name,
                    state="ok",
                    message=f"{payload['latitude']}, {payload['longitude']}",
                    last_update=_now(),
                    last_fix=payload.get("timestamp"),
                )
                self._add_log(
                    f"[{name}] {payload.get('timestamp', '?')}  "
                    f"{payload['latitude']}, {payload['longitude']}"
                )
            except Exception as e:  # noqa: BLE001
                self._set_status(device_id, name=name, state="error", message=str(e),
                                 last_update=_now())
                self._add_log(f"[{name}] Fout: {e}", "error")

            stop.wait(POLL_INTERVAL)


# Eén gedeelde instantie voor de hele app.
tracking_service = TrackingService()
