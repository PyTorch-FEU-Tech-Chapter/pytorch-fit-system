"""Convert evidence-grounded AI answers into deterministic draft-write steps."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .models import DynamicInteractionStep, QuestionAnswer, ScreeningQuestion
from .question_answering import AIQuestionAnswerer


class QuestionPlanningResult(BaseModel):
    answers: list[QuestionAnswer] = Field(default_factory=list)
    steps: list[DynamicInteractionStep] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)


class AutonomousQuestionPipeline:
    def __init__(self, answerer: AIQuestionAnswerer) -> None:
        self.answerer = answerer

    def plan(self, questions: list[ScreeningQuestion], *, starting_step: int = 1) -> QuestionPlanningResult:
        result = QuestionPlanningResult()
        for offset, question in enumerate(questions):
            answer = self.answerer.answer(question)
            result.answers.append(answer)
            if answer.abstain:
                result.unresolved.append(question.question_id)
                continue
            action = "select" if question.kind in {"select", "radio"} else "fill"
            result.steps.append(DynamicInteractionStep(
                step=starting_step + offset,
                action=action,
                selector=question.selector,
                purpose=f"answer screening question {question.question_id}",
                expected_change="field contains evidence-grounded answer",
                value=answer.answer,
                value_source="ai:search_career_evidence",
                action_class="draft_write",
            ))
        return result
