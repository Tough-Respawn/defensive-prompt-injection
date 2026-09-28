"""Build tiny PDFs in memory for tests, without any PDF library.

Each hiding technique is written explicitly in the content stream, so a
reader of the tests can see exactly what the fixture contains.
"""

from __future__ import annotations


def pdf_string(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return f"({escaped})"


def text_op(text: str, *, x: float = 72, y: float = 700, size: float = 12, prefix: str = "") -> str:
    """One BT/ET text object; ``prefix`` holds color or render-mode operators."""
    return f"BT {prefix} /F1 {size} Tf {x} {y} Td {pdf_string(text)} Tj ET"


def build_pdf(
    pages: list[list[str]],
    *,
    info: dict[str, str] | None = None,
    annotation: str | None = None,
    form_value: str | None = None,
    javascript: str | None = None,
    attachment: bytes | None = None,
) -> bytes:
    objects: list[str | tuple[str, bytes]] = []

    def add(obj: str | tuple[str, bytes]) -> int:
        objects.append(obj)
        return len(objects)

    catalog = add("")  # filled in last
    pages_ref = add("")
    font = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")

    annot_ref = None
    if annotation is not None:
        annot_ref = add(
            f"<< /Type /Annot /Subtype /Text /Rect [10 10 20 20] /Contents {pdf_string(annotation)} >>"
        )

    kids = []
    for index, operations in enumerate(pages):
        stream = "\n".join(operations).encode("latin-1")
        content = add((f"<< /Length {len(stream)} >>", stream))
        annots = f" /Annots [{annot_ref} 0 R]" if annot_ref and index == 0 else ""
        kids.append(
            add(
                f"<< /Type /Page /Parent {pages_ref} 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font} 0 R >> >> /Contents {content} 0 R{annots} >>"
            )
        )
    objects[pages_ref - 1] = (
        f"<< /Type /Pages /Kids [{' '.join(f'{kid} 0 R' for kid in kids)}] /Count {len(kids)} >>"
    )

    extras = ""
    if form_value is not None:
        field = add(f"<< /FT /Tx /T (note) /V {pdf_string(form_value)} >>")
        extras += f" /AcroForm << /Fields [{field} 0 R] >>"
    if javascript is not None:
        extras += f" /OpenAction << /S /JavaScript /JS {pdf_string(javascript)} >>"
    if attachment is not None:
        embedded = add((f"<< /Type /EmbeddedFile /Length {len(attachment)} >>", attachment))
        spec = add(f"<< /Type /Filespec /F (payload.txt) /EF << /F {embedded} 0 R >> >>")
        extras += f" /Names << /EmbeddedFiles << /Names [(payload.txt) {spec} 0 R] >> >>"
    objects[catalog - 1] = f"<< /Type /Catalog /Pages {pages_ref} 0 R{extras} >>"

    info_ref = None
    if info:
        entries = " ".join(f"/{key} {pdf_string(value)}" for key, value in info.items())
        info_ref = add(f"<< {entries} >>")

    output = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n".encode()
        if isinstance(obj, tuple):
            header, stream = obj
            output += header.encode("latin-1") + b"\nstream\n" + stream + b"\nendstream"
        else:
            output += obj.encode("latin-1")
        output += b"\nendobj\n"
    xref = len(output)
    output += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        output += f"{offset:010d} 00000 n \n".encode()
    trailer_info = f" /Info {info_ref} 0 R" if info_ref else ""
    output += (
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R{trailer_info} >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode()
    return bytes(output)
