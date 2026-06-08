"""
auth_service.py - Google-account login voor de website
======================================================
Brengt het bestaande Google-loginproces (Auth/auth_flow.py) naar de website,
zodat een klant met zijn EIGEN Google-account kan inloggen via een knop in
plaats van via de terminal.

Bij inloggen opent Chrome op de machine waar de backend draait
(accounts.google.com/EmbeddedSetup). De klant logt in; we wisselen de
oauth_token om naar een AAS-token en cachen dat (samen met het e-mailadres)
in Auth/secrets.json - exact dezelfde opslag als de terminalversie.

Endpoints in app.py:
    GET  /api/auth/status   -> ingelogd? welk account?
    POST /api/auth/login    -> start het Chrome-loginproces (achtergrond)
    POST /api/auth/logout   -> wis de tokens (ander account kunnen kiezen)
"""

from __future__ import annotations

import threading


class AuthService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._busy = False
        self._state = {"state": "idle", "message": ""}
        self._keys_busy = False
        self._keys_state = {"state": "idle", "message": ""}

    # ─── interne status ──────────────────────────────────────────────────────

    def _set(self, **fields) -> None:
        with self._lock:
            self._state.update(fields)

    def _set_keys(self, **fields) -> None:
        with self._lock:
            self._keys_state.update(fields)

    # ─── publieke API ────────────────────────────────────────────────────────

    def status(self) -> dict:
        from Auth.token_cache import get_cached_value
        from Auth.username_provider import get_username

        aas = get_cached_value("aas_token")
        username = get_username()
        logged_in = bool(aas and username)
        has_keys = bool(get_cached_value("shared_key"))
        with self._lock:
            state = dict(self._state)
            keys_state = dict(self._keys_state)
        return {
            "logged_in": logged_in,
            "username": username or None,
            "busy": self._busy,
            "state": state.get("state", "idle"),
            "message": state.get("message", ""),
            "has_keys": has_keys,
            "keys_busy": self._keys_busy,
            "keys_state": keys_state.get("state", "idle"),
            "keys_message": keys_state.get("message", ""),
        }

    # ─── E2EE-sleutels ophalen (apart subprocess: do_shared_key.py) ──────────

    def retrieve_keys(self) -> bool:
        with self._lock:
            if self._keys_busy:
                return False
            self._keys_busy = True
            self._keys_state = {"state": "opening", "message": "Browser openen voor sleutels…"}
        threading.Thread(target=self._run_keys, daemon=True).start()
        return True

    def _run_keys(self) -> None:
        import subprocess
        import sys
        from pathlib import Path

        script = str(Path(__file__).parent / "do_shared_key.py")
        try:
            proc = subprocess.Popen(
                [sys.executable, script],
                cwd=str(Path(__file__).parent),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            self._set_keys(
                state="waiting",
                message="Meld je aan in het venster en bevestig (mogelijk je telefoon-pincode)…",
            )
            try:
                out, _ = proc.communicate(timeout=450)
            except subprocess.TimeoutExpired:
                proc.kill()
                self._set_keys(state="error", message="Sleutels ophalen niet op tijd voltooid.")
                return

            if "KEYS_OK" in (out or ""):
                self._set_keys(
                    state="ok",
                    message="E2EE-sleutels opgehaald — locaties kunnen nu ontsleuteld worden.",
                )
            else:
                last = (out or "").strip().splitlines()
                reason = last[-1] if last else "onbekende fout"
                self._set_keys(state="error", message=f"Sleutels ophalen mislukt: {reason[:200]}")
        except Exception as e:  # noqa: BLE001
            self._set_keys(state="error", message=f"Sleutels ophalen mislukt: {e}")
        finally:
            with self._lock:
                self._keys_busy = False

    def login(self) -> bool:
        """Start het loginproces in de achtergrond. False als er al een loopt."""
        with self._lock:
            if self._busy:
                return False
            self._busy = True
            self._state = {"state": "opening", "message": "Chrome openen voor Google-login…"}
        threading.Thread(target=self._run_login, daemon=True).start()
        return True

    def login_with_token(self, oauth_token: str) -> tuple[bool, str]:
        """Log in met een handmatig geplakt Google oauth_token (geen browser nodig).

        Wisselt het token om naar een AAS-token via gpsoauth en cachet het —
        exact dezelfde opslag als de browser-login.
        """
        oauth_token = (oauth_token or "").strip()
        if not oauth_token:
            return False, "Leeg token."
        try:
            import gpsoauth
            from Auth.fcm_receiver import FcmReceiver
            from Auth.token_cache import set_cached_value
            from Auth.username_provider import username_string, get_username

            username = get_username() or ""
            android_id = FcmReceiver().get_android_id()
            resp = gpsoauth.exchange_token(username, oauth_token, android_id)
            if "Token" not in resp:
                return False, f"Google weigerde het token: {resp}"
            set_cached_value("aas_token", resp["Token"])
            email = resp.get("Email")
            if email:
                set_cached_value(username_string, email)
            who = email or get_username()
            self._set(state="ok", message=f"Ingelogd als {who} (via token).")
            return True, who
        except Exception as e:  # noqa: BLE001
            self._set(state="error", message=f"Token-login mislukt: {e}")
            return False, str(e)

    def logout(self) -> bool:
        """Wis de gecachte tokens zodat een ander account gekozen kan worden."""
        # Stop eerst tracking (anders blijft die met het oude account draaien).
        try:
            from tracking_service import tracking_service
            tracking_service.stop()
        except Exception:
            pass

        from Auth.token_cache import _get_secrets_file, get_cached_value, set_cached_value

        # Behoud apparaat-/E2EE-gegevens zodat een volgende login niet opnieuw
        # moet registreren (FCM) of de sleutels opnieuw moet ophalen.
        preserve = {}
        for key in ("fcm_credentials", "shared_key", "owner_key"):
            val = get_cached_value(key)
            if val:
                preserve[key] = val

        path = _get_secrets_file()
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("{}")
            for key, val in preserve.items():
                set_cached_value(key, val)
        except Exception as e:  # noqa: BLE001
            self._set(state="error", message=f"Uitloggen mislukt: {e}")
            return False
        self._set(state="idle", message="Uitgelogd. Je kan nu een ander account verbinden.")
        return True

    # ─── achtergrond-loginflow ───────────────────────────────────────────────

    def _run_login(self) -> None:
        """Start de Google-login als APART subprocess (do_google_login.py).

        Browser-automatisering werkt betrouwbaar als los proces (zoals main.py),
        maar faalt van binnenuit de uvicorn-server ('Failed to connect to
        browser'). Daarom draaien we het in een eigen Python-proces.
        """
        import subprocess
        import sys
        from pathlib import Path

        self._set(state="opening", message="Browser openen voor Google-login…")
        script = str(Path(__file__).parent / "do_google_login.py")
        try:
            proc = subprocess.Popen(
                [sys.executable, script],
                cwd=str(Path(__file__).parent),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            self._set(
                state="waiting",
                message="Log in met je Google-account in het venster dat opent…",
            )
            try:
                out, _ = proc.communicate(timeout=400)
            except subprocess.TimeoutExpired:
                proc.kill()
                self._set(state="error", message="Login niet op tijd voltooid.")
                return

            from Auth.username_provider import get_username

            if "LOGIN_OK" in (out or ""):
                self._set(state="ok", message=f"Ingelogd als {get_username()}.")
            else:
                last = (out or "").strip().splitlines()
                reason = last[-1] if last else "onbekende fout"
                self._set(state="error", message=f"Login mislukt: {reason[:200]}")
        except Exception as e:  # noqa: BLE001
            self._set(state="error", message=f"Login mislukt: {e}")
        finally:
            with self._lock:
                self._busy = False


# Eén gedeelde instantie voor de hele app.
auth_service = AuthService()
