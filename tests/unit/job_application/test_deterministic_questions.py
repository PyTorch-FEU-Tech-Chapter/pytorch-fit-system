from datetime import date

from resume_builder.core.models import (
    ContactInfo,
    Resume,
    ResumeEducation,
    RoleSpec,
)
from resume_builder.job_application import (
    AutonomousQuestionPipeline,
    DeterministicQuestionResolver,
    HybridQuestionPipeline,
    ScreeningQuestion,
    VerifiedApplicationProfile,
)
from resume_builder.job_application.models import QuestionAnswer


def _resume() -> Resume:
    return Resume(
        role=RoleSpec(id="ai", label="AI Engineer"),
        contact=ContactInfo(
            name="John Andrew Balbarosa",
            location="Philippines",
            github="https://github.com/example",
        ),
        education=[
            ResumeEducation(
                school="FEU Institute of Technology",
                degree="Computer Science",
                field="Computer Software Engineering",
                end="Sep 2027",
            )
        ],
    )


def _question(
    question_id: str,
    label: str,
    *,
    kind: str = "text",
    options: list[str] | None = None,
) -> ScreeningQuestion:
    return ScreeningQuestion(
        question_id=question_id,
        label=label,
        selector=f"#{question_id}",
        kind=kind,
        options=options or [],
    )


class _RecordingAnswerer:
    def __init__(self) -> None:
        self.labels: list[str] = []

    def answer(self, question: ScreeningQuestion) -> QuestionAnswer:
        self.labels.append(question.label)
        return QuestionAnswer(
            question_id=question.question_id,
            answer="I built evidence-grounded agent orchestration projects.",
            confidence=0.9,
            evidence_ids=["project:1"],
        )


def test_standard_resume_and_verified_profile_questions_skip_ai():
    answerer = _RecordingAnswerer()
    resolver = DeterministicQuestionResolver(
        _resume(),
        verified_profile=VerifiedApplicationProfile(
            phone="+639123456789",
            country="Philippines",
        ),
        today=date(2026, 7, 24),
    )
    result = HybridQuestionPipeline(resolver, answerer).plan(
        [
            _question("name", "Legal name"),
            _question("generic_name", "Name"),
            _question("phone", "Mobile number"),
            _question(
                "graduate",
                "Have you graduated?",
                kind="radio",
                options=["Yes", "No"],
            ),
            _question(
                "student",
                "Are you currently a student?",
                kind="radio",
                options=["Yes", "No"],
            ),
            _question("years", "Years of professional experience"),
        ]
    )

    assert answerer.labels == []
    assert result.unresolved == []
    assert [answer.answer for answer in result.answers] == [
        "John Andrew Balbarosa",
        "John Andrew Balbarosa",
        "+639123456789",
        "No",
        "Yes",
        "0",
    ]
    assert result.steps[0].value_source == "resume.contact.name"
    assert result.steps[2].value_source == "verified_profile.phone"
    assert result.steps[3].value_source == "resume.education[0].end"
    assert result.steps[5].value_source == "resume.experience"


def test_nonstandard_career_question_is_the_only_ai_intervention():
    answerer = _RecordingAnswerer()
    pipeline = HybridQuestionPipeline(
        DeterministicQuestionResolver(_resume()),
        answerer,
    )

    result = pipeline.plan(
        [
            _question("country", "Country"),
            _question("agents", "Describe your experience with AI agent orchestration"),
        ]
    )

    assert answerer.labels == ["Describe your experience with AI agent orchestration"]
    assert result.unresolved == []
    assert result.steps[0].value_source == "resume.contact.location"
    assert result.steps[1].value_source == "ai:search_career_evidence"


def test_backward_compatible_pipeline_is_deterministic_first():
    answerer = _RecordingAnswerer()
    answerer.evidence_tool = type("EvidenceTool", (), {"resume": _resume()})()

    result = AutonomousQuestionPipeline(answerer).plan(
        [_question("name", "Full name")]
    )

    assert answerer.labels == []
    assert result.answers[0].answer == "John Andrew Balbarosa"
    assert result.steps[0].value_source == "resume.contact.name"


def test_missing_private_and_judgment_values_never_call_ai():
    answerer = _RecordingAnswerer()
    pipeline = HybridQuestionPipeline(
        DeterministicQuestionResolver(_resume()),
        answerer,
    )

    result = pipeline.plan(
        [
            _question("email", "Email address"),
            _question("street", "Full address"),
            _question("salary", "Expected salary"),
            _question("visa", "Will you require visa sponsorship?"),
            _question("relocate", "Are you willing to relocate?"),
        ]
    )

    assert answerer.labels == []
    assert result.unresolved == ["email", "street", "salary", "visa", "relocate"]
    assert result.steps == []


def test_missing_employment_is_zero_only_for_explicit_total_experience():
    answerer = _RecordingAnswerer()
    pipeline = HybridQuestionPipeline(
        DeterministicQuestionResolver(_resume()),
        answerer,
    )

    result = pipeline.plan(
        [
            _question("years", "How many years of work experience do you have?"),
            _question("company", "Most recent employer"),
            _question("python", "How many years of experience with Python?"),
        ]
    )

    assert result.answers[0].answer == "0"
    assert result.answers[1].abstain is True
    assert answerer.labels == ["How many years of experience with Python?"]
