"""Flag model-directed instructions hidden in untrusted text."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

from ..textfold import INVISIBLE, fold


Risk = Literal["low", "medium", "high"]

MAX_EXCERPT = 160

# Tag characters U+E0020..U+E007E mirror printable ASCII and are invisible in
# most renderers, yet models read them as text.
TAG_RUN = re.compile("[\U000e0020-\U000e007e]+")

_APOSTROPHE = "['’]"

INJECTION_PHRASES = [
    # English
    r"\b(?:ignore|disregard|forget|override|bypass)\s+(?:(?:all|any|the|your|of|these|those)\s+)*"
    r"(?:(?:previous|prior|above|earlier|preceding|former|system|original|initial)\s+)?"
    r"(?:instructions?|prompts?|rules|directions|guidelines|messages)\b",
    r"\byou\s+are\s+now\b",
    r"\bfrom\s+now\s+on\s*,?\s+(?:you|respond|answer|reply|always|only|ignore)\b",
    r"\bpretend\s+(?:to\s+be|you\s+are)\b",
    r"\bnew\s+(?:system\s+)?instructions?\s*:",
    r"\b(?:do\s+not|don" + _APOSTROPHE + r"t|never)\s+(?:tell|inform|mention\s+(?:it\s+)?to|reveal\s+(?:it\s+)?to|let)\s+the\s+user\b",
    r"\b(?:reveal|print|repeat|show|output)\s+(?:me\s+)?(?:your|the)\s+(?:system\s+prompt|instructions|initial\s+prompt|hidden\s+prompt)\b",
    # French
    r"(?<!pas\s)\b(?:ignore[rz]?|oublie[rz]?|néglige[rz]?)\s+(?:(?:toutes|tous|toute|les|tes|vos|ces)\s+|l" + _APOSTROPHE + r")*"
    r"(?:instructions?|consignes?|règles|directives|indications)\b",
    r"\b(?:tu\s+es|vous\s+êtes)\s+(?:désormais|maintenant|dorénavant)\b",
    r"\b(?:à|a)\s+partir\s+de\s+maintenant\s*,?\s+(?:tu|vous|réponds|répondez|dis|dites|ignore|ignorez)\b",
    r"\bdorénavant\s*,?\s+(?:tu|vous|réponds|répondez)\b",
    r"\bne\s+(?:le\s+|lui\s+)?(?:dis|dites|mentionne[sz]?|signale[sz]?|révèle[sz]?|informe[sz]?)\s+(?:pas|jamais|rien)\s+"
    r"(?:à\s+)?(?:l" + _APOSTROPHE + r"utilisateur|au\s+client|à\s+l" + _APOSTROPHE + r"utilisateur)",
    r"\b(?:révèle[rz]?|affiche[rz]?|répète[rz]?|donne[rz]?)\s+(?:moi\s+)?(?:ton|votre|le|tes|vos)\s+"
    r"(?:prompt\s+système|prompt|instructions\s+(?:système|initiales))\b",
    r"\bnouvelles?\s+(?:instructions?|consignes?)\s*:",
]

ROLE_MARKERS = [
    r"^[ \t]*(?:#{1,4}[ \t]*)?(?:system|assistant|developer)[ \t]*:",
    r"<\|(?:im_start|im_end|system|user|assistant|endoftext)\|>",
    r"\[/?inst\]",
    r"</?(?:system|assistant|instructions?)>",
]

EXFILTRATION = [
    r"!\[[^\]\r\n]*\]\(\s*<?(?:https?:)?//",
    r"<img\b[^>]*\bsrc\s*=\s*[\"']?\s*(?:https?:)?//",
    r"\b(?:send|post|upload|forward|transmit|envoie[rz]?|transmet[sz]?|transmettre|poste[rz]?)\b"
    r"[^\r\n]{0,80}?\b(?:to|à|vers|sur)\s+(?:https?:)?//",
]

INJECTION_PATTERNS = [re.compile(p, re.IGNORECASE) for p in INJECTION_PHRASES]
ROLE_PATTERNS = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in ROLE_MARKERS]
EXFILTRATION_PATTERNS = [re.compile(p, re.IGNORECASE) for p in EXFILTRATION]

# Weight per distinct finding kind. Soft hyphens and zero-width joiners are
# common in extracted PDF text, so invisible characters alone stay low risk.
WEIGHTS = {
    "hidden-tag-text": 4,
    "exfiltration-instruction": 3,
    "injection-phrase": 2,
    "role-marker": 2,
    "invisible-characters": 1,
}


@dataclass(frozen=True)
class TextFinding:
    kind: str
    excerpt: str = ""


@dataclass(frozen=True)
class TextScan:
    text: str
    findings: tuple[TextFinding, ...]
    risk: Risk
    score: int


def _excerpt(text: str, start: int, end: int) -> str:
    snippet = " ".join(text[max(0, start - 40) : end + 40].split())
    return snippet[:MAX_EXCERPT]


def _risk(score: int) -> Risk:
    if score >= 4:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


def scan_text(text: str) -> TextScan:
    """Scan untrusted text before it is given to a model.

    ``text`` in the result has invisible characters removed but is otherwise
    unchanged; matching itself runs on a folded copy so that zero-width and
    homoglyph obfuscation cannot hide a phrase.
    """
    findings: list[TextFinding] = []

    for run in TAG_RUN.finditer(text):
        decoded = "".join(chr(ord(char) - 0xE0000) for char in run.group(0))
        findings.append(TextFinding("hidden-tag-text", decoded[:MAX_EXCERPT]))

    other_invisible = len(INVISIBLE.findall(TAG_RUN.sub("", text)))
    if other_invisible:
        findings.append(TextFinding("invisible-characters", f"{other_invisible} characters"))

    folded = fold(text)
    for kind, patterns in (
        ("injection-phrase", INJECTION_PATTERNS),
        ("role-marker", ROLE_PATTERNS),
        ("exfiltration-instruction", EXFILTRATION_PATTERNS),
    ):
        for pattern in patterns:
            for match in pattern.finditer(folded):
                findings.append(TextFinding(kind, _excerpt(folded, match.start(), match.end())))

    score = sum(WEIGHTS[kind] for kind in {finding.kind for finding in findings})
    return TextScan(
        text=INVISIBLE.sub("", text),
        findings=tuple(findings),
        risk=_risk(score),
        score=score,
    )
