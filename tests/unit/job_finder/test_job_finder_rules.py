from __future__ import annotations

import json

from resume_builder.job_finder import (
    JobListingAction,
    JobListingExtraction,
    JobListingLayoutStore,
    JobListingPlanner,
    JobListingRule,
    LearnedJobListingLayout,
    apply_listing_rules,
    build_listing_dom_inventory,
    fingerprint,
)

_LISTINGS = """
<html><body>
  <header class="topbar"><a href="/login">Login</a></header>
  <form class="job-search">
    <label for="q">Keyword</label><input id="q" name="q" type="search" placeholder="Search jobs">
    <label for="loc">Location</label><input id="loc" name="location" placeholder="Location">
    <select name="remote"><option>Any</option><option>Remote</option><option>On-site</option></select>
    <button class="search-button" type="submit">Search</button>
  </form>
  <main class="jobs">
    <article class="job-card">
      <a class="job-title" href="/jobs/backend-engineer">Backend Engineer</a>
      <span class="company">Acme Labs</span>
      <span class="location">Remote - Philippines</span>
      <span class="type">Full-time</span>
      <p class="summary">Build APIs and internal tools.</p>
    </article>
    <article class="job-card">
      <a class="job-title" href="/jobs/ml-engineer">ML Engineer</a>
      <span class="company">Acme Labs</span>
      <span class="location">Makati</span>
      <span class="type">Hybrid</span>
      <p class="summary">Train and evaluate models.</p>
    </article>
    <nav class="pagination"><a class="next" href="/jobs?page=2">Next</a></nav>
  </main>
  <footer>Privacy and boilerplate</footer>
</body></html>
"""

_LISTINGS_PAGE_2 = _LISTINGS.replace("Backend Engineer", "Platform Engineer").replace(
    "/jobs/backend-engineer", "/jobs/platform-engineer"
)


def _good_layout(layout_fingerprint: str = "x") -> LearnedJobListingLayout:
    return LearnedJobListingLayout(
        domain="careers.example.com",
        sample_url="https://careers.example.com/jobs",
        layout_fingerprint=layout_fingerprint,
        confidence=0.92,
        rules=[
            JobListingRule(selector="header.topbar, footer", role=JobListingAction.IGNORE),
            JobListingRule(
                selector="article.job-card",
                role=JobListingAction.JOB_CARD,
                extract=JobListingExtraction(
                    title="a.job-title",
                    company="span.company",
                    location="span.location",
                    remote_signal="span.location",
                    employment_type="span.type",
                    detail_url="a.job-title@href",
                    description="p.summary",
                ),
            ),
            JobListingRule(selector="a.next", role=JobListingAction.NEXT_PAGE),
            JobListingRule(selector="select[name=remote]", role=JobListingAction.FILTER_CONTROL),
            JobListingRule(selector="input[name=q]", role=JobListingAction.SEARCH_INPUT),
        ],
    )


class _FakeLLM:
    def __init__(self) -> None:
        self.calls = 0
        self.prompts: list[str] = []

    def structured(self, prompt, schema, system=None, max_tokens=2048):
        self.calls += 1
        self.prompts.append(prompt)
        return _good_layout()


def test_listing_dom_inventory_is_separate_and_exposes_job_controls():
    inventory = build_listing_dom_inventory(_LISTINGS, "https://careers.example.com/jobs")

    assert "selector='article.job-card'" in inventory
    assert "'Backend Engineer'->https://careers.example.com/jobs/backend-engineer" in inventory
    assert "placeholder='Search jobs'" in inventory
    assert "options=['Any', 'Remote', 'On-site']" in inventory


def test_listing_rules_extract_jobs_and_next_page_deterministically():
    layout = _good_layout()
    listings, next_urls, filters, searches = apply_listing_rules(
        _LISTINGS,
        "https://careers.example.com/jobs",
        "https://careers.example.com",
        layout.rules,
    )

    assert [listing.title for listing in listings] == ["Backend Engineer", "ML Engineer"]
    assert listings[0].detail_url == "https://careers.example.com/jobs/backend-engineer"
    assert listings[0].remote_signal == "Remote - Philippines"
    assert next_urls == ["https://careers.example.com/jobs?page=2"]
    assert filters == ["Any Remote On-site"]
    assert searches == ["input[name=q]"]


def test_planner_caches_same_layout_rules_without_second_ai_call():
    llm = _FakeLLM()
    store = JobListingLayoutStore(output_dir=None)
    planner = JobListingPlanner(llm, store=store)

    first = planner.plan_page("https://careers.example.com/jobs", _LISTINGS)
    second = planner.plan_page("https://careers.example.com/jobs?page=2", _LISTINGS_PAGE_2)

    assert llm.calls == 1
    assert first.extraction_method == "ai_rules"
    assert second.extraction_method == "ai_rules_cache"
    assert second.listings[0].title == "Platform Engineer"


def test_job_listing_fingerprint_reuses_same_template_not_text():
    assert fingerprint(_LISTINGS) == fingerprint(_LISTINGS_PAGE_2)
    different = _LISTINGS.replace('article class="job-card"', 'article class="opening-card"')
    assert fingerprint(_LISTINGS) != fingerprint(different)


def test_store_persists_machine_readable_layout(tmp_path):
    layout = _good_layout(layout_fingerprint="abc")
    store = JobListingLayoutStore(output_dir=tmp_path)

    store.put(layout)

    payload = json.loads(next(tmp_path.glob("careers.example.com-abc.json")).read_text())
    assert payload["rules"][1]["role"] == "job_card"
    assert payload["rules"][1]["extract"]["detail_url"] == "a.job-title@href"
    assert JobListingLayoutStore(output_dir=tmp_path).get("abc").rules[1].role == (
        JobListingAction.JOB_CARD
    )
