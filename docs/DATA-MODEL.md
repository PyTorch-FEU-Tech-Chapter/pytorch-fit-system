# PyTorch FIT System — Org-Ops Data Model

> Layer: Org-Operations (Layer 1 foundation + Layer 5 analytics extension).
> Stack: Supabase Postgres (serverless). RLS mandatory on every user-owned table.
> Migrations: `supabase/migrations/0001_org_activities.sql`,
>   `0002_points_leaderboard.sql`, `0003_referrals_growth.sql`.

---

## ERD (Mermaid)

```mermaid
erDiagram
    AUTH_USERS {
        uuid id PK
    }

    MEMBER_PROFILES {
        uuid id PK
        text role
        boolean is_officer
        department officer_department
        text display_name
        text nickname
        text avatar_url
        text bio
    }

    ACTIVITIES {
        uuid id PK
        activity_category category
        activity_scope scope
        text title
        pipeline_status pipeline_status
        uuid created_by FK
    }

    INTAKE_SUBMISSIONS {
        uuid id PK
        uuid activity_id FK
        uuid submitted_by FK
        text url
        text details
    }

    ACTIVITY_CONTEXTS {
        uuid id PK
        uuid activity_id FK
        activity_category category
        activity_scope scope
        text title
        text summary
        text source_url
        jsonb facts
    }

    ROUTING_RULES {
        uuid id PK
        activity_category category
        activity_scope scope
        department[] required_departments
    }

    DEPARTMENT_BRIEFS {
        uuid id PK
        uuid activity_id FK
        department department
        text recipient
        text required_content
        text draft
    }

    APPROVALS {
        uuid id PK
        uuid activity_id FK
        department department
        uuid approver_user_id FK
        approval_decision decision
        text note
    }

    DISPATCH_RECORDS {
        uuid id PK
        uuid activity_id FK
        dispatch_channel channel
        dispatch_status status
        text drafted_content
        uuid human_approved_by FK
    }

    POINT_EVENTS {
        uuid id PK
        uuid member_id FK
        point_source source
        numeric points
        numeric weight
        numeric weighted_points
        text description
        uuid reference_id
        timestamptz earned_at
    }

    CLUSTERS {
        uuid id PK
        text name
        text slug
        text description
    }

    CLUSTER_ITEMS {
        uuid id PK
        uuid cluster_id FK
        text title
        text item_type
        uuid activity_id FK
    }

    MEMBER_CLUSTER_STANDINGS {
        uuid id PK
        uuid member_id FK
        uuid cluster_id FK
        numeric total_points
        integer rank
    }

    REFERRALS {
        uuid id PK
        uuid referrer_id FK
        uuid referee_id FK
        numeric points_awarded
        timestamptz awarded_at
    }

    ACTIVITY_ASSESSMENTS {
        uuid id PK
        uuid member_id FK
        uuid activity_id FK
        numeric pretest_score
        numeric posttest_score
        numeric gain
    }

    GROWTH_RECOMMENDATIONS {
        uuid id PK
        uuid member_id FK
        recommendation_type recommendation_type
        text title
        text reason
        uuid activity_id FK
        uuid cluster_id FK
        boolean is_dismissed
    }

    AUTH_USERS         ||--o| MEMBER_PROFILES          : "has profile"
    MEMBER_PROFILES    ||--o{ ACTIVITIES                : "creates"
    MEMBER_PROFILES    ||--o{ INTAKE_SUBMISSIONS        : "submits"
    MEMBER_PROFILES    ||--o{ POINT_EVENTS              : "earns"
    MEMBER_PROFILES    ||--o{ MEMBER_CLUSTER_STANDINGS  : "ranked in"
    MEMBER_PROFILES    ||--o{ REFERRALS                 : "refers"
    MEMBER_PROFILES    ||--o{ REFERRALS                 : "referred by"
    MEMBER_PROFILES    ||--o{ ACTIVITY_ASSESSMENTS      : "assessed in"
    MEMBER_PROFILES    ||--o{ GROWTH_RECOMMENDATIONS    : "recommended to"

    ACTIVITIES         ||--o{ INTAKE_SUBMISSIONS        : "triggered by"
    ACTIVITIES         ||--o| ACTIVITY_CONTEXTS         : "ingested as"
    ACTIVITIES         ||--o{ DEPARTMENT_BRIEFS         : "briefed for"
    ACTIVITIES         ||--o{ APPROVALS                 : "reviewed by"
    ACTIVITIES         ||--o{ DISPATCH_RECORDS          : "dispatched via"
    ACTIVITIES         ||--o{ CLUSTER_ITEMS             : "linked in"
    ACTIVITIES         ||--o{ ACTIVITY_ASSESSMENTS      : "assessed via"
    ACTIVITIES         ||--o{ GROWTH_RECOMMENDATIONS    : "recommended as"

    CLUSTERS           ||--o{ CLUSTER_ITEMS             : "contains"
    CLUSTERS           ||--o{ MEMBER_CLUSTER_STANDINGS  : "standings in"
    CLUSTERS           ||--o{ GROWTH_RECOMMENDATIONS    : "suggested in"
```

---

## Table Catalog

### Migration 0001 — Activity Pipeline + Auth Foundation

#### `member_profiles`
Auth foundation (SPEC §5 Layer 1). Links `auth.users` to the org-ops layer.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | `REFERENCES auth.users(id)` |
| `role` | text | `member \| premium \| research \| moderator \| admin \| super_admin` |
| `is_officer` | boolean | Whether user holds an officer position |
| `officer_department` | department | Required when `is_officer = true` |
| `display_name` | text | Added in 0002 |
| `nickname` | text UNIQUE | Public handle (e.g. `Angela #7A82F`); never email. Added in 0002 |
| `avatar_url` | text | Added in 0002 |
| `bio` | text (≤500) | Added in 0002 |

#### `activities`
Master record for each org activity item. All pipeline child tables FK here.
Pipeline state is tracked via `pipeline_status` enum.

#### `intake_submissions`
Any authenticated member may submit a URL or free-text to start a pipeline.
Constraint: at least one of `url` or `details` must be non-null.

#### `activity_contexts`
Structured JSON output from the LinkIngestor / RAG step.
Maps 1:1 to `ActivityContext` in `platform/org-ops/types.ts`.
`facts` column is JSONB; has a GIN index for key/value queries.
Populated by service_role (AI pipeline) — no client INSERT policy.

#### `routing_rules`
Admin-editable configuration table.
One row per `(category, scope)` pair defines which departments must approve.
No code deployment required to change routing.

#### `department_briefs`
Per-department compacted context + AI-generated draft.
One brief per `(activity_id, department)`.
Maps to `DepartmentBrief` in `platform/org-ops/types.ts`.
Officers edit the draft in-place before approval.

#### `approvals`
One verdict row per `(activity_id, department)`.
Unanimous approval across all required departments (from `routing_rules`) is needed before the pipeline advances.
Maps to `ApprovalVerdict` in `platform/org-ops/types.ts`.
Effectively immutable: re-approvals require DELETE + INSERT at service_role level.

#### `dispatch_records`
One row per `(activity_id, channel)`.
Database-level HITL invariants: `status = 'approved'` requires `human_approved_by`; `status = 'sent'` requires both approver and timestamp.

---

### Migration 0002 — Points Ledger, Leaderboard & Cluster Graph

#### `point_events`
Append-only, tamper-evident audit ledger.
`weighted_points` is a stored generated column (`points * weight`).
No client UPDATE or DELETE policies — corrections via service_role only.

Default weights by source:

| Source | Recommended weight |
|---|---|
| `achievement` | 3.0 |
| `grade` | 2.5 |
| `project` | 2.0 |
| `competition` | 2.0 |
| `activity` | 1.0 |
| `referral` | 0.5 |

Weights are stored per-row, so individual events can differ from defaults.

#### `leaderboard` (materialized view)
Cut-throat merit ranking. Only public-safe columns (no email, no PII).

| Column | Exposed |
|---|---|
| `member_id` | UUID only — not PII |
| `nickname` | Public handle |
| `avatar_url` | Public avatar |
| `total_points` | Aggregated weighted score |
| `source_diversity` | Count of distinct point sources |
| `first_earned_at` | Tiebreaker 1 (earlier = higher) |
| `last_earned_at` | Tiebreaker 2 (more recent = higher) |
| `rank` | `RANK()` — gaps on ties (e.g. 1, 1, 3) |

Tiebreaker order: `total_points DESC` → `first_earned_at ASC` → `last_earned_at DESC` → `nickname ASC`.

Refresh with `REFRESH MATERIALIZED VIEW CONCURRENTLY leaderboard` (unique index on `member_id` exists to support this).

#### `clusters`
Thematic groupings (academics, tutorial, competitive-programming, research, etc.).

#### `cluster_items`
Concrete projects, competitions, or events within a cluster.
May optionally reference an `activities` record (FK nullable).

#### `member_cluster_standings`
Per-member per-cluster point totals and cached rank.
Updated by Edge Function hooks on `point_events` insert.

---

### Migration 0003 — Referrals & Growth Track

#### `referrals`
Audit record for member-to-member referrals.
`CHECK (referrer_id != referee_id)` — hard database constraint prevents self-referral.
`UNIQUE (referrer_id, referee_id)` — one credit per pair.
Actual point events are written to `point_events` via service_role; this table is the referral audit log only.

#### `activity_assessments`
Pretest and posttest scores per member per activity.
`gain` is a stored generated column (`posttest - pretest`). Negative gain is valid and meaningful.

**DIAGNOSTIC ONLY.** Gain does not generate points. Does not affect leaderboard rank.

#### `growth_recommendations`
AI/pipeline-generated recommendations for members with low points or low learning gain.

**DIAGNOSTIC ONLY — NOT a second leaderboard.** This table:
- Does not redistribute points
- Does not grant equity adjustments
- Does not change any member's leaderboard rank
- Is private to the member (owner-only RLS)

#### `member_growth_summary` (view, non-materialized)
Per-member per-category aggregate of gain statistics.
Used by the recommendation engine and admin dashboards.
Not exposed to end users.

---

## RLS Policy Summary

| Table | anon | member (own) | officer | admin |
|---|---|---|---|---|
| `member_profiles` | SELECT (nickname ≠ null) | SELECT + UPDATE | — | SELECT + UPDATE all |
| `activities` | — | SELECT own, INSERT | SELECT all, UPDATE | SELECT + UPDATE + DELETE |
| `intake_submissions` | — | SELECT own, INSERT | SELECT all | SELECT all |
| `activity_contexts` | — | — | SELECT all | SELECT all |
| `routing_rules` | — | SELECT | SELECT | SELECT + INSERT + UPDATE + DELETE |
| `department_briefs` | — | — | SELECT own dept, UPDATE own dept | SELECT + INSERT + UPDATE |
| `approvals` | — | — | SELECT own dept, INSERT own dept | SELECT all |
| `dispatch_records` | — | — | SELECT all, UPDATE (HITL gate) | SELECT + INSERT + UPDATE |
| `point_events` | — | SELECT own | — | SELECT all |
| `leaderboard` (matview) | SELECT | SELECT | SELECT | SELECT |
| `clusters` | SELECT | SELECT | SELECT | SELECT + INSERT + UPDATE + DELETE |
| `cluster_items` | SELECT | SELECT | SELECT | SELECT + INSERT + UPDATE |
| `member_cluster_standings` | SELECT | SELECT | SELECT | SELECT |
| `referrals` | — | SELECT own (referrer or referee) | — | SELECT + INSERT |
| `activity_assessments` | — | SELECT + INSERT + UPDATE own | — | SELECT all |
| `growth_recommendations` | — | SELECT own, UPDATE (dismiss only) | — | SELECT + INSERT |

### Key RLS Decisions

1. **`is_admin()` / `is_officer()` are SECURITY DEFINER** owned by `postgres`. They bypass RLS on `member_profiles` when called from within RLS policies on other tables. This prevents infinite recursion without needing a separate roles table.

2. **`(SELECT auth.uid())` pattern** is used in every policy that checks the calling user's identity. This ensures the expression is evaluated once per statement, not once per row.

3. **`point_events` has no client INSERT/UPDATE/DELETE policy.** All mutations go through service_role (Edge Functions). This makes the ledger append-only and tamper-evident from the client's perspective. `service_role` bypasses RLS in Supabase.

4. **`leaderboard` materialized view has no RLS** (Postgres does not support RLS on matviews). Safety is structural: the view selects only `member_id` (UUID), `nickname`, `avatar_url`, and aggregate metrics. No email, phone, or raw data appears in the view schema.

5. **`growth_recommendations` is private by default.** Only the member (owner) and admins can read it. This is intentional: the growth track is diagnostic, not a public-facing feature.

6. **Column-level privilege escalation** (e.g. a member promoting their own `role` to `admin`) cannot be fully prevented by RLS alone in Postgres — RLS operates on whole rows. The application layer (Edge Functions) must enforce that only admins may write `role`, `is_officer`, and `officer_department`. This is documented and is an accepted architecture constraint for the MVP serverless stack.

7. **`department_briefs` officer access** is scoped to `officer_dept()` which returns the calling user's assigned department. A secretary cannot read the treasurer's brief.

---

## TypeScript ↔ SQL Enum Mapping

Some TypeScript enum values in `platform/org-ops/types.ts` use kebab-case (JavaScript convention). SQL uses snake_case.

| TypeScript value | SQL value |
|---|---|
| `"competitive-programming"` | `'competitive_programming'` |
| `"external-relations"` | `'external_relations'` |

The application layer must translate between these when reading from or writing to the database.

---

## Index Strategy

| Table | Index | Rationale |
|---|---|---|
| `member_profiles` | `(id, role)` | Fast role-check in `is_admin()` / `is_officer()` |
| `member_profiles` | `(officer_department) WHERE is_officer` | Partial; fast officer-dept RLS lookup |
| `activities` | `(category, scope)` | Routing rule lookups |
| `activities` | `(pipeline_status)` | Status-filtered dashboard queries |
| `activity_contexts` | GIN on `facts` | JSONB key/value searches on AI-extracted data |
| `point_events` | `(member_id, earned_at DESC)` | Leaderboard aggregation; timeline queries |
| `point_events` | `(member_id, source)` | Source-filtered point breakdowns |
| `point_events` | `(reference_table, reference_id)` | Cross-domain attribution queries |
| `leaderboard` | UNIQUE on `member_id` | Required for CONCURRENTLY refresh |
| `leaderboard` | `(rank)` | "What rank am I?" single-row lookup |
| `activity_assessments` | `(gain ASC) WHERE gain IS NOT NULL` | Recommendation engine low-gain scan |
| `growth_recommendations` | `(member_id, type) WHERE NOT dismissed` | Active recommendation surface |

---

## Open Questions

1. **Leaderboard refresh scheduling.** `REFRESH MATERIALIZED VIEW CONCURRENTLY leaderboard` needs to be triggered after `point_events` inserts. Options: (a) pg_cron extension job (scheduled), (b) Edge Function hook, (c) trigger-based on `point_events`. The right choice depends on how frequently points are awarded. pg_cron is not available on all Supabase plans — confirm before using.

2. **Officer multi-department support.** The current schema supports one `officer_department` per `member_profiles` row. If an officer serves multiple departments (e.g. an executive who also acts as secretary), the schema needs a `member_officer_departments` junction table. Not implemented yet — confirm org structure.

3. **Activity revision semantics.** Approvals have a `UNIQUE (activity_id, department)` constraint. If a department rejects and the submitter revises, the current design requires the pipeline to either (a) delete the approval row and re-insert, or (b) create a new `activities` revision record. The revision strategy (versioned vs. mutable) is not yet decided.

4. **Referral eligibility window.** Currently there is no time constraint on when a referral must be claimed. Consider adding a `expires_at` column or a CHECK constraint to limit the claiming window.

5. **`point_events` weight governance.** Weights are stored per-row and allow per-event overrides, but there is no `weight_config` table governing the default weights per source. If weights change org-wide, all historical events retain their original weights. Decide whether retrospective weight changes are desired (they'd require a ledger correction event, not an UPDATE).

6. **Growth track visibility.** `growth_recommendations` is currently private (member + admin only). Consider whether moderators should also have read access for coaching purposes, or whether a separate "coaching view" is needed.

7. **`dispatch_records` revision history.** Currently there is one dispatch record per `(activity, channel)`. If a draft is rejected and rewritten multiple times, history is lost. A `dispatch_revisions` child table would preserve the full draft history.
