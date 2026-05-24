"""Deeper FB own-posts scrape (v3).

Builds on v2 (accumulate-while-scrolling, top-level-only, story-message body) and
adds three things to pull more out of a photo-heavy profile:

1. Stronger scroll: scrollTo(bottom) + a synthetic wheel event each pass, and track
   document.body.scrollHeight growth as a secondary "is the page still loading?"
   signal (article count is unreliable under virtualization).
2. Bigger budget: more passes, longer settle, higher no-growth tolerance.
3. Media hints: capture image alt-text (FB auto-generates e.g. "May be an image of
   3 people and text") and treat a post's caption as body when no text message
   exists — graduation/award photos often carry the only achievement signal.

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
MAX_SCROLLS = 80
SETTLE_MS = 3000
NO_GROWTH_LIMIT = 10

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

# Returns {body, alt} — body from story-message/caption, alt from image alt-text.
_EXTRACT = """
(node) => {
  const sels = [
    '[data-ad-rendering-role="story_message"]',
    '[data-ad-comet-preview="message"]',
    '[data-ad-preview="message"]',
  ];
  let body = '';
  for (const s of sels) {
    const el = node.querySelector(s);
    if (el && el.innerText && el.innerText.trim().length > 0) { body = el.innerText.trim(); break; }
  }
  if (!body) {
    let best = '';
    node.querySelectorAll('div[dir="auto"]').forEach(d => {
      const t = (d.innerText || '').trim();
      if (t.length > best.length) best = t;
    });
    body = best;
  }
  const alts = [];
  node.querySelectorAll('img[alt]').forEach(im => {
    const a = (im.getAttribute('alt') || '').trim();
    if (a && a.length > 8 && !alts.includes(a)) alts.push(a);
  });
  return { body: body, alt: alts.join(' | ') };
}
"""

_PERMALINK_RE = re.compile(r"(pfbid[0-9A-Za-z]+|/posts/[^/?\"]+|/permalink/\d+)")
_COMMENT_RE = re.compile(r"comment_id=|reply_comment_id=")


def _say(msg: str) -> None:
    print(msg, flush=True)


def _key(permalink: str, body: str, alt: str) -> str:
    if permalink:
        return permalink
    return "h:" + hashlib.sha1((body + "||" + alt).encode("utf-8", "ignore")).hexdigest()[:16]


def _permalink_of(art) -> str:
    try:
        for a in art.query_selector_all('a[href]') or []:
            href = a.get_attribute("href") or ""
            if _COMMENT_RE.search(href):
                continue
            m = _PERMALINK_RE.search(href)
            if m:
                return href.split("?")[0] if ("/posts/" in href or "/permalink/" in href) else m.group(1)
    except Exception:  # noqa: BLE001
        pass
    return ""


def main() -> int:
    try:
        from resume_builder.sources.social.auth import SessionStore
        from resume_builder.sources.social.headless_browser import PlaywrightSession
    except Exception as exc:  # noqa: BLE001
        _say(f"[v3] import failed: {exc!r}")
        return 3

    store = SessionStore()
    collected: dict[str, dict] = {}

    with PlaywrightSession("facebook", headless=False, store=store) as page:
        _say(f"[v3] goto {URL}")
        page.goto(URL, wait_until="domcontentloaded")
        try:
            page.wait_for_selector("div[role='main']", timeout=25_000)
        except Exception as exc:  # noqa: BLE001
            _say(f"[v3] main feed never rendered: {exc}")
            return 5

        last_total = 0
        last_height = 0
        flat = 0
        for i in range(MAX_SCROLLS):
            articles = page.query_selector_all("div[role='article']") or []
            new_this_pass = 0
            for art in articles:
                try:
                    if not art.evaluate(_IS_TOP_LEVEL):
                        continue
                    data = art.evaluate(_EXTRACT) or {}
                    body = (data.get("body") or "").strip()
                    alt = (data.get("alt") or "").strip()
                    if len(body) < 15 and len(alt) < 15:
                        continue
                    permalink = _permalink_of(art)
                    k = _key(permalink, body, alt)
                    if k not in collected:
                        collected[k] = {"permalink": permalink, "text": body, "media_alt": alt}
                        new_this_pass += 1
                except Exception:  # noqa: BLE001
                    continue

            height = page.evaluate("document.body.scrollHeight") or 0
            total = len(collected)
            _say(f"[v3] scroll {i}: {len(articles)} live, +{new_this_pass} new, "
                 f"{total} total, height={height}")

            grew = total != last_total or height != last_height
            if not grew:
                flat += 1
                if flat >= NO_GROWTH_LIMIT:
                    _say(f"[v3] no growth (posts+height) for {NO_GROWTH_LIMIT} passes — stopping")
                    break
            else:
                flat = 0
                last_total = total
                last_height = height

            # Stronger scroll: jump to bottom + synthetic wheel to nudge the loader.
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            try:
                page.mouse.wheel(0, 3000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(SETTLE_MS)

    posts = []
    for k, v in collected.items():
        pid = v["permalink"].rstrip("/").rsplit("/", 1)[-1].split("?")[0] if v["permalink"] else ""
        url = v["permalink"]
        if url.startswith("/"):
            url = f"https://www.facebook.com{url}"
        posts.append({
            "vendor": "facebook",
            "post_id": pid or k,
            "url": url or URL,
            "text": v["text"][:1500],
            "media_alt": v["media_alt"][:500],
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"vendor": "facebook", "handle": HANDLE, "posts": posts},
                   indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _say(f"[v3] SUCCESS — {len(posts)} posts written to {OUT}")
    for i, p in enumerate(posts, 1):
        line = p["text"][:120].replace(chr(10), " ")
        if p["media_alt"]:
            line += f"   [img: {p['media_alt'][:80]}]"
        _say(f"[v3]   {i}. {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
