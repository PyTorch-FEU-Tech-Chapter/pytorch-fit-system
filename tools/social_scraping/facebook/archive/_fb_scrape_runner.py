"""Scrape the signed-in user's own Facebook posts via the headless/visible Chromium
path (reuses the saved storage_state) and dump them to out/facebook.json.

Scratch runner — not part of the package. Writes progress to stdout (line-buffered)
so a parent process can monitor it.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

HANDLE = "your.facebook.handle"
LIMIT = 50
OUT_PATH = Path("out/facebook.json")


def _say(msg: str) -> None:
    print(msg, flush=True)


def main() -> int:
    # Surface the vendor's INFO logs (article counts, fallbacks) on stdout.
    logging.basicConfig(level=logging.INFO, format="[fb] %(message)s", stream=sys.stdout)

    _say(f"[runner] scraping own posts for handle={HANDLE} limit={LIMIT}")
    try:
        from resume_builder.sources.social.vendors.facebook import FacebookVendor
    except Exception as exc:  # noqa: BLE001
        _say(f"[runner] import failed: {exc!r}")
        return 3

    vendor = FacebookVendor()
    if not vendor._has_storage_state:  # noqa: SLF001
        _say("[runner] WARNING: no storage_state found — Chromium path unavailable.")

    try:
        _say("[runner] opening Chromium and scrolling the profile feed...")
        posts = vendor.fetch_own_posts(HANDLE, limit=LIMIT)
    except Exception as exc:  # noqa: BLE001
        _say(f"[runner] scrape failed: {exc!r}")
        return 6

    payload = {
        "vendor": "facebook",
        "handle": HANDLE,
        "posts": [p.model_dump(mode="json") for p in posts],
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    _say(f"[runner] SUCCESS — {len(posts)} posts written to {OUT_PATH}")
    for i, p in enumerate(posts[:5], 1):
        preview = (p.text or "").replace("\n", " ")[:120]
        _say(f"[runner]   {i}. {preview}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
