"""Visible, slow, per-post step-through for the social scraper.

Unlike ``playwright_debug`` (passive highlighting), this module *mutates* the live
DOM: it walks the first N collected posts one at a time and aggressively **deletes**
everything that won't be read — comments, action chrome, and media — so the only
thing left inside each post is the text the scraper actually extracts. This is a
visualization aid: it makes "what does the scraper focus on?" literally visible.

Four stages per post:
  1. POST     — outline the whole post (red): "this is all I look at".
  2. COMMENTS — flash + delete the comment section (orange): ignored.
  3. TEXT     — strip media/chrome too, outline what remains (green): the read text.
  4. SHARED   — if this is a reshare, outline the shared post (blue) as PRESERVED.

Enabled only when ``RESUME_BUILD_PLAYWRIGHT_STEP_LIMIT`` is a positive integer — off
(0) by default. The long per-step pause is decoupled from the global ``slow_mo`` so
the scroll-collect phase isn't crawled to a halt.
"""

from __future__ import annotations

import logging
import os

from .playwright_debug import PlaywrightVisualDebug, pause, visual_debug_from_env

log = logging.getLogger(__name__)

_POST_COLOR = "#ff2d75"     # red    — the whole post being scraped
_COMMENT_COLOR = "#ff7a18"  # orange — comments about to be deleted
_TEXT_COLOR = "#22c55e"     # green  — the text that remains after stripping
_SHARED_COLOR = "#3b82f6"   # blue   — a reshared post, preserved (never deleted)

# Outline + label a single element (persists through the pause; the next step
# overwrites it). Scrolls the element into view so the user can follow along.
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

# Remove the comment articles + action chrome from the live DOM. Returns how many
# comment articles were deleted (shared posts are never matched, so never removed).
_DELETE_COMMENTS_JS = """
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

# Strip non-text media so only the readable text is left inside the post. Media inside
# a preserved shared post is intentionally left alone so its context survives.
_STRIP_MEDIA_JS = """
el => {
  const shared = Array.from(el.querySelectorAll('[role="article"]')).find(n => {
    const label = n.getAttribute('aria-label') || '';
    return !/^\\s*comment by/i.test(label) && !/^\\s*reply by/i.test(label);
  });
  let removed = 0;
  el.querySelectorAll('img, video, image, [role="img"], svg').forEach(n => {
    if (shared && shared.contains(n)) return;  // keep the reshared post's media
    n.remove();
    removed++;
  });
  return removed;
}
"""

# Outline a nested reshared post (a nested article that is NOT a comment) so the user
# sees it is preserved, not deleted. Returns true when a shared post is present.
_MARK_SHARED_JS = """
(el, { color }) => {
  const shared = Array.from(el.querySelectorAll('[role="article"]')).find(n => {
    const label = n.getAttribute('aria-label') || '';
    return !/^\\s*comment by/i.test(label) && !/^\\s*reply by/i.test(label);
  });
  if (!shared) return false;
  shared.style.outline = `4px solid ${color}`;
  shared.style.boxShadow = `0 0 0 6px ${color}55`;
  shared.setAttribute('data-resume-build-step', 'SHARED (preserved)');
  return true;
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
    """Slowly walk the first ``limit`` posts, stripping each down to its text live.

    Returns the number of posts stepped through. A no-op when ``limit`` resolves to 0.
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
    n = index + 1

    # 1. The whole post — "this is all I look at".
    article.evaluate(_HIGHLIGHT_EL_JS, {"color": _POST_COLOR, "label": f"POST #{n} — ito lang ang titingin"})
    pause(page, debug=debug, ms=delay_ms)

    # 2. Comments hit -> flash, then delete from the DOM so they're visibly ignored.
    article.evaluate(_FLASH_DOOMED_JS, {"color": _COMMENT_COLOR})
    pause(page, debug=debug, ms=delay_ms)
    removed = article.evaluate(_DELETE_COMMENTS_JS)
    log.debug("post #%d: deleted %s comment article(s)", n, removed)
    pause(page, debug=debug, ms=delay_ms)

    # 3. Strip media/chrome too -> only the readable TEXT remains.
    stripped = article.evaluate(_STRIP_MEDIA_JS)
    log.debug("post #%d: stripped %s media node(s)", n, stripped)
    article.evaluate(_HIGHLIGHT_EL_JS, {"color": _TEXT_COLOR, "label": "natitirang TEXT — ito lang kinukuha"})
    pause(page, debug=debug, ms=delay_ms)

    # 4. Shared post (if any) — preserved, never deleted.
    has_shared = article.evaluate(_MARK_SHARED_JS, {"color": _SHARED_COLOR})
    if has_shared:
        log.debug("post #%d: shared post preserved", n)
        pause(page, debug=debug, ms=delay_ms)


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default
