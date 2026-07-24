"""Sequential deterministic execution for verified Indeed Smart Apply modules."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from resume_builder.core.models import Resume

from .indeed_smart_apply import (
    IndeedSmartApplyModule,
    SmartApplyApprovals,
    build_indeed_smart_apply_plan,
    classify_indeed_smart_apply_module,
)
from .autonomous_questions import QuestionPlanningResult
from .permissions import ApplicationPermissionPolicy


class IndeedSmartApplyRunStatus(str, Enum):
    GATE_REACHED = "gate_reached"
    REVIEW_READY = "review_ready"
    POST_APPLY = "post_apply"
    HUMAN_HANDOFF = "human_handoff"
    FAILED = "failed"


class IndeedSmartApplyRunResult(BaseModel):
    status: IndeedSmartApplyRunStatus
    module: IndeedSmartApplyModule
    modules_seen: list[IndeedSmartApplyModule] = Field(default_factory=list)
    actions_executed: list[str] = Field(default_factory=list)
    stop_reason: str = ""
    selected_resume: str = ""


def _first(page: Any, selector: str) -> Any:
    return page.locator(selector).first


def _input_value(page: Any, selector: str) -> str:
    locator = _first(page, selector)
    return locator.input_value() if locator.count() else ""


def _visible_access_blocker(page: Any) -> str:
    recaptcha_frames = page.locator('iframe[src*="recaptcha"]')
    for index in range(recaptcha_frames.count()):
        iframe = recaptcha_frames.nth(index)
        if not iframe.is_visible():
            continue
        src = iframe.get_attribute("src") or ""
        if "/bframe" in src:
            return "captcha"
        handle = iframe.element_handle()
        frame = handle.content_frame() if handle is not None else None
        anchor = frame.locator("#recaptcha-anchor") if frame is not None else None
        if (
            anchor is not None
            and anchor.count()
            and anchor.get_attribute("aria-checked") == "true"
        ):
            continue
        return "captcha"

    for selector, reason in (
        ('iframe[src*="hcaptcha"]', "captcha"),
        ("[data-testid=challenge-form]", "verification_required"),
    ):
        locator = page.locator(selector)
        if any(locator.nth(index).is_visible() for index in range(locator.count())):
            return reason

    text = _first(page, "body").inner_text().lower()
    for marker, reason in (
        ("verify you are human", "verification_required"),
        ("sign in to continue", "signed_out"),
        ("access denied", "blocked"),
        ("too many requests", "rate_limited"),
    ):
        if marker in text:
            return reason
    return ""


def _observe_fields(page: Any, module: IndeedSmartApplyModule) -> dict[str, str]:
    if module == IndeedSmartApplyModule.CONTACT:
        return {
            "first_name": _input_value(
                page,
                "[data-testid=name-fields-first-name-input], input[name=firstName]",
            ),
            "last_name": _input_value(
                page,
                "[data-testid=name-fields-last-name-input], input[name=lastName]",
            ),
            "phone": _input_value(page, "input[name=phone], input[type=tel]"),
        }
    if module == IndeedSmartApplyModule.LOCATION:
        body = _first(page, "body").inner_text()
        return {"country": "Philippines" if "Philippines" in body else ""}
    return {}


def _selected_resume(page: Any, approved_resume: Path | None) -> str:
    if approved_resume is None:
        return ""
    return approved_resume.name if approved_resume.name in _first(page, "body").inner_text() else ""


def _execute_action(page: Any, action: Any) -> None:
    locator = _first(page, action.target)
    normalized = action.action.lower().strip()
    if normalized == "upload":
        locator.set_input_files(action.value)
    elif normalized in {"fill", "type"}:
        locator.wait_for(state="visible")
        locator.fill(action.value)
    elif normalized == "click":
        locator.wait_for(state="visible")
        locator.click()
    elif normalized == "final_submit":
        locator.wait_for(state="visible")
        locator.click()
    else:
        raise ValueError(f"unsupported Indeed Smart Apply action: {action.action}")


def _execute_question_step(page: Any, step: Any) -> None:
    locator = _first(page, step.selector)
    if step.action in {"fill", "type"}:
        locator.wait_for(state="visible")
        locator.fill(step.value)
    elif step.action == "select":
        locator.wait_for(state="visible")
        locator.get_by_text(step.value, exact=True).last.click()
    elif step.action == "check":
        locator.wait_for(state="visible")
        locator.check()
    else:
        raise ValueError(f"unsupported screening-question action: {step.action}")


def _required_question_answers_present(page: Any) -> bool:
    groups = page.locator('fieldset[role="radiogroup"]')
    for index in range(groups.count()):
        if groups.nth(index).locator("input:checked").count() == 0:
            return False
    for selector in ("input[required]:not([type=radio])", "textarea[required]", "select[required]"):
        fields = page.locator(selector)
        for index in range(fields.count()):
            if not fields.nth(index).input_value().strip():
                return False
    return True


def _wait_for_url_change(page: Any, before_url: str, *, timeout_ms: int = 5_000) -> bool:
    interval_ms = 250
    attempts = max(1, timeout_ms // interval_ms)
    for _ in range(attempts):
        if str(page.url) != before_url:
            return True
        page.wait_for_timeout(interval_ms)
    return str(page.url) != before_url


def _wait_for_known_module(page: Any, *, timeout_ms: int = 5_000) -> IndeedSmartApplyModule:
    interval_ms = 250
    attempts = max(1, timeout_ms // interval_ms)
    for _ in range(attempts):
        module = classify_indeed_smart_apply_module(str(page.url))
        if module != IndeedSmartApplyModule.UNKNOWN:
            return module
        page.wait_for_timeout(interval_ms)
    return classify_indeed_smart_apply_module(str(page.url))


def run_indeed_smart_apply_until_gate(
    page: Any,
    resume: Resume,
    *,
    approved_resume: Path | None = None,
    approvals: SmartApplyApprovals | None = None,
    permission_policy: ApplicationPermissionPolicy | None = None,
    verified_phone: str = "",
    phone_country_calling_code: str = "",
    question_plan: QuestionPlanningResult | None = None,
    max_modules: int = 8,
) -> IndeedSmartApplyRunResult:
    """Advance known modules and stop at the next human or AI fallback gate."""
    gates = approvals or SmartApplyApprovals()
    policy = permission_policy or ApplicationPermissionPolicy()
    seen: list[IndeedSmartApplyModule] = []
    executed: list[str] = []

    for _ in range(max(1, max_modules)):
        blocker = _visible_access_blocker(page)
        module = classify_indeed_smart_apply_module(str(page.url))
        if blocker:
            return IndeedSmartApplyRunResult(
                status=IndeedSmartApplyRunStatus.HUMAN_HANDOFF,
                module=module,
                modules_seen=seen,
                actions_executed=executed,
                stop_reason=f"access gate: {blocker}",
            )
        if module == IndeedSmartApplyModule.UNKNOWN:
            module = _wait_for_known_module(page)
        seen.append(module)
        if module == IndeedSmartApplyModule.UNKNOWN:
            return IndeedSmartApplyRunResult(
                status=IndeedSmartApplyRunStatus.HUMAN_HANDOFF,
                module=module,
                modules_seen=seen,
                actions_executed=executed,
                stop_reason="unknown module requires bounded AI sampling",
            )
        if module == IndeedSmartApplyModule.POST_APPLY:
            return IndeedSmartApplyRunResult(
                status=IndeedSmartApplyRunStatus.POST_APPLY,
                module=module,
                modules_seen=seen,
                actions_executed=executed,
                stop_reason="observable post-apply page reached",
            )
        if module == IndeedSmartApplyModule.QUESTIONS:
            if question_plan is None or question_plan.unresolved or not question_plan.steps:
                return IndeedSmartApplyRunResult(
                    status=IndeedSmartApplyRunStatus.HUMAN_HANDOFF,
                    module=module,
                    modules_seen=seen,
                    actions_executed=executed,
                    stop_reason=(
                        "questionnaire requires an accepted evidence-grounded answer plan"
                    ),
                )
            domain = (urlsplit(str(page.url)).hostname or "").lower()
            for step in sorted(question_plan.steps, key=lambda item: item.step):
                if not policy.allows(step.action_class, domain=domain):
                    return IndeedSmartApplyRunResult(
                        status=IndeedSmartApplyRunStatus.GATE_REACHED,
                        module=module,
                        modules_seen=seen,
                        actions_executed=executed,
                        stop_reason=f"{step.action_class} permission required",
                    )
                _execute_question_step(page, step)
                executed.append(f"{module.value}:{step.action}")
            if not _required_question_answers_present(page):
                return IndeedSmartApplyRunResult(
                    status=IndeedSmartApplyRunStatus.GATE_REACHED,
                    module=module,
                    modules_seen=seen,
                    actions_executed=executed,
                    stop_reason="required questionnaire fields remain unanswered",
                )
            before_url = str(page.url)
            _first(page, "button:visible:has-text('Continue')").click()
            executed.append(f"{module.value}:click")
            question_plan = None
            if not _wait_for_url_change(page, before_url):
                return IndeedSmartApplyRunResult(
                    status=IndeedSmartApplyRunStatus.FAILED,
                    module=module,
                    modules_seen=seen,
                    actions_executed=executed,
                    stop_reason="expected questionnaire transition was not observed",
                )
            if (
                classify_indeed_smart_apply_module(str(page.url))
                == IndeedSmartApplyModule.QUESTIONS
            ):
                return IndeedSmartApplyRunResult(
                    status=IndeedSmartApplyRunStatus.GATE_REACHED,
                    module=module,
                    modules_seen=seen,
                    actions_executed=executed,
                    stop_reason="next questionnaire page requires fresh inventory and planning",
                )
            continue

        selected = _selected_resume(page, approved_resume)
        plan = build_indeed_smart_apply_plan(
            str(page.url),
            resume,
            field_values=_observe_fields(page, module),
            selected_resume=selected,
            approved_resume=approved_resume,
            approvals=gates,
            verified_phone=verified_phone,
            phone_country_calling_code=phone_country_calling_code,
        )
        if module == IndeedSmartApplyModule.REVIEW and not plan.browser_actions:
            return IndeedSmartApplyRunResult(
                status=IndeedSmartApplyRunStatus.REVIEW_READY,
                module=module,
                modules_seen=seen,
                actions_executed=executed,
                stop_reason=plan.stop_reason,
                selected_resume=plan.selected_resume,
            )
        if not plan.browser_actions:
            return IndeedSmartApplyRunResult(
                status=IndeedSmartApplyRunStatus.GATE_REACHED,
                module=module,
                modules_seen=seen,
                actions_executed=executed,
                stop_reason=plan.stop_reason or "no safe deterministic action",
                selected_resume=plan.selected_resume,
            )

        before_url = str(page.url)
        for action in sorted(plan.browser_actions, key=lambda item: item.step):
            domain = (urlsplit(str(page.url)).hostname or "").lower()
            if not policy.allows(action.action_class, domain=domain):
                return IndeedSmartApplyRunResult(
                    status=IndeedSmartApplyRunStatus.GATE_REACHED,
                    module=module,
                    modules_seen=seen,
                    actions_executed=executed,
                    stop_reason=f"{action.action_class} permission required",
                    selected_resume=plan.selected_resume,
                )
            _execute_action(page, action)
            executed.append(f"{module.value}:{action.action}")

        submitted = any(
            action.action.lower().strip() == "final_submit"
            for action in plan.browser_actions
        )
        if submitted:
            if not _wait_for_url_change(page, before_url):
                return IndeedSmartApplyRunResult(
                    status=IndeedSmartApplyRunStatus.FAILED,
                    module=module,
                    modules_seen=seen,
                    actions_executed=executed,
                    stop_reason="submission outcome was not observably confirmed; do not retry",
                    selected_resume=plan.selected_resume,
                )
            next_module = _wait_for_known_module(page)
            if next_module == IndeedSmartApplyModule.POST_APPLY:
                return IndeedSmartApplyRunResult(
                    status=IndeedSmartApplyRunStatus.POST_APPLY,
                    module=next_module,
                    modules_seen=seen,
                    actions_executed=executed,
                    stop_reason="observable post-apply page reached",
                    selected_resume=plan.selected_resume,
                )
            return IndeedSmartApplyRunResult(
                status=IndeedSmartApplyRunStatus.FAILED,
                module=next_module,
                modules_seen=seen,
                actions_executed=executed,
                stop_reason="submit navigated to an unexpected route; do not retry",
                selected_resume=plan.selected_resume,
            )

        if plan.stop_reason:
            return IndeedSmartApplyRunResult(
                status=IndeedSmartApplyRunStatus.GATE_REACHED,
                module=module,
                modules_seen=seen,
                actions_executed=executed,
                stop_reason=plan.stop_reason,
                selected_resume=plan.selected_resume,
            )

        if not _wait_for_url_change(page, before_url):
            return IndeedSmartApplyRunResult(
                status=IndeedSmartApplyRunStatus.FAILED,
                module=module,
                modules_seen=seen,
                actions_executed=executed,
                stop_reason="expected module transition was not observed",
                selected_resume=plan.selected_resume,
            )

    current = classify_indeed_smart_apply_module(str(page.url))
    return IndeedSmartApplyRunResult(
        status=IndeedSmartApplyRunStatus.HUMAN_HANDOFF,
        module=current,
        modules_seen=seen,
        actions_executed=executed,
        stop_reason="bounded module limit reached",
    )
