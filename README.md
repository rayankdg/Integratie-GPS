# GPS Puck Tracker — Integratie-GPS

Een volledig GPS-tracking systeem dat GPS-pucks (Find My Device-trackers) volgt via het Google Find Hub Network en hun locatie weergeeft op een live web-dashboard.

> **Gebouwd op basis van [GoogleFindMyTools](https://github.com/leonbottger/GoogleFindMyTools) door Leon Böttger.**  
> De originele bibliotheek verzorgt de authenticatie en communicatie met de Google Find Hub API. Rondom die basis is dit project gebouwd: een FastAPI-backend, een live web-dashboard, MQTT-integratie en een achtergrond-tracking service.

---

## Wat doet dit project?

- Haalt automatisch de locatie van GPS-pucks op via het **Google Find Hub Network**
- Slaat locatiedata op (laatste positie, geschiedenis) als JSON
- Publiceert locaties via **MQTT** (Mosquitto)
- Stuurt data door naar **InfluxDB** voor tijdreeksen
- Toont alles op een **live web-dashboard** (kaart met markers, geschiedenis, per-puck status)
- Beheerpaneel met admin-login voor het toevoegen/verwijderen van pucks

---

## Stappenplan — installatie & gebruik

### Stap 1 — Vereisten installeren

Zorg dat je het volgende hebt:

- **Python 3.11+** — [python.org](https://www.python.org/downloads/)
- **Google Chrome** (laatste versie) — [google.com/chrome](https://www.google.com/chrome/)
- **Mosquitto MQTT broker** — [mosquitto.org](https://mosquitto.org/download/)
- **InfluxDB 3 Core** — [influxdata.com](https://www.influxdata.com/downloads/)

Installeer de Python-dependencies:

```bash
pip install -r requirements.txt
```

---

### Stap 2 — Configuratie instellen

Kopieer `secrets.h` en pas de waarden aan:

```c
#define INFLUX_HOST     "http://localhost:8181"
#define INFLUX_TOKEN    "jouw-influxdb-token"
#define INFLUX_DATABASE "gps"

#define MQTT_HOST       "localhost"
#define MQTT_PORT       1883
#define MQTT_TOPIC      "gpsTracker/pucks/+/location"

#define ADMIN_PASSWORD  "kies-een-sterk-wachtwoord"
```

> `secrets.h` staat in `.gitignore` en wordt nooit naar GitHub gepusht.

---

### Stap 3 — Google-account koppelen (eenmalig)

De tracker heeft toegang nodig tot je Google-account om pucks op te vragen.

1. Zorg dat Chrome is ingelogd op het Google-account waaraan je pucks zijn gekoppeld
2. Start de authenticatie:

```bash
python do_google_login.py
```

3. Haal de E2EE-ontsleutelsleutels op:

```bash
python do_shared_key.py
```

De resultaten worden opgeslagen in `Auth/secrets.json` (niet in git).

---

### Stap 4 — Pucks toevoegen

Voeg je GPS-pucks toe via de terminal-wizard:

```bash
python tracker_writer.py
```

Kies optie **2 — Voeg een nieuwe puck toe**. De wizard haalt automatisch de beschikbare apparaten op uit Google Find My.

Of doe het via het web-dashboard (zie stap 5) onder **Admin → Pucks beheren**.

---

### Stap 5 — Alles starten

**Windows (aanbevolen):**

```
START.bat
```

Of handmatig via PowerShell:

```powershell
.\start_all.ps1
```

Dit start:
- De FastAPI-backend op `http://localhost:8000`
- De MQTT-broker (Mosquitto)
- De InfluxDB-bridge

Open daarna het dashboard: **[http://localhost:8000](http://localhost:8000)**

---

### Stap 6 — Tracking starten

1. Ga naar `http://localhost:8000`
2. Log in als admin (wachtwoord uit `secrets.h`)
3. Klik op **Start tracking**

De pucks worden nu elke 30 seconden bijgewerkt.

---

## Projectstructuur

```
├── app.py                  # FastAPI backend + alle API-endpoints
├── tracking_service.py     # Achtergrond-tracking (threads per puck)
├── tracker_writer.py       # Data lezen/schrijven + terminal-menu
├── google_findmy_bridge.py # Brug naar de GoogleFindMyTools CLI
├── auth_service.py         # Google-account beheer
├── admin_auth.py           # Admin-login logica
├── mqtt_publisher.py       # MQTT publicatie
├── mqtt_influx_bridge.py   # InfluxDB bridge
├── secrets_loader.py       # Laadt secrets.h in Python
├── secrets.h               # Configuratie (NIET in git)
├── START.bat               # Windows opstart-script
├── start_all.ps1           # PowerShell opstart-script
├── webapp/                 # Web-dashboard (HTML/JS/CSS)
├── data/                   # Locatiedata (NIET in git)
│   ├── latest.json
│   ├── latest_all.json
│   └── history.jsonl
├── Auth/                   # GoogleFindMyTools authenticatie
├── NovaApi/                # Google Nova API-aanroepen
└── ...                     # Overige GoogleFindMyTools bibliotheek
```

---

## Team

- Rayan ([@rayankdg](https://github.com/rayankdg))
- Valentina
- Mohammed ([@menoilimohmammedriyad-del](https://github.com/menoilimohmammedriyad-del))
- Asif ([@Asifbenhaddou](https://github.com/Asifbenhaddou))

---

## Licentie

De GoogleFindMyTools-basis valt onder de originele licentie van Leon Böttger (zie [LICENSE](LICENSE)).
