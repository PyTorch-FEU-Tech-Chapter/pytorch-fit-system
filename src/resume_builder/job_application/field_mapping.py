from __future__ import annotations

from resume_builder.job_application.field_taxonomy import is_judgment_field
from resume_builder.job_application.models import DetectedField, MissingInformation

_DEGREE_TIERS: list[tuple[list[str], list[str]]] = [
    (["phd", "doctor", "doctorate"], ["doctorate", "phd", "doctor"]),
    (["ms", "master", "msc", "m.s."], ["master"]),
    (["bs", "bachelor", "bsc", "b.s."], ["bachelor"]),
    (["high school", "diploma", "hs"], ["high school", "diploma", "hs"]),
]


def total_years_experience(spans: list[tuple[float, float]]) -> float:
    total = sum(max(0.0, end - start) for start, end in spans)
    return round(total, 1)


def degree_to_enum(degree: str, options: list[str]) -> str | None:
    normalized = degree.lower()
    for keywords, tier_keywords in _DEGREE_TIERS:
        if any(kw in normalized for kw in keywords):
            for option in options:
                option_lower = option.lower()
                if any(tk in option_lower for tk in tier_keywords):
                    return option
    return None


def build_detected_field(
    canonical: str,
    label: str,
    kind: str,
    required: bool,
    ncd_value: str | None,
) -> DetectedField | MissingInformation:
    if is_judgment_field(canonical):
        return MissingInformation(
            canonical=canonical,
            label=label,
            reason="judgment field",
        )
    if not ncd_value:
        return MissingInformation(
            canonical=canonical,
            label=label,
            reason="not in NCD",
        )
    return DetectedField(
        selector_hint=f"[name='{canonical}']",
        canonical=canonical,
        kind=kind,
        required=required,
        mapped_value=ncd_value,
        source="ncd",
        confidence=0.95,
    )
