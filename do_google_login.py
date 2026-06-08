"""
do_google_login.py - opzichzelfstaande Google-login (als apart proces).
=======================================================================
Wordt door de website als SUBPROCESS gestart (net zoals main.py een apart
proces is). De browser-automatisering werkt betrouwbaar als los proces, terwijl
ze van binnenuit de uvicorn-server faalt ("Failed to connect to browser").

Opent een browser (nodriver) op de Google-setuppagina, wacht tot het
oauth_token-cookie verschijnt, wisselt het om naar een AAS-token en cachet het
in Auth/secrets.json. Print 'LOGIN_OK <email>' of 'LOGIN_FAIL <reden>'.
"""

from __future__ import annotations

import asyncio
import os
import sys


async def _capture_oauth_token() -> str | None:
    import nodriver

    browser = await nodriver.start(
        headless=False,
        sandbox=False,
        browser_args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    try:
        await browser.get("https://accounts.google.com/EmbeddedSetup")
        # Poll tot het token gezet is (max ~6 min). De pagina mag blijven spinnen.
        for _ in range(720):
            try:
                cookies = await browser.cookies.get_all()
            except Exception:
                cookies = []
            for c in cookies:
                if getattr(c, "name", "") == "oauth_token" and getattr(c, "value", ""):
                    return c.value
            await asyncio.sleep(0.5)
        return None
    finally:
        try:
            browser.stop()
        except Exception:
            pass


def main() -> int:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        oauth_token = loop.run_until_complete(_capture_oauth_token())
    except Exception as e:  # noqa: BLE001
        print(f"LOGIN_FAIL browser: {e}")
        return 1
    finally:
        try:
            loop.close()
        except Exception:
            pass

    if not oauth_token:
        print("LOGIN_FAIL geen_token_ontvangen")
        return 1

    try:
        import gpsoauth
        from Auth.fcm_receiver import FcmReceiver
        from Auth.token_cache import set_cached_value
        from Auth.username_provider import username_string, get_username

        username = get_username() or ""
        android_id = FcmReceiver().get_android_id()
        resp = gpsoauth.exchange_token(username, oauth_token, android_id)
        if "Token" not in resp:
            print(f"LOGIN_FAIL exchange: {str(resp)[:200]}")
            return 1
        set_cached_value("aas_token", resp["Token"])
        email = resp.get("Email")
        if email:
            set_cached_value(username_string, email)
        print(f"LOGIN_OK {email or get_username()}")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"LOGIN_FAIL exchange_err: {e}")
        return 1


if __name__ == "__main__":
    rc = main()
    # Forceer afsluiten: de FCM-luisteraar draait in een achtergrondthread en
    # zou het proces anders open houden (waardoor de backend op 'bezig' blijft).
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(rc)
