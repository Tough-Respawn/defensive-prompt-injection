"""Guards for chatbots that ingest untrusted documents.

Unlike the harness adapters, these helpers are called by the application
itself: before a document reaches the model, when it is placed in the prompt,
and before the model's answer is rendered.
"""

from .output import OutputFinding, OutputResult, guard_output, new_canary
from .pdf import DocumentError, DocumentFinding, DocumentScan, HiddenSpan, guard_document
from .prompt import UntrustedBlock, wrap_untrusted
from .scan import TextFinding, TextScan, scan_text

__all__ = [
    "DocumentError",
    "DocumentFinding",
    "DocumentScan",
    "HiddenSpan",
    "OutputFinding",
    "OutputResult",
    "TextFinding",
    "TextScan",
    "UntrustedBlock",
    "guard_document",
    "guard_output",
    "new_canary",
    "scan_text",
    "wrap_untrusted",
]
