"""playwright_step: slow, visible per-post walk that deletes comment DOM."""

from __future__ import annotations

from unittest.mock import MagicMock

from resume_builder.sources.social.playwright_step import (
    step_delay_ms_from_env,
    step_limit_from_env,
    step_through_articles,
)


def test_step_limit_defaults_to_zero(monkeypatch):
    monkeypatch.delenv("RESUME_BUILD_PLAYWRIGHT_STEP_LIMIT", raising=False)
    assert step_limit_from_env() == 0


def test_step_limit_reads_env(monkeypatch):
    monkeypatch.setenv("RESUME_BUILD_PLAYWRIGHT_STEP_LIMIT", "3")
    assert step_limit_from_env() == 3


def test_step_limit_ignores_garbage(monkeypatch):
    monkeypatch.setenv("RESUME_BUILD_PLAYWRIGHT_STEP_LIMIT", "not-a-number")
    assert step_limit_from_env() == 0


def test_step_delay_defaults_to_5000(monkeypatch):
    monkeypatch.delenv("RESUME_BUILD_PLAYWRIGHT_STEP_DELAY_MS", raising=False)
    assert step_delay_ms_from_env() == 5000


def test_step_delay_reads_env(monkeypatch):
    monkeypatch.setenv("RESUME_BUILD_PLAYWRIGHT_STEP_DELAY_MS", "8000")
    assert step_delay_ms_from_env() == 8000


def test_step_through_walks_only_the_limit(monkeypatch):
    monkeypatch.setenv("RESUME_BUILD_PLAYWRIGHT_VISUAL", "1")
    page = MagicMock()
    articles = [MagicMock(name=f"article-{i}") for i in range(5)]
    page.query_selector_all.return_value = articles

    stepped = step_through_articles(page, "sel", limit=2)

    assert stepped == 2
    assert articles[0].evaluate.called
    assert articles[1].evaluate.called
    assert not articles[2].evaluate.called


def test_step_through_is_noop_when_limit_zero(monkeypatch):
    page = MagicMock()
    articles = [MagicMock()]
    page.query_selector_all.return_value = articles

    stepped = step_through_articles(page, "sel", limit=0)

    assert stepped == 0
    assert not articles[0].evaluate.called


def test_step_through_deletes_comments_per_article(monkeypatch):
    monkeypatch.setenv("RESUME_BUILD_PLAYWRIGHT_VISUAL", "1")
    page = MagicMock()
    article = MagicMock()
    page.query_selector_all.return_value = [article]

    step_through_articles(page, "sel", limit=1)

    # One of the per-article evaluate calls must carry the comment-deletion JS,
    # keyed off the authoritative aria-label="Comment by ..." signal.
    joined = " ".join(str(c.args[0]) for c in article.evaluate.call_args_list).lower()
    assert "comment by" in joined
    assert "reply by" in joined


def test_step_through_strips_media_and_preserves_shared(monkeypatch):
    monkeypatch.setenv("RESUME_BUILD_PLAYWRIGHT_VISUAL", "1")
    page = MagicMock()
    article = MagicMock()
    page.query_selector_all.return_value = [article]

    step_through_articles(page, "sel", limit=1)

    joined = " ".join(str(c.args[0]) for c in article.evaluate.call_args_list).lower()
    # Aggressive strip removes media, and shared posts are explicitly preserved.
    assert "img" in joined and "video" in joined
    assert "shared (preserved)" in joined


def test_step_through_handles_more_articles_than_exist(monkeypatch):
    monkeypatch.setenv("RESUME_BUILD_PLAYWRIGHT_VISUAL", "1")
    page = MagicMock()
    articles = [MagicMock(), MagicMock()]
    page.query_selector_all.return_value = articles

    stepped = step_through_articles(page, "sel", limit=10)

    assert stepped == 2
