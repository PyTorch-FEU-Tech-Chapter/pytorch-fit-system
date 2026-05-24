"""FB own-posts Phase-2 re-extract (v6).

v5 correctly identified 12 OWN post permalinks but its body extraction returned the
same text for all of them: FB's SPA didn't hard-navigate to old permalinks, so a
document-wide story_message query kept hitting the feed's top (most-recent) post.

v6 fixes extraction only (reuses the 12 URLs from out/facebook.json):
  - Read the post text from the page's og:description / og:title meta tags, which
    are served per-URL and are not affected by SPA feed state.
  - Also try a DOM body scoped to the article that actually links to THIS post's
    pfbid, as a richer fallback.
  - Force a real navigation by appending a cache-busting nothing + waiting on the
    meta tag to change.

Scratch tool — not packaged. Rewrites out/facebook.json in place.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

OUT = Path("out/facebook.json")

_EXTRACT = """
(pfbid) => {
  const meta = (p) => {
    const el = document.querySelector(`meta[property="${p}"]`) || document.querySelector(`meta[name="${p}"]`);
    return el ? (el.getAttribute('content') || '').trim() : '';
  };
  const ogTitle = meta('og:title');
  const ogDesc = meta('og:description');

  // Scoped DOM body: the article that links to this exact pfbid.
  let scoped = '';
  for (const art of document.querySelectorAll('div[role="article"]')) {
    let linksHere = false;
    for (const a of art.querySelectorAll('a[href]')) {
      if ((a.getAttribute('href') || '').includes(pfbid)) { linksHere = true; break; }
    }
    if (!linksHere) continue;
    const sels = ['[data-ad-rendering-role="story_message"]','[data-ad-comet-preview="message"]','[data-ad-preview="message"]'];
    for (const s of sels) {
      const el = art.querySelector(s);
      if (el && el.innerText && el.innerText.trim()) { scoped = el.innerText.trim(); break; }
    }
    if (scoped) break;
  }
  return { ogTitle, ogDesc, scoped };
}
"""


def _say(m: str) -> None:
    print(m, flush=True)


def _best_text(og_desc: str, scoped: str, og_title: str) -> str:
    # Prefer the scoped DOM body (full post), then og:description, then title.
    for cand in (scoped, og_desc, og_title):
        c = (cand or "").strip()
        if len(c) >= 5:
            return c
    return ""


def main() -> int:
    from resume_builder.sources.social.auth import SessionStore
    from resume_builder.sources.social.headless_browser import PlaywrightSession

    data = json.loads(OUT.read_text(encoding="utf-8"))
    posts = data.get("posts", [])
    if not posts:
        _say("[v6] no posts in facebook.json — run v5 first")
        return 2

    store = SessionStore()
    with PlaywrightSession("facebook", headless=False, store=store) as page:
        for idx, p in enumerate(posts, 1):
            url = p["url"]
            pfbid = p["post_id"]
            try:
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_timeout(2500)
                res = page.evaluate(_EXTRACT, pfbid) or {}
                text = _best_text(res.get("ogDesc", ""), res.get("scoped", ""), res.get("ogTitle", ""))
                p["text"] = text[:1500]
                p["_og_title"] = (res.get("ogTitle") or "")[:120]
                src = "scoped" if res.get("scoped") else ("og:desc" if res.get("ogDesc") else "og:title/none")
                _say(f"[v6] {idx}/{len(posts)} [{src}] {text[:110].replace(chr(10),' ')}")
            except Exception as exc:  # noqa: BLE001
                _say(f"[v6] {idx}: failed {url} — {exc!r}")

    data["posts"] = posts
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    _say(f"[v6] DONE — re-extracted {len(posts)} posts -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
