from __future__ import annotations

from urllib.parse import urlsplit

from resume_builder.llm.base import LLMProvider

from .dom_inventory import build_listing_dom_inventory, fingerprint
from .models import JobListingRun, LearnedJobListingLayout
from .rule_executor import apply_listing_rules
from .store import JobListingLayoutStore

_SYSTEM = """You are the structure-learning component for a job finder.
You observe a rendered DOM inventory for a job listing/search page and emit reusable JSON rules.
Do not extract jobs yourself. Build selectors and extraction instructions that a deterministic
parser can apply every future run for the same domain/layout.

Allowed roles:
- ignore: site chrome/noise/auth/legal/cookie widgets; remove before extraction.
- job_card: one repeated container per job. Must include extract mapping.
- next_page: pagination link/button anchor to the next listing page.
- filter_control: visible filters for location, remote, role, level, employment type, salary.
- search_input: keyword/location search inputs.
- submit_search: search submit control.
- job_description: detail page description region, only when current page is a job detail page.
- apply_link: link/button leading from a job detail to an application page.

Extraction mapping values are selectors relative to each job_card. Use selector@attr for
attributes such as a@href. Prefer stable selectors from the inventory. Do not invent selectors.
Return one strict JSON object matching the schema."""


class JobListingPlanner:
    """Learn and replay reusable job-listing extraction rules."""

    def __init__(
        self,
        llm: LLMProvider,
        store: JobListingLayoutStore | None = None,
        *,
        min_listings: int = 1,
        max_revision_attempts: int = 1,
    ) -> None:
        self.llm = llm
        self.store = store or JobListingLayoutStore()
        self.min_listings = min_listings
        self.max_revision_attempts = max_revision_attempts

    def plan_page(
        self,
        page_url: str,
        html: str,
        *,
        user_preferences: str = "",
        force_relearn: bool = False,
    ) -> JobListingRun:
        layout_fingerprint = fingerprint(html)
        cached = None if force_relearn else self.store.get(layout_fingerprint)
        if cached is not None:
            run = self._execute(page_url, html, cached, "ai_rules_cache")
            if not run.validation_errors:
                return run

        inventory = build_listing_dom_inventory(html, page_url)
        previous = cached
        errors: list[str] = []
        attempts = self.max_revision_attempts + 1
        for revision in range(attempts):
            layout = self._infer_layout(
                page_url=page_url,
                layout_fingerprint=layout_fingerprint,
                inventory=inventory,
                user_preferences=user_preferences,
                previous=previous,
                errors=errors,
                revision=revision,
            )
            run = self._execute(page_url, html, layout, "ai_rules")
            if not run.validation_errors:
                self.store.put(layout)
                run.learned_layout = layout
                return run
            previous = layout
            errors = run.validation_errors

        run.learned_layout = previous
        return run

    def _infer_layout(
        self,
        *,
        page_url: str,
        layout_fingerprint: str,
        inventory: str,
        user_preferences: str,
        previous: LearnedJobListingLayout | None,
        errors: list[str],
        revision: int,
    ) -> LearnedJobListingLayout:
        revision_block = ""
        if previous is not None or errors:
            previous_json = previous.model_dump_json(indent=2) if previous is not None else "none"
            revision_block = (
                "\n\nPREVIOUS RULES:\n"
                f"{previous_json}\n"
                "VALIDATION ERRORS:\n- "
                + "\n- ".join(errors)
                + "\nRevise the rule selectors/extraction mappings to fix these errors."
            )
        prompt = (
            f"PAGE URL: {page_url}\n"
            f"LAYOUT FINGERPRINT: {layout_fingerprint}\n"
            f"USER JOB PREFERENCES:\n{user_preferences or '(none supplied)'}\n\n"
            f"JOB LISTING DOM INVENTORY:\n{inventory}"
            f"{revision_block}"
        )
        layout = self.llm.structured(
            prompt,
            schema=LearnedJobListingLayout,
            system=_SYSTEM,
            max_tokens=4096,
        )
        layout.domain = urlsplit(page_url).netloc.lower()
        layout.sample_url = page_url
        layout.layout_fingerprint = layout_fingerprint
        layout.revision = revision
        return layout

    def _execute(
        self,
        page_url: str,
        html: str,
        layout: LearnedJobListingLayout,
        extraction_method: str,
    ) -> JobListingRun:
        listings, next_urls, filters, searches = apply_listing_rules(
            html,
            page_url,
            f"{urlsplit(page_url).scheme}://{urlsplit(page_url).netloc}",
            layout.rules,
        )
        errors: list[str] = []
        if len(listings) < self.min_listings:
            errors.append(
                f"expected at least {self.min_listings} job listing(s), got {len(listings)}"
            )
        if not any(rule.role.value == "job_card" for rule in layout.rules):
            errors.append("no job_card rule emitted")
        return JobListingRun(
            page_url=page_url,
            layout_fingerprint=layout.layout_fingerprint,
            extraction_method=extraction_method,
            listings=listings,
            next_page_urls=next_urls,
            filter_controls=filters,
            search_controls=searches,
            learned_layout=layout if extraction_method == "ai_rules" else None,
            validation_errors=errors,
        )
