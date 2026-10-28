"""Helpers for X post text: weighted length (twitter-text v3 rules) and trimming."""
from __future__ import annotations

import re

URL_RE = re.compile(r"https?://\S+|\b[\w-]+\.(?:org|com|net|gov|io)(?:/\S*)?", re.I)
URL_WEIGHT = 23
LIMIT = 280
# code point ranges that count as 1; everything else counts as 2
_LIGHT = ((0, 4351), (8192, 8205), (8208, 8223), (8242, 8247))


def _char_weight(ch: str) -> int:
    cp = ord(ch)
    return 1 if any(a <= cp <= b for a, b in _LIGHT) else 2


def weighted_length(text: str) -> int:
    total, last = 0, 0
    for m in URL_RE.finditer(text):
        total += sum(_char_weight(c) for c in text[last:m.start()]) + URL_WEIGHT
        last = m.end()
    total += sum(_char_weight(c) for c in text[last:])
    return total


def fits(text: str) -> bool:
    return weighted_length(text) <= LIMIT


def fit_lines(lines: list[str], optional_from: int | None = None) -> str:
    """Join lines; if too long, drop optional trailing lines, then hard-trim."""
    keep = list(lines)
    text = "\n".join(keep).strip()
    while not fits(text) and optional_from is not None and len(keep) > optional_from:
        keep.pop()
        text = "\n".join(keep).strip()
    while not fits(text):
        text = text[:-2].rstrip() + "…"
    return text
