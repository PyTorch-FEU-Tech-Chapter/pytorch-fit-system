"""Diagnostic: open the FB profile in visible Chromium, scroll slowly while logging
article growth, then for each article probe several candidate post-body selectors so
we can see which one yields a clean post message (vs. the whole article inner_text
which carries comments + the reaction bar).

Writes a screenshot + a diagnostics JSON to out/. Scratch tool — not packaged.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HANDLE = "your.facebook.handle"
URL = f"https://www.facebook.com/{HANDLE}"
SHOT = Path("out/fb_profile_shot.png")
DIAG = Path("out/fb_diagnostics.json")

# Candidate selectors FB has used for the actual post message body.
BODY_SELECTORS = [
    '[data-ad-preview="message"]',
    '[data-ad-comet-preview="message"]',
    '[data-ad-rendering-role="story_message"]',
    'div[dir="auto"][style*="text-align"]',
]


def _say(msg: str) -> None:
    print(msg, flush=True)


def main() -> int:
    try:
        from resume_builder.sources.social.auth import SessionStore
        from resume_builder.sources.social.headless_browser import PlaywrightSession
    except Exception as exc:  # noqa: BLE001
        _say(f"[diag] import failed: {exc!r}")
        return 3

    store = SessionStore()
    diagnostics: dict = {"url": URL, "scroll_log": [], "articles": []}

    with PlaywrightSession("facebook", headless=False, store=store) as page:
        _say(f"[diag] goto {URL}")
        page.goto(URL, wait_until="domcontentloaded")
        try:
            page.wait_for_selector("div[role='main']", timeout=25_000)
        except Exception as exc:  # noqa: BLE001
            _say(f"[diag] main feed never rendered: {exc}")

        # Slow scroll with generous settle; log growth each pass.
        last = -1
        flat = 0
        for i in range(40):
            count = len(page.query_selector_all("div[role='article']") or [])
            diagnostics["scroll_log"].append({"pass": i, "articles": count})
            _say(f"[diag] scroll {i}: {count} articles")
            if count == last:
                flat += 1
                if flat >= 6:  # tolerate slow lazy-load before giving up
                    _say("[diag] no growth for 6 passes — stopping scroll")
                    break
            else:
                flat = 0
                last = count
            page.evaluate("window.scrollBy(0, window.innerHeight * 0.9)")
            page.wait_for_timeout(2500)

        page.screenshot(path=str(SHOT), full_page=False)
        _say(f"[diag] screenshot -> {SHOT}")

        articles = page.query_selector_all("div[role='article']") or []
        _say(f"[diag] probing {len(articles)} articles for body selectors")
        for idx, art in enumerate(articles):
            entry: dict = {"index": idx}
            try:
                entry["inner_text_len"] = len((art.inner_text() or ""))
                entry["inner_text_head"] = (art.inner_text() or "").replace("\n", " ")[:160]
            except Exception as exc:  # noqa: BLE001
                entry["inner_text_error"] = repr(exc)
            for sel in BODY_SELECTORS:
                try:
                    el = art.query_selector(sel)
                    if el:
                        txt = (el.inner_text() or "").replace("\n", " ").strip()
                        entry[sel] = txt[:200]
                except Exception as exc:  # noqa: BLE001
                    entry[sel] = f"ERR {exc!r}"
            diagnostics["articles"].append(entry)

    DIAG.parent.mkdir(parents=True, exist_ok=True)
    DIAG.write_text(json.dumps(diagnostics, indent=2, ensure_ascii=False), encoding="utf-8")
    _say(f"[diag] diagnostics -> {DIAG}")
    _say(f"[diag] DONE: {len(diagnostics['articles'])} articles, "
         f"final scroll count {diagnostics['scroll_log'][-1]['articles'] if diagnostics['scroll_log'] else 0}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
