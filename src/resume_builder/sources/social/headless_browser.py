"""Headless Chromium scraper that reuses the storage_state captured at sign-in.

The first run of ``resume-build login`` opens a real Chrome window for the user to
sign in (with 2FA, CAPTCHA, whatever). That window writes
``~/.cache/resume-builder/social/sessions/{vendor}.storage_state.json`` — the full
cookies + localStorage + IndexedDB snapshot of an authenticated session.

This module wraps that snapshot so vendors can fetch any URL on the vendor's domain
as the logged-in user, fully headless, without re-prompting.

Usage::

    with HeadlessBrowser("facebook") as page:
        page.goto("https://www.facebook.com/jane.doe")
        html = page.content()

The context manager handles browser teardown even if the caller raises.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from .auth import SessionStore
from .browser_login import PlaywrightNotInstalled, _resolve_playwright

log = logging.getLogger(__name__)


class NoStoredSessionError(RuntimeError):
    """Raised when ``storage_state.json`` for the requested vendor is missing.

    Callers can catch this and fall back to a curl-only path.
    """


@contextmanager
def HeadlessBrowser(  # noqa: N802 - context-manager helper, capitalized like a class
    vendor: str,
    *,
    playwright_module=None,
    store: SessionStore | None = None,
    timeout_ms: int = 20_000,
) -> Iterator[object]:
    """Yield a Playwright ``page`` bound to the vendor's stored authenticated context."""
    store = store or SessionStore()
    state = store.load_storage_state(vendor)
    if state is None:
        raise NoStoredSessionError(
            f"No stored sign-in for {vendor}. Run `resume-build login` first."
        )
    sync_playwright = _resolve_playwright(playwright_module)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(storage_state=state)
            context.set_default_timeout(timeout_ms)
            page = context.new_page()
            yield page
        finally:
            browser.close()


def fetch_rendered_html(
    vendor: str,
    url: str,
    *,
    wait_for_selector: str | None = None,
    timeout_ms: int = 20_000,
    playwright_module=None,
    store: SessionStore | None = None,
) -> str:
    """Convenience wrapper: open ``url`` headless, optionally wait for a selector,
    return the fully-rendered page HTML.

    Returns an empty string on any internal failure so callers can detect "nothing
    parseable" without try/except boilerplate.
    """
    try:
        with HeadlessBrowser(
            vendor,
            playwright_module=playwright_module,
            store=store,
            timeout_ms=timeout_ms,
        ) as page:
            page.goto(url, wait_until="domcontentloaded")
            if wait_for_selector:
                try:
                    page.wait_for_selector(wait_for_selector, timeout=timeout_ms)
                except Exception as exc:  # noqa: BLE001
                    log.debug("wait_for_selector %s missed: %s", wait_for_selector, exc)
            return page.content() or ""
    except NoStoredSessionError:
        raise
    except PlaywrightNotInstalled:
        raise
    except Exception as exc:  # noqa: BLE001
        log.warning("headless fetch %s failed: %s", url, exc)
        return ""
