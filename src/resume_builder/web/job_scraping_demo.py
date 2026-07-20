"""Current-session fixture for the first job-scraping model-output visualization."""

from resume_builder.job_finder.models import (
    JobListing,
    JobListingAction,
    JobListingExtraction,
    JobListingRule,
    JobListingRun,
    JobScrapeVisualizationArtifact,
    LearnedJobListingLayout,
)


def current_session_artifact() -> JobScrapeVisualizationArtifact:
    rendered_dom = """
    <div class="sample-site">
      <header class="topbar"><strong>Sample Careers PH</strong><a href="/login">Login</a></header>
      <section class="search-panel">
        <input name="keywords" placeholder="Job title or skill">
        <input name="where" placeholder="Location">
        <button class="search-submit">Search</button>
      </section>
      <main>
        <section class="job-results">
          <article class="job-card"><h2><a class="job-title" href="/jobs/backend-engineer">Backend Engineer</a></h2><span class="company">MangoByte PH</span><span class="location">Makati City</span><span class="workplace">Hybrid</span><span class="employment-type">Full time</span><p class="summary">Own Python services, integrations, and production dashboards.</p></article>
          <article class="job-card"><h2><a class="job-title" href="/jobs/data-engineer">Data Engineer</a></h2><span class="company">MangoByte PH</span><span class="location">Philippines</span><span class="workplace">Remote</span><span class="employment-type">Contract</span><p class="summary">Build ETL jobs and analytics warehouse models.</p></article>
          <a class="next-page" href="/jobs?page=2">Next page</a>
        </section>
        <aside class="recommendations"><a href="/salary-guide">Salary guide</a></aside>
      </main>
      <footer>Terms, privacy, and repeated site links.</footer>
    </div>
    """
    layout = LearnedJobListingLayout(
        domain="careers.example.com",
        sample_url="https://careers.example.com/jobs",
        layout_fingerprint="current-session-demo-v1",
        rules=[
            JobListingRule(
                selector="header, footer, aside.recommendations",
                role=JobListingAction.IGNORE,
                reason="Site chrome and unrelated recommendations.",
            ),
            JobListingRule(
                selector="input[name=keywords], input[name=where]",
                role=JobListingAction.SEARCH_INPUT,
                reason="User-controlled search fields; deterministic fill action.",
            ),
            JobListingRule(
                selector="button.search-submit",
                role=JobListingAction.SUBMIT_SEARCH,
                reason="Safe search action after fields are filled.",
            ),
            JobListingRule(
                selector="article.job-card",
                role=JobListingAction.JOB_CARD,
                reason="Repeated job result container with visible summary fields.",
                extract=JobListingExtraction(
                    title="a.job-title",
                    company=".company",
                    location=".location",
                    remote_signal=".workplace",
                    employment_type=".employment-type",
                    detail_url="a.job-title@href",
                    description=".summary",
                ),
            ),
            JobListingRule(
                selector="a.next-page",
                role=JobListingAction.NEXT_PAGE,
                reason="Safe read-only pagination to more job results.",
            ),
        ],
        include_url_patterns=["/jobs", "/jobs/*"],
        exclude_url_patterns=["/login", "/apply/*"],
        confidence=0.94,
        warnings=["Demo HTML only; verify selectors again on a real rendered site."],
    )
    run = JobListingRun(
        page_url=layout.sample_url,
        layout_fingerprint=layout.layout_fingerprint,
        extraction_method="ai_rules",
        listings=[
            JobListing(
                title="Backend Engineer",
                company="MangoByte PH",
                location="Makati City",
                remote_signal="Hybrid",
                employment_type="Full time",
                description="Own Python services, integrations, and production dashboards.",
                detail_url="https://careers.example.com/jobs/backend-engineer",
                source_url=layout.sample_url,
                source_selector="article.job-card",
            ),
            JobListing(
                title="Data Engineer",
                company="MangoByte PH",
                location="Philippines",
                remote_signal="Remote",
                employment_type="Contract",
                description="Build ETL jobs and analytics warehouse models.",
                detail_url="https://careers.example.com/jobs/data-engineer",
                source_url=layout.sample_url,
                source_selector="article.job-card",
            ),
        ],
        next_page_urls=["https://careers.example.com/jobs?page=2"],
        signed_in_status="signed_out",
        learned_layout=layout,
    )
    return JobScrapeVisualizationArtifact(
        source_label="Current Codex session — initial model test fixture",
        model_output=layout,
        scraping_output=run,
        rendered_dom=rendered_dom,
    )
