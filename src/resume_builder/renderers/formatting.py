"""Deterministic, display-only resume formatting helpers."""

from __future__ import annotations

from collections.abc import Iterable

_ECOSYSTEMS = (
    ("JavaScript", ("ReactJS", "React Native", "Vue")),
    ("Python", ("PyTorch", "FastAPI")),
)


def compact_skills(skills: Iterable[str]) -> list[str]:
    """Group known language ecosystems without changing normalized source data."""

    values = [skill.strip() for skill in skills if skill and skill.strip()]
    lower_to_value = {skill.casefold(): skill for skill in values}
    consumed: set[str] = set()
    grouped_at: dict[int, str] = {}

    for parent, children in _ECOSYSTEMS:
        parent_key = parent.casefold()
        present_children = [
            lower_to_value[child.casefold()]
            for child in children
            if child.casefold() in lower_to_value
        ]
        if not present_children:
            continue
        keys = {parent_key, *(child.casefold() for child in present_children)}
        positions = [i for i, value in enumerate(values) if value.casefold() in keys]
        grouped_at[min(positions)] = f"{parent} ({', '.join(present_children)})"
        consumed.update(keys)

    output: list[str] = []
    for index, value in enumerate(values):
        if index in grouped_at:
            output.append(grouped_at[index])
        if value.casefold() not in consumed:
            output.append(value)
    return output
