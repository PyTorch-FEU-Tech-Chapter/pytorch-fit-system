"""Author-structure probe: for each TOP-LEVEL-ish article on the profile feed, dump
the DOM bits that could carry the poster's name so we can build a reliable
'authored by me' filter:

  - article aria-label (FB often labels posts/comments here)
  - every [role=heading] / h2-h4 text + the anchor href inside it (the actor link)
  - all profile-looking anchors (href + visible text) in the article header region
  - post-vs-comment hints: presence of a Share control vs a 'Reply' affordance
  - inner_text head

Dumps to out/fb_author_probe.json. Scratch tool — not packaged.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HANDLE = "your.facebook.handle"
C_USER = "0000000000"
URL = f"https://www.facebook.com/{HANDLE}"
OUT = Path("out/fb_author_probe.json")

_PROBE = """
(node) => {
  const headings = [];
  node.querySelectorAll('[role="heading"], h1, h2, h3, h4').forEach(h => {
    const a = h.querySelector('a[href]');
    headings.push({
      tag: h.tagName.toLowerCase(),
      text: (h.innerText || '').trim().slice(0, 80),
      href: a ? (a.getAttribute('href') || '') : '',
      linkText: a ? (a.innerText || '').trim().slice(0, 60) : ''
    });
  });
  const links = [];
  let n = 0;
  for (const a of node.querySelectorAll('a[href]')) {
    const h = a.getAttribute('href') || '';
    const t = (a.innerText || '').trim();
    if (t && h && t.length < 60) { links.push({ href: h.slice(0, 80), text: t.slice(0, 50) }); }
    if (++n > 8) break;
  }
  const txt = (node.innerText || '');
  return {
    ariaLabel: node.getAttribute('aria-label') || '',
    headings: headings.slice(0, 6),
    headerLinks: links,
    hasReply: /\\bReply\\b|Tumugon/.test(txt),
    hasShare: !!node.querySelector('[aria-label*="Share" i], [aria-label*="Ibahagi" i]'),
    innerHead: txt.replace(/\\n/g, ' ').slice(0, 140)
  };
}
"""

_IS_TOP = """
(node) => { let p=node.parentElement; while(p){ if(p.getAttribute&&p.getAttribute('role')==='article') return false; p=p.parentElement;} return true; }
"""


def _say(m: str) -> None:
    print(m, flush=True)


def main() -> int:
    from resume_builder.sources.social.auth import SessionStore
    from resume_builder.sources.social.headless_browser import PlaywrightSession

    store = SessionStore()
    out = {"url": URL, "owner": {"handle": HANDLE, "c_user": C_USER}, "articles": []}
    seen_keys = set()

    with PlaywrightSession("facebook", headless=False, store=store) as page:
        _say(f"[probe] goto {URL}")
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_selector("div[role='main']", timeout=25_000)

        for i in range(20):
            for art in page.query_selector_all("div[role='article']") or []:
                try:
                    top = art.evaluate(_IS_TOP)
                    data = art.evaluate(_PROBE) or {}
                    key = data.get("innerHead", "")[:60]
                    if not key or key in seen_keys:
                        continue
                    seen_keys.add(key)
                    data["topLevel"] = top
                    out["articles"].append(data)
                except Exception:  # noqa: BLE001
                    continue
            _say(f"[probe] pass {i}: {len(out['articles'])} unique articles captured")
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            try:
                page.mouse.wheel(0, 3000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(2500)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    _say(f"[probe] DONE -> {OUT} ({len(out['articles'])} articles)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
