"""Guards for chatbots that ingest untrusted documents.

Unlike the harness adapters, these helpers are called by the application
itself: before a document reaches the model, when it is placed in the prompt,
and before the model's answer is rendered.
"""

from .output import OutputFinding, OutputResult, guard_output, new_canary
from .prompt import UntrustedBlock, wrap_untrusted

__all__ = [
    "OutputFinding",
    "OutputResult",
    "UntrustedBlock",
    "guard_output",
    "new_canary",
    "wrap_untrusted",
]
