"""FB own-posts scrape (v5) — the correct approach, grounded in the author probe.

The probe proved that div[role='article'] on this profile layout only ever yields
COMMENTS/REPLIES (aria-label="Comment by ..."/"Reply by ..."), never the post bodies.
But each comment's timestamp link points at its PARENT POST permalink. So:

  1. Scroll the feed; for every comment/reply article, read the timestamp link =
     parent post URL. Keep only parents hosted under the owner's profile
     (facebook.com/<handle>/posts/...) — those are the owner's OWN posts. Drop
     parents under anyone else's profile (posts where the owner was merely tagged
     or left a comment).
  2. Visit each unique owner post permalink and extract the real post body
     (story message) + image alt-text, with the owner as author by construction.

Scratch tool — not packaged. Writes out/facebook.json + progress to stdout.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

HANDLE = "your.facebook.handle"
C_USER = "0000000000"
URL = f"https://www.facebook.com/{HANDLE}"
OUT = Path("out/facebook.json")
MAX_SCROLLS = 60
SETTLE_MS = 2800
NO_GROWTH_LIMIT = 8

# Collect, per comment/reply article: aria-label + every anchor href (full, untruncated).
_COLLECT_LINKS = """
(node) => {
  const aria = node.getAttribute('aria-label') || '';
  const hrefs = [];
  node.querySelectorAll('a[href]').forEach(a => hrefs.push(a.getAttribute('href') || ''));
  return { aria: aria, hrefs: hrefs };
}
"""

# On a post permalink page, extract the post body + image alts.
_EXTRACT_POST = """
() => {
  const sels = [
    '[data-ad-rendering-role="story_message"]',
    '[data-ad-comet-preview="message"]',
    '[data-ad-preview="message"]',
  ];
  let body = '';
  for (const s of sels) {
    const el = document.querySelector(s);
    if (el && el.innerText && el.innerText.trim().length > 0) { body = el.innerText.trim(); break; }
  }
  if (!body) {
    // Fallback: the longest dir=auto block inside the first role=article.
    const art = document.querySelector('div[role="article"]') || document.body;
    let best = '';
    art.querySelectorAll('div[dir="auto"]').forEach(d => {
      const t = (d.innerText || '').trim();
      if (t.length > best.length) best = t;
    });
    body = best;
  }
  const alts = [];
  document.querySelectorAll('div[role="main"] img[alt]').forEach(im => {
    const a = (im.getAttribute('alt') || '').trim();
    if (a && a.length > 8 && !alts.includes(a)) alts.push(a);
  });
  return { body: body, alt: alts.join(' | ') };
}
"""

# A parent-post permalink: /<something>/posts/<id> or /permalink/ or photo with story.
_POST_PATH_RE = re.compile(r"^/([^/]+)/posts/([^/?]+)")
_PERMALINK_PATH_RE = re.compile(r"^/permalink/(\d+)")


def _say(m: str) -> None:
    print(m, flush=True)


def _owner_post_permalink(href: str) -> str | None:
    """Return a normalized owner post URL if href is a parent-post link under the
    owner's profile; else None. Rejects comment_id-bearing links' query but keeps
    the path (the path host is what matters)."""
    if not href:
        return None
    # Make absolute for parsing.
    full = href if href.startswith("http") else f"https://www.facebook.com{href}"
    p = urlparse(full)
    if "facebook.com" not in p.netloc:
        return None
    m = _POST_PATH_RE.match(p.path)
    if m:
        host_seg, post_id = m.group(1), m.group(2)
        if host_seg == HANDLE:  # owner's own post
            return f"https://www.facebook.com/{HANDLE}/posts/{post_id}"
        return None  # someone else's post
    # /permalink/<id> on the profile also belongs to the profile owner being viewed.
    m2 = _PERMALINK_PATH_RE.match(p.path)
    if m2:
        return f"https://www.facebook.com/{HANDLE}/posts/{m2.group(1)}"
    return None


def main() -> int:
    from resume_builder.sources.social.auth import SessionStore
    from resume_builder.sources.social.headless_browser import PlaywrightSession

    store = SessionStore()
    own_post_urls: dict[str, None] = {}  # ordered set
    rejected_other = 0

    with PlaywrightSession("facebook", headless=False, store=store) as page:
        _say(f"[v5] PHASE 1 — collect owner post permalinks from comment timestamps")
        _say(f"[v5] goto {URL}")
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_selector("div[role='main']", timeout=25_000)

        last = 0
        flat = 0
        for i in range(MAX_SCROLLS):
            for art in page.query_selector_all("div[role='article']") or []:
                try:
                    data = art.evaluate(_COLLECT_LINKS) or {}
                    for href in data.get("hrefs", []):
                        url = _owner_post_permalink(href)
                        if url:
                            own_post_urls.setdefault(url, None)
                        elif "/posts/" in (href or "") and HANDLE not in (href or ""):
                            rejected_other += 1
                except Exception:  # noqa: BLE001
                    continue
            total = len(own_post_urls)
            _say(f"[v5] scroll {i}: {total} unique owner posts (skipped {rejected_other} others)")
            if total == last:
                flat += 1
                if flat >= NO_GROWTH_LIMIT:
                    _say(f"[v5] no new owner posts for {NO_GROWTH_LIMIT} passes — stopping scroll")
                    break
            else:
                flat = 0
                last = total
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            try:
                page.mouse.wheel(0, 3000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(SETTLE_MS)

        _say(f"[v5] PHASE 2 — visit {len(own_post_urls)} owner posts and extract bodies")
        posts = []
        for idx, url in enumerate(own_post_urls, 1):
            try:
                page.goto(url, wait_until="domcontentloaded")
                try:
                    page.wait_for_selector("div[role='article']", timeout=15_000)
                except Exception:  # noqa: BLE001
                    pass
                page.wait_for_timeout(1500)
                data = page.evaluate(_EXTRACT_POST) or {}
                body = (data.get("body") or "").strip()
                alt = (data.get("alt") or "").strip()
                post_id = url.rstrip("/").rsplit("/", 1)[-1]
                posts.append({
                    "vendor": "facebook",
                    "post_id": post_id,
                    "url": url,
                    "author": "JA Doe",
                    "text": body[:1500],
                    "media_alt": alt[:500],
                })
                preview = (body[:90] or "(no text — likely photo/share)").replace("\n", " ")
                _say(f"[v5]   {idx}/{len(own_post_urls)} {preview}"
                     + (f"  [img: {alt[:60]}]" if alt else ""))
            except Exception as exc:  # noqa: BLE001
                _say(f"[v5]   {idx}: failed {url} — {exc!r}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"vendor": "facebook", "handle": HANDLE, "owner_only": True, "posts": posts},
                   indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _say(f"[v5] SUCCESS — {len(posts)} OWN posts written to {OUT} (rejected {rejected_other} others' posts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
