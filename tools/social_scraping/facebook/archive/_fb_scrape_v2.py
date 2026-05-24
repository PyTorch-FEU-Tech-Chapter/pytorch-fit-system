"""Improved FB own-posts scrape that fixes the two structural bugs found in
diagnostics:

1. The feed is VIRTUALIZED — role=article nodes are recycled as you scroll, so
   querying once at the end only sees the last ~5. Fix: accumulate at every scroll
   step into a dict keyed by permalink/text-hash.

2. role=article matches COMMENTS too (they're nested inside a post's article). Fix:
   keep only TOP-LEVEL articles (no role=article ancestor) and pull the story
   message body, not the whole inner_text (which carries the reaction bar +
   comment threads).

Scratch tool — not packaged. Writes out/facebook.json + progress to stdout.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

HANDLE = "your.facebook.handle"
URL = f"https://www.facebook.com/{HANDLE}"
OUT = Path("out/facebook.json")
MAX_SCROLLS = 50
SETTLE_MS = 2500

# JS: is this article top-level (i.e. a post, not a nested comment)?
_IS_TOP_LEVEL = """
(node) => {
  let p = node.parentElement;
  while (p) {
    if (p.getAttribute && p.getAttribute('role') === 'article') return false;
    p = p.parentElement;
  }
  return true;
}
"""

# JS: extract the post body text from a top-level article, skipping the reaction
# bar and comments. Prefers FB's known story-message containers; falls back to the
# longest dir="auto" text block above the comment region.
_EXTRACT_BODY = """
(node) => {
  const sels = [
    '[data-ad-rendering-role="story_message"]',
    '[data-ad-comet-preview="message"]',
    '[data-ad-preview="message"]',
  ];
  for (const s of sels) {
    const el = node.querySelector(s);
    if (el && el.innerText && el.innerText.trim().length > 0) {
      return el.innerText.trim();
    }
  }
  // Fallback: longest dir=auto block (post text is usually the largest one).
  let best = '';
  node.querySelectorAll('div[dir="auto"]').forEach(d => {
    const t = (d.innerText || '').trim();
    if (t.length > best.length) best = t;
  });
  return best;
}
"""

_PERMALINK_RE = re.compile(r"(pfbid[0-9A-Za-z]+|/posts/[^/?\"]+|/permalink/\d+)")
# Comment permalinks carry comment_id / reply_comment_id; reject those.
_COMMENT_RE = re.compile(r"comment_id=|reply_comment_id=")


def _say(msg: str) -> None:
    print(msg, flush=True)


def _key(permalink: str, body: str) -> str:
    if permalink:
        return permalink
    return "h:" + hashlib.sha1(body.encode("utf-8", "ignore")).hexdigest()[:16]


def _permalink_of(art) -> str:
    try:
        for a in art.query_selector_all('a[href]') or []:
            href = a.get_attribute("href") or ""
            if _COMMENT_RE.search(href):
                continue
            m = _PERMALINK_RE.search(href)
            if m:
                return href.split("?")[0] if "/posts/" in href or "/permalink/" in href else m.group(1)
    except Exception:  # noqa: BLE001
        pass
    return ""


def main() -> int:
    try:
        from resume_builder.sources.social.auth import SessionStore
        from resume_builder.sources.social.headless_browser import PlaywrightSession
    except Exception as exc:  # noqa: BLE001
        _say(f"[v2] import failed: {exc!r}")
        return 3

    store = SessionStore()
    collected: dict[str, dict] = {}

    with PlaywrightSession("facebook", headless=False, store=store) as page:
        _say(f"[v2] goto {URL}")
        page.goto(URL, wait_until="domcontentloaded")
        try:
            page.wait_for_selector("div[role='main']", timeout=25_000)
        except Exception as exc:  # noqa: BLE001
            _say(f"[v2] main feed never rendered: {exc}")
            return 5

        last_total = 0
        flat = 0
        for i in range(MAX_SCROLLS):
            articles = page.query_selector_all("div[role='article']") or []
            new_this_pass = 0
            for art in articles:
                try:
                    if not art.evaluate(_IS_TOP_LEVEL):
                        continue  # nested = comment
                    body = (art.evaluate(_EXTRACT_BODY) or "").strip()
                    if len(body) < 15:
                        continue  # reaction-only / empty
                    permalink = _permalink_of(art)
                    k = _key(permalink, body)
                    if k not in collected:
                        collected[k] = {"permalink": permalink, "text": body}
                        new_this_pass += 1
                except Exception:  # noqa: BLE001
                    continue
            total = len(collected)
            _say(f"[v2] scroll {i}: {len(articles)} live articles, "
                 f"+{new_this_pass} new, {total} total collected")
            if total == last_total:
                flat += 1
                if flat >= 6:
                    _say("[v2] no new posts for 6 passes — stopping")
                    break
            else:
                flat = 0
                last_total = total
            page.evaluate("window.scrollBy(0, window.innerHeight * 0.9)")
            page.wait_for_timeout(SETTLE_MS)

    posts = []
    for k, v in collected.items():
        pid = ""
        if v["permalink"]:
            pid = v["permalink"].rstrip("/").rsplit("/", 1)[-1].split("?")[0]
        url = v["permalink"]
        if url.startswith("/"):
            url = f"https://www.facebook.com{url}"
        posts.append({
            "vendor": "facebook",
            "post_id": pid or k,
            "url": url or URL,
            "text": v["text"][:1500],
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"vendor": "facebook", "handle": HANDLE, "posts": posts},
                   indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _say(f"[v2] SUCCESS — {len(posts)} posts written to {OUT}")
    for i, p in enumerate(posts, 1):
        _say(f"[v2]   {i}. {p['text'][:140].replace(chr(10), ' ')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
