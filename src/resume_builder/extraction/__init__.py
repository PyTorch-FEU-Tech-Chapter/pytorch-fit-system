"""P2 — website-agnostic extraction package."""
from __future__ import annotations

from .fetch import SourceFetcher
from .github_traversal import collect_repo_markdown
from .models import CHARS_PER_TOKEN, DEFAULT_CAP_CHARS, DEFAULT_TOKEN_CAP, CleanedSource, apply_token_cap
from .rules import ExtractionRuleEngine, apply_rules
from .web import extract_website

__all__ = [
    "CleanedSource",
    "CHARS_PER_TOKEN",
    "DEFAULT_TOKEN_CAP",
    "DEFAULT_CAP_CHARS",
    "SourceFetcher",
    "ExtractionRuleEngine",
    "apply_rules",
    "collect_repo_markdown",
    "extract_website",
    "apply_token_cap",
]
