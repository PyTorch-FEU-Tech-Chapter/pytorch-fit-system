"""Sync visible Indeed Applied cards into the persistent submission-confirmation database."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

ROOT = next(path for path in Path(__file__).resolve().parents if (path / "pyproject.toml").exists())
sys.path.insert(0, str(ROOT / "src"))

from resume_builder.job_application import (  # noqa: E402
    DEFAULT_SUBMISSION_HISTORY_PATH,
    ApplicationSubmissionHistory,
    ConfirmationSource,
    check_access_gate,
)


@dataclass(frozen=True)
class AppliedCard:
    company: str
    job_title: str
    applied_on: date
    source_url: str


def _parse_applied_date(label: str, observed_on: date) -> date:
    if label == "Applied today on Indeed":
        return observed_on
    prefix = "Applied on Indeed on "
    if not label.startswith(prefix):
        raise ValueError(f"unsupported Indeed application date: {label!r}")
    weekday = label.removeprefix(prefix)
    weekdays = (
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    )
    try:
        target_weekday = weekdays.index(weekday)
    except ValueError as exc:
        raise ValueError(f"unsupported Indeed weekday: {weekday!r}") from exc
    days_back = (observed_on.weekday() - target_weekday) % 7 or 7
    return observed_on - timedelta(days=days_back)


def _extract_applied_cards(page, *, observed_on: date) -> list[AppliedCard]:
    cards = page.locator(".atw-AppCard")
    extracted: list[AppliedCard] = []
    for index in range(cards.count()):
        card = cards.nth(index)
        title_link = card.locator(".atw-JobInfo-jobTitle").first
        job_title = " ".join(
            title_link.inner_text().replace("job description opens in a new window", "").split()
        )
        company_nodes = card.locator(".atw-JobInfo-companyLocation span")
        if company_nodes.count() < 1:
            raise ValueError(f"Applied card {index + 1} has no company")
        company = " ".join(company_nodes.nth(0).inner_text().split())
        label = card.locator("[data-testid=jobStatusDateShort]").first.inner_text().strip()
        source_url = title_link.get_attribute("href") or ""
        if not company or not job_title:
            raise ValueError(f"Applied card {index + 1} has incomplete identity")
        extracted.append(
            AppliedCard(
                company=company,
                job_title=job_title,
                applied_on=_parse_applied_date(label, observed_on),
                source_url=source_url,
            )
        )
    return extracted


def sync(args: argparse.Namespace) -> int:
    from playwright.sync_api import sync_playwright

    local_zone = ZoneInfo(args.timezone)
    observed = datetime.now(local_zone)
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(args.cdp_url)
        pages = [
            page
            for context in browser.contexts
            for page in context.pages
            if urlsplit(page.url).netloc == "myjobs.indeed.com"
            and urlsplit(page.url).path == "/applied"
        ]
        if not pages:
            print("STOP: no open https://myjobs.indeed.com/applied page")
            return 2
        page = pages[-1]
        access = check_access_gate(page)
        if access.blocked:
            print(f"STOP: access gate requires human action: {access.reason}")
            return 2
        cards = _extract_applied_cards(page, observed_on=observed.date())

    history = ApplicationSubmissionHistory(args.database)
    inserted = 0
    matched = 0
    for card in cards:
        before = len(history.recent_submissions(within_days=args.history_days, now=observed))
        # Indeed exposes day precision here. UTC midnight is a normalized date value, not an
        # invented application time.
        applied_at = datetime.combine(card.applied_on, time.min, tzinfo=timezone.utc)
        history.record_existing_submission(
            company=card.company,
            job_title=card.job_title,
            applied_at=applied_at,
            confirmation="visible on Indeed Applied page",
            confirmation_source=ConfirmationSource.BROWSER,
            source_url=card.source_url,
        )
        after = len(history.recent_submissions(within_days=args.history_days, now=observed))
        if after > before:
            inserted += 1
        else:
            matched += 1
    print(
        f"access=clear cards={len(cards)} inserted={inserted} "
        f"matched_existing={matched} database={args.database}"
    )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    parser.add_argument("--database", type=Path, default=DEFAULT_SUBMISSION_HISTORY_PATH)
    parser.add_argument("--timezone", default="Asia/Manila")
    parser.add_argument("--history-days", type=int, default=3650)
    return parser


def main() -> int:
    return sync(_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
