"""FacebookVendor headless scrape: storage_state present -> render & parse."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from resume_builder.sources.social.auth import SessionStore
from resume_builder.sources.social.vendors.facebook import FacebookVendor


_RENDERED_PROFILE = """
<html><body>
<div role="article">
  <strong>Jane Doe</strong>
  <a href="/jane.doe/posts/12345"></a>
  <span>NASA Space Apps 2024 Top 8 — People's Choice Award.</span>
</div>
<div role="article">
  <a href="/jane.doe/posts/67890"></a>
  <span>Built an XSS sanitization layer for our project.</span>
</div>
</body></html>
"""

_RENDERED_SEARCH = """
<html><body>
<div role="article">
  <strong>Justine Jude Pura</strong>
  <a href="/permalink/55555"></a>
  <span>Congrats Jane Doe for the win.</span>
</div>
</body></html>
"""


@pytest.fixture()
def fb_vendor_with_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RESUME_BUILDER_CACHE", str(tmp_path))
    store = SessionStore(base_dir=tmp_path)
    store.save_storage_state(
        "facebook", {"cookies": [{"name": "c_user", "value": "100"}], "origins": []}
    )
    return FacebookVendor(cookies={"c_user": "100"}, session_store=store)


def test_fetch_own_posts_uses_headless_when_storage_state_present(fb_vendor_with_state):
    with patch(
        "resume_builder.sources.social.vendors.facebook.fetch_rendered_html",
        return_value=_RENDERED_PROFILE,
    ) as render:
        posts = fb_vendor_with_state.fetch_own_posts("jane.doe")
    render.assert_called_once()
    call_url = render.call_args.args[1]
    assert call_url == "https://www.facebook.com/jane.doe"
    assert len(posts) == 2
    assert any("NASA" in p.text for p in posts)
    assert any("XSS" in p.text for p in posts)
    assert posts[0].post_id == "12345"


def test_search_mentions_uses_headless_when_storage_state_present(fb_vendor_with_state):
    with patch(
        "resume_builder.sources.social.vendors.facebook.fetch_rendered_html",
        return_value=_RENDERED_SEARCH,
    ) as render:
        mentions = fb_vendor_with_state.search_mentions("Jane Doe")
    render.assert_called_once()
    assert "search/posts" in render.call_args.args[1]
    assert len(mentions) == 1
    assert mentions[0].author_name == "Justine Jude Pura"
    assert "Congrats" in mentions[0].text


def test_falls_back_to_mbasic_curl_when_no_storage_state(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RESUME_BUILDER_CACHE", str(tmp_path))
    store = SessionStore(base_dir=tmp_path)  # no storage_state saved
    vendor = FacebookVendor(cookies={"c_user": "100", "xs": "x"}, session_store=store)
    # Confirm the headless path is not taken; mbasic curl is invoked.
    with (
        patch(
            "resume_builder.sources.social.vendors.facebook.fetch_rendered_html"
        ) as render,
        patch.object(vendor, "_get", return_value="") as curl,
    ):
        result = vendor.fetch_own_posts("jane.doe")
    render.assert_not_called()
    curl.assert_called_once()
    assert result == []


def test_can_opt_out_of_headless_via_constructor(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RESUME_BUILDER_CACHE", str(tmp_path))
    store = SessionStore(base_dir=tmp_path)
    store.save_storage_state("facebook", {"cookies": [], "origins": []})
    vendor = FacebookVendor(
        cookies={"c_user": "100"}, prefer_headless=False, session_store=store
    )
    with (
        patch(
            "resume_builder.sources.social.vendors.facebook.fetch_rendered_html"
        ) as render,
        patch.object(vendor, "_get", return_value="") as curl,
    ):
        vendor.fetch_own_posts("jane.doe")
    render.assert_not_called()
    curl.assert_called_once()
