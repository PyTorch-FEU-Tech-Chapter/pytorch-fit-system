"""Deterministic access checks and a non-secret human-verification queue."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel

from .privacy import redact


class AccessGateState(str, Enum):
    CLEAR = "clear"
    HUMAN_REQUIRED = "human_required"


class VerificationQueueState(str, Enum):
    PENDING = "pending"
    RESOLVED = "resolved"


class AccessGateResult(BaseModel):
    state: AccessGateState
    reason: str = ""
    evidence: str = ""

    @property
    def blocked(self) -> bool:
        return self.state == AccessGateState.HUMAN_REQUIRED


class VerificationQueueEntry(BaseModel):
    id: str
    application_reference: str
    domain: str
    url: str
    reason: str
    status: VerificationQueueState
    created_at: str
    updated_at: str
    occurrences: int = 1


def sanitize_application_url(url: str) -> str:
    """Remove query parameters and fragments that may contain session identifiers."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _safe_application_reference(application_reference: str, safe_url: str) -> str:
    reference = application_reference.strip()
    parts = urlsplit(reference)
    if parts.scheme and parts.netloc:
        reference = sanitize_application_url(reference)
    return redact(reference, limit=200) or safe_url


def check_access_gate(page: Any) -> AccessGateResult:
    """Classify visible access controls without solving or bypassing them."""
    recaptcha_frames = page.locator('iframe[src*="recaptcha"]')
    for index in range(recaptcha_frames.count()):
        iframe = recaptcha_frames.nth(index)
        if not iframe.is_visible():
            continue
        src = iframe.get_attribute("src") or ""
        if "/bframe" in src:
            return AccessGateResult(
                state=AccessGateState.HUMAN_REQUIRED,
                reason="captcha",
                evidence="visible reCAPTCHA challenge",
            )
        try:
            handle = iframe.element_handle()
            frame = handle.content_frame() if handle is not None else None
            anchor = frame.locator("#recaptcha-anchor") if frame is not None else None
            checked = (
                anchor is not None
                and anchor.count()
                and anchor.get_attribute("aria-checked") == "true"
            )
        except Exception:  # Browser/frame drift must fail closed.
            checked = False
        if checked:
            continue
        return AccessGateResult(
            state=AccessGateState.HUMAN_REQUIRED,
            reason="captcha",
            evidence="visible incomplete reCAPTCHA",
        )

    for selector, reason, evidence in (
        ('iframe[src*="hcaptcha"]', "captcha", "visible hCaptcha"),
        (
            "[data-testid=challenge-form]",
            "verification_required",
            "visible verification challenge",
        ),
    ):
        locator = page.locator(selector)
        if any(locator.nth(index).is_visible() for index in range(locator.count())):
            return AccessGateResult(
                state=AccessGateState.HUMAN_REQUIRED,
                reason=reason,
                evidence=evidence,
            )

    body = page.locator("body").first
    text = body.inner_text().lower() if body.count() else ""
    for marker, reason in (
        ("verify you are human", "verification_required"),
        ("sign in to continue", "signed_out"),
        ("access denied", "blocked"),
        ("too many requests", "rate_limited"),
    ):
        if marker in text:
            return AccessGateResult(
                state=AccessGateState.HUMAN_REQUIRED,
                reason=reason,
                evidence=f"visible page marker: {marker}",
            )
    return AccessGateResult(state=AccessGateState.CLEAR)


class HumanVerificationQueue:
    """JSON-backed queue containing no cookies, credentials, or URL query values."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def enqueue(
        self,
        *,
        application_reference: str,
        url: str,
        result: AccessGateResult,
    ) -> VerificationQueueEntry:
        if not result.blocked:
            raise ValueError("only human-required access results may be queued")
        safe_url = sanitize_application_url(url)
        domain = (urlsplit(safe_url).hostname or "").lower()
        reference = _safe_application_reference(application_reference, safe_url)
        entry_id = self._entry_id(domain, reference)
        payload = self._load()
        existing = payload.get(entry_id)
        now = datetime.now(timezone.utc).isoformat()
        entry = VerificationQueueEntry(
            id=entry_id,
            application_reference=reference,
            domain=domain,
            url=safe_url,
            reason=result.reason,
            status=VerificationQueueState.PENDING,
            created_at=existing.get("created_at", now) if existing else now,
            updated_at=now,
            occurrences=int(existing.get("occurrences", 0)) + 1 if existing else 1,
        )
        payload[entry_id] = entry.model_dump(mode="json")
        self._save(payload)
        return entry

    def resolve_if_clear(
        self,
        *,
        application_reference: str,
        url: str,
        result: AccessGateResult,
    ) -> VerificationQueueEntry | None:
        if result.blocked:
            return None
        safe_url = sanitize_application_url(url)
        domain = (urlsplit(safe_url).hostname or "").lower()
        reference = _safe_application_reference(application_reference, safe_url)
        entry_id = self._entry_id(domain, reference)
        payload = self._load()
        existing = payload.get(entry_id)
        if not existing:
            return None
        existing["status"] = VerificationQueueState.RESOLVED.value
        existing["updated_at"] = datetime.now(timezone.utc).isoformat()
        payload[entry_id] = existing
        self._save(payload)
        return VerificationQueueEntry.model_validate(existing)

    def pending(self) -> list[VerificationQueueEntry]:
        return sorted(
            (
                VerificationQueueEntry.model_validate(value)
                for value in self._load().values()
                if value.get("status") == VerificationQueueState.PENDING.value
            ),
            key=lambda item: item.updated_at,
        )

    @staticmethod
    def _entry_id(domain: str, application_reference: str) -> str:
        value = f"{domain}\n{application_reference}".encode()
        return hashlib.sha256(value).hexdigest()[:20]

    def _load(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self, payload: dict[str, dict]) -> None:
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(self.path)
