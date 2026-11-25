"""Evidence checks for leads: the quote must really be in what was fetched."""

from __future__ import annotations

import re
import unicodedata

_TRANS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
                        "…": "...", " ": " "})


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").translate(_TRANS)
    return re.sub(r"\s+", " ", s).strip().lower()


def quote_in_text(quote: str, text: str, min_len: int = 15) -> tuple[bool, str]:
    q = normalize(quote).strip(" .\"'")
    if len(q) < min_len:
        return False, f"quote too short (need at least {min_len} characters of the author's own words)"
    if q in normalize(text):
        return True, ""
    return False, "quote not found verbatim in the captured text; copy the author's exact words from that capture"
