# PyTorch FIT System

**Purpose:** AI career-intelligence platform for collecting, normalizing, and deriving outputs from verified career evidence.

**Canonical model:** Normalized Career Database (NCD) = source of truth. Résumés, profiles, portfolios, analytics, and recommendations are derived artifacts.

## Quick start

Prerequisites: Node.js `>=22.13.0 <25`, Docker Desktop, npm.

```powershell
npm run setup  # first run or dependency refresh
npm run dev    # portal + local Supabase + synthetic sessions + Prefect
```

Endpoints:

- Member portal: `http://members.localhost:3000`
- Officer portal: `http://officers.localhost:3000`
- Prefect: `http://127.0.0.1:4200`

Runtime paths:

- `var/`: durable SQLite state, browser sessions, environments, caches, bounded logs
- `out/`: human-reviewable screenshots, reports, exports
- Overrides: `PYTORCH_FIT_VAR_ROOT`, `PYTORCH_FIT_ARTIFACT_ROOT`

Canonical references:

- [Product specification](docs/SPECIFICATION.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Task backlog](docs/TASKS.md)
- [Portal](apps/portal/README.md)
- [Process Lab](development/process-lab/README.md)
- [Agent operating policy](AGENTS.md)

## Architecture

```text
Next.js/Vercel
  -> Supabase Auth
  -> PostgreSQL + Row Level Security (RLS)
  -> Normalized Career Database
  -> AI processing
  -> derived résumés, profiles, portfolios, analytics, recommendations
```

MVP: serverless Next.js + Supabase. Future server boundary: verification, AI queues, scheduled jobs, payments.

| Layer | Data | Access |
|---|---|---|
| Auth | users, profiles, roles | policy-controlled |
| Raw | posts, certificates, projects, history | private via RLS |
| Normalized | experiences, skills, projects, industries | private via RLS |
| Generated | résumés, summaries, recommendations | derived/disposable |
| Analytics | metrics, trends, leaderboards | aggregated/anonymous |

Privacy classes:

- **Private:** owner only.
- **Public profile:** curated fields; excludes email, phone, raw posts, certificates, full résumés.
- **Aggregated analytics:** anonymous.
- Enforcement boundary: database [Row Level Security (RLS)](https://supabase.com/docs/guides/database/postgres/row-level-security), not UI-only checks.

## AI evidence contract

AI interpretation MUST return strict JSON:

```json
{
  "results": {
    "quantitative": ["metric + exact value + context + plain-language meaning"],
    "qualitative": ["problem solved + beneficiary/system effect + demonstrated capability"]
  },
  "conclusion": "evidence-grounded value + strongest demonstrated capability"
}
```

Constraints:

- Never invent, estimate, alter, or extrapolate metrics.
- Preserve an already-effective evidence sentence; add missing context as a separate short item.
- Keep normalized `skill_subtags` atomic for matching and deduplication.
- Resume JSON uses `skill_groups[]`: platform/language `name` + evidenced framework/library `items[]`.
- Renderers compute skill-grid columns from content and usable width; no fixed column count.
- Chromium bounds analysis and actual PDF page count determine one-page fit.

## Web automation

Systems remain separate: evidence scraping, job discovery, application form filling.

Pipeline:

1. Access gate: stop on CAPTCHA, Cloudflare, `403`, `429`, login, or verification.
2. Bounded rendered-DOM inventory.
3. Provider-neutral HTTP model API produces strict JSON rules once per layout.
4. Cache key: exact `subdomain + layout fingerprint`.
5. Deterministic code replay; no repeated model call for a confident cached layout.
6. Human gate for low confidence, sensitive judgment, uploads, Continue, Review, and final Submit unless an explicit domain-scoped policy authorizes the action.

Permission model: domain-scoped `ApplicationPermissionPolicy`; conservative defaults. `autonomous_submit` applies only to its configured domain and still requires validation plus observable confirmation.

Safety invariants:

- No CAPTCHA/anti-bot bypass, stealth plugin, fingerprint spoofing, solver, proxy rotation, or identity rotation.
- Preserve explicit `work_mode`: `remote | hybrid | onsite | any`; never infer or broaden it.
- Treat contact data and job geography as independent inputs.
- Inventory complete application questionnaire containers and nested fields.
- Recommend only existing role-specific résumés; require human review before upload or progression.
- Fail closed on missing required data, unknown questionnaires, access/layout drift, Review, and final Submit without the matching scoped approval.
- A confirmed exact `company + job title` blocks duplicate submission for 30 days.
- Confirmation providers: observable browser proof, explicit manual confirmation, or an authorized optional email adapter. Never store mailbox bodies, credentials, cookies, or unrelated messages.
- Persistent confirmation ledger: `var/state/job-applications/submissions.sqlite3`.

Adapters:

- Indeed and JobStreet: deterministic adapter only when required live selectors/capabilities match.
- Indeed Smart Apply: preserve matching contact fields; derive names from the selected résumé; use only runtime-verified phone data; re-observe after each module transition.
- Layout drift or unknown domain: bounded inventory -> AI plan -> cached deterministic replay.
- Production execution: headless.
- Development overlays: `/out/`; exact executable rules only.
- Application executor: text, selections, checkboxes, approved safe clicks, and approved résumé upload; required-field validation; explicit failure on unsafe or unsupported actions.
- Mock-ATS Chromium integration test covers draft-ready and confirmed-submission outcomes.
- CDP harnesses: `tools/job_finder/cdp_tag.py`, `tools/job_finder/application_cdp_tag.py`.
- Indeed history reconciliation: `tools/job_finder/sync_indeed_applied.py`.
- Cross-site application checks: `legacy/python/resume_builder/job_application/shared/`.

Full invariants: [Agent operating policy](AGENTS.md).

## Repository state

The active platform is the fresh Next.js + Supabase implementation. The Python résumé engine under [`legacy/python/resume_builder/`](legacy/python/resume_builder/README.md) is a proven, non-production parity reference during migration.

GitHub evidence collection is runtime-user-driven and website-first. `gh` is an optional development backend; no account identifier is hardcoded.

## Verification

```powershell
npm run typecheck
npm test
npm run build
```

Scraper cost benchmark: [`tests/benchmarks/scraper_token_cost/`](tests/benchmarks/scraper_token_cost/README.md).

Recorded benchmark facts:

- Five live `quotes.toscrape.com` pages; `tiktoken cl100k_base` tokenization.
- Strict DOM fingerprint: two layouts; pages 3-5 cache hits.
- Accumulating agent context: modeled `O(N²)`; isolated calls and pipeline: modeled `O(N)`.
- Pipeline token slope: approximately `15x` smaller than isolated calls plus bounded `O(L)` layout-learning cost.
- Modeled crossover: approximately six pages.
- Scope: measured page/fingerprint data plus an explicit complexity model; not provider billing.

## Contribution contract

1. Read the [product specification](docs/SPECIFICATION.md).
2. Select work from the [task backlog](docs/TASKS.md).
3. Require human review for every AI-generated artifact before shipment.

License: see repository license metadata.
