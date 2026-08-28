"""Extract LEGO set numbers from listing text."""
from __future__ import annotations

import re
from typing import Iterable

# 3-7 digit run, optional "-1" suffix, not glued to other digits
_TOKEN_RE = re.compile(r"(?<!\d)(\d{3,7})(?:-\d)?(?!\d)")
_LEGO_CONTEXT_RE = re.compile(r"(lego|set|nr\.?|art\.?|artikel|item)\s*#?\s*$", re.I)


def extract_set_numbers(text: str, known: Iterable[str] = ()) -> list[str]:
    """Return candidate set numbers found in ``text``, best guesses first.

    ``known`` is a set of numbers from the reference book; any exact hit is
    always kept. Bare 4-digit numbers that look like calendar years are dropped
    unless a LEGO-ish word sits right before them.
    """
    if not text:
        return []
    known = {str(k).strip() for k in known}
    out: list[str] = []
    for m in _TOKEN_RE.finditer(text):
        tok = m.group(1)
        if tok in known:
            out.append(tok)
            continue
        if len(tok) < 4:
            continue
        if len(tok) == 4 and 1949 <= int(tok) <= 2099:
            prefix = text[max(0, m.start() - 14):m.start()]
            if not _LEGO_CONTEXT_RE.search(prefix):
                continue
        out.append(tok)
    seen: set[str] = set()
    ordered: list[str] = []
    # known numbers first, then the rest in reading order
    for t in list(out):
        if t in known and t not in seen:
            seen.add(t)
            ordered.append(t)
    for t in out:
        if t not in seen:
            seen.add(t)
            ordered.append(t)
    return ordered
