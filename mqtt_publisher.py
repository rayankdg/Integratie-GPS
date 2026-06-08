"""
mqtt_publisher.py — publiceert puck-locaties naar een MQTT-broker (Mosquitto)
============================================================================
Best-effort: als de broker niet bereikbaar is of paho-mqtt niet geïnstalleerd,
faalt publiceren stil zodat tracking gewoon blijft doorlopen.

Berichten worden RETAINED gepubliceerd op:
    <prefix>/<device_id>/location      (default: gpsTracker/pucks/<id>/location)

zodat een browser die later verbindt meteen de laatst bekende positie krijgt.

Configuratie via omgevingsvariabelen:
    MQTT_ENABLED        "0" om uit te schakelen (default "1")
    MQTT_HOST           default "localhost"
    MQTT_PORT           default 1883
    MQTT_TOPIC_PREFIX   default "gpsTracker/pucks"
    MQTT_USERNAME       optioneel
    MQTT_PASSWORD       optioneel
"""

from __future__ import annotations

import json
import os
import threading

_ENABLED = os.getenv("MQTT_ENABLED", "1") != "0"
_HOST = os.getenv("MQTT_HOST", "localhost")
_PORT = int(os.getenv("MQTT_PORT", "1883"))
_PREFIX = os.getenv("MQTT_TOPIC_PREFIX", "gpsTracker/pucks").rstrip("/")
_USERNAME = os.getenv("MQTT_USERNAME")
_PASSWORD = os.getenv("MQTT_PASSWORD")

_client = None
_lock = threading.Lock()
_failed = False  # zet True na een mislukte init, om niet te blijven herproberen


def is_enabled() -> bool:
    return _ENABLED and not _failed


def _get_client():
    """Maak (eenmalig) een verbonden paho-client met automatische reconnect."""
    global _client, _failed
    if _client is not None:
        return _client
    with _lock:
        if _client is not None:
            return _client
        import paho.mqtt.client as mqtt

        # Werk zowel met paho-mqtt 2.x (CallbackAPIVersion) als 1.x.
        try:
            client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2, client_id="gps-tracker-publisher"
            )
        except (AttributeError, TypeError):
            client = mqtt.Client(client_id="gps-tracker-publisher")

        if _USERNAME:
            client.username_pw_set(_USERNAME, _PASSWORD)

        # connect_async + loop_start: verbindt op de achtergrond en herverbindt
        # automatisch, zonder de trackingthread te blokkeren.
        client.connect_async(_HOST, _PORT, keepalive=60)
        client.loop_start()
        _client = client
        return client


def publish_location(payload: dict) -> bool:
    """Publiceer één locatie-payload (retained). Geeft False bij elke fout."""
    if not is_enabled():
        return False
    device_id = payload.get("device_id")
    if not device_id:
        return False
    try:
        client = _get_client()
        topic = f"{_PREFIX}/{device_id}/location"
        client.publish(
            topic,
            json.dumps(payload, ensure_ascii=False),
            qos=1,
            retain=True,
        )
        return True
    except Exception:
        # paho niet geïnstalleerd of broker onbereikbaar — niet blijven proberen.
        global _failed
        _failed = True
        return False
