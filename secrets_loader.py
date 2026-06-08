"""
secrets_loader.py — leest waarden uit secrets.h (C-header) in Python.
=====================================================================
Zo staat elke geheime/instelbare waarde op één plek (secrets.h), bruikbaar
voor zowel de Python-bridge als eventuele ESP32-firmware.

Ondersteunt regels van de vorm:
    #define KEY "string waarde"
    #define KEY 1883
"""

from __future__ import annotations

import re
from pathlib import Path

_DEFINE_RE = re.compile(r'#define\s+(\w+)\s+(.+?)\s*$')


def load_secrets(path: str | Path | None = None) -> dict[str, str]:
    p = Path(path) if path else Path(__file__).parent / "secrets.h"
    out: dict[str, str] = {}
    if not p.exists():
        return out

    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("#define"):
            continue
        m = _DEFINE_RE.match(line)
        if not m:
            continue
        key, raw = m.group(1), m.group(2).strip()
        if raw.startswith('"') and '"' in raw[1:]:
            # Quoted string: neem alles tussen eerste en laatste quote
            # (behoudt bv. http:// in een URL, negeert trailing comment).
            out[key] = raw[1:raw.rindex('"')]
        else:
            # Bare token (bv. een poortnummer); strip eventuele // comment.
            out[key] = raw.split("//")[0].strip()
    return out
