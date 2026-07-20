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

## Live CDP development test

Use `tools/job_finder/cdp_tag.py` with a normal Chrome instance already opened with local CDP.
The human signs in and completes any verification. The harness then runs in two explicit phases:

```bash
python tools/job_finder/cdp_tag.py inventory --url "https://example.com/jobs?q=python"
# Development only: current-session AI writes strict rules.json from inventory.txt.
python tools/job_finder/cdp_tag.py apply --rules out/live-job-model/rules.json
```

`inventory` runs the access gate first and stops on sign-out, CAPTCHA, Cloudflare, 403/429, or other
verification. It saves only a sanitized DOM, compact inventory, access decision, and screenshot
under `/out/`; it never exports cookies or credentials. `apply` validates the domain + layout
fingerprint, executes the same rules used by the deterministic extractor, and writes
`annotated.html`, `annotated.png`, and strict JSON results.

For production-style model execution, use `api-plan`. It calls only the configured provider-neutral
HTTP model API; that endpoint may be remote or locally hosted:

```bash
python tools/job_finder/cdp_tag.py api-plan --preferences "remote Python roles"
```

Pass work arrangement separately so it remains a strict constraint rather than free-form text:

```bash
python tools/job_finder/cdp_tag.py api-plan --work-mode hybrid
```

No command implements access-control bypass, fingerprint spoofing, proxy/identity rotation, or
CAPTCHA solving.
