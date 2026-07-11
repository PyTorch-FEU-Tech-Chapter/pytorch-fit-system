from resume_builder.renderers.formatting import compact_skills


def test_compact_skills_groups_known_frameworks_under_language():
    assert compact_skills(["SQL", "ReactJS", "JavaScript", "Vue", "Docker"]) == [
        "SQL",
        "JavaScript (ReactJS, Vue)",
        "Docker",
    ]


def test_compact_skills_preserves_unrelated_skills_and_source_list():
    source = ["Python", "FastAPI", "Go", "Kubernetes"]
    assert compact_skills(source) == ["Python (FastAPI)", "Go", "Kubernetes"]
    assert source == ["Python", "FastAPI", "Go", "Kubernetes"]
