"""Deterministic, human-gated execution for job application plans."""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, Field
from resume_builder.extraction.crawler_dom import fingerprint

from .models import ApplicationPlan, BrowserAction, DynamicApplicationPlan, DynamicInteractionStep
from .ledger import ApplicationLedger, LedgerState
from .permissions import ApplicationPermissionPolicy
from .privacy import redact


class ExecutionStatus(str, Enum):
    """Terminal state of one application execution attempt."""

    DRAFT_READY = "draft_ready"
    SUBMITTED = "submitted"
    HUMAN_HANDOFF = "human_handoff"
    FAILED = "failed"
    SUBMISSION_UNKNOWN = "submission_unknown"
    ALREADY_SUBMITTED = "already_submitted"


class ExecutionEvent(BaseModel):
    """Auditable record of a deterministic browser action."""

    step: int
    action: str
    target: str
    status: str
    detail: str = ""


class ApplicationExecutionResult(BaseModel):
    """Result returned without exposing credentials, cookies, or storage state."""

    status: ExecutionStatus
    events: list[ExecutionEvent] = Field(default_factory=list)
    confirmation_text: str = ""
    stopped_before_submit: bool = True


class SafeApplicationExecutor:
    """Execute an accepted plan while preserving the final human approval gate.

    ``page`` is intentionally typed as ``Any`` so the core package does not require
    Playwright at import time. At runtime it must provide Playwright's Page API.
    """

    _SUBMIT_HINT = re.compile(r"submit|send[-_ ]?application|apply[-_ ]?now|final", re.I)

    def __init__(self, *, max_attempts: int = 3) -> None:
        self.max_attempts = max(1, max_attempts)

    def execute(
        self,
        page: Any,
        application_plan: ApplicationPlan,
        dynamic_plan: DynamicApplicationPlan | None = None,
        *,
        human_approved: bool = False,
        permission_policy: ApplicationPermissionPolicy | None = None,
        application_id: str = "",
        ledger: ApplicationLedger | None = None,
    ) -> ApplicationExecutionResult:
        events: list[ExecutionEvent] = []
        policy = permission_policy or ApplicationPermissionPolicy()
        domain = (urlsplit(str(getattr(page, "url", ""))).hostname or "").lower()

        if dynamic_plan and not self._plan_matches_page(page, dynamic_plan):
            return ApplicationExecutionResult(
                status=ExecutionStatus.HUMAN_HANDOFF,
                events=[ExecutionEvent(step=0, action="validate_plan", target=domain,
                                       status="blocked", detail="domain or layout mismatch")],
            )
        if ledger and application_id:
            existing = ledger.get(application_id)
            if existing and existing.state == LedgerState.SUBMITTED:
                return ApplicationExecutionResult(
                    status=ExecutionStatus.ALREADY_SUBMITTED,
                    confirmation_text=existing.confirmation,
                )

        if application_plan.missing_information:
            return ApplicationExecutionResult(
                status=ExecutionStatus.HUMAN_HANDOFF,
                events=[
                    ExecutionEvent(
                        step=0,
                        action="validate_input",
                        target="missing_information",
                        status="blocked",
                        detail=", ".join(
                            item.canonical for item in application_plan.missing_information
                        ),
                    )
                ],
            )

        try:
            for action in sorted(application_plan.browser_actions, key=lambda item: item.step):
                if self._is_submit_action(action.action, action.target):
                    validation_error = self._validate(page, application_plan)
                    if validation_error:
                        events.append(ExecutionEvent(step=action.step, action="validate",
                                                     target="application", status="failed",
                                                     detail=validation_error))
                        return ApplicationExecutionResult(status=ExecutionStatus.FAILED,
                                                          events=events)
                    submit_result = self._submit_or_stop(
                        page,
                        action.step,
                        action.target,
                        None,
                        human_approved or policy.allows("irreversible", domain=domain),
                        events,
                        application_id,
                        ledger,
                    )
                    if submit_result is not None:
                        return submit_result
                    continue
                if not policy.allows(action.action_class, domain=domain):
                    events.append(ExecutionEvent(step=action.step, action=action.action,
                                                 target=action.target, status="blocked",
                                                 detail="permission required"))
                    return ApplicationExecutionResult(status=ExecutionStatus.HUMAN_HANDOFF,
                                                      events=events)
                self._retry(page, lambda: self._execute_browser_action(page, action))
                events.append(
                    ExecutionEvent(
                        step=action.step,
                        action=action.action,
                        target=action.target,
                        status="completed",
                    )
                )

            for step in sorted(
                dynamic_plan.interaction_steps if dynamic_plan else [],
                key=lambda item: item.step,
            ):
                if step.action == "final_submit":
                    validation_error = self._validate(page, application_plan)
                    if validation_error:
                        events.append(ExecutionEvent(step=step.step, action="validate",
                                                     target="application", status="failed",
                                                     detail=validation_error))
                        return ApplicationExecutionResult(status=ExecutionStatus.FAILED,
                                                          events=events)
                    result = self._submit_or_stop(
                        page,
                        step.step,
                        step.selector,
                        step.wait_for_selector,
                        human_approved or policy.allows("irreversible", domain=domain),
                        events,
                        application_id,
                        ledger,
                    )
                    if result is not None:
                        return result
                    continue

                action_class = (
                    "sensitive_write"
                    if step.requires_human and step.action != "final_submit"
                    else step.action_class
                )
                if not policy.allows(action_class, domain=domain):
                    events.append(self._interaction_event(step, "blocked", "human review required"))
                    return ApplicationExecutionResult(
                        status=ExecutionStatus.HUMAN_HANDOFF,
                        events=events,
                    )

                self._retry(page, lambda: self._execute_interaction(page, step))
                events.append(self._interaction_event(step, "completed"))

            validation_error = self._validate(page, application_plan)
            if validation_error:
                events.append(ExecutionEvent(step=len(events) + 1, action="validate",
                                             target="application", status="failed",
                                             detail=validation_error))
                return ApplicationExecutionResult(status=ExecutionStatus.FAILED, events=events)

            return ApplicationExecutionResult(
                status=ExecutionStatus.DRAFT_READY,
                events=events,
            )
        except Exception as exc:  # Playwright errors vary by installed version.
            events.append(
                ExecutionEvent(
                    step=len(events) + 1,
                    action="execution_error",
                    target="browser",
                    status="failed",
                    detail=redact(str(exc)),
                )
            )
            return ApplicationExecutionResult(status=ExecutionStatus.FAILED, events=events)

    def _execute_browser_action(self, page: Any, action: BrowserAction) -> None:
        locator = page.locator(action.target)
        locator.wait_for(state="visible")
        normalized = action.action.lower().strip()

        if normalized in {"fill", "type"}:
            locator.fill(action.value)
        elif normalized == "select":
            locator.select_option(value=action.value)
        elif normalized == "check":
            locator.check()
        elif normalized == "upload":
            upload = Path(action.value).expanduser().resolve()
            if not upload.is_file():
                raise FileNotFoundError(f"Upload file does not exist: {upload}")
            locator.set_input_files(str(upload))
        elif normalized == "click":
            locator.click()
        else:
            raise ValueError(f"Unsupported browser action: {action.action}")

    @staticmethod
    def _execute_interaction(page: Any, step: DynamicInteractionStep) -> None:
        locator = page.locator(step.selector)
        locator.wait_for(state="visible")
        if step.action in {"click", "expand", "open"}:
            locator.click()
        elif step.action in {"fill", "type"}:
            locator.fill(step.value)
        elif step.action == "select":
            locator.select_option(value=step.value)
        elif step.action == "check":
            locator.check()
        elif step.action == "upload":
            upload = Path(step.value).expanduser().resolve()
            if not upload.is_file():
                raise FileNotFoundError(f"Upload file does not exist: {upload}")
            locator.set_input_files(str(upload))
        elif step.action in {"read", "extract"}:
            locator.text_content()
        else:
            raise ValueError(f"Unsupported dynamic interaction: {step.action}")
        if step.wait_for_selector:
            page.locator(step.wait_for_selector).wait_for(state="visible")

    def _submit_or_stop(
        self,
        page: Any,
        step: int,
        selector: str,
        confirmation_selector: str | None,
        human_approved: bool,
        events: list[ExecutionEvent],
        application_id: str,
        ledger: ApplicationLedger | None,
    ) -> ApplicationExecutionResult | None:
        if not human_approved:
            events.append(
                ExecutionEvent(
                    step=step,
                    action="final_submit",
                    target=selector,
                    status="blocked",
                    detail="explicit human approval required",
                )
            )
            return ApplicationExecutionResult(
                status=ExecutionStatus.DRAFT_READY,
                events=events,
            )

        if ledger and application_id:
            ledger.set(application_id, LedgerState.SUBMITTING)
        locator = page.locator(selector)
        locator.wait_for(state="visible")
        locator.click()
        confirmation_text = ""
        if confirmation_selector:
            try:
                confirmation = page.locator(confirmation_selector)
                confirmation.wait_for(state="visible")
                confirmation_text = (confirmation.text_content() or "").strip()
            except Exception:
                if ledger and application_id:
                    ledger.set(application_id, LedgerState.SUBMISSION_UNKNOWN)
                events.append(ExecutionEvent(step=step, action="final_submit", target=selector,
                                             status="unknown",
                                             detail="confirmation proof not observed"))
                return ApplicationExecutionResult(
                    status=ExecutionStatus.SUBMISSION_UNKNOWN, events=events
                )
        else:
            if ledger and application_id:
                ledger.set(application_id, LedgerState.SUBMISSION_UNKNOWN)
            events.append(ExecutionEvent(step=step, action="final_submit", target=selector,
                                         status="unknown",
                                         detail="no confirmation proof configured"))
            return ApplicationExecutionResult(
                status=ExecutionStatus.SUBMISSION_UNKNOWN, events=events
            )
        events.append(
            ExecutionEvent(
                step=step,
                action="final_submit",
                target=selector,
                status="completed",
                detail=confirmation_text,
            )
        )
        if ledger and application_id:
            ledger.set(application_id, LedgerState.SUBMITTED, confirmation_text)
        return ApplicationExecutionResult(
            status=ExecutionStatus.SUBMITTED,
            events=events,
            confirmation_text=confirmation_text,
            stopped_before_submit=False,
        )

    def _is_submit_action(self, action: str, target: str) -> bool:
        return action.lower().strip() in {"submit", "final_submit"} or bool(
            self._SUBMIT_HINT.search(target)
        )

    @staticmethod
    def _plan_matches_page(page: Any, plan: DynamicApplicationPlan) -> bool:
        host = (urlsplit(str(getattr(page, "url", ""))).hostname or "").lower()
        if not host:
            return True
        if plan.root_domain and not (host == plan.root_domain or host.endswith("." + plan.root_domain)):
            return False
        sample_hosts = {sample.subdomain.lower() for sample in plan.samples}
        if sample_hosts and host not in sample_hosts:
            return False
        host_fingerprints = {
            sample.layout_fingerprint
            for sample in plan.samples
            if sample.subdomain.lower() == host
        }
        if host_fingerprints and hasattr(page, "content"):
            return fingerprint(page.content()) in host_fingerprints
        return True

    def _retry(self, page: Any, action) -> None:
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                action()
                return
            except Exception as exc:
                last_error = exc
                if attempt + 1 < self.max_attempts:
                    page.wait_for_timeout(250 * (2 ** attempt))
        if last_error:
            raise last_error

    @staticmethod
    def _validate(page: Any, plan: ApplicationPlan) -> str:
        for validation in plan.validation_steps:
            if not validation.selector:
                continue
            locator = page.locator(validation.selector)
            if validation.expected == "hidden":
                passed = locator.count() == 0 or locator.is_hidden()
            elif validation.expected == "checked":
                passed = locator.is_checked()
            else:
                passed = locator.count() > 0 and locator.is_visible()
            if validation.required and not passed:
                return f"validation failed: {validation.check}"
        return ""

    @staticmethod
    def _interaction_event(
        step: DynamicInteractionStep,
        status: str,
        detail: str = "",
    ) -> ExecutionEvent:
        return ExecutionEvent(
            step=step.step,
            action=step.action,
            target=step.selector,
            status=status,
            detail=detail,
        )
