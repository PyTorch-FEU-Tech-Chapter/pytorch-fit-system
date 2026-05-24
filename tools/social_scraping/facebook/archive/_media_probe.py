"""Probe v2: for each large scontent image on a post permalink, report its nearest
ancestor <a href>, the nearest preceding heading/strong text (author/attribution),
and whether it sits before the first comment — to find a reliable signal that
separates the post's OWN photo from suggested/other-author content."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))
from social_scraping.common.paths import FB_JSON  # noqa: E402

PROBE = """
() => {
  const main = document.querySelector('div[role="main"]') || document.body;
  const out = [];
  main.querySelectorAll('img').forEach(im => {
    const src = im.currentSrc || im.src || '';
    if (src.indexOf('scontent') === -1) return;
    if ((im.naturalWidth||0) < 400) return;
    // nearest ancestor anchor
    let a = im.closest('a');
    let href = a ? (a.getAttribute('href')||'') : '';
    // nearest preceding strong/h2/h3 text within 6 ancestor levels
    let author = '';
    let node = im;
    for (let i=0;i<8 && node;i++){
      let h = node.querySelector && node.querySelector('h2 a, h3 a, strong a, h2, h3');
      if (h && h.innerText && h.innerText.trim()){ author = h.innerText.trim().slice(0,40); break; }
      node = node.parentElement;
    }
    out.push({ w: im.naturalWidth+'x'+im.naturalHeight, href: href.slice(0,70), author: author });
  });
  return out;
}
"""


def main() -> int:
    from resume_builder.sources.social.auth import SessionStore
    from resume_builder.sources.social.headless_browser import PlaywrightSession

    posts = json.loads(FB_JSON.read_text(encoding="utf-8"))["posts"]
    url = posts[3]["url"]  # CTF post
    print(f"[probe] {url}\n", flush=True)
    with PlaywrightSession("facebook", headless=False, store=SessionStore()) as page:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(3000)
        page.evaluate("window.scrollBy(0, 400)")
        page.wait_for_timeout(2500)
        data = page.evaluate(PROBE)
    print(json.dumps(data, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
