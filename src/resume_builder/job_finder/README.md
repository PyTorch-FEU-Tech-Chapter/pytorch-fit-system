# `job_finder/` — Reusable Job Listing Rules

This package is separate from the resume scraper and from the job-application
form filler. It learns reusable, machine-readable rules for job listing pages:

1. observe a rendered job-search/listing page,
2. build a compact DOM inventory,
3. ask an AI to emit strict JSON rules for this layout,
4. cache those rules by domain + layout fingerprint,
5. reuse the cached rules deterministically on later pages with the same layout.

The goal is token amortization: one model call per stable domain/layout, then
zero-token extraction for repeated runs.

This package only handles job discovery/listing extraction. Application form
analysis and form filling belong in `job_application/`.
