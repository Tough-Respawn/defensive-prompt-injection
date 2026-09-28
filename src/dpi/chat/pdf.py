"""Extract the visible text of a PDF and report what a reader cannot see.

Requires the optional ``pdfminer.six`` dependency (MIT licensed)::

    pip install "defensive-prompt-injection[pdf]"
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any

from .scan import MAX_EXCERPT, Risk, TextFinding, scan_text


MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 200
MAX_OBJECTS = 100_000

# Below this rendered height (in points) a glyph is unreadable on screen.
MIN_GLYPH_SIZE = 2.0
# Fill colors this close to white are invisible on a white page.
WHITE_THRESHOLD = 0.95
# Text render modes 3 (invisible) and 7 (clip only) paint nothing.
INVISIBLE_RENDER_MODES = {3, 7}

# Finding kinds that show intent when they come from content a reader
# cannot see (hidden text, metadata, annotations, form values).
INTENT_KINDS = {"injection-phrase", "role-marker", "exfiltration-instruction", "hidden-tag-text"}

_LEVEL = {"low": 0, "medium": 1, "high": 2}


class DocumentError(ValueError):
    """The document could not be parsed safely or exceeds a limit."""


@dataclass(frozen=True)
class HiddenSpan:
    page: int
    reason: str
    excerpt: str


@dataclass(frozen=True)
class DocumentFinding:
    kind: str
    location: str
    excerpt: str = ""


@dataclass(frozen=True)
class DocumentScan:
    text: str
    pages: int
    hidden: tuple[HiddenSpan, ...]
    findings: tuple[DocumentFinding, ...]
    risk: Risk


def _is_white(color: Any) -> bool:
    if color is None:
        return False
    values = color if isinstance(color, (list, tuple)) else (color,)
    try:
        values = [float(value) for value in values]
    except (TypeError, ValueError):
        return False
    if len(values) in (1, 3):
        return all(value >= WHITE_THRESHOLD for value in values)
    if len(values) == 4:  # CMYK: no ink at all
        return all(value <= 1 - WHITE_THRESHOLD for value in values)
    return False


def _on_colored_fill(char: Any, fills: list[Any]) -> bool:
    center_x, center_y = (char.x0 + char.x1) / 2, (char.y0 + char.y1) / 2
    return any(
        fill.x0 <= center_x <= fill.x1 and fill.y0 <= center_y <= fill.y1 for fill in fills
    )


def _hidden_reason(
    char: Any, page_box: tuple[float, float, float, float], fills: list[Any]
) -> str | None:
    if getattr(char, "dpi_render_mode", 0) in INVISIBLE_RENDER_MODES:
        return "invisible-render-mode"
    x0, y0, x1, y1 = page_box
    if char.x1 <= x0 or char.x0 >= x1 or char.y1 <= y0 or char.y0 >= y1:
        return "off-page"
    if char.size < MIN_GLYPH_SIZE:
        return "tiny-text"
    # White text is legitimate on a colored shape (table headers, banners).
    if _is_white(getattr(char.graphicstate, "ncolor", None)) and not _on_colored_fill(char, fills):
        return "white-text"
    return None


def _aggregator_class() -> type:
    from pdfminer.converter import PDFPageAggregator

    class Aggregator(PDFPageAggregator):
        """Page aggregator that records the text render mode on each glyph."""

        _dpi_render_mode = 0

        def render_string(self, textstate, seq, ncs, graphicstate):  # type: ignore[no-untyped-def]
            self._dpi_render_mode = textstate.render
            super().render_string(textstate, seq, ncs, graphicstate)

        def render_char(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            advance = super().render_char(*args, **kwargs)
            self.cur_item._objs[-1].dpi_render_mode = self._dpi_render_mode
            return advance

    return Aggregator


def _text_value(value: Any) -> str:
    from pdfminer.pdftypes import resolve1
    from pdfminer.utils import decode_text

    value = resolve1(value)
    if isinstance(value, bytes):
        return decode_text(value)
    if isinstance(value, str):
        return value
    return ""


def _name(value: Any) -> str:
    return str(getattr(value, "name", "") or "")


def _active_content(obj: Any, depth: int = 0) -> set[str]:
    """Find JavaScript and attachments, including inline (direct) dictionaries."""
    kinds: set[str] = set()
    if depth > 8:
        return kinds
    if isinstance(obj, dict):
        if "JS" in obj or _name(obj.get("S")) == "JavaScript":
            kinds.add("javascript")
        if "EF" in obj or _name(obj.get("Type")) == "EmbeddedFile":
            kinds.add("embedded-file")
        values = obj.values()
    elif isinstance(obj, list):
        values = obj
    else:
        return kinds
    for value in values:
        kinds |= _active_content(value, depth + 1)
    return kinds


def _page_text(layout: Any, page_number: int, hidden: list[HiddenSpan]) -> str:
    from pdfminer.layout import LTChar, LTCurve, LTTextContainer, LTTextLine

    box = layout.bbox
    parts: list[str] = []

    def shapes(item: Any):  # type: ignore[no-untyped-def]
        if isinstance(item, LTCurve):  # LTRect and LTLine derive from LTCurve
            yield item
        elif not isinstance(item, LTTextContainer) and hasattr(item, "__iter__"):
            for child in item:
                yield from shapes(child)

    fills = [
        shape
        for shape in shapes(layout)
        if shape.fill and not _is_white(shape.non_stroking_color)
    ]

    def lines(item: Any):  # type: ignore[no-untyped-def]
        if isinstance(item, LTTextLine):
            yield item
        elif isinstance(item, LTTextContainer) or hasattr(item, "__iter__"):
            for child in item:
                yield from lines(child)

    for line in lines(layout):
        current_reason: str | None = None
        buffer: list[str] = []

        def flush() -> None:
            excerpt = " ".join("".join(buffer).split())
            if current_reason and excerpt:
                hidden.append(HiddenSpan(page_number, current_reason, excerpt[:MAX_EXCERPT]))
            buffer.clear()

        for char in line:
            reason = _hidden_reason(char, box, fills) if isinstance(char, LTChar) else current_reason
            if reason:
                if reason != current_reason:
                    flush()
                    current_reason = reason
                buffer.append(char.get_text())
                continue
            if current_reason:
                flush()
                current_reason = None
            parts.append(char.get_text())
        flush()
    return "".join(parts)


def _scan(source: str, location: str, findings: list[DocumentFinding]) -> list[TextFinding]:
    scan = scan_text(source)
    for finding in scan.findings:
        findings.append(DocumentFinding(finding.kind, location, finding.excerpt))
    return list(scan.findings)


def guard_document(
    data: bytes,
    *,
    max_bytes: int = MAX_BYTES,
    max_pages: int = MAX_PAGES,
) -> DocumentScan:
    """Return the visible text of a PDF and what is hidden in it.

    Send ``text`` (visible content only) to the model. ``hidden`` and
    ``findings`` are metadata for the application: warn, refuse, or log.
    Raises :class:`DocumentError` for malformed input or exceeded limits; the
    caller should reject the upload in that case.
    """
    if len(data) > max_bytes:
        raise DocumentError(f"document exceeds {max_bytes} bytes")
    if b"%PDF-" not in data[:1024]:
        raise DocumentError("not a PDF document")

    try:
        from pdfminer.layout import LAParams
        from pdfminer.pdfdocument import PDFDocument
        from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
        from pdfminer.pdfpage import PDFPage
        from pdfminer.pdfparser import PDFParser
        from pdfminer.pdftypes import resolve1
    except ImportError as error:  # pragma: no cover - depends on the environment
        raise ImportError(
            'PDF support requires pdfminer.six: pip install "defensive-prompt-injection[pdf]"'
        ) from error

    hidden: list[HiddenSpan] = []
    findings: list[DocumentFinding] = []
    concealed: list[TextFinding] = []
    page_texts: list[str] = []
    risk = 0

    try:
        document = PDFDocument(PDFParser(BytesIO(data)))
        resources = PDFResourceManager()
        device = _aggregator_class()(resources, laparams=LAParams())
        interpreter = PDFPageInterpreter(resources, device)

        for number, page in enumerate(PDFPage.create_pages(document), start=1):
            if number > max_pages:
                raise DocumentError(f"document exceeds {max_pages} pages")
            interpreter.process_page(page)
            hidden_before = len(hidden)
            page_texts.append(_page_text(device.get_result(), number, hidden))
            page_hidden = " ".join(span.excerpt for span in hidden[hidden_before:])
            if page_hidden:
                concealed += _scan(page_hidden, f"hidden:page-{number}", findings)
            for annotation in resolve1(page.annots) or []:
                annotation = resolve1(annotation)
                if isinstance(annotation, dict):
                    concealed += _scan(
                        _text_value(annotation.get("Contents")), f"annotation:page-{number}", findings
                    )

        for info in document.info:
            for key, value in info.items():
                concealed += _scan(_text_value(value), f"metadata:{key}", findings)

        form = resolve1(document.catalog.get("AcroForm"))
        for field in resolve1(form.get("Fields")) if isinstance(form, dict) else []:
            field = resolve1(field)
            if isinstance(field, dict):
                name = _text_value(field.get("T")) or "unnamed"
                concealed += _scan(_text_value(field.get("V")), f"form-field:{name}", findings)

        seen: set[str] = set()
        checked = 0
        for xref in document.xrefs:
            for object_id in xref.get_objids():
                checked += 1
                if checked > MAX_OBJECTS:
                    raise DocumentError(f"document exceeds {MAX_OBJECTS} objects")
                try:
                    obj = document.getobj(object_id)
                except Exception:  # noqa: BLE001 - unresolved objects are skipped
                    continue
                seen |= _active_content(getattr(obj, "attrs", obj))
        for kind in sorted(seen):
            findings.append(DocumentFinding(kind, "document"))
            risk = max(risk, _LEVEL["medium"])
    except DocumentError:
        raise
    except Exception as error:  # noqa: BLE001 - any parser failure fails closed
        raise DocumentError(f"unreadable PDF: {type(error).__name__}") from error

    if not page_texts:
        raise DocumentError("document has no pages")

    visible_parts = []
    for number, page_text in enumerate(page_texts, start=1):
        scan = scan_text(page_text)
        visible_parts.append(scan.text)
        risk = max(risk, _LEVEL[scan.risk])
        findings.extend(DocumentFinding(f.kind, f"page-{number}", f.excerpt) for f in scan.findings)

    if hidden:
        risk = max(risk, _LEVEL["medium"])
    if any(finding.kind in INTENT_KINDS for finding in concealed):
        risk = _LEVEL["high"]

    return DocumentScan(
        text="\n\n".join(part.strip() for part in visible_parts),
        pages=len(page_texts),
        hidden=tuple(hidden),
        findings=tuple(findings),
        risk=next(level for level, value in _LEVEL.items() if value == risk),  # type: ignore[arg-type]
    )
