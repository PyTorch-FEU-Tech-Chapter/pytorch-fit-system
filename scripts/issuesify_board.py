#!/usr/bin/env python3
"""Promote board tasks to GitHub issues + sync every Project field. Idempotent.

Model (the confirmed "full recipe"):
- ACTIVE tasks (stage != Done)  -> a real GitHub ISSUE (labelled), added to the Project, all
  fields set; the matching draft card is deleted so the issue replaces it.
- DONE tasks                    -> kept as a DRAFT card (created if missing), all fields set.

Idempotent + authoritative:
- issues matched by exact title (never duplicated); reused if already present.
- project items matched by title; drafts for active tasks are pruned once an issue exists.

Windows-safe: every gh call decodes UTF-8 (bodies carry emoji/box-drawing); dates are \\r-stripped.

Usage:
    python scripts/issuesify_board.py                 # process ALL tasks
    python scripts/issuesify_board.py "Title A" ...   # only these titles (staged/test run)
Requires: gh authenticated with the `project` scope; labels already created.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = "JohnAndrewBalbarosa/pytorch-fit-system"
HERE = Path(__file__).resolve().parent
CONFIG = HERE / "board_tasks.json"

# Project single-select field name -> task json key.
FIELD_KEY = {
    "Stage": "stage",
    "Role": "role",
    "Group": "group",
    "Department": "department",
    "HITL Gate": "hitl",
}
DATE_KEY = {"Start": "start", "Target": "target"}

DEPT_LABEL = {
    "Legacy Engine": "dept:legacy-engine",
    "Platform Core": "dept:platform-core",
    "Org Operations": "dept:org-operations",
    "Points & Leaderboard": "dept:points",
    "Data & DB": "dept:data-db",
    "AI & ML": "dept:ai-ml",
    "Frontend": "dept:frontend",
    "DevOps": "dept:devops",
    "Docs & Ops": "dept:docs-ops",
}


def gh(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["gh", *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )


def gh_project_json(args: list[str]):
    r = gh([*args, "--format", "json"])
    if r.returncode != 0:
        sys.exit(f"gh {' '.join(args)} failed:\n{r.stderr}")
    return json.loads(r.stdout)


def issue_body(task: dict) -> str:
    """Task body + a delegation footer (department / HITL / reverse-prompt seed)."""
    dept = task.get("department", "—")
    hitl = task.get("hitl", "No")
    seed = (
        "Before coding, restate the goal in your own words, list the exact files you'll touch, "
        "and surface any assumption that, if wrong, changes the approach."
    )
    return (
        f"{task.get('body', '').strip()}\n\n"
        "---\n"
        f"**Department:** {dept} · **HITL Gate:** {hitl}\n"
        f"**Reverse-prompt seed:** {seed}\n"
        "_Boundary: stay within the files in Scope; if the change spills outside, stop and flag it._"
    )


def labels_for(task: dict) -> list[str]:
    out = ["delegation", DEPT_LABEL.get(task.get("department", ""), "dept:platform-core")]
    if task.get("hitl") == "Yes":
        out.append("hitl")
    if task.get("group") == "Model Training":
        out.append("model-training")
    return out


def set_fields(item_id: str, project_id: str, fmap: dict, opts: dict, task: dict) -> None:
    for fname, key in FIELD_KEY.items():
        value = task.get(key)
        if not value:
            continue
        opt_id = opts[fname].get(value)
        if opt_id is None:
            print(f"  ! unknown {fname} {value!r}")
            continue
        gh(["project", "item-edit", "--id", item_id, "--project-id", project_id,
            "--field-id", fmap[fname]["id"], "--single-select-option-id", opt_id])
    for fname, key in DATE_KEY.items():
        value = (task.get(key) or "").strip()
        if not value:
            continue
        gh(["project", "item-edit", "--id", item_id, "--project-id", project_id,
            "--field-id", fmap[fname]["id"], "--date", value])


def main() -> None:
    only = set(sys.argv[1:])
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    owner, num = cfg["owner"], str(cfg["project_number"])

    project_id = gh_project_json(["project", "view", num, "--owner", owner])["id"]
    fields = gh_project_json(["project", "field-list", num, "--owner", owner])["fields"]
    fmap = {f["name"]: f for f in fields}
    for name in [*FIELD_KEY, *DATE_KEY]:
        if name not in fmap:
            sys.exit(f"field {name!r} missing on the project")
    opts = {n: {o["name"]: o["id"] for o in fmap[n].get("options", [])} for n in FIELD_KEY}

    items = gh_project_json(
        ["project", "item-list", num, "--owner", owner, "--limit", "200"]
    )["items"]
    draft_by_title: dict[str, str] = {}
    issue_item_by_title: dict[str, str] = {}
    for it in items:
        c = it.get("content") or {}
        title = c.get("title") or it.get("title")
        if c.get("type") == "DraftIssue":
            draft_by_title.setdefault(title, it["id"])
        else:
            issue_item_by_title.setdefault(title, it["id"])

    # existing repo issues by title (avoid duplicate creation)
    r = gh(["issue", "list", "--repo", REPO, "--state", "all", "--limit", "300",
            "--json", "number,title,url"])
    existing_issues = {i["title"]: i for i in json.loads(r.stdout or "[]")}

    created_issue = reused_issue = drafts_made = pruned = 0
    for task in cfg["tasks"]:
        title = task["title"]
        if only and title not in only:
            continue
        is_done = task.get("stage") == "Done"

        if is_done:
            item_id = draft_by_title.get(title) or issue_item_by_title.get(title)
            if item_id is None:
                rc = gh(["project", "item-create", num, "--owner", owner, "--title", title,
                         "--body", task.get("body", ""), "--format", "json"])
                if rc.returncode != 0:
                    print(f"  ! draft create failed: {title}: {rc.stderr.strip()[:100]}")
                    continue
                item_id = json.loads(rc.stdout)["id"]
                drafts_made += 1
            set_fields(item_id, project_id, fmap, opts, task)
            print(f"  done-draft  {title[:54]}")
            continue

        # ACTIVE -> real issue
        issue = existing_issues.get(title)
        if issue is None:
            label_args: list[str] = []
            for lb in labels_for(task):
                label_args += ["--label", lb]
            rc = gh(["issue", "create", "--repo", REPO, "--title", title,
                     "--body", issue_body(task), *label_args])
            url = (rc.stdout or "").strip().splitlines()[-1] if rc.returncode == 0 else ""
            if not url.startswith("http"):
                print(f"  ! issue create failed: {title}: {rc.stderr.strip()[:120]}")
                continue
            created_issue += 1
        else:
            url = issue["url"]
            reused_issue += 1

        item_id = issue_item_by_title.get(title)
        if item_id is None:
            rc = gh(["project", "item-add", num, "--owner", owner, "--url", url, "--format", "json"])
            if rc.returncode != 0:
                print(f"  ! item-add failed: {title}: {rc.stderr.strip()[:100]}")
                continue
            item_id = json.loads(rc.stdout)["id"]
        set_fields(item_id, project_id, fmap, opts, task)

        # the issue replaces the draft card
        draft_id = draft_by_title.get(title)
        if draft_id:
            if gh(["project", "item-delete", num, "--owner", owner, "--id", draft_id]).returncode == 0:
                pruned += 1
        print(f"  issue       {title[:54]}")

    print(
        f"\n{created_issue} issues created, {reused_issue} reused, "
        f"{drafts_made} done-drafts created, {pruned} drafts pruned"
    )


if __name__ == "__main__":
    main()
