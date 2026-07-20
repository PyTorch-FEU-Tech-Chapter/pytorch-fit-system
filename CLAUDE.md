# CLAUDE.md — PyTorch FIT System (project operating guide for AI agents)

> Read this before doing any work in this repo. It defines the **Kanban delegation workflow**, the
> **gh CLI prerequisite**, and the **human-in-the-loop (HITL) gate**. The master product spec is
> [`docs/SPECIFICATION.md`](docs/SPECIFICATION.md); org-ops detail is in
> [`docs/ORG-OPERATIONS.md`](docs/ORG-OPERATIONS.md).

## 0. Prerequisite — GitHub CLI (`gh`)

The Kanban board is a **GitHub Project** automated from this repo. Before touching the board,
**verify `gh` is installed and authenticated with the `project` scope**:

```bash
gh --version                 # is gh installed?
gh auth status               # logged in? check "Token scopes:" includes 'project'
```

**If `gh` is missing or unauthenticated, STOP and guide the user — do not silently skip the board:**

1. Install: https://cli.github.com (Windows: `winget install GitHub.cli`).
2. Authenticate: `gh auth login` (choose GitHub.com → HTTPS → browser).
3. Add the Projects scope (required for board automation):
   ```bash
   gh auth refresh -s project --hostname github.com
   ```
4. Re-run `gh auth status` and confirm `project` appears in the scopes.

Only once `gh auth status` shows the `project` scope should you run any board script.

## 1. The Kanban board

- **Project:** `PyTorch-FEU-Tech-Chapter` (org) Project **#1** (`scripts/board_tasks.json` → `owner` + `project_number`).
- **Source of truth:** `scripts/board_tasks.json`. Every task is one object; the scripts make the
  live board match the JSON. Edit the JSON, then run a script — never hand-edit the board for
  anything the JSON can express.
- **Every task becomes a real GitHub issue** (not a draft card) so it is assignable, searchable,
  and labelled.

### Fields (all automated)
| Field | Meaning |
|---|---|
| `Status` (built-in) + `Stage` | lifecycle column — set from the task's `stage` (both kept in sync) |
| `Role` | discipline: Architect/Database/AI/Frontend/Security/Analytics/QA/DevOps |
| `Group` | workstream (Foundation, Org Operations, …) |
| `Department` | module/team (Platform Core, Points & Leaderboard, …) |
| `HITL Gate` | **Yes** = a human must verify before Done; **No** = mechanical |
| `Priority` | P0–P3 |
| `Estimate` | days |
| `Start` / `Target` / `Worst Case` | optimistic = `Target`; `Worst Case` = +1 week slack |

GitHub Projects has **no native "slack" concept** — it is modelled with the `Worst Case` date field.
Labels: `delegation`, `hitl`, `model-training`, and one `dept:*` per department. Milestones group
by phase (`Foundation — Wk1`, `Org Operations — Wk1`, `Platform & Intelligence — Wk2`, …, `Shipped`).

### Scripts (`scripts/`)
| Script | Purpose |
|---|---|
| `issuesify_board.py` | promote tasks → issues + set every field/milestone/assignee. Idempotent (matches by exact title). Pass titles as args for a staged subset. |
| `prune_drafts.py` | delete stale/duplicate draft cards once tasks are issues (safe: only titles present in the JSON). |
| `sync_board.py` | legacy draft-based sync (Stage/Role/Group only). Superseded by `issuesify_board.py`. |

## 2. The lifecycle — who moves what

```
Backlog → Todo → In Progress → In Review → Done
```

- **AI agents may move a task up to `In Review` only.** When you finish implementing a task, set its
  `stage` to `In Review` in `board_tasks.json` (or move the issue) and hand it back.
- **AI must NEVER self-mark a task `Done`.** Done is a human decision.
- New incoming work the AI picks up at its own discretion starts in `Backlog`/`Todo`; mark it
  `In Progress` while actively working it.

## 3. Human-in-the-loop gate (HITL Gate = Yes)

For any task with **`HITL Gate = Yes`**, a human must manually verify **at least one of**:
- the **code** (read the diff / implementation), or
- the **logic** (does the approach hold up), or
- the **output** (run it; check the result).

**Only the human, after it passes, pushes the card to `Done`.** If it fails review, the human moves
it back to `In Progress` with notes; the AI iterates. Tasks with `HITL Gate = No` (purely mechanical)
may go straight to Done by whoever verifies the mechanical result.

> Principle: **AI generates and eases the work; a human confirms before anything is "Done"** —
> the same gate that applies to org-ops email/posting (`docs/ORG-OPERATIONS.md`).

## 4. Reconciling board state (is a task already done?)

Before starting a task, check whether it (or its prerequisites) is already shipped:
```bash
gh issue list --repo PyTorch-FEU-Tech-Chapter/pytorch-fit-system --state all --search "in:title <keywords>"
gh project item-list 1 --owner PyTorch-FEU-Tech-Chapter --limit 300 --format json   # current Status per item
```
If the code already exists, update the task's `stage` to reflect reality instead of redoing it.

## 5. Windows / gh gotchas (this machine is Windows)

- **Always decode UTF-8 when shelling to `gh` from Python**: `subprocess.run(..., encoding="utf-8",
  errors="replace")`. The default cp1252 codec crashes on emoji/box-drawing in issue bodies.
- **Strip `\r`** before feeding any gh TSV/JSON value to `--date` (`tr -d '\r'`), or you get
  `extra text \x0d` parse errors.
- `gh project item-list` defaults to 30 items — pass `--limit 300`.
- The **Board layout + "Group by: Status"** view and any **Roadmap view** are **UI-only** — they
  cannot be set via API. Tell the user to toggle those once in the Project settings.

## 6. Website-agnostic AI planning and deterministic replay

For resume scraping, job finding, and application-form work, follow the detailed source of truth in
[`AGENTS.md`](AGENTS.md): access gate → rendered DOM inventory → AI-authored strict JSON rules →
domain + layout-fingerprint cache → deterministic replay → human gates.

- The current Codex/Claude session is allowed only for development fixtures and review. It is not
  embedded in the shipped system and must not be a production runtime provider.
- Runtime model calls must go through the provider-neutral HTTP API boundary. Configuration may
  point that boundary to a remote API or a locally hosted model server implementing the supported
  API contract.
- Job-finder development visualization must apply the exact executable selectors to a sanitized
  rendered DOM and visibly tag `CLICK`, `FILL/INTERACT`, `EXTRACT`, `CRAWL`,
  `EXTRACT + CRAWL`, `IGNORE`, `AUTH CHECK`, and `HUMAN GATE` decisions.
- Visual overlays are local debug artifacts under `/out/`; production replay remains headless and
  deterministic and never calls the model again for a confident cached layout.
- For a live Chrome/CDP development test, use `tools/job_finder/cdp_tag.py inventory`, author strict
  `rules.json` with the current session only as a development fixture, then use `apply`. Use
  `api-plan` for configured local-or-remote HTTP model execution. The harness must stop at access
  blockers and must never implement an OSI-layer, CAPTCHA, Cloudflare, fingerprint, proxy, or
  identity bypass.
