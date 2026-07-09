from __future__ import annotations

import re
from pathlib import Path

from .models import LearnedJobListingLayout


class JobListingLayoutStore:
    """Memory-first store for learned job-listing layout rules."""

    def __init__(self, output_dir: Path | None = Path("out/job-finder-rules")) -> None:
        self.output_dir = output_dir
        self._layouts: dict[str, LearnedJobListingLayout] = {}
        self._load_local_layouts()

    def _load_local_layouts(self) -> None:
        if self.output_dir is None or not self.output_dir.exists():
            return
        for path in self.output_dir.glob("*.json"):
            try:
                layout = LearnedJobListingLayout.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except Exception:
                continue
            self._layouts[layout.layout_fingerprint] = layout

    def get(self, layout_fingerprint: str) -> LearnedJobListingLayout | None:
        layout = self._layouts.get(layout_fingerprint)
        return layout.model_copy(deep=True) if layout else None

    def put(self, layout: LearnedJobListingLayout) -> None:
        self._layouts[layout.layout_fingerprint] = layout.model_copy(deep=True)
        if self.output_dir is None:
            return
        self.output_dir.mkdir(parents=True, exist_ok=True)
        domain = re.sub(r"[^a-zA-Z0-9.-]+", "_", layout.domain)
        path = self.output_dir / f"{domain}-{layout.layout_fingerprint}.json"
        path.write_text(layout.model_dump_json(indent=2), encoding="utf-8")

    def all(self) -> list[LearnedJobListingLayout]:
        return [layout.model_copy(deep=True) for layout in self._layouts.values()]
