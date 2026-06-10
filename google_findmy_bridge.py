from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Adjust this if your cloned GoogleFindMyTools repo lives elsewhere.
_env = os.getenv("GOOGLE_FINDMYTOOLS_DIR")
PROJECT_DIR = Path(_env) if _env else Path(__file__).parent

DEVICE_LINE_RE = re.compile(r"^\s*(\d+)\.\s+(.+?):\s+([\w-]{8,})\s*$", re.MULTILINE)


def _find_chrome() -> str | None:
    possible_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\ProgramData\chocolatey\bin\chrome.exe",
        r"C:\Users\%USERNAME%\AppData\Local\Google\Chrome\Application\chrome.exe",
        "/usr/bin/google-chrome",
        "/usr/local/bin/google-chrome",
        "/opt/google/chrome/chrome",
        "/snap/bin/chromium",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path
    try:
        if platform.system() == "Windows":
            return shutil.which("chrome")
        return shutil.which("google-chrome") or shutil.which("chromium")
    except Exception:
        return None


def _chrome_options():
    import undetected_chromedriver as uc

    opts = uc.ChromeOptions()
    opts.add_argument("--start-maximized")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    return uc, opts


def create_driver():
    uc, opts = _chrome_options()
    try:
        driver = uc.Chrome(options=opts, version_main=None)
        return driver
    except Exception:
        chrome_path = _find_chrome()
        if chrome_path:
            opts.binary_location = chrome_path
            driver = uc.Chrome(options=opts, version_main=None)
            return driver
        opts.add_argument("--headless")
        driver = uc.Chrome(options=opts, version_main=None)
        return driver


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


def discover_devices() -> list[dict[str, str]]:
    """Run the existing Google Find My flow and parse the menu output."""
    output = run_main_py("\n", timeout=120)
    devices: list[dict[str, str]] = []
    for match in DEVICE_LINE_RE.finditer(output):
        devices.append(
            {
                "index": match.group(1).strip(),
                "name": match.group(2).strip(),
                "device_id": match.group(3).strip(),
            }
        )
    if not devices:
        lower = output.lower()
        if "google-account niet verbonden" in lower or "niet verbonden" in lower:
            raise RuntimeError(
                "Google-account niet verbonden. "
                "Klik op 'Google verbinden' in de zijbalk om in te loggen."
            )
        if "sessie verlopen" in lower or "session expired" in lower:
            raise RuntimeError(
                "Google-sessie verlopen. "
                "Klik op 'Google verbinden' om opnieuw in te loggen."
            )
        raw = output.strip()
        preview = ("...\n" + raw[-600:]) if len(raw) > 600 else (raw or "(geen output)")
        raise RuntimeError(
            f"Geen apparaten gevonden in Google Find My.\n\n"
            f"Ruwe output van main.py:\n{preview}"
        )
    return devices


def fetch_location_for_index(index: str) -> str:
    """Proxy to the existing CLI by selecting an index."""
    return run_main_py(f"{index}\n")
