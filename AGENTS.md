# AGENTS.md

This repo's operating guide for AI agents lives in **[CLAUDE.md](CLAUDE.md)** — read it first.

It covers, in order:
1. **gh CLI prerequisite** — verify `gh` is installed and has the `project` scope; if not, guide the user to install/auth before any board work.
2. **Kanban board** — `scripts/board_tasks.json` is the source of truth; `scripts/issuesify_board.py` promotes tasks to GitHub issues with all fields.
3. **Lifecycle** — Backlog → Todo → In Progress → In Review → Done. **AI may only advance work to `In Review`; it must never self-mark `Done`.**
4. **Human-in-the-loop** — tasks with `HITL Gate = Yes` require a human to verify the code, logic, or output, and only the human pushes the card to `Done`.
5. **Windows/gh gotchas** — UTF-8 subprocess decoding, `\r` stripping, `--limit`, UI-only Board/Roadmap views.

## User's Web Automation Pipeline

When working on resume evidence scraping, job finding, or job application automation, keep the
pipeline below as the source of truth. Keep scraper, job finder, and job application form filling as
separate systems even when they share the same learn-once/replay-many pattern.

1. **Access gate.**
   Open the page with a normal browser context, classify access state first, and stop for
   verification, CAPTCHA, Cloudflare, 403/429, login walls, or sign-in blockers. Use bounded retry,
   backoff, and per-domain cooldown only; do not add bypass or identity-rotation behavior.

2. **Rendered sample inventory.**
   Capture a small rendered DOM sample for the target page type. For job finder pages, inventory
   search controls, filters, job cards, detail panels, pagination, and safe read-only detail
   interactions. For application forms, use a separate form-specific inventory.

3. **AI rule planning.**
   Ask AI to convert the inventory into strict, parseable rules. The AI should identify reusable
   structure, page roles, selectors, extraction/fill mappings, confidence, warnings, and any SPA or
   same-page detail workflow. The AI should not be called repeatedly for a layout that already has
   confident cached rules.

   The accepted AI artifact must be saved as strict JSON. For resume evidence, use an explicit
   `results` object split into `quantitative` and `qualitative`, followed by a `conclusion`:

   ```json
   {
     "results": {
       "quantitative": ["metric + value + context + what the number means"],
       "qualitative": ["problem solved + effect/beneficiary + demonstrated capability"]
     },
     "conclusion": "evidence-grounded value + strongest demonstrated capability"
   }
   ```

   Result writing must add context without bloating existing prose: keep an already-good sentence
   unchanged; add one short follow-up sentence or array item. Each fact/context item must render as
   its own bullet so it can be scanned or removed independently. Explain numbers for a non-expert;
   prefer lists and `:`, `-`, `,`, `()` over filler/connector phrases. Never invent,
   estimate, alter, or extrapolate metrics. Keep internal `skill_subtags` atomic for matching and
   deduplication. Only the final resume display may group related ecosystems to save space, e.g.
   `JavaScript (ReactJS, React Native, Vue)` or `Python (PyTorch, FastAPI)`.

   Skills must also be emitted as a real hierarchy in resume JSON: `skill_groups[]` contains a
   programming language/platform `name` plus an `items[]` sublist of evidenced libraries or
   frameworks. Use names only—no skill explanations, proficiency claims, or filler. A framework
   supplies its own context. Do not infer a library from the language alone. Renderers must compute
   the skill-grid column count from actual group content and available page width; never hardcode
   `repeat(3, 1fr)` or manually guess space. After injection, run the bounds analyzer/actual PDF page
   count; layout measurement—not an agent estimate—is the final authority for one-page fit.

4. **Rule cache.**
   Cache accepted rules by domain and layout fingerprint. Reuse cached rules on later pages with the
   same fingerprint; resample or replan only when the fingerprint changes or confidence is low.

5. **Deterministic execution.**
   Execute cached rules with code, not model calls. For job finder, extract job definition details
   from visible details/panels first, then cards and pagination. For application forms, fill only
   draft-safe fields and keep submit blocked.

6. **Human review gates.**
   Hand off whenever access is blocked, confidence is low, the page asks for sensitive judgment, or
   a final submit would be required. Never auto-submit an application without human approval.

7. **Debug visualizers only.**
   Playwright visual tagging is allowed only as a temporary development aid under `/out/`. The final
   scraper/job finder path should stay headless and should not depend on visual debug tooling.

## Every Prompt Save Rule

For every user prompt that causes codebase changes, the agent must save the work before ending the turn:

1. Run `git status --short --branch`.
2. Review the diff for the files changed by the agent.
3. Run the relevant formatter/test/check command when practical for the scope of the change.
4. Commit the agent-made changes with a concise message.
5. Push the current branch to `origin`.
6. Report the commit hash, pushed branch, and any checks that were run.

Do not commit or revert unrelated user changes. If unrelated changes are present, leave them alone and commit only the files changed for the current prompt.
