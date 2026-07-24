"""Run a bounded explicit Indeed application batch in independent Chrome/CDP pages."""

from __future__ import annotations

import argparse
import heapq
import json
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit

ROOT = next(path for path in Path(__file__).resolve().parents if (path / "pyproject.toml").exists())
sys.path.insert(0, str(ROOT / "src"))

from resume_builder.job_application import (  # noqa: E402
    ApplicationPermissionPolicy,
    ApplicationSubmissionHistory,
    BatchApplicationOutcome,
    BatchApplicationStatus,
    HumanVerificationQueue,
    SmartApplyApprovals,
    check_access_gate,
    indeed_batch_outcome,
    load_resume_artifact,
    recommend_role_resume,
    run_indeed_smart_apply_until_gate,
)
from resume_builder.job_application.indeed_unattended import (  # noqa: E402
    IndeedUnattendedJob,
    IndeedUnattendedManifest,
    description_is_allowed,
    has_recent_exact_submission,
)

_WRITE_LOCK = Lock()
_APPLY_SELECTORS = (
    "[data-testid=indeedApplyButton]",
    "button:visible:has-text('Apply now')",
    "button:visible:has-text('Apply with Indeed')",
    "a:visible:has-text('Apply now')",
)


def _write_json(path: Path, value: object) -> None:
    with _WRITE_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
        temporary.replace(path)


def _outcome(
    job: IndeedUnattendedJob,
    status: BatchApplicationStatus,
    detail: str,
) -> BatchApplicationOutcome:
    return BatchApplicationOutcome(task=job.batch_task(), status=status, detail=detail)


def _check_access(page, job, queue):
    reference = job.batch_task().application_reference
    access = check_access_gate(page)
    if not access.blocked:
        queue.resolve_if_clear(
            application_reference=reference,
            url=str(page.url),
            result=access,
        )
        return access
    host = (urlsplit(str(page.url)).hostname or "").lower()
    already_pending = any(
        item.application_reference == reference and item.domain == host for item in queue.pending()
    )
    if not already_pending:
        queue.enqueue(
            application_reference=reference,
            url=str(page.url),
            result=access,
        )
    return access


def _visible_text(page, selector: str) -> str:
    locator = page.locator(selector).first
    return locator.inner_text() if locator.count() and locator.is_visible() else ""


def _open_smart_apply(page, context):
    before_pages = set(context.pages)
    apply_control = None
    for selector in _APPLY_SELECTORS:
        candidate = page.locator(selector).first
        if candidate.count() and candidate.is_visible():
            apply_control = candidate
            break
    if apply_control is None:
        return None, "no verified visible Indeed Apply control"
    apply_control.click()
    page.wait_for_timeout(2_000)
    new_pages = [candidate for candidate in context.pages if candidate not in before_pages]
    application_page = new_pages[-1] if new_pages else page
    try:
        application_page.wait_for_load_state("domcontentloaded", timeout=8_000)
    except Exception:
        pass
    host = (urlsplit(str(application_page.url)).hostname or "").lower()
    if host != "smartapply.indeed.com":
        return (
            application_page,
            f"apply control did not reach Indeed Smart Apply: {host or 'unknown'}",
        )
    return application_page, ""


def _select_resume(job: IndeedUnattendedJob, artifact_dir: Path, description: str) -> Path | None:
    if job.resume_file:
        candidate = artifact_dir / job.resume_file
        return candidate if candidate.is_file() else None
    return recommend_role_resume(
        job.job_title,
        artifact_dir,
        job_description=description,
    )


def _matching_existing_page(context, job: IndeedUnattendedJob):
    listing_url = job.listing_url.rstrip("/")
    company = " ".join(job.company.casefold().split())
    title = " ".join(job.job_title.casefold().split())
    for page in reversed(context.pages):
        if str(page.url).rstrip("/") == listing_url:
            return page, False
    for page in reversed(context.pages):
        if (urlsplit(str(page.url)).hostname or "").lower() != "smartapply.indeed.com":
            continue
        try:
            body = " ".join(_visible_text(page, "body").casefold().split())
        except Exception:
            continue
        if company in body and title in body:
            return page, True
    return None, False


def _run_application(
    application_page,
    job: IndeedUnattendedJob,
    args: argparse.Namespace,
    queue: HumanVerificationQueue,
    history: ApplicationSubmissionHistory,
    *,
    description: str,
) -> BatchApplicationOutcome:
    application_access = _check_access(application_page, job, queue)
    if application_access.blocked:
        return _outcome(
            job,
            BatchApplicationStatus.VERIFICATION_PENDING,
            f"application access gate remains pending: {application_access.reason}",
        )
    resume_path = _select_resume(job, args.artifact_dir, description)
    if resume_path is None:
        return _outcome(
            job,
            BatchApplicationStatus.HUMAN_HANDOFF,
            "no approved real role-specific resume artifact is available",
        )
    resume_json = resume_path.with_suffix(".resume.json")
    if not resume_json.is_file():
        return _outcome(
            job,
            BatchApplicationStatus.HUMAN_HANDOFF,
            f"resume evidence JSON is missing for {resume_path.name}",
        )
    resume = load_resume_artifact(resume_json)
    policy = ApplicationPermissionPolicy(
        autonomous_draft_writes=True,
        autonomous_sensitive_writes=True,
        autonomous_submit=True,
        allowed_domains={"smartapply.indeed.com"},
    )
    approvals = SmartApplyApprovals(
        resume_upload=True,
        resume_continue=True,
        final_submit=True,
    )
    result = None
    for _ in range(3):
        result = run_indeed_smart_apply_until_gate(
            application_page,
            resume,
            approved_resume=resume_path,
            approvals=approvals,
            permission_policy=policy,
            verified_phone=args.verified_phone,
            phone_country_calling_code=args.phone_country_calling_code,
            phone_country_iso=args.phone_country_iso,
            verification_queue=queue,
            application_reference=job.batch_task().application_reference,
            submission_history=history,
            company=job.company,
            job_title=job.job_title,
            duplicate_window_days=args.duplicate_days,
        )
        if result.status.value != "gate_reached" or "stop after upload" not in result.stop_reason:
            break
        application_page.wait_for_timeout(2_000)
    if result is None:
        return _outcome(job, BatchApplicationStatus.FAILED, "runner produced no result")
    return indeed_batch_outcome(job.batch_task(), result)


def _retire_if_submitted(page, outcome: BatchApplicationOutcome) -> BatchApplicationOutcome:
    if outcome.status == BatchApplicationStatus.SUBMITTED:
        try:
            page.close()
        except Exception:
            pass
    return outcome


def _worker(job: IndeedUnattendedJob, args: argparse.Namespace) -> BatchApplicationOutcome:
    from playwright.sync_api import sync_playwright

    queue = HumanVerificationQueue(args.queue)
    history = ApplicationSubmissionHistory(args.database)
    if has_recent_exact_submission(
        history,
        company=job.company,
        job_title=job.job_title,
        within_days=args.duplicate_days,
    ):
        return _outcome(
            job,
            BatchApplicationStatus.SKIPPED,
            f"confirmed exact company/title submission exists within {args.duplicate_days} days",
        )

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(args.cdp_url)
        if not browser.contexts:
            return _outcome(job, BatchApplicationStatus.FAILED, "Chrome has no browser context")
        context = browser.contexts[0]
        page, is_application_page = _matching_existing_page(context, job)
        if is_application_page:
            return _retire_if_submitted(
                page,
                _run_application(
                    page,
                    job,
                    args,
                    queue,
                    history,
                    description="",
                ),
            )
        if page is None:
            page = context.new_page()
            page.goto(job.listing_url, wait_until="domcontentloaded", timeout=30_000)
        access = _check_access(page, job, queue)
        if access.blocked:
            return _outcome(
                job,
                BatchApplicationStatus.VERIFICATION_PENDING,
                f"access gate remains pending: {access.reason}",
            )

        body_text = _visible_text(page, "body")
        normalized_body = " ".join(body_text.casefold().split())
        if (
            " ".join(job.job_title.casefold().split()) not in normalized_body
            or " ".join(job.company.casefold().split()) not in normalized_body
        ):
            return _outcome(
                job,
                BatchApplicationStatus.HUMAN_HANDOFF,
                "rendered listing does not prove the exact manifest company/title",
            )
        description = _visible_text(page, "#jobDescriptionText")
        allowed, reason = description_is_allowed(
            description,
            required_any_groups=job.required_any_groups,
            blocked_terms=job.blocked_terms,
        )
        if not allowed:
            return _outcome(job, BatchApplicationStatus.SKIPPED, reason)

        application_page, apply_error = _open_smart_apply(page, context)
        if apply_error:
            return _outcome(job, BatchApplicationStatus.HUMAN_HANDOFF, apply_error)
        return _retire_if_submitted(
            application_page,
            _run_application(
                application_page,
                job,
                args,
                queue,
                history,
                description=description,
            ),
        )


def _run_payload(
    *,
    status: str,
    started_at: str,
    jobs: list[IndeedUnattendedJob],
    latest: dict[str, BatchApplicationOutcome],
    target_submissions: int,
    candidates_started: set[str],
    finished_at: str = "",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": status,
        "started_at": started_at,
        "target_submissions": target_submissions,
        "confirmed_submissions": sum(
            outcome.status == BatchApplicationStatus.SUBMITTED
            for outcome in latest.values()
        ),
        "candidates_started": len(candidates_started),
        "jobs": [job.model_dump(mode="json") for job in jobs],
        "outcomes": [
            latest[job.task_id].model_dump(mode="json")
            for job in jobs
            if job.task_id in latest
        ],
    }
    if finished_at:
        payload["finished_at"] = finished_at
    return payload


def run(args: argparse.Namespace, *, worker=_worker) -> int:
    manifest = IndeedUnattendedManifest.model_validate_json(
        args.manifest.read_text(encoding="utf-8")
    )
    jobs = manifest.jobs[: args.max_candidates]
    started_at = datetime.now(timezone.utc).isoformat()
    outcomes: dict[str, BatchApplicationOutcome] = {}
    latest: dict[str, BatchApplicationOutcome] = {}
    candidates_started: set[str] = set()
    confirmed = 0
    deadline = time.monotonic() + args.verification_wait_minutes * 60
    scheduled: list[tuple[float, int, IndeedUnattendedJob]] = []
    sequence = 0
    for job in jobs:
        heapq.heappush(scheduled, (time.monotonic(), sequence, job))
        sequence += 1
    _write_json(
        args.output / "run.json",
        _run_payload(
            status="running",
            started_at=started_at,
            jobs=jobs,
            latest=latest,
            target_submissions=args.target_submissions,
            candidates_started=candidates_started,
        ),
    )
    with ThreadPoolExecutor(max_workers=args.max_parallel) as executor:
        active = {}
        while scheduled or active:
            now = time.monotonic()
            safe_parallel = min(args.max_parallel, args.target_submissions - confirmed)
            while (
                scheduled
                and scheduled[0][0] <= now
                and len(active) < safe_parallel
                and confirmed < args.target_submissions
            ):
                _, _, job = heapq.heappop(scheduled)
                candidates_started.add(job.task_id)
                active[executor.submit(worker, job, args)] = job
            if not active:
                if confirmed >= args.target_submissions:
                    scheduled.clear()
                    break
                if scheduled:
                    time.sleep(min(0.25, max(0.0, scheduled[0][0] - time.monotonic())))
                continue
            completed, _ = wait(tuple(active), timeout=0.25, return_when=FIRST_COMPLETED)
            for future in completed:
                job = active.pop(future)
                try:
                    outcome = future.result()
                except Exception as exc:
                    outcome = _outcome(
                        job,
                        BatchApplicationStatus.FAILED,
                        f"worker failed closed: {type(exc).__name__}",
                    )
                latest[job.task_id] = outcome
                if (
                    outcome.status == BatchApplicationStatus.SUBMITTED
                    and job.task_id not in outcomes
                ):
                    confirmed += 1
                _write_json(
                    args.output / f"{job.task_id}.json",
                    outcome.model_dump(mode="json"),
                )
                if (
                    outcome.status == BatchApplicationStatus.VERIFICATION_PENDING
                    and time.monotonic() < deadline
                ):
                    # Human gates are delayed tasks, never worker-blocking busy loops.
                    retry_seconds = getattr(args, "verification_retry_seconds", 5.0)
                    heapq.heappush(
                        scheduled,
                        (time.monotonic() + retry_seconds, sequence, job),
                    )
                    sequence += 1
                else:
                    outcomes[job.task_id] = outcome
            _write_json(
                args.output / "run.json",
                _run_payload(
                    status="running",
                    started_at=started_at,
                    jobs=jobs,
                    latest=latest,
                    target_submissions=args.target_submissions,
                    candidates_started=candidates_started,
                ),
            )
            if confirmed >= args.target_submissions:
                scheduled.clear()
            if time.monotonic() >= deadline:
                for _, _, job in scheduled:
                    if job.task_id in candidates_started:
                        outcomes[job.task_id] = latest.get(
                            job.task_id,
                            _outcome(
                                job,
                                BatchApplicationStatus.VERIFICATION_PENDING,
                                "human-verification wait window expired",
                            ),
                        )
                scheduled.clear()
    terminal_status = (
        "target_reached"
        if confirmed >= args.target_submissions
        else "bounded_without_target"
    )
    _write_json(
        args.output / "run.json",
        _run_payload(
            status=terminal_status,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
            jobs=jobs,
            latest=latest,
            target_submissions=args.target_submissions,
            candidates_started=candidates_started,
        ),
    )
    if confirmed >= args.target_submissions:
        return 0
    return 1 if any(
        item.status == BatchApplicationStatus.FAILED for item in outcomes.values()
    ) else 2


def _unique_run_directory(base: Path) -> Path:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate = base / run_id
    suffix = 1
    while candidate.exists():
        candidate = base / f"{run_id}-{suffix}"
        suffix += 1
    candidate.mkdir(parents=True)
    return candidate


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    parser.add_argument(
        "--database",
        type=Path,
        default=ROOT / ".cache" / "application-submissions.sqlite3",
    )
    parser.add_argument(
        "--queue",
        type=Path,
        default=ROOT / ".cache" / "application-verification-queue.json",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "out" / "indeed-unattended")
    parser.add_argument("--target-submissions", type=int, default=3)
    parser.add_argument("--max-parallel", type=int, default=3)
    parser.add_argument("--max-candidates", type=int, default=12)
    parser.add_argument("--verification-wait-minutes", type=int, default=180)
    parser.add_argument("--duplicate-days", type=int, default=30)
    parser.add_argument("--verified-phone", required=True)
    parser.add_argument("--phone-country-calling-code", required=True)
    parser.add_argument("--phone-country-iso", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if not 1 <= args.target_submissions <= 12:
        raise SystemExit("--target-submissions must be between 1 and 12")
    if not 1 <= args.max_parallel <= 5:
        raise SystemExit("--max-parallel must be between 1 and 5")
    if not 1 <= args.max_candidates <= 12:
        raise SystemExit("--max-candidates must be between 1 and 12")
    if not 1 <= args.verification_wait_minutes <= 720:
        raise SystemExit("--verification-wait-minutes must be between 1 and 720")
    args.output = _unique_run_directory(args.output)
    print(f"Indeed unattended run directory: {args.output}", flush=True)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
