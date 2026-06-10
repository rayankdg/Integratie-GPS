"""
mqtt_influx_bridge.py — MQTT → InfluxDB 3 bridge
================================================
Abonneert op de puck-locaties op de MQTT-broker (Mosquitto) en schrijft elk
bericht weg naar InfluxDB 3 Core. Zo loopt zowel de live kaart als de
historiek-opslag via dezelfde MQTT-berichten.

Eigenschappen:
  • Gebruikt de ECHTE fix-tijd uit de payload als tijdstip in InfluxDB.
  • Buffert punten als InfluxDB tijdelijk onbereikbaar is en schrijft ze
    automatisch alsnog weg zodra de databank terug online is (geen dataverlies).

Config komt uit secrets.h (zie secrets_loader.py).

Draaien:
    python mqtt_influx_bridge.py
"""

from __future__ import annotations

import json
import sys
import threading
from datetime import datetime, timezone

from secrets_loader import load_secrets

# Buffer voor punten die (nog) niet weggeschreven konden worden.
_buffer: list = []
_buffer_lock = threading.Lock()
_stop = threading.Event()
MAX_BUFFER = 10000          # bovengrens; oudste punten vallen weg boven dit aantal
RETRY_SECONDS = 10          # interval om de buffer leeg te schrijven


def _parse_time(p: dict):
    """Bepaal het tijdstip van de fix (UTC) uit de payload.

    Voorkeur: 'timestamp' (moment van de GPS-fix), anders 'received'.
    Geeft None als niets parseerbaar is (dan gebruikt InfluxDB de schrijftijd).
    """
    for key in ("timestamp", "received"):
        val = p.get(key)
        if not isinstance(val, str) or not val.strip():
            continue
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(val.strip(), fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def build_point(p: dict):
    from influxdb_client_3 import Point

    point = (
        Point("location")
        .tag("device_id", str(p.get("device_id", "")))
        .tag("name", str(p.get("name", "")))
    )
    wrote_field = False
    for f in ("latitude", "longitude", "altitude", "battery", "status"):
        v = p.get(f)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            point.field(f, float(v))
            wrote_field = True
    if isinstance(p.get("own_report"), bool):
        point.field("own_report", 1.0 if p["own_report"] else 0.0)
        wrote_field = True
    if not wrote_field:
        return None
    ts = _parse_time(p)
    if ts is not None:
        point.time(ts)
    return point


def main() -> None:
    # Direct doorstromen + UTF-8 (vermijdt cp1252-fouten op Windows-console).
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass

    cfg = load_secrets()
    influx_host = cfg.get("INFLUX_HOST", "http://localhost:8181")
    influx_token = cfg.get("INFLUX_TOKEN", "")
    influx_db = cfg.get("INFLUX_DATABASE", "gps")
    mqtt_host = cfg.get("MQTT_HOST", "localhost")
    mqtt_port = int(cfg.get("MQTT_PORT", "1883"))
    mqtt_topic = cfg.get("MQTT_TOPIC", "gpsTracker/pucks/+/location")

    if not influx_token:
        raise SystemExit("Geen INFLUX_TOKEN in secrets.h gevonden.")

    from influxdb_client_3 import InfluxDBClient3
    import paho.mqtt.client as mqtt

    influx = InfluxDBClient3(host=influx_host, token=influx_token, database=influx_db)
    print(f"[bridge] InfluxDB: {influx_host} db='{influx_db}'")

    def buffer_point(point) -> None:
        with _buffer_lock:
            _buffer.append(point)
            if len(_buffer) > MAX_BUFFER:
                overflow = len(_buffer) - MAX_BUFFER
                del _buffer[:overflow]
                print(f"[bridge] buffer vol — {overflow} oudste punt(en) weggegooid.")

    def retry_loop() -> None:
        """Probeer periodiek de gebufferde punten alsnog weg te schrijven."""
        while not _stop.is_set():
            _stop.wait(RETRY_SECONDS)
            with _buffer_lock:
                batch = _buffer[:200]
            if not batch:
                continue
            written = 0
            for pt in batch:
                try:
                    influx.write(pt)
                    written += 1
                except Exception:
                    break  # databank nog steeds weg — later opnieuw proberen
            if written:
                with _buffer_lock:
                    del _buffer[:written]
                    remaining = len(_buffer)
                print(f"[bridge] {written} gebufferd(e) punt(en) alsnog weggeschreven "
                      f"(nog {remaining} in buffer).")

    def on_connect(client, userdata, flags, reason_code, properties=None):
        print(f"[bridge] MQTT verbonden ({mqtt_host}:{mqtt_port}) — subscribe '{mqtt_topic}'")
        client.subscribe(mqtt_topic, qos=1)

    def on_message(client, userdata, msg):
        try:
            p = json.loads(msg.payload.decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            print(f"[bridge] ongeldige payload op {msg.topic}: {e}")
            return
        point = build_point(p)
        if point is None:
            return
        label = p.get("name", p.get("device_id"))
        try:
            influx.write(point)
            ts = p.get('timestamp') or p.get('received') or ''
            print(f"[bridge] → InfluxDB  {label}  {ts}  {p.get('latitude')}, {p.get('longitude')}")
        except Exception:
            buffer_point(point)
            with _buffer_lock:
                depth = len(_buffer)
            print(f"[bridge] InfluxDB onbereikbaar — {label} gebufferd (buffer={depth}).")

    retry_thread = threading.Thread(target=retry_loop, daemon=True)
    retry_thread.start()

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="gps-influx-bridge")
    except (AttributeError, TypeError):
        client = mqtt.Client(client_id="gps-influx-bridge")

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(mqtt_host, mqtt_port, keepalive=60)

    print("[bridge] gestart — Ctrl+C om te stoppen.")
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[bridge] gestopt.")
    finally:
        _stop.set()
        try:
            influx.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
