# AGENTS.md

This repo's operating guide for AI agents lives in **[CLAUDE.md](CLAUDE.md)** — read it first.

It covers, in order:
1. **gh CLI prerequisite** — verify `gh` is installed and has the `project` scope; if not, guide the user to install/auth before any board work.
2. **Kanban board** — `scripts/board_tasks.json` is the source of truth; `scripts/issuesify_board.py` promotes tasks to GitHub issues with all fields.
3. **Lifecycle** — Backlog → Todo → In Progress → In Review → Done. **AI may only advance work to `In Review`; it must never self-mark `Done`.**
4. **Human-in-the-loop** — tasks with `HITL Gate = Yes` require a human to verify the code, logic, or output, and only the human pushes the card to `Done`.
5. **Windows/gh gotchas** — UTF-8 subprocess decoding, `\r` stripping, `--limit`, UI-only Board/Roadmap views.
