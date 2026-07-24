from datetime import datetime, timedelta, timezone

from resume_builder.job_application import (
    ApplicationSubmissionHistory,
    LedgerState,
    SubmissionDecision,
)


NOW = datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc)


def test_recent_exact_company_and_title_is_skipped(tmp_path):
    history = ApplicationSubmissionHistory(tmp_path / "applications.sqlite3")
    reservation = history.reserve_submission(
        company="DataAnnotation",
        job_title="Backend Developer - AI Trainer",
        now=NOW,
    )
    assert reservation.allowed
    history.mark_submitted(
        reservation.application_id,
        confirmation="post-apply reached",
        now=NOW,
    )

    duplicate = history.reserve_submission(
        company="  dataannotation ",
        job_title="Backend   Developer - AI Trainer",
        now=NOW + timedelta(days=29),
    )

    assert duplicate.decision == SubmissionDecision.RECENT_DUPLICATE
    assert duplicate.matched_application_id == reservation.application_id


def test_different_exact_title_at_same_company_is_allowed(tmp_path):
    history = ApplicationSubmissionHistory(tmp_path / "applications.sqlite3")
    first = history.reserve_submission(
        company="Example Co",
        job_title="Backend Engineer",
        now=NOW,
    )
    history.mark_submitted(first.application_id, now=NOW)

    second = history.reserve_submission(
        company="Example Co",
        job_title="Machine Learning Engineer",
        now=NOW + timedelta(days=1),
    )

    assert second.decision == SubmissionDecision.RESERVED


def test_same_exact_application_after_30_days_is_allowed(tmp_path):
    history = ApplicationSubmissionHistory(tmp_path / "applications.sqlite3")
    first = history.reserve_submission(
        company="Example Co",
        job_title="Backend Engineer",
        now=NOW,
    )
    history.mark_submitted(first.application_id, now=NOW)

    second = history.reserve_submission(
        company="Example Co",
        job_title="Backend Engineer",
        now=NOW + timedelta(days=30, seconds=1),
    )

    assert second.decision == SubmissionDecision.RESERVED


def test_unresolved_recent_attempt_stops_duplicate_click(tmp_path):
    history = ApplicationSubmissionHistory(tmp_path / "applications.sqlite3")
    first = history.reserve_submission(
        company="Example Co",
        job_title="Backend Engineer",
        now=NOW,
    )
    history.mark_submission_unknown(first.application_id, details="navigation timed out")

    second = history.reserve_submission(
        company="Example Co",
        job_title="Backend Engineer",
        now=NOW + timedelta(days=1),
    )

    assert second.decision == SubmissionDecision.UNRESOLVED_ATTEMPT


def test_source_query_and_private_confirmation_are_not_stored(tmp_path):
    path = tmp_path / "applications.sqlite3"
    history = ApplicationSubmissionHistory(path)
    reservation = history.reserve_submission(
        company="Example Co",
        job_title="Backend Engineer",
        source_url="https://apply.example.com/review?token=private",
        now=NOW,
    )
    entry = history.mark_submitted(
        reservation.application_id,
        confirmation="sent to person@example.com +63 912 345 6789",
        now=NOW,
    )

    assert entry.source_url == "https://apply.example.com/review"
    assert "person@example.com" not in entry.confirmation
    assert "+63 912 345 6789" not in entry.confirmation
    assert entry.state == LedgerState.SUBMITTED
