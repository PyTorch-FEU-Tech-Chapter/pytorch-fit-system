"""SQLite application history with an atomic recent-duplicate submission guard."""

from __future__ import annotations

import sqlite3
import unicodedata
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel

from .ledger import LedgerState
from .privacy import redact


class SubmissionDecision(str, Enum):
    RESERVED = "reserved"
    RECENT_DUPLICATE = "recent_duplicate"
    UNRESOLVED_ATTEMPT = "unresolved_attempt"


class SubmissionReservation(BaseModel):
    decision: SubmissionDecision
    application_id: int | None = None
    matched_application_id: int | None = None
    matched_applied_at: str = ""

    @property
    def allowed(self) -> bool:
        return self.decision == SubmissionDecision.RESERVED


class ApplicationHistoryEntry(BaseModel):
    id: int
    company: str
    job_title: str
    state: LedgerState
    applied_at: str = ""
    updated_at: str
    confirmation: str = ""
    source_domain: str = ""
    source_url: str = ""


def normalize_exact_identity(value: str) -> str:
    """Normalize presentation differences while preserving exact word identity."""
    return unicodedata.normalize("NFKC", " ".join(value.split())).casefold()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_source_url(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}" if parts.scheme else ""


class ApplicationSubmissionHistory:
    """Durable SQL history for exact company/title submission decisions."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def reserve_submission(
        self,
        *,
        company: str,
        job_title: str,
        source_url: str = "",
        within_days: int = 30,
        now: datetime | None = None,
    ) -> SubmissionReservation:
        """Atomically query recent history and reserve an eligible submission."""
        if within_days < 1:
            raise ValueError("within_days must be at least 1")
        company_value, title_value = self._validated_identity(company, job_title)
        timestamp = (now or _utc_now()).astimezone(timezone.utc)
        timestamp_text = timestamp.isoformat()
        cutoff = (timestamp - timedelta(days=within_days)).isoformat()
        company_key = normalize_exact_identity(company_value)
        title_key = normalize_exact_identity(title_value)
        safe_url = _safe_source_url(source_url)
        domain = (urlsplit(safe_url).hostname or "").lower()

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            recent = connection.execute(
                """
                SELECT id, applied_at
                FROM applications
                WHERE company_key = ?
                  AND job_title_key = ?
                  AND state = ?
                  AND applied_at >= ?
                ORDER BY applied_at DESC
                LIMIT 1
                """,
                (company_key, title_key, LedgerState.SUBMITTED.value, cutoff),
            ).fetchone()
            if recent:
                reservation = SubmissionReservation(
                    decision=SubmissionDecision.RECENT_DUPLICATE,
                    matched_application_id=recent["id"],
                    matched_applied_at=recent["applied_at"] or "",
                )
                self._insert_audit(
                    connection,
                    timestamp_text,
                    company_value,
                    title_value,
                    "eligibility_check",
                    reservation.decision.value,
                    f"confirmed submission found within {within_days} days",
                )
                return reservation

            unresolved = connection.execute(
                """
                SELECT id, updated_at
                FROM applications
                WHERE company_key = ?
                  AND job_title_key = ?
                  AND state IN (?, ?)
                  AND updated_at >= ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (
                    company_key,
                    title_key,
                    LedgerState.SUBMITTING.value,
                    LedgerState.SUBMISSION_UNKNOWN.value,
                    cutoff,
                ),
            ).fetchone()
            if unresolved:
                reservation = SubmissionReservation(
                    decision=SubmissionDecision.UNRESOLVED_ATTEMPT,
                    matched_application_id=unresolved["id"],
                )
                self._insert_audit(
                    connection,
                    timestamp_text,
                    company_value,
                    title_value,
                    "eligibility_check",
                    reservation.decision.value,
                    "recent submission attempt has no confirmed outcome",
                )
                return reservation

            cursor = connection.execute(
                """
                INSERT INTO applications (
                    company, job_title, company_key, job_title_key, state,
                    applied_at, updated_at, confirmation, source_domain, source_url
                ) VALUES (?, ?, ?, ?, ?, NULL, ?, '', ?, ?)
                """,
                (
                    company_value,
                    title_value,
                    company_key,
                    title_key,
                    LedgerState.SUBMITTING.value,
                    timestamp_text,
                    domain,
                    safe_url,
                ),
            )
            application_id = int(cursor.lastrowid)
            self._insert_audit(
                connection,
                timestamp_text,
                company_value,
                title_value,
                "eligibility_check",
                SubmissionDecision.RESERVED.value,
                f"no confirmed submission found within {within_days} days",
                application_id=application_id,
            )
            return SubmissionReservation(
                decision=SubmissionDecision.RESERVED,
                application_id=application_id,
            )

    def mark_submitted(
        self,
        application_id: int,
        *,
        confirmation: str = "",
        now: datetime | None = None,
    ) -> ApplicationHistoryEntry:
        return self._mark(
            application_id,
            LedgerState.SUBMITTED,
            confirmation=confirmation,
            applied_at=now or _utc_now(),
            audit_action="submission_confirmed",
        )

    def mark_submission_unknown(
        self,
        application_id: int,
        *,
        details: str = "",
    ) -> ApplicationHistoryEntry:
        return self._mark(
            application_id,
            LedgerState.SUBMISSION_UNKNOWN,
            confirmation=details,
            audit_action="submission_unknown",
        )

    def mark_failed(self, application_id: int, *, details: str = "") -> ApplicationHistoryEntry:
        return self._mark(
            application_id,
            LedgerState.FAILED,
            confirmation=details,
            audit_action="submission_failed",
        )

    def record_existing_submission(
        self,
        *,
        company: str,
        job_title: str,
        applied_at: datetime,
        confirmation: str = "confirmed in browser",
        source_url: str = "",
    ) -> ApplicationHistoryEntry:
        """Seed a known confirmed submission without duplicating a recent record."""
        reservation = self.reserve_submission(
            company=company,
            job_title=job_title,
            source_url=source_url,
            now=applied_at,
        )
        if reservation.allowed and reservation.application_id is not None:
            return self.mark_submitted(
                reservation.application_id,
                confirmation=confirmation,
                now=applied_at,
            )
        if reservation.matched_application_id is None:
            raise RuntimeError("submission history returned no matching application")
        entry = self.get(reservation.matched_application_id)
        if entry is None:
            raise RuntimeError("matching submission history entry was not found")
        return entry

    def get(self, application_id: int) -> ApplicationHistoryEntry | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM applications WHERE id = ?",
                (application_id,),
            ).fetchone()
        return self._entry(row) if row else None

    def recent_submissions(
        self,
        *,
        within_days: int = 30,
        now: datetime | None = None,
    ) -> list[ApplicationHistoryEntry]:
        timestamp = (now or _utc_now()).astimezone(timezone.utc)
        cutoff = (timestamp - timedelta(days=within_days)).isoformat()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM applications
                WHERE state = ? AND applied_at >= ?
                ORDER BY applied_at DESC
                """,
                (LedgerState.SUBMITTED.value, cutoff),
            ).fetchall()
        return [self._entry(row) for row in rows]

    def _mark(
        self,
        application_id: int,
        state: LedgerState,
        *,
        confirmation: str,
        audit_action: str,
        applied_at: datetime | None = None,
    ) -> ApplicationHistoryEntry:
        timestamp = _utc_now().isoformat()
        applied_at_text = (
            applied_at.astimezone(timezone.utc).isoformat() if applied_at is not None else None
        )
        safe_confirmation = redact(confirmation, limit=500)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM applications WHERE id = ?",
                (application_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"application history id {application_id} does not exist")
            connection.execute(
                """
                UPDATE applications
                SET state = ?, applied_at = COALESCE(?, applied_at),
                    updated_at = ?, confirmation = ?
                WHERE id = ?
                """,
                (
                    state.value,
                    applied_at_text,
                    timestamp,
                    safe_confirmation,
                    application_id,
                ),
            )
            self._insert_audit(
                connection,
                timestamp,
                row["company"],
                row["job_title"],
                audit_action,
                state.value,
                safe_confirmation,
                application_id=application_id,
            )
        entry = self.get(application_id)
        if entry is None:
            raise RuntimeError("updated application history entry was not found")
        return entry

    @staticmethod
    def _validated_identity(company: str, job_title: str) -> tuple[str, str]:
        company_value = " ".join(company.split())
        title_value = " ".join(job_title.split())
        if not company_value or not title_value:
            raise ValueError("company and exact job title are required")
        return company_value, title_value

    @staticmethod
    def _insert_audit(
        connection: sqlite3.Connection,
        event_at: str,
        company: str,
        job_title: str,
        action: str,
        decision: str,
        details: str,
        *,
        application_id: int | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO submission_audit (
                application_id, event_at, company, job_title, action, decision, details
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                application_id,
                event_at,
                company,
                job_title,
                action,
                decision,
                redact(details, limit=500),
            ),
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company TEXT NOT NULL,
                    job_title TEXT NOT NULL,
                    company_key TEXT NOT NULL,
                    job_title_key TEXT NOT NULL,
                    state TEXT NOT NULL,
                    applied_at TEXT,
                    updated_at TEXT NOT NULL,
                    confirmation TEXT NOT NULL DEFAULT '',
                    source_domain TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_applications_recent_exact
                    ON applications(company_key, job_title_key, state, applied_at);
                CREATE INDEX IF NOT EXISTS idx_applications_unresolved_exact
                    ON applications(company_key, job_title_key, state, updated_at);

                CREATE TABLE IF NOT EXISTS submission_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    application_id INTEGER,
                    event_at TEXT NOT NULL,
                    company TEXT NOT NULL,
                    job_title TEXT NOT NULL,
                    action TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    details TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(application_id) REFERENCES applications(id)
                );
                CREATE INDEX IF NOT EXISTS idx_submission_audit_application
                    ON submission_audit(application_id, event_at);
                """
            )

    @staticmethod
    def _entry(row: sqlite3.Row) -> ApplicationHistoryEntry:
        return ApplicationHistoryEntry(
            id=row["id"],
            company=row["company"],
            job_title=row["job_title"],
            state=LedgerState(row["state"]),
            applied_at=row["applied_at"] or "",
            updated_at=row["updated_at"],
            confirmation=row["confirmation"],
            source_domain=row["source_domain"],
            source_url=row["source_url"],
        )
