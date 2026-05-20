"""Instagram handler via the public web-profile JSON endpoint.

Authenticated requests work best with the `IG_COOKIE` env var (`sessionid=...`).
Without it the JSON endpoint usually 401s; we return [] cleanly.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Iterable

from ..base import SocialVendor
from ..http import HttpClient
from ..models import SocialMention, SocialPost

log = logging.getLogger(__name__)

_PROFILE = "https://www.instagram.com/api/v1/users/web_profile_info/"
_TAG_SEARCH = "https://www.instagram.com/api/v1/tags/web_info/"


class InstagramVendor(SocialVendor):
    name = "instagram"

    def __init__(self, cookie_env: str = "IG_COOKIE") -> None:
        sessionid = os.environ.get(cookie_env, "")
        cookies = {"sessionid": sessionid} if sessionid else {}
        self._client = HttpClient(cookies=cookies)
        self._headers = {"x-ig-app-id": "936619743392459"}
        if not sessionid:
            log.info("IG_COOKIE not set — Instagram vendor will likely return empty.")

    def fetch_own_posts(self, handle: str, limit: int = 50) -> list[SocialPost]:
        try:
            resp = self._client.get(
                _PROFILE, params={"username": handle}, headers=self._headers
            )
            payload = _safe_json(resp)
        except Exception as exc:  # noqa: BLE001
            log.warning("instagram fetch_own_posts failed: %s", exc)
            return []
        user = ((payload or {}).get("data") or {}).get("user") or {}
        edges = ((user.get("edge_owner_to_timeline_media") or {}).get("edges")) or []
        return list(self._edges_to_posts(edges))[:limit]

    def search_mentions(self, full_name: str, limit: int = 50) -> list[SocialMention]:
        slug = full_name.lower().replace(" ", "")
        try:
            resp = self._client.get(
                _TAG_SEARCH, params={"tag_name": slug}, headers=self._headers
            )
            payload = _safe_json(resp)
        except Exception as exc:  # noqa: BLE001
            log.warning("instagram search_mentions failed: %s", exc)
            return []
        sections = ((payload or {}).get("data") or {}).get("top") or {}
        edges = sections.get("sections") or []
        return list(self._sections_to_mentions(edges, full_name))[:limit]

    def _edges_to_posts(self, edges: list[dict]) -> Iterable[SocialPost]:
        for edge in edges:
            node = edge.get("node") or {}
            shortcode = node.get("shortcode") or node.get("code") or ""
            if not shortcode:
                continue
            caption_edges = (node.get("edge_media_to_caption") or {}).get("edges") or []
            caption = (caption_edges[0]["node"].get("text") if caption_edges else "") or ""
            ts = node.get("taken_at_timestamp")
            yield SocialPost(
                vendor=self.name,
                post_id=shortcode,
                url=f"https://www.instagram.com/p/{shortcode}/",
                posted_at=datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None,
                text=caption,
            )

    def _sections_to_mentions(
        self, sections: list[dict], full_name: str
    ) -> Iterable[SocialMention]:
        name_lower = full_name.lower()
        for section in sections:
            medias = ((section.get("layout_content") or {}).get("medias")) or []
            for media in medias:
                m = media.get("media") or {}
                shortcode = m.get("code") or ""
                caption = (m.get("caption") or {}).get("text") or ""
                if not shortcode or name_lower not in caption.lower():
                    continue
                author = (m.get("user") or {}).get("username") or ""
                ts = m.get("taken_at")
                yield SocialMention(
                    vendor=self.name,
                    mention_id=shortcode,
                    url=f"https://www.instagram.com/p/{shortcode}/",
                    posted_at=datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None,
                    text=caption,
                    author_name=author,
                )


def _safe_json(resp: object) -> dict | None:
    text = getattr(resp, "text", None)
    if not text:
        return None
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None
