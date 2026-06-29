from __future__ import annotations

from .fetch import SourceFetcher
from .models import DEFAULT_CAP_CHARS, CleanedSource
from .rules import ExtractionRuleEngine, apply_rules


def extract_website(
    url: str,
    fetcher: SourceFetcher,
    engine: ExtractionRuleEngine,
    cap_chars: int = DEFAULT_CAP_CHARS,
) -> CleanedSource:
    """Fetch a page, learn/apply its extraction rule, return token-capped CleanedSource."""
    html, degraded = fetcher.fetch(url)
    rule = engine.rules_for(url, html)
    text = apply_rules(html, rule)
    truncated = len(text) > cap_chars
    return CleanedSource(
        source_id=url,
        kind="website",
        text=text[:cap_chars],
        truncated=truncated,
        degraded=degraded or not text.strip(),
    )
