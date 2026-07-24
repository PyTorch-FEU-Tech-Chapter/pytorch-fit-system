"""Map Indeed Smart Apply results into the website-agnostic batch contract."""

from __future__ import annotations

from .batch import (
    BatchApplicationOutcome,
    BatchApplicationStatus,
    BatchApplicationTask,
)
from .indeed_smart_apply_runner import (
    IndeedSmartApplyRunResult,
    IndeedSmartApplyRunStatus,
)


def indeed_batch_outcome(
    task: BatchApplicationTask,
    result: IndeedSmartApplyRunResult,
) -> BatchApplicationOutcome:
    if result.status == IndeedSmartApplyRunStatus.POST_APPLY:
        status = BatchApplicationStatus.SUBMITTED
    elif result.status == IndeedSmartApplyRunStatus.SKIPPED_DUPLICATE:
        status = BatchApplicationStatus.SKIPPED
    elif result.status == IndeedSmartApplyRunStatus.FAILED:
        status = BatchApplicationStatus.FAILED
    elif result.status == IndeedSmartApplyRunStatus.HUMAN_HANDOFF and any(
        marker in result.stop_reason.casefold()
        for marker in ("captcha", "verification_required", "access gate")
    ):
        status = BatchApplicationStatus.VERIFICATION_PENDING
    else:
        status = BatchApplicationStatus.HUMAN_HANDOFF
    return BatchApplicationOutcome(
        task=task,
        status=status,
        detail=result.stop_reason,
    )
