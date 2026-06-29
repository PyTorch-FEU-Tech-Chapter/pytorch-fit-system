from __future__ import annotations

import base64
import logging
import re
from typing import Callable

from .models import DEFAULT_CAP_CHARS, CleanedSource, apply_token_cap

log = logging.getLogger(__name__)

_MD_KEEP = re.compile(r"(^|/)README\.[^/]+$|^docs/.*\.md$", re.IGNORECASE)


def _strip_md_noise(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)            # HTML comments
    text = re.sub(r"\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)", "", text)      # badge links
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)                   # images
    text = re.sub(r"<[^>]+>", "", text)                               # raw html tags
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def collect_repo_markdown(
    full_name: str,
    gh_json: Callable[[list[str]], object],
    ref: str = "HEAD",
    cap_chars: int = DEFAULT_CAP_CHARS,
    max_files: int = 50,
) -> list[CleanedSource]:
    """Collect every README.* + docs/*.md in a repo as light-normalized CleanedSources.

    Each source's text is capped to ``cap_chars`` characters (spec §6 bounding).
    Collection stops after ``max_files`` files to bound total work.
    """
    try:
        tree = gh_json(["api", f"repos/{full_name}/git/trees/{ref}?recursive=1"]) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("git-tree fetch failed for %s: %s", full_name, exc)
        return []
    out: list[CleanedSource] = []
    for node in (tree.get("tree", []) if isinstance(tree, dict) else []):
        if len(out) >= max_files:
            break
        path = node.get("path", "")
        if node.get("type") != "blob" or not _MD_KEEP.search(path):
            continue
        try:
            blob = gh_json(["api", f"repos/{full_name}/contents/{path}"]) or {}
            raw = base64.b64decode(blob.get("content", "")).decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001
            log.warning("blob fetch failed for %s/%s: %s", full_name, path, exc)
            continue
        if not raw.strip():
            continue
        text = _strip_md_noise(raw)
        capped, truncated = apply_token_cap(text, cap_chars)
        out.append(
            CleanedSource(
                source_id=f"{full_name}:{path}",
                kind="github_readme",
                title=path,
                text=capped,
                section_hints=[path],
                truncated=truncated,
            )
        )
    return out
