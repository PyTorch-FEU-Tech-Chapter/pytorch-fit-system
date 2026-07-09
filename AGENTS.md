# AGENTS.md

This repo's operating guide for AI agents lives in **[CLAUDE.md](CLAUDE.md)** — read it first.

It covers, in order:
1. **gh CLI prerequisite** — verify `gh` is installed and has the `project` scope; if not, guide the user to install/auth before any board work.
2. **Kanban board** — `scripts/board_tasks.json` is the source of truth; `scripts/issuesify_board.py` promotes tasks to GitHub issues with all fields.
3. **Lifecycle** — Backlog → Todo → In Progress → In Review → Done. **AI may only advance work to `In Review`; it must never self-mark `Done`.**
4. **Human-in-the-loop** — tasks with `HITL Gate = Yes` require a human to verify the code, logic, or output, and only the human pushes the card to `Done`.
5. **Windows/gh gotchas** — UTF-8 subprocess decoding, `\r` stripping, `--limit`, UI-only Board/Roadmap views.

## User's General Algorithm For Web Automation

When working on job finding, job listing extraction, or job application automation, stay true to
this architecture before rereading or changing large parts of the codebase:

The reason to use AI here is not to scrape every page with model calls. The AI exists to make the
system **website-agnostic** and smarter across different site contexts: from a small rendered sample
of a few pages, it should infer the site's repeatable framework, page types, and extraction/fill
rules. Once confidence is high that the pattern is repeatable, the system should cache and replay
those rules deterministically. This mirrors the `rdtii-autoextract` approach: learn structure from a
bounded sample, fingerprint/cache the layout, then amortize token usage across same-layout pages.

1. **AI identifies reusable structure; deterministic code executes it.**
   The AI should inspect a rendered DOM inventory and emit strict, machine-readable rules
   (JSON/Pydantic schema), such as selectors, roles, extraction mappings, include/exclude URL
   patterns, and confidence/warnings. After that, normal code applies those rules. Do not keep
   sending the same layout to the model every run.

2. **Cache by domain and layout fingerprint.**
   A website or ATS normally keeps the same flow/layout for a domain or page type. Learn the
   layout from a small representative sample, store the rules, and reuse them on future pages with
   the same fingerprint to reduce token usage. If confidence is low, ask for a revised rule set or
   sample a few more pages; do not jump to writing a domain-specific crawler unless the generic rule
   approach has clearly failed.

3. **Keep the systems separate.**
   - The resume/data scraper keeps its own extraction actions.
   - `job_finder/` owns job listing discovery rules only.
   - `job_application/` owns future form understanding, form filling, upload, review, and HITL
     submit safety.
   Do not merge these taxonomies just because they share the same "AI learns rules, code replays
   rules" pattern.

4. **Job finder comes first.**
   For job listing pages, the first reusable planner should identify job cards, title, company,
   location, remote/hybrid/f2f signals, employment type, salary/level hints, detail URLs, filters,
   search controls, and pagination. This output must be easy for the system to parse and reuse
   automatically.
   Before extracting, the agent should check whether the browser appears signed in or signed out,
   then decide if it needs to run/search/navigate using search terms first. The title is useful but
   is not the main evidence: after search results exist, prioritize detail links and job-definition
   content such as responsibilities, requirements, qualifications, benefits, salary, location, and
   remote/hybrid/f2f signals.

5. **Application form DOM inventory must be separate.**
   Future form-specific inventory should collect form semantics, not generic scraper content:
   input name/type/placeholder/autocomplete, labels, required markers, aria attributes, options,
   file upload accept types, hidden/disabled state, button text, nearest headings, and validation
   messages.

6. **Application actions need a different taxonomy.**
   Future application-form actions should be separate from job finder and scraper actions, e.g.
   fill text, select option, check option, upload file, click next, review required, human
   required, and submit blocked.

7. **Never auto-submit without human approval.**
   The agent may prepare job applications and fill drafts, but final submit must stay behind the
   existing human-in-the-loop gate. CAPTCHA, login blockers, and sensitive/judgment fields should
   hand off to the user.

8. **Use Playwright visualizers only as temporary debug aids.**
   The final system should be a headless scraper/job finder. During development, it is acceptable
   to use Playwright to render sample pages with visual rule tags so the user can inspect whether
   elements are being marked as `ignore`, `crawl`, `extract`, or `extract_and_crawl`. Keep these
   visual outputs under `/out/` and do not make the production pipeline depend on them. Apply this
   visual checking pattern to both job listing rules and resume evidence scraping rules for posts,
   projects, and achievements.

## Every Prompt Save Rule

For every user prompt that causes codebase changes, the agent must save the work before ending the turn:

1. Run `git status --short --branch`.
2. Review the diff for the files changed by the agent.
3. Run the relevant formatter/test/check command when practical for the scope of the change.
4. Commit the agent-made changes with a concise message.
5. Push the current branch to `origin`.
6. Report the commit hash, pushed branch, and any checks that were run.

Do not commit or revert unrelated user changes. If unrelated changes are present, leave them alone and commit only the files changed for the current prompt.
