"""Pure normalization helpers for draw ingestion — money + vendor names.

Real draw PDFs render money in many shapes: ``$5,949.22``, ``-$17,699.18``, ``($ (851.75)``,
``($ 3,947.37)``, ``-3,113.05``. In accounting parens and a leading minus both mean negative
(here, a retention *release*). These helpers are deterministic and side-effect free.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

# A money token: optional sign/paren/$, digits with commas, two decimals, optional close paren.
# Whitespace is bounded to a single char (\s?, never \s*) so long layout-text space runs
# cannot trigger catastrophic regex backtracking.
MONEY_RE = re.compile(r"\(?\s?-?\s?\$?\s?\(?\s?-?[\d,]+\.\d{2}\s?\)?")

_SUFFIXES = (" LLC", " L.L.C.", " INC", " INC.", " CO", " CO.", " COMPANY",
             " CORPORATION", " CORP", " CORP.", " LTD", " LP", " LLP", " PLLC")


def parse_money(token: str) -> Decimal | None:
    """Parse one money token to a signed Decimal (parens or '-' ⇒ negative). None if unparseable."""
    if token is None:
        return None
    raw = token.strip()
    if not raw:
        return None
    negative = "(" in raw or raw.lstrip().startswith("-") or "-" in raw.replace("($", "(")
    digits = re.sub(r"[^\d.]", "", raw)
    if not digits or digits == ".":
        return None
    try:
        value = Decimal(digits)
    except InvalidOperation:
        return None
    return -value if negative else value


def money_tokens(text: str) -> list[Decimal]:
    """All money values found in a line, in order, signed."""
    out: list[Decimal] = []
    for m in MONEY_RE.findall(text):
        v = parse_money(m)
        if v is not None:
            out.append(v)
    return out


def normalize_name(name: str) -> str:
    """Canonical vendor key: upper, de-punctuate, drop entity suffixes, collapse spaces."""
    if not name:
        return ""
    n = name.upper().strip()
    n = n.replace("&", " AND ").replace("É", "E").replace("�", "")
    n = re.sub(r"[^\w\s]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    changed = True
    while changed:
        changed = False
        for suf in (s.replace(".", "").strip() for s in _SUFFIXES):
            if n.endswith(" " + suf):
                n = n[: -(len(suf) + 1)].strip()
                changed = True
    return n
