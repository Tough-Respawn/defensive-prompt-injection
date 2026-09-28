"""Fold Unicode text to a canonical form before signature matching."""

from __future__ import annotations

import re
import unicodedata


# Characters that render as nothing (or as a direction change) but survive
# copy/paste: soft hyphen, combining grapheme joiner, Hangul fillers, zero-width
# and bidi controls, word joiners, variation selectors, BOM, and the Unicode
# "tag" block that can carry an entire hidden ASCII message.
INVISIBLE = re.compile(
    "[­͏؜ᅟᅠ឴឵᠋-᠏"
    "​-‏‪-‮⁠-⁯ㅤ︀-️﻿ﾠ"
    "\U000e0000-\U000e007f\U000e0100-\U000e01ef]"
)

# Cyrillic and Greek letters that are visually identical to ASCII letters.
# NFKC does not fold these, so they are mapped explicitly.
CONFUSABLES = str.maketrans(
    {
        "а": "a", "е": "e", "о": "o", "р": "p", "с": "c",
        "у": "y", "х": "x", "і": "i", "ј": "j", "ѕ": "s",
        "ԁ": "d", "һ": "h", "А": "A", "В": "B", "Е": "E",
        "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P",
        "С": "C", "Т": "T", "Х": "X", "І": "I", "Ј": "J",
        "Ѕ": "S", "ο": "o", "α": "a", "ρ": "p", "ι": "i",
        "κ": "k", "ν": "v", "Ο": "O", "Α": "A", "Β": "B",
        "Ε": "E", "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M",
        "Ν": "N", "Ρ": "P", "Τ": "T", "Χ": "X", "Ζ": "Z",
    }
)


def fold(text: str) -> str:
    """Return ``text`` with compatibility forms, invisibles, and homoglyphs folded.

    Case is preserved so callers that depend on it (camelCase tool names) keep
    working; accented Latin letters are left untouched.
    """
    text = unicodedata.normalize("NFKC", text)
    text = INVISIBLE.sub("", text)
    return text.translate(CONFUSABLES)


def invisible_count(text: str) -> int:
    return len(INVISIBLE.findall(text))
