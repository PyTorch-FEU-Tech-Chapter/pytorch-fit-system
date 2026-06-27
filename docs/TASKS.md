# Delegation Backlog — PyTorch FIT System

> Single source for delegation. Mirrors the GitHub Project board (once `project` scope is
> granted — see bottom). Columns: **Done · Todo · In Progress · In Review · Blocked**.
> Every AI-produced artifact passes a **human-in-the-loop (HITL)** review before it moves to Done.

Legend: 🏛️ Architect · 🗄️ DB · 🤖 AI · 🎨 Frontend · 🔒 Security · 📊 Analytics · 🧪 QA · 🚀 DevOps

---

## ✅ DONE (already built — legacy reference engine + planning)

These exist in the repo today. They are **reference/validated-as-prototype**, not the new platform.

| Item | Where | Notes |
|---|---|---|
| Legacy 5-stage resume pipeline (Python) | `src/resume_builder/` | Proven blueprint for the AI Pipeline |
| Canonical domain models | `src/resume_builder/models.py` | Maps to the normalized schema |
| LLM provider adapter + registry | `src/resume_builder/llm/` | Blueprint for §15 adapter layer |
| Social scraper (FB/LinkedIn/X/IG) + visual debugger | `src/resume_builder/sources/social/` | Reference for raw-input ingestion |
| Renderers (LaTeX/PDF/HTML/MD/JSON) | `src/resume_builder/renderers/` | Reference for generated resume templates |
| Per-folder module READMEs + Mermaid | `src/**/README.md` | Documents the legacy engine |
| Department docs + PlantUML | `docs/departments/` | Legacy architecture reference |
| **Master specification (this pivot)** | `docs/SPECIFICATION.md` | NotebookLM source of truth |
| **Delegation backlog (this file)** | `docs/TASKS.md` | Board source |

---

## 🔲 TODO — unfinished tasks to delegate

> ⚠️ Everything below is **not yet implemented, tested, or validated** on the new stack.
> Each task lists the owner role and its HITL gate.

### Phase 1 — Foundation

| # | Task | Owner | HITL gate |
|---|---|---|---|
| 1 | Finalize platform architecture + ADRs (stack, boundaries) | 🏛️ | Architect sign-off |
| 2 | Design normalized DB schema (Layers 1–3) + ERD | 🗄️ | Schema review |
| 3 | Write SQL migrations + seed data | 🗄️ | Migration dry-run reviewed |
| 4 | Author RLS policies for all user-scoped tables | 🗄️ 🔒 | Security review of every policy |
| 5 | Supabase Auth (Google/GitHub/Email) + role bootstrap | 🎨 🔒 | Auth flow review |
| 6 | Next.js app scaffold on Vercel (routing, layout, env) | 🎨 🚀 | Deploy preview reviewed |
| 7 | Raw-input capture UI (manual + import) | 🎨 | UX review |
| 8 | **AI extraction pipeline** (cleaning→dedup→classify→tag) | 🤖 | Output samples reviewed by human |
| 9 | Skill + experience + industry extraction into normalized tables | 🤖 🗄️ | Spot-check accuracy |
| 10 | Resume Generator (NCD → generated_resume) | 🤖 | Generated resume reviewed |

### Phase 2 — Profiles & Analytics

| # | Task | Owner | HITL gate |
|---|---|---|---|
| 11 | Public profile (curated fields only) + nickname scheme | 🎨 🔒 | Privacy review (no leaks) |
| 12 | Career score + career metrics | 📊 🤖 | Metric definition sign-off |
| 13 | Aggregated/anonymous platform analytics + leaderboards | 📊 🔒 | Anonymity audit |
| 14 | Resume templates system | 🎨 | Design review |

### Phase 3 — Intelligence

| # | Task | Owner | HITL gate |
|---|---|---|---|
| 15 | Portfolio builder | 🎨 🤖 | Review |
| 16 | Job matching | 🤖 | Relevance eval |
| 17 | AI recommendations + missing-skills + roadmap | 🤖 | Human eval of suggestions |

### Phase 4 — Scale

| # | Task | Owner | HITL gate |
|---|---|---|---|
| 18 | Backend API (verification, AI queue, scheduled jobs) | 🚀 🏛️ | Architecture review |
| 19 | Migrate scraping to backend background jobs | 🚀 🤖 | Review |

### Cross-cutting — AI / Model training (chapter-owned)

| # | Task | Owner | HITL gate |
|---|---|---|---|
| 20 | **Define ML task(s):** industry classifier / skill tagger / career scorer | 🤖 🏛️ | Problem framing reviewed |
| 21 | **Dataset:** collect + label from normalized data (privacy-safe) | 🤖 🔒 | Labeling + consent reviewed |
| 22 | **Train PyTorch model(s)** + track experiments | 🤖 | Metrics reviewed by human |
| 23 | **Evaluate** (held-out set, bias/fairness check) | 🤖 🧪 | Eval sign-off before deploy |
| 24 | Serve model behind the AI adapter (§15) | 🤖 🚀 | Inference review |

### Cross-cutting — Quality & Adapter

| # | Task | Owner | HITL gate |
|---|---|---|---|
| 25 | AI model adapter layer (Gemini/OpenAI/Claude/Ollama/LM Studio) | 🤖 🏛️ | Interface review |
| 26 | Test suite: AI output validation, DB consistency, RLS tests | 🧪 | Coverage + RLS pass |
| 27 | Regression harness for AI outputs | 🧪 🤖 | Baseline approved |
| 28 | Security: threat model + access-control docs | 🔒 | Threat model review |
| 29 | CI/CD + monitoring | 🚀 | Pipeline green |

---

## 👤 Human-in-the-loop (HITL) policy

No AI-generated artifact (extracted data, generated resume, trained-model output, recommendation)
is published or marked Done until a human reviewer in the owning role approves it. AI proposes;
humans dispose. Untested or unvalidated code stays in **In Review / Blocked**, never Done.

---

## 🔗 GitHub board provisioning (action required from the maintainer)

The current `gh` token lacks the `project` scope, so the kanban + timeline board cannot be
created programmatically yet. To enable it, run this **yourself** in the session (interactive):

```
! gh auth refresh -s project --hostname github.com
```

After that's granted, the board can be created with:

```
gh project create --owner JohnAndrewBalbarosa --title "PyTorch FIT System"
# + a Status single-select field (Todo/In Progress/In Review/Blocked/Done)
# + Start date / Target date fields for the timeline view
# + one item per task above, labeled by role
```

Until then, this file is the canonical backlog.
