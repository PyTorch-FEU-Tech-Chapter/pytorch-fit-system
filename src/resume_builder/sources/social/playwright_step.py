"""Visible, slow, per-post step-through for the social scraper.

Unlike ``playwright_debug`` (passive highlighting), this module *mutates* the live
DOM: it walks the first N collected posts one at a time and **deletes** their comment
sections so the user can watch what content actually remains as the post text.

Enabled only when ``RESUME_BUILD_PLAYWRIGHT_STEP_LIMIT`` is a positive integer — off
(0) by default. The long per-step pause is decoupled from the global ``slow_mo`` so
the scroll-collect phase isn't crawled to a halt.
"""

from __future__ import annotations

import logging
import os

from .playwright_debug import PlaywrightVisualDebug, pause, visual_debug_from_env

log = logging.getLogger(__name__)

_POST_COLOR = "#ff2d75"   # red   — the whole post being scraped
_TEXT_COLOR = "#22c55e"   # green — the cleaned text source
_COMMENT_COLOR = "#ff7a18"  # orange — comments about to be deleted

# Highlight a single article element and label it (persists through the pause; the
# next step overwrites the outline).
_HIGHLIGHT_EL_JS = """
(el, { color, label }) => {
  try { el.scrollIntoView({ block: "center", inline: "center", behavior: "smooth" }); } catch (e) {}
  el.style.transition = "outline 120ms ease, box-shadow 120ms ease";
  el.style.outline = `4px solid ${color}`;
  el.style.boxShadow = `0 0 0 6px ${color}55`;
  if (label) el.setAttribute("data-resume-build-step", label);
  return true;
}
"""

# Flash the comment / chrome nodes that are about to be removed, so the deletion is
# visible rather than instantaneous. Shared posts are preserved: only articles whose
# aria-label marks them as a comment/reply are targeted (chrome is buttons/svg/etc.).
_FLASH_DOOMED_JS = """
(el, { color }) => {
  const comments = Array.from(el.querySelectorAll('[role="article"]')).filter(n => {
    const label = n.getAttribute('aria-label') || '';
    return /^\\s*comment by/i.test(label) || /^\\s*reply by/i.test(label);
  });
  const chrome = Array.from(el.querySelectorAll(
    '[role="button"], [role="toolbar"], form, svg, [data-visualcompletion="ignore"]'));
  for (const n of [...comments, ...chrome]) {
    n.style.outline = `4px solid ${color}`;
    n.style.boxShadow = `0 0 0 6px ${color}55`;
  }
  return comments.length;
}
"""

# Actually remove the comment articles + chrome from the live DOM. Returns how many
# comment articles were deleted (shared posts are never matched, so never removed).
_DELETE_DOOMED_JS = """
el => {
  let removed = 0;
  el.querySelectorAll('[role="article"]').forEach(n => {
    const label = n.getAttribute('aria-label') || '';
    if (/^\\s*comment by/i.test(label) || /^\\s*reply by/i.test(label)) {
      n.remove();
      removed++;
    }
  });
  el.querySelectorAll(
    '[role="button"], [role="toolbar"], form, svg, [data-visualcompletion="ignore"]'
  ).forEach(n => n.remove());
  return removed;
}
"""


def step_limit_from_env() -> int:
    """How many posts to walk in slow step mode. 0 (default) disables step mode."""
    return _int_env("RESUME_BUILD_PLAYWRIGHT_STEP_LIMIT", 0)


def step_delay_ms_from_env() -> int:
    """Pause (ms) held on each step so the user can follow along. Default 5s."""
    return _int_env("RESUME_BUILD_PLAYWRIGHT_STEP_DELAY_MS", 5000)


def step_through_articles(
    page,
    selector: str,
    *,
    limit: int | None = None,
    debug: PlaywrightVisualDebug | None = None,
) -> int:
    """Slowly walk the first ``limit`` posts, deleting their comments on the live page.

    For each post: outline it red (the post), then green (the text source), then flash
    its comments orange and delete them from the DOM. Returns the number of posts
    stepped through. A no-op when ``limit`` resolves to 0.
    """
    limit = step_limit_from_env() if limit is None else limit
    if limit <= 0:
        return 0

    debug = debug or visual_debug_from_env()
    delay_ms = step_delay_ms_from_env()

    try:
        articles = page.query_selector_all(selector) or []
    except Exception as exc:  # noqa: BLE001 - page/browser closed
        log.info("step-through skipped (page closed?): %s", exc)
        return 0

    stepped = 0
    for index, article in enumerate(articles[:limit]):
        try:
            _step_one(page, article, index, debug=debug, delay_ms=delay_ms)
            stepped += 1
        except Exception as exc:  # noqa: BLE001 - one bad card shouldn't abort the walk
            log.debug("step-through failed on article %d: %s", index, exc)
    log.info("step-through walked %d post(s)", stepped)
    return stepped


def _step_one(
    page,
    article,
    index: int,
    *,
    debug: PlaywrightVisualDebug,
    delay_ms: int,
) -> None:
    # 1. The whole post.
    article.evaluate(_HIGHLIGHT_EL_JS, {"color": _POST_COLOR, "label": f"POST #{index + 1} being scraped"})
    pause(page, debug=debug, ms=delay_ms)

    # 2. The cleaned text source (same region — matches current extraction).
    article.evaluate(_HIGHLIGHT_EL_JS, {"color": _TEXT_COLOR, "label": "text source"})
    pause(page, debug=debug, ms=delay_ms)

    # 3. Comments hit -> flash, then delete from the DOM so focus is visible.
    article.evaluate(_FLASH_DOOMED_JS, {"color": _COMMENT_COLOR})
    pause(page, debug=debug, ms=delay_ms)
    removed = article.evaluate(_DELETE_DOOMED_JS)
    log.debug("deleted %s comment article(s) from post #%d", removed, index + 1)
    pause(page, debug=debug, ms=delay_ms)


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default
