"""POS card id  <->  Coca-Cola card number.

The USB reader returns a full unsigned 32-bit card id (e.g. 3377269862). The
Coca-Cola personnel system stores only the LOW 24 BITS of that same number,
formatted as `DDD-DDDDD`, and discards the highest byte:

    low24     = POS_ID & 0xFFFFFF
    leftPart  = (low24 >> 16) & 0xFF     -> 3 digits
    rightPart = low24 & 0xFFFF           -> 5 digits

    3377269862 -> 077-03174
    3378757254 -> 099-48774
    3673926606 -> 251-43982
    4153314197 -> 142-35733

The mapping is therefore MANY-TO-ONE: the discarded high byte means 256
different POS ids collapse onto the same Coca-Cola code, and it is not a
constant we could add back (observed prefixes include 0xC9, 0xDA, 0xF7). So
POS -> Coca-Cola is exact and safe; the reverse is not, and is deliberately
not implemented — a card must be read physically to learn its real POS id.
"""
from __future__ import annotations

import re

# A Coca-Cola card number: exactly 3 digits, a hyphen, exactly 5 digits.
CC_CODE_RE = re.compile(r"^\d{3}-\d{5}$")

_LOW24_MASK = 0xFFFFFF


def pos_to_cc(card_id: str | int) -> str:
    """POS card id -> 'DDD-DDDDD'. Returns "" when the id is not numeric.

    Card ids are stored as TEXT (leading zeros matter), so this accepts a
    string and only converts when it is a plain decimal number. Anything else
    — a name-like id, an empty tap — has no Coca-Cola equivalent and yields "".
    """
    if isinstance(card_id, int):
        value = card_id
    else:
        text = (card_id or "").strip()
        if not text.isdigit():
            return ""
        try:
            value = int(text)
        except ValueError:
            return ""
    if value < 0:
        return ""
    low24 = value & _LOW24_MASK
    return f"{(low24 >> 16) & 0xFF:03d}-{low24 & 0xFFFF:05d}"


def is_cc_code(text: str) -> bool:
    """True if `text` already looks like a Coca-Cola card number."""
    return bool(CC_CODE_RE.match((text or "").strip()))


def normalize_cc_code(text: str) -> str:
    """Tidy a Coca-Cola code from a spreadsheet into canonical 'DDD-DDDDD'.

    Excel likes to mangle these: '77-3174' (leading zeros eaten), '077 - 03174'
    (stray spaces). Both name the same card as '077-03174', so they are
    accepted and re-padded rather than rejected.
    """
    raw = (text or "").strip()
    if not raw:
        return ""
    if CC_CODE_RE.match(raw):
        return raw
    compact = raw.replace(" ", "")
    if "-" in compact:
        left, _, right = compact.partition("-")
        if left.isdigit() and right.isdigit():
            return f"{int(left):03d}-{int(right):05d}"
    return ""
