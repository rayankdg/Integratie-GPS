"""
do_shared_key.py - haalt de E2EE-sleutels op (als apart proces).
================================================================
De pucks gebruiken end-to-end encryptie; om locaties te ontsleutelen zijn een
'shared_key' (uit Google's beveiligingskluis) en een afgeleide 'owner_key'
nodig. Dit script opent een browser (nodriver), laat je aanmelden, opent de
E2EE-ontgrendelpagina en vangt de kluissleutels op via de window.mm-bridge
(dezelfde die de Android-app gebruikt). Daarna worden shared_key + owner_key
gecachet in Auth/secrets.json.

Print 'KEYS_OK' of 'KEYS_FAIL <reden>'. Wordt door de website als SUBPROCESS
gestart (browser-automatisering werkt betrouwbaar als los proces).
"""

from __future__ import annotations

import asyncio
import os
import sys

# Faken van de Android-WebView-bridge: de kluispagina roept
# window.mm.setVaultSharedKeys(str, vaultKeys) aan zodra de sleutels vrijkomen.
# We bewaren ze in sessionStorage (overleeft herinjectie/herrendering).
BRIDGE_JS = """
window.mm = {
  setVaultSharedKeys: function(str, vaultKeys) {
    try { sessionStorage.setItem('__fmdn_vault', JSON.stringify({str: str, vaultKeys: vaultKeys})); } catch (e) {}
  },
  closeView: function() { try { sessionStorage.setItem('__fmdn_closed', '1'); } catch (e) {} }
};
"""


async def _capture_shared_key() -> str | None:
    import nodriver
    from KeyBackup.shared_key_request import get_security_domain_request_url

    browser = await nodriver.start(
        headless=False,
        sandbox=False,
        browser_args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    try:
        tab = await browser.get("https://accounts.google.com/")

        # 1) Wacht tot je aangemeld bent (redirect naar myaccount.google.com).
        signed_in = False
        for _ in range(720):  # ~6 min
            try:
                url = str(await tab.evaluate("location.href") or "")
            except Exception:
                url = ""
            if "myaccount.google.com" in url:
                signed_in = True
                break
            await asyncio.sleep(0.5)
        if not signed_in:
            return None

        # 2) Open de E2EE-ontgrendelpagina en vang de kluissleutels op.
        security_url = get_security_domain_request_url()
        tab = await browser.get(security_url)
        for _ in range(720):  # ~6 min (je moet mogelijk je telefoon-pincode ingeven)
            try:
                await tab.evaluate(BRIDGE_JS)  # herinjecteer (idempotent)
                res = await tab.evaluate("sessionStorage.getItem('__fmdn_vault')")
            except Exception:
                res = None
            if res:
                return str(res)
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
        raw = loop.run_until_complete(_capture_shared_key())
    except Exception as e:  # noqa: BLE001
        print(f"KEYS_FAIL browser: {e}")
        return 1
    finally:
        try:
            loop.close()
        except Exception:
            pass

    if not raw:
        print("KEYS_FAIL geen_sleutels_ontvangen")
        return 1

    try:
        import json
        from KeyBackup.response_parser import get_fmdn_shared_key
        from Auth.token_cache import set_cached_value

        data = json.loads(raw)
        shared_key = get_fmdn_shared_key(data["vaultKeys"])
        set_cached_value("shared_key", shared_key.hex())

        # Owner_key wordt uit de shared_key afgeleid -> nu cachen zodat
        # ontsleuteling meteen werkt.
        try:
            from SpotApi.GetEidInfoForE2eeDevices.get_owner_key import get_owner_key
            get_owner_key()
        except Exception as e:  # noqa: BLE001
            print(f"KEYS_WARN owner_key: {e}")

        print("KEYS_OK")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"KEYS_FAIL parse: {e}")
        return 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(rc)
