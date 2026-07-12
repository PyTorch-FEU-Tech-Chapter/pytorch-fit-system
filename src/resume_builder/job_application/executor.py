"""Deterministic, human-gated execution for job application plans."""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .models import ApplicationPlan, BrowserAction, DynamicApplicationPlan, DynamicInteractionStep


class ExecutionStatus(str, Enum):
    """Terminal state of one application execution attempt."""

    DRAFT_READY = "draft_ready"
    SUBMITTED = "submitted"
    HUMAN_HANDOFF = "human_handoff"
    FAILED = "failed"


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

    def execute(
        self,
        page: Any,
        application_plan: ApplicationPlan,
        dynamic_plan: DynamicApplicationPlan | None = None,
        *,
        human_approved: bool = False,
    ) -> ApplicationExecutionResult:
        events: list[ExecutionEvent] = []

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
                    submit_result = self._submit_or_stop(
                        page,
                        action.step,
                        action.target,
                        None,
                        human_approved,
                        events,
                    )
                    if submit_result is not None:
                        return submit_result
                    continue
                self._execute_browser_action(page, action)
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
                    result = self._submit_or_stop(
                        page,
                        step.step,
                        step.selector,
                        step.wait_for_selector,
                        human_approved,
                        events,
                    )
                    if result is not None:
                        return result
                    continue

                if step.requires_human or not step.safe_read_only:
                    events.append(self._interaction_event(step, "blocked", "human review required"))
                    return ApplicationExecutionResult(
                        status=ExecutionStatus.HUMAN_HANDOFF,
                        events=events,
                    )

                self._execute_interaction(page, step)
                events.append(self._interaction_event(step, "completed"))

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
                    detail=str(exc),
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
        if step.action == "click":
            locator.click()
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

        locator = page.locator(selector)
        locator.wait_for(state="visible")
        locator.click()
        confirmation_text = ""
        if confirmation_selector:
            confirmation = page.locator(confirmation_selector)
            confirmation.wait_for(state="visible")
            confirmation_text = (confirmation.text_content() or "").strip()
        events.append(
            ExecutionEvent(
                step=step,
                action="final_submit",
                target=selector,
                status="completed",
                detail=confirmation_text,
            )
        )
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
