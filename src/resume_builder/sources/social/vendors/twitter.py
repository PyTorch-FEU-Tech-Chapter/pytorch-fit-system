"""X / Twitter handler via nitter.net RSS — no auth required.

Nitter mirrors are unstable; we cycle through a small list and gracefully return [] if
all are down. `NITTER_HOST` env var lets the user pin a private instance.
"""

from __future__ import annotations

import logging
import os
import re
from email.utils import parsedate_to_datetime
from typing import Iterable

from ..base import SocialVendor
from ..http import HttpClient
from ..models import SocialMention, SocialPost

log = logging.getLogger(__name__)

_DEFAULT_HOSTS = (
    "https://nitter.net",
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
)

_ITEM_RE = re.compile(r"<item>(.*?)</item>", re.DOTALL)
_TITLE_RE = re.compile(r"<title><!\[CDATA\[(.*?)\]\]></title>", re.DOTALL)
_LINK_RE = re.compile(r"<link>(.*?)</link>")
_DESC_RE = re.compile(r"<description><!\[CDATA\[(.*?)\]\]></description>", re.DOTALL)
_PUB_RE = re.compile(r"<pubDate>(.*?)</pubDate>")
_AUTHOR_RE = re.compile(r"<dc:creator>(.*?)</dc:creator>")
_TAG_STRIP = re.compile(r"<[^>]+>")
_STATUS_ID_RE = re.compile(r"/status/(\d+)")


class TwitterVendor(SocialVendor):
    name = "twitter"

    def __init__(self) -> None:
        env_host = os.environ.get("NITTER_HOST", "").strip()
        self._hosts = (env_host,) + _DEFAULT_HOSTS if env_host else _DEFAULT_HOSTS
        self._client = HttpClient(min_interval_s=1.5)

    def fetch_own_posts(self, handle: str, limit: int = 50) -> list[SocialPost]:
        xml = self._fetch_first(f"/{handle}/rss")
        return list(self._parse_posts(xml))[:limit]

    def search_mentions(self, full_name: str, limit: int = 50) -> list[SocialMention]:
        xml = self._fetch_first(f"/search/rss?f=tweets&q=%22{full_name.replace(' ', '+')}%22")
        return list(self._parse_mentions(xml, full_name))[:limit]

    def _fetch_first(self, path: str) -> str:
        for host in self._hosts:
            url = f"{host}{path}"
            try:
                resp = self._client.get(url)
                text = getattr(resp, "text", "") or ""
                if "<item>" in text:
                    return text
            except Exception as exc:  # noqa: BLE001
                log.debug("nitter %s failed: %s", host, exc)
        return ""

    def _parse_posts(self, xml: str) -> Iterable[SocialPost]:
        for item in _ITEM_RE.findall(xml):
            link_m = _LINK_RE.search(item)
            if not link_m:
                continue
            link = link_m.group(1).strip()
            id_m = _STATUS_ID_RE.search(link)
            if not id_m:
                continue
            text = _extract_text(item)
            yield SocialPost(
                vendor=self.name,
                post_id=id_m.group(1),
                url=link.replace("nitter.net", "x.com"),
                posted_at=_parse_date(item),
                text=text,
            )

    def _parse_mentions(self, xml: str, full_name: str) -> Iterable[SocialMention]:
        name_lower = full_name.lower()
        for item in _ITEM_RE.findall(xml):
            link_m = _LINK_RE.search(item)
            if not link_m:
                continue
            link = link_m.group(1).strip()
            id_m = _STATUS_ID_RE.search(link)
            if not id_m:
                continue
            text = _extract_text(item)
            if name_lower not in text.lower():
                continue
            author_m = _AUTHOR_RE.search(item)
            yield SocialMention(
                vendor=self.name,
                mention_id=id_m.group(1),
                url=link.replace("nitter.net", "x.com"),
                posted_at=_parse_date(item),
                text=text,
                author_name=(author_m.group(1).strip() if author_m else ""),
            )


def _extract_text(item: str) -> str:
    desc_m = _DESC_RE.search(item)
    title_m = _TITLE_RE.search(item)
    raw = (desc_m.group(1) if desc_m else "") or (title_m.group(1) if title_m else "")
    return _TAG_STRIP.sub(" ", raw).strip()


def _parse_date(item: str) -> object | None:
    pub_m = _PUB_RE.search(item)
    if not pub_m:
        return None
    try:
        return parsedate_to_datetime(pub_m.group(1).strip())
    except (TypeError, ValueError):
        return None
