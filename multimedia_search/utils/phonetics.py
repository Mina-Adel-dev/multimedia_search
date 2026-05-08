"""Phonetic helpers such as Soundex."""

from __future__ import annotations

from collections import defaultdict
from typing import DefaultDict, Dict, Iterable, List


def _phonetic_normalize(text: str) -> str:
    """
    Small normalization step before Soundex.

    This is intentionally light:
    - helps practical cases like phone ~ fone
    - keeps behavior deterministic
    """
    t = "".join(ch for ch in str(text).upper() if ch.isalpha())
    if not t:
        return ""

    replacements = [
        ("PH", "F"),
        ("GH", "G"),
        ("KN", "N"),
        ("GN", "N"),
        ("WR", "R"),
        ("WH", "W"),
        ("DG", "J"),
        ("TCH", "CH"),
        ("Q", "K"),
        ("X", "KS"),
        ("Z", "S"),
    ]

    for src, dst in replacements:
        t = t.replace(src, dst)

    return t


def soundex(term: str) -> str:
    """
    Compute a practical Soundex code with light phonetic normalization.
    """
    text = _phonetic_normalize(term)
    if not text:
        return ""

    first = text[0]

    mapping = {
        "B": "1", "F": "1", "P": "1", "V": "1",
        "C": "2", "G": "2", "J": "2", "K": "2", "Q": "2", "S": "2", "X": "2", "Z": "2",
        "D": "3", "T": "3",
        "L": "4",
        "M": "5", "N": "5",
        "R": "6",
    }

    digits: List[str] = []
    previous = mapping.get(first, "")

    for ch in text[1:]:
        code = mapping.get(ch, "")
        if code != previous:
            if code:
                digits.append(code)
        previous = code

    result = first + "".join(digits)
    result = (result + "000")[:4]
    return result


def build_soundex_buckets(vocabulary: Iterable[str]) -> Dict[str, List[str]]:
    buckets: DefaultDict[str, List[str]] = defaultdict(list)

    for term in vocabulary:
        code = soundex(term)
        if not code:
            continue
        buckets[code].append(term)

    for code in buckets:
        buckets[code] = sorted(set(buckets[code]))

    return dict(buckets)