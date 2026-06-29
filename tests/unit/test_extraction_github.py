from __future__ import annotations

import base64

from resume_builder.extraction.github_traversal import collect_repo_markdown


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _fake_gh_json(calls):
    tree = {
        "tree": [
            {"path": "README.md", "type": "blob"},
            {"path": "sub/README.md", "type": "blob"},
            {"path": "docs/ARCH.md", "type": "blob"},
            {"path": "src/main.py", "type": "blob"},   # ignored (not md/readme)
            {"path": "docs", "type": "tree"},          # ignored (not a blob)
        ]
    }
    bodies = {
        "README.md": "# Title\n<!-- comment -->\n![badge](x.png)\nReal text.",
        "sub/README.md": "Sub readme content.",
        "docs/ARCH.md": "Architecture notes.",
    }

    def gh_json(args):
        calls.append(args)
        joined = " ".join(args)
        if "git/trees" in joined:
            return tree
        for path, body in bodies.items():
            if joined.endswith(f"contents/{path}"):
                return {"content": _b64(body)}
        return None

    return gh_json


def test_collects_all_readmes_and_docs_md():
    sources = collect_repo_markdown("owner/repo", _fake_gh_json([]))
    paths = {s.title for s in sources}
    assert paths == {"README.md", "sub/README.md", "docs/ARCH.md"}
    assert all(s.kind == "github_readme" for s in sources)


def test_markdown_noise_is_stripped():
    sources = collect_repo_markdown("owner/repo", _fake_gh_json([]))
    root = next(s for s in sources if s.title == "README.md")
    assert "Real text." in root.text
    assert "<!--" not in root.text and "badge" not in root.text


def test_tree_failure_returns_empty():
    assert collect_repo_markdown("owner/repo", lambda args: None) == []
