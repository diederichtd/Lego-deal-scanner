"""Guess item condition from German/English listing text."""
from __future__ import annotations

import re

_INCOMPLETE = re.compile(
    r"unvollst[aä]ndig|nicht komplett|teile fehlen|teile fehlt|incomplete|"
    r"ohne anleitung|ohne ba|missing", re.I,
)
_USED = re.compile(
    r"gebraucht|benutzt|bespielt|(?<!un)(?:auf)?gebaut|neuwertig|(?<!un)ge[oö]ffnet|"
    r"(?<!un)geoeffnet|used|second[ -]hand|zusammengebaut|konvolut|kiloware", re.I,
)
_NEW = re.compile(
    r"\bneu\b|\bnew\b|\bovp\b|versiegelt|unge[oö]ffnet|ungeoeffnet|sealed|nib|misb|"
    r"original verpackt|new in box", re.I,
)

CONDITIONS = ("new_sealed", "used_complete", "used_incomplete", "unknown")


def detect_condition(text: str) -> str:
    t = text or ""
    if _INCOMPLETE.search(t):
        return "used_incomplete"
    used = bool(_USED.search(t))
    new = bool(_NEW.search(t))
    if new and not used:
        return "new_sealed"
    if used:
        return "used_complete"
    return "unknown"
