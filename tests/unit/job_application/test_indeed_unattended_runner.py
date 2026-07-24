import argparse
import importlib.util
import json
from pathlib import Path
from threading import Lock
import time

from resume_builder.job_application import BatchApplicationOutcome, BatchApplicationStatus


_SCRIPT = Path(__file__).parents[3] / "tools" / "job_finder" / "run_indeed_unattended.py"
_SPEC = importlib.util.spec_from_file_location("run_indeed_unattended", _SCRIPT)
assert _SPEC and _SPEC.loader
runner = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(runner)


def _manifest(path: Path, count: int) -> None:
    jobs = [
        {
            "task_id": f"job-{index}",
            "company": f"Company {index}",
            "job_title": f"Backend Engineer {index}",
            "listing_url": f"https://ca.indeed.com/viewjob?jk={index}",
            "target_country": "Canada",
            "work_mode": "remote",
        }
        for index in range(count)
    ]
    path.write_text(json.dumps({"jobs": jobs}), encoding="utf-8")


def _args(tmp_path: Path, *, count: int, target: int = 3) -> argparse.Namespace:
    manifest = tmp_path / "manifest.json"
    _manifest(manifest, count)
    return argparse.Namespace(
        manifest=manifest,
        output=tmp_path / "run",
        max_candidates=12,
        max_parallel=3,
        target_submissions=target,
        verification_wait_minutes=1,
        verification_retry_seconds=0.01,
    )


def _outcome(job, status):
    return BatchApplicationOutcome(task=job.batch_task(), status=status)


def test_scheduler_replenishes_skips_and_stops_at_exact_target(tmp_path):
    args = _args(tmp_path, count=6)
    started: list[str] = []
    active = 0
    peak = 0
    lock = Lock()

    def worker(job, _args):
        nonlocal active, peak
        with lock:
            started.append(job.task_id)
            active += 1
            peak = max(peak, active)
        time.sleep(0.01)
        with lock:
            active -= 1
        status = (
            BatchApplicationStatus.SKIPPED
            if job.task_id == "job-0"
            else BatchApplicationStatus.SUBMITTED
        )
        return _outcome(job, status)

    assert runner.run(args, worker=worker) == 0
    payload = json.loads((args.output / "run.json").read_text(encoding="utf-8"))
    assert payload["status"] == "target_reached"
    assert payload["confirmed_submissions"] == 3
    assert payload["candidates_started"] == 4
    assert set(started) == {"job-0", "job-1", "job-2", "job-3"}
    assert peak == 3


def test_captcha_retry_reuses_candidate_while_replacements_continue(tmp_path):
    args = _args(tmp_path, count=4)
    calls: dict[str, int] = {}
    order: list[str] = []

    def worker(job, _args):
        calls[job.task_id] = calls.get(job.task_id, 0) + 1
        order.append(job.task_id)
        if job.task_id == "job-0" and calls[job.task_id] == 1:
            return _outcome(job, BatchApplicationStatus.VERIFICATION_PENDING)
        if job.task_id == "job-1":
            return _outcome(job, BatchApplicationStatus.SKIPPED)
        return _outcome(job, BatchApplicationStatus.SUBMITTED)

    assert runner.run(args, worker=worker) == 0
    payload = json.loads((args.output / "run.json").read_text(encoding="utf-8"))
    assert payload["confirmed_submissions"] == 3
    assert calls["job-0"] == 2
    assert order.index("job-3") < len(order) - 1
    assert order[-1] == "job-0"


def test_scheduler_honors_candidate_bound_when_target_is_not_reached(tmp_path):
    args = _args(tmp_path, count=6)
    args.max_candidates = 2

    def worker(job, _args):
        return _outcome(job, BatchApplicationStatus.SKIPPED)

    assert runner.run(args, worker=worker) == 2
    payload = json.loads((args.output / "run.json").read_text(encoding="utf-8"))
    assert payload["status"] == "bounded_without_target"
    assert payload["candidates_started"] == 2


def test_unresolved_validation_is_parked_then_reentered(tmp_path):
    args = _args(tmp_path, count=1, target=1)
    calls = 0

    def worker(job, _args):
        nonlocal calls
        calls += 1
        if calls == 1:
            return BatchApplicationOutcome(
                task=job.batch_task(),
                status=BatchApplicationStatus.HUMAN_HANDOFF,
                detail="module validation remains unresolved: Enter a valid location",
            )
        return _outcome(job, BatchApplicationStatus.SUBMITTED)

    assert runner.run(args, worker=worker) == 0
    assert calls == 2
