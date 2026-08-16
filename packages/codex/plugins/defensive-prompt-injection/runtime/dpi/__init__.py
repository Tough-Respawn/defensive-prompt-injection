"""Harness-neutral defensive prompt-injection policy engine."""

from .model import Action, Decision
from .policy import evaluate

__all__ = ["Action", "Decision", "evaluate"]
__version__ = "0.4.0.dev0"
