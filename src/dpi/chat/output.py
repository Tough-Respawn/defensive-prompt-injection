"""Sanitize a chatbot answer before it is rendered to the user."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import re
import secrets
from urllib.parse import urlsplit

from ..policy import URL_EXFIL
from ..textfold import fold


IMAGE_REMOVED = "[external image removed]"
LINK_REMOVED = "[link removed]"

MARKDOWN_IMAGE = re.compile(
    r"!\[[^\]\r\n]*\]\(\s*<?((?:https?:)?//[^)\s>]+)>?(?:\s+[\"'][^\"'\r\n]*[\"'])?\s*\)",
    re.IGNORECASE,
)
REFERENCE_IMAGE = re.compile(r"!\[[^\]\r\n]*\]\[[^\]\r\n]+\]")
HTML_IMAGE = re.compile(
    r"<img\b[^>]*\bsrc\s*=\s*[\"']?\s*((?:https?:)?//[^\s\"'>]+)[^>]*>", re.IGNORECASE
)
MARKDOWN_LINK = re.compile(
    r"\[([^\]\r\n]*)\]\(\s*<?((?:https?:)?//[^)\s>]+)>?(?:\s+[\"'][^\"'\r\n]*[\"'])?\s*\)",
    re.IGNORECASE,
)
REFERENCE_DEFINITION = re.compile(
    r"^[ \t]{0,3}\[[^\]\r\n]+\]:[ \t]*<?((?:https?:)?//[^\s>]+)>?[^\r\n]*$",
    re.IGNORECASE | re.MULTILINE,
)
HTML_LINK = re.compile(
    r"<a\b[^>]*\bhref\s*=\s*[\"']?\s*((?:https?:)?//[^\s\"'>]+)[^>]*>(.*?)</a\s*>",
    re.IGNORECASE | re.DOTALL,
)
AUTOLINK = re.compile(r"<((?:https?:)?//[^>\s]+)>", re.IGNORECASE)
# Trailing sentence punctuation is not part of a bare URL.
BARE_URL = re.compile(
    r"(?<![(<\"'=\w/])https?://[^\s<>()\"']*[^\s<>()\"'.,;:!?]", re.IGNORECASE
)

# Longer query strings are an easy carrier for encoded conversation data.
MAX_QUERY_LENGTH = 64


@dataclass(frozen=True)
class OutputFinding:
    kind: str
    host: str = ""


@dataclass(frozen=True)
class OutputResult:
    text: str
    findings: tuple[OutputFinding, ...]
    canary_leaked: bool

    @property
    def blocked(self) -> bool:
        """True when the answer should not be shown at all."""
        return self.canary_leaked


def new_canary() -> str:
    """Return a random marker to embed in the system prompt.

    The marker has no meaning to the model; if it ever appears in an answer,
    the system prompt leaked.
    """
    return f"dpi-canary-{secrets.token_hex(8)}"


def _host(url: str) -> str:
    try:
        return urlsplit(url if "://" in url[:10] else f"https:{url}").hostname or ""
    except ValueError:
        return ""


def _host_allowed(host: str, allowed_hosts: Iterable[str]) -> bool:
    for allowed in allowed_hosts:
        allowed = allowed.lower().strip(".")
        if host == allowed or host.endswith(f".{allowed}"):
            return True
    return False


def guard_output(
    text: str,
    allowed_hosts: Iterable[str] | None = None,
    canary: str | None = None,
) -> OutputResult:
    """Remove data-exfiltration channels from ``text``.

    External images are always removed because chat clients fetch them without
    any click. Links are kept when their host is in ``allowed_hosts`` (a host
    also allows its subdomains). Without an allowlist, only links whose query
    looks like a data payload are neutralized.
    """
    allowlist = None if allowed_hosts is None else tuple(allowed_hosts)
    findings: list[OutputFinding] = []

    canary_leaked = bool(canary) and canary in fold(text)
    if canary_leaked:
        text = fold(text).replace(canary, "[redacted]")
        findings.append(OutputFinding("canary-leak"))

    def link_is_safe(url: str) -> bool:
        host = _host(url)
        if allowlist is not None:
            return _host_allowed(host, allowlist)
        parts = urlsplit(url if "://" in url[:10] else f"https:{url}")
        payload = f"{parts.query}{parts.fragment}"
        return not (URL_EXFIL.search(url) or len(payload) > MAX_QUERY_LENGTH)

    def link_kind() -> str:
        return "suspicious-link" if allowlist is None else "disallowed-link"

    def drop_image(match: re.Match[str]) -> str:
        findings.append(OutputFinding("external-image", _host(match.group(1))))
        return IMAGE_REMOVED

    def drop_reference_image(_match: re.Match[str]) -> str:
        findings.append(OutputFinding("external-image"))
        return IMAGE_REMOVED

    def keep_label(match: re.Match[str]) -> str:
        label, url = match.group(1), match.group(2)
        if link_is_safe(url):
            return match.group(0)
        findings.append(OutputFinding(link_kind(), _host(url)))
        return label

    def keep_html_label(match: re.Match[str]) -> str:
        url, label = match.group(1), match.group(2)
        if link_is_safe(url):
            return match.group(0)
        findings.append(OutputFinding(link_kind(), _host(url)))
        return label

    def drop_url(match: re.Match[str]) -> str:
        url = match.group(1) if match.re.groups else match.group(0)
        if link_is_safe(url):
            return match.group(0)
        findings.append(OutputFinding(link_kind(), _host(url)))
        return LINK_REMOVED

    text = MARKDOWN_IMAGE.sub(drop_image, text)
    text = HTML_IMAGE.sub(drop_image, text)
    text = REFERENCE_IMAGE.sub(drop_reference_image, text)
    text = MARKDOWN_LINK.sub(keep_label, text)
    text = HTML_LINK.sub(keep_html_label, text)
    text = REFERENCE_DEFINITION.sub(drop_url, text)
    text = AUTOLINK.sub(drop_url, text)
    text = BARE_URL.sub(drop_url, text)

    return OutputResult(text=text, findings=tuple(findings), canary_leaked=canary_leaked)
