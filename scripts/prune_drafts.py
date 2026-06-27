#!/usr/bin/env python3
"""Delete stale DRAFT cards from the Project once every task is a real issue.

After issuesify_board.py, every task in board_tasks.json has a real GitHub issue. Any remaining
DraftIssue is stale (a leftover or a duplicate from an earlier partial sync) and shows up as a
"No Status" card. This removes them so the board has zero No-Status items.

Safety: only deletes a draft whose title matches a task title in board_tasks.json. Drafts with no
matching task are reported, NOT deleted (so nothing unexpected is lost).

Usage: python scripts/prune_drafts.py [--dry]
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "board_tasks.json"


def gh(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["gh", *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )


def main() -> None:
    dry = "--dry" in sys.argv[1:]
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    owner, num = cfg["owner"], str(cfg["project_number"])
    task_titles = {t["title"] for t in cfg["tasks"]}

    r = gh(["project", "item-list", num, "--owner", owner, "--limit", "300", "--format", "json"])
    if r.returncode != 0:
        sys.exit(f"item-list failed:\n{r.stderr}")
    items = json.loads(r.stdout)["items"]

    deleted = kept_unmatched = 0
    for it in items:
        c = it.get("content") or {}
        if c.get("type") != "DraftIssue":
            continue
        title = c.get("title") or it.get("title") or ""
        if title in task_titles:
            if dry:
                print(f"  would delete draft: {title[:60]}")
            else:
                if gh(["project", "item-delete", num, "--owner", owner, "--id", it["id"]]).returncode == 0:
                    deleted += 1
                    print(f"  deleted draft: {title[:60]}")
        else:
            kept_unmatched += 1
            print(f"  ! KEPT (no matching task): {title[:60]}")

    print(f"\n{'(dry) ' if dry else ''}deleted {deleted} drafts, kept {kept_unmatched} unmatched")


if __name__ == "__main__":
    main()
