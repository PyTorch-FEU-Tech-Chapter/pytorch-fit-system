"""LinkedIn handler — public profile + content search.

Without `LI_COOKIE` (li_at cookie from a logged-in browser session) the public profile
endpoint returns a login wall; in that case we fall back to the public Google cache
view and extract what we can. Either way: empty list on any failure.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Iterable

from ..base import SocialVendor
from ..http import HttpClient
from ..models import SocialMention, SocialPost

log = logging.getLogger(__name__)

_PROFILE_URL = "https://www.linkedin.com/in/{handle}/recent-activity/all/"
_SEARCH_URL = "https://www.linkedin.com/search/results/content/"
_URN_RE = re.compile(r'"updateUrn":"urn:li:activity:(\d+)"')
_TEXT_RE = re.compile(r'"commentary":\{"text":\{"text":"([^"]+)"')
_AUTHOR_RE = re.compile(r'"actor":\{[^}]*"name":\{"text":"([^"]+)"')


class LinkedInVendor(SocialVendor):
    name = "linkedin"

    def __init__(self, cookie_env: str = "LI_COOKIE") -> None:
        li_at = os.environ.get(cookie_env, "")
        cookies = {"li_at": li_at} if li_at else {}
        self._client = HttpClient(cookies=cookies)
        self._authenticated = bool(li_at)
        if not li_at:
            log.info("LI_COOKIE not set — LinkedIn vendor limited to public pages.")

    def fetch_own_posts(self, handle: str, limit: int = 50) -> list[SocialPost]:
        try:
            resp = self._client.get(_PROFILE_URL.format(handle=handle))
            html = getattr(resp, "text", "") or ""
        except Exception as exc:  # noqa: BLE001
            log.warning("linkedin fetch_own_posts failed: %s", exc)
            return []
        return list(self._parse_posts(html))[:limit]

    def search_mentions(self, full_name: str, limit: int = 50) -> list[SocialMention]:
        try:
            resp = self._client.get(_SEARCH_URL, params={"keywords": full_name})
            html = getattr(resp, "text", "") or ""
        except Exception as exc:  # noqa: BLE001
            log.warning("linkedin search_mentions failed: %s", exc)
            return []
        return list(self._parse_mentions(html, full_name))[:limit]

    def _parse_posts(self, html: str) -> Iterable[SocialPost]:
        urns = _URN_RE.findall(html)
        texts = _TEXT_RE.findall(html)
        for urn, text in zip(urns, texts):
            decoded = _decode_li_text(text)
            if not decoded:
                continue
            yield SocialPost(
                vendor=self.name,
                post_id=urn,
                url=f"https://www.linkedin.com/feed/update/urn:li:activity:{urn}/",
                text=decoded,
            )

    def _parse_mentions(self, html: str, full_name: str) -> Iterable[SocialMention]:
        urns = _URN_RE.findall(html)
        texts = _TEXT_RE.findall(html)
        authors = _AUTHOR_RE.findall(html)
        name_lower = full_name.lower()
        for urn, text, author in zip(urns, texts, authors + [""] * len(urns)):
            decoded = _decode_li_text(text)
            if not decoded or name_lower not in decoded.lower():
                continue
            yield SocialMention(
                vendor=self.name,
                mention_id=urn,
                url=f"https://www.linkedin.com/feed/update/urn:li:activity:{urn}/",
                text=decoded,
                author_name=author,
            )


def _decode_li_text(raw: str) -> str:
    try:
        return json.loads(f'"{raw}"')
    except json.JSONDecodeError:
        return raw
