# GPS Puck Tracker

Een GPS-tracking systeem dat pucks volgt via het Google Find Hub Network en hun locatie toont op een live web-dashboard — inclusief kaart, geschiedenis en per-puck status.

Gebouwd als uitbreiding op [GoogleFindMyTools](https://github.com/leonbottger/GoogleFindMyTools) van Leon Böttger. Die bibliotheek regelt de authenticatie en communicatie met Google's Find Hub API; dit project voegt daar een FastAPI-backend, MQTT-integratie, InfluxDB-opslag en een webinterface bovenop.

---

## Functionaliteit

- Locaties ophalen van één of meerdere pucks via Google Find Hub
- Locatiegeschiedenis bijhouden in JSON en InfluxDB
- Live kaart in de browser, ververst automatisch
- Pucks toevoegen en verwijderen via het dashboard
- MQTT-publicatie voor integratie met andere systemen
- Beveiligd beheerpaneel met admin-login

---

## Vereisten

Alleen **Git** en **Windows 10/11** zijn nodig om te beginnen. De rest installeert de setup automatisch.

Wordt automatisch geïnstalleerd door `SETUP.bat`:
- Python 3.12 (via winget)
- Google Chrome (via winget, als nog niet aanwezig)
- Mosquitto MQTT broker (via winget)
- InfluxDB 3 Core (automatisch gedownload van GitHub)
- Alle Python-packages uit `requirements.txt`

---

## Installatie

### Stap 1 — Repository clonen

Open een terminal (cmd of PowerShell) en voer uit:

```bash
git clone https://github.com/rayankdg/Integratie-GPS.git
```

Je kan ook rechtstreeks op GitHub klikken op **Code → Download ZIP**, het ZIP-bestand uitpakken en de map openen.

> VS Code gebruikers: als je clonet via VS Code, klik daarna op **Open Folder** en selecteer de `Integratie-GPS` map zodat je de bestanden ziet.

### Stap 2 — Setup uitvoeren

Open de gekloonde map in **Verkenner** (File Explorer).  
Dubbelklik op **`SETUP.bat`**.

Heb je de map al open in een terminal? Dan kan het ook zo:

```powershell
.\SETUP.bat
```

Het script installeert automatisch alle ontbrekende software, maakt een virtuele Python-omgeving aan en begeleidt je daarna stap voor stap door de configuratie. Je hoeft zelf niets handmatig in te stellen.

**Wat de setup doorloopt:**
1. Python 3.12 installeren (via winget)
2. Google Chrome installeren (via winget)
3. Mosquitto installeren (via winget)
4. InfluxDB 3 Core downloaden en uitpakken
5. Python-packages installeren
6. InfluxDB token aanmaken — de browser opent automatisch, het script legt elke stap uit
7. Admin-wachtwoord instellen voor de website

### Stap 3 — InfluxDB token

De setup genereert dit **automatisch** — je hoeft hier niets voor te doen. Het token wordt opgeslagen in `secrets.h` en `local.ps1`.

### Stap 4 — Admin-wachtwoord

De setup vraagt om een wachtwoord voor het beheerpaneel op de website. Kies iets wat je kan onthouden.

> `secrets.h` staat in `.gitignore` en wordt nooit gepusht. Gebruik `secrets.h.example` als referentie.

### Stap 4 — Google-account koppelen (eenmalig)

Zorg dat Chrome ingelogd is op het Google-account waaraan je pucks zijn gekoppeld.

Open een terminal in de projectmap en voer uit:

```powershell
.\venv\Scripts\activate
python do_google_login.py
python do_shared_key.py
```

> De eerste regel (`.\venv\Scripts\activate`) is verplicht. Zonder die stap gebruikt Windows de verkeerde Python en ontbreken de geïnstalleerde packages (`No module named 'nodriver'`).

De authenticatiegegevens worden opgeslagen in `Auth/secrets.json` (ook niet in git).

### Stap 5 — Opstarten

Dubbelklik **`START.bat`**.

Dit start InfluxDB, Mosquitto, de MQTT-bridge en de webserver op. De browser opent automatisch op `http://localhost:8000`.

Als `local.ps1` nog niet bestaat (eerste keer), wordt de setup eerst automatisch uitgevoerd.

### Stap 6 — Pucks toevoegen en tracking starten

1. Ga naar `http://localhost:8000`
2. Log in als admin met het wachtwoord uit `secrets.h`
3. Voeg pucks toe via **Admin → Pucks beheren** of via de terminal:
   ```bash
   python tracker_writer.py
   ```
4. Klik op **Start tracking** — pucks worden elke 30 seconden bijgewerkt

---

## Projectstructuur

```
├── SETUP.bat / setup.ps1       eerste-keer installatie
├── START.bat / start_all.ps1   dagelijks opstarten
│
├── app.py                      FastAPI backend + API-endpoints
├── tracking_service.py         achtergrond-tracking per puck
├── tracker_writer.py           data opslaan + terminal-menu
├── google_findmy_bridge.py     koppeling met GoogleFindMyTools CLI
├── auth_service.py             Google-account beheer
├── admin_auth.py               admin-login
├── mqtt_publisher.py           MQTT-publicatie
├── mqtt_influx_bridge.py       doorsturen naar InfluxDB
│
├── secrets.h                   jouw configuratie (niet in git)
├── secrets.h.example           template voor nieuwe gebruikers
├── local.ps1                   machine-specifieke paden (niet in git)
│
├── webapp/                     web-dashboard
├── data/                       locatiedata (niet in git)
├── Auth/                       GoogleFindMyTools authenticatie
└── NovaApi/ SpotApi/ ...       GoogleFindMyTools bibliotheek
```

---

## Team

| Naam | GitHub |
|---|---|
| Rayan | [@rayankdg](https://github.com/rayankdg) |
| Valentina | [@Shinobi815](https://github.com/Shinobi815) |
| Mohammed | [@menoilimohmammedriyad-del](https://github.com/menoilimohmammedriyad-del) |
| Asif | [@Asifbenhaddou](https://github.com/Asifbenhaddou) |

---

## Licentie

De GoogleFindMyTools-basis valt onder de licentie van Leon Böttger — zie [LICENSE](LICENSE).
