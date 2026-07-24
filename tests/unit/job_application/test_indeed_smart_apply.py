from pathlib import Path

from resume_builder.core.models import (
    ContactInfo,
    Resume,
    ResumeAchievement,
    ResumeExperience,
    RoleSpec,
)
from resume_builder.job_application import (
    IndeedSmartApplyModule,
    SmartApplyApprovals,
    build_indeed_smart_apply_plan,
    classify_indeed_smart_apply_module,
    load_resume_artifact,
    recommend_role_resume,
)


def _resume(*, experience: list[ResumeExperience] | None = None) -> Resume:
    return Resume(
        role=RoleSpec(id="software", label="Software Engineer", keywords=[]),
        contact=ContactInfo(name="John Andrew Balbarosa", location="Philippines"),
        experience=experience or [],
        achievements=[
            ResumeAchievement(
                title="Campus Labs Lead",
                source="linkedin",
                snippet="Student technical-community leadership.",
            )
        ],
    )


def test_classifies_verified_module_urls_and_rejects_other_domains():
    root = "https://smartapply.indeed.com/beta/indeedapply/form"
    assert classify_indeed_smart_apply_module(f"{root}/contact-info-module") == (
        IndeedSmartApplyModule.CONTACT
    )
    assert classify_indeed_smart_apply_module(f"{root}/review-module") == (
        IndeedSmartApplyModule.REVIEW
    )
    assert classify_indeed_smart_apply_module("https://apply.example.com/review-module") == (
        IndeedSmartApplyModule.UNKNOWN
    )


def test_contact_fills_only_missing_names_and_preserves_account_fields():
    plan = build_indeed_smart_apply_plan(
        "https://smartapply.indeed.com/beta/indeedapply/form/contact-info-module",
        _resume(),
        field_values={"first_name": "", "last_name": "", "phone": "existing"},
    )

    assert [(action.target, action.value) for action in plan.browser_actions[:2]] == [
        ("[data-testid=name-fields-first-name-input]", "John Andrew"),
        ("[data-testid=name-fields-last-name-input]", "Balbarosa"),
    ]
    assert all("phone" not in action.target for action in plan.browser_actions)


def test_prefilled_contact_skips_name_writes_and_continues():
    plan = build_indeed_smart_apply_plan(
        "https://smartapply.indeed.com/beta/indeedapply/form/contact-info-module",
        _resume(),
        field_values={
            "first_name": "John Andrew",
            "last_name": "Balbarosa",
            "phone": "9123456789",
        },
        verified_phone="+63 912 345 6789",
        phone_country_calling_code="+63",
    )
    assert [action.action for action in plan.browser_actions] == ["click"]


def test_checker_corrects_only_mismatched_contact_fields():
    plan = build_indeed_smart_apply_plan(
        "https://smartapply.indeed.com/beta/indeedapply/form/contact-info-module",
        _resume(),
        field_values={"first_name": "John", "last_name": "Balbarosa", "phone": ""},
        verified_phone="+63 912 345 6789",
        phone_country_calling_code="+63",
    )

    assert [(action.action, action.value) for action in plan.browser_actions] == [
        ("fill", "John Andrew"),
        ("fill", "9123456789"),
        ("click", ""),
    ]
    assert all(
        action.target != "[data-testid=name-fields-last-name-input]"
        for action in plan.browser_actions
    )


def test_contact_stops_when_no_verified_phone_is_available():
    plan = build_indeed_smart_apply_plan(
        "https://smartapply.indeed.com/beta/indeedapply/form/contact-info-module",
        _resume(),
        field_values={
            "first_name": "John Andrew",
            "last_name": "Balbarosa",
            "phone": "",
        },
    )

    assert plan.browser_actions == []
    assert "verified phone number is unavailable" in plan.stop_reason


def test_empty_experience_never_promotes_achievement_to_employment():
    plan = build_indeed_smart_apply_plan(
        "https://smartapply.indeed.com/beta/indeedapply/form/resume-module/relevant-experience",
        _resume(),
    )
    assert [action.action for action in plan.browser_actions] == ["click"]
    assert "achievements" in plan.warnings[0]


def test_professional_experience_is_the_only_employment_source():
    plan = build_indeed_smart_apply_plan(
        "https://smartapply.indeed.com/beta/indeedapply/form/resume-module/relevant-experience",
        _resume(experience=[ResumeExperience(role="Developer", company="Acme")]),
    )
    assert [action.value_source for action in plan.browser_actions[:2]] == [
        "resume.experience[0].role",
        "resume.experience[0].company",
    ]


def test_resume_upload_and_continue_are_two_separate_human_gates(tmp_path: Path):
    artifact = tmp_path / "software-systems.pdf"
    artifact.write_bytes(b"%PDF-1.4\n")
    url = (
        "https://smartapply.indeed.com/beta/indeedapply/form/"
        "resume-selection-module/resume-selection"
    )

    upload = build_indeed_smart_apply_plan(
        url,
        _resume(),
        approved_resume=artifact,
        approvals=SmartApplyApprovals(resume_upload=True),
    )
    assert [action.action for action in upload.browser_actions] == ["upload"]
    assert "stop after upload" in upload.stop_reason

    review = build_indeed_smart_apply_plan(
        url,
        _resume(),
        selected_resume=artifact.name,
        approved_resume=artifact,
    )
    assert review.browser_actions == []
    assert "preview requires human approval" in review.stop_reason

    continued = build_indeed_smart_apply_plan(
        url,
        _resume(),
        selected_resume=artifact.name,
        approved_resume=artifact,
        approvals=SmartApplyApprovals(resume_continue=True),
    )
    assert [action.action for action in continued.browser_actions] == ["click"]


def test_review_never_submits_without_explicit_approval():
    url = "https://smartapply.indeed.com/beta/indeedapply/form/review-module"
    stopped = build_indeed_smart_apply_plan(url, _resume())
    approved = build_indeed_smart_apply_plan(
        url,
        _resume(),
        approvals=SmartApplyApprovals(final_submit=True),
    )
    assert stopped.browser_actions == []
    assert approved.browser_actions[0].action_class == "irreversible"


def test_role_resume_recommendation_returns_only_existing_artifacts(tmp_path: Path):
    software = tmp_path / "software-systems.pdf"
    software.write_bytes(b"%PDF")
    assert recommend_role_resume("Software Engineer", tmp_path) == software.resolve()
    assert recommend_role_resume("Machine Learning Engineer", tmp_path) is None


def test_generated_resume_loader_ignores_renderer_metadata(tmp_path: Path):
    path = tmp_path / "resume.json"
    payload = _resume().model_dump(mode="json")
    payload["layout"] = {"page_count": 1}
    import json

    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_resume_artifact(path).contact.name == "John Andrew Balbarosa"
