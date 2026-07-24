from dataclasses import dataclass

from resume_builder.core.models import ContactInfo, Resume, RoleSpec
from resume_builder.job_application import (
    HumanVerificationQueue,
    ApplicationPermissionPolicy,
    DynamicInteractionStep,
    IndeedSmartApplyRunStatus,
    QuestionPlanningResult,
    SmartApplyApprovals,
    run_indeed_smart_apply_until_gate,
)
from resume_builder.job_application.indeed_smart_apply_runner import _visible_access_blocker


@dataclass
class _State:
    url: str
    body: str
    fields: dict[str, str]


class _Locator:
    def __init__(self, page, selector: str):
        self.page = page
        self.selector = selector

    @property
    def first(self):
        return self

    @property
    def last(self):
        return self

    def nth(self, _index):
        return self

    def count(self):
        if self.selector.startswith(("iframe", "[data-testid=challenge")):
            return 0
        if self.selector.startswith(("input[required]", "textarea[required]", "select[required]")):
            return 0
        return 1

    def is_visible(self):
        return True

    def inner_text(self):
        return self.page.state.body

    def input_value(self):
        if "first-name" in self.selector or "firstName" in self.selector:
            return self.page.state.fields.get("first_name", "")
        if "last-name" in self.selector or "lastName" in self.selector:
            return self.page.state.fields.get("last_name", "")
        if "phone" in self.selector:
            return self.page.state.fields.get("phone", "")
        return ""

    def locator(self, selector):
        return _Locator(self.page, f"{self.selector} {selector}")

    def get_by_text(self, text, exact=False):
        return _Locator(self.page, f"text={text}")

    def wait_for(self, **_kwargs):
        return None

    def fill(self, value):
        if "first-name" in self.selector:
            self.page.state.fields["first_name"] = value
        elif "last-name" in self.selector:
            self.page.state.fields["last_name"] = value
        elif "phone" in self.selector:
            self.page.state.fields["phone"] = value

    def click(self):
        if self.selector.startswith("text="):
            self.page.state.fields["question_answer"] = self.selector.removeprefix("text=")
        else:
            self.page.advance()

    def check(self):
        self.page.state.fields["checked"] = "true"

    def set_input_files(self, value):
        self.page.uploaded = value


class _Page:
    def __init__(self, states):
        self.states = states
        self.index = 0
        self.uploaded = ""

    @property
    def state(self):
        return self.states[self.index]

    @property
    def url(self):
        return self.state.url

    def locator(self, selector):
        return _Locator(self, selector)

    def wait_for_timeout(self, _milliseconds):
        return None

    def advance(self):
        self.index += 1


class _DelayedPage(_Page):
    def __init__(self, states):
        super().__init__(states)
        self.pending_advance = False
        self.waits = 0

    def advance(self):
        self.pending_advance = True

    def wait_for_timeout(self, _milliseconds):
        self.waits += 1
        if self.pending_advance and self.waits >= 2:
            self.index += 1
            self.pending_advance = False


class _HydratingPage(_Page):
    def __init__(self, states):
        super().__init__(states)
        self.waits = 0

    def wait_for_timeout(self, _milliseconds):
        self.waits += 1
        if self.waits == 2:
            self.index += 1


def _resume():
    return Resume(
        role=RoleSpec(id="ai", label="AI Engineer", keywords=[]),
        contact=ContactInfo(name="John Andrew Balbarosa", location="Philippines"),
    )


def test_runner_advances_known_safe_modules_and_stops_at_review():
    root = "https://smartapply.indeed.com/beta/indeedapply/form"
    page = _Page(
        [
            _State(
                f"{root}/contact-info-module",
                "Add contact information +63",
                {
                    "first_name": "John Andrew",
                    "last_name": "Balbarosa",
                    "phone": "9123456789",
                },
            ),
            _State(f"{root}/profile-location", "Country Philippines", {}),
            _State(f"{root}/resume-module/relevant-experience", "Relevant experience", {}),
            _State(f"{root}/review-module", "Submit your application", {}),
        ]
    )

    result = run_indeed_smart_apply_until_gate(
        page,
        _resume(),
        approvals=SmartApplyApprovals(),
        verified_phone="+63 9123456789",
        phone_country_calling_code="+63",
    )

    assert result.status == IndeedSmartApplyRunStatus.REVIEW_READY
    assert result.actions_executed == [
        "contact:click",
        "location:click",
        "relevant_experience:click",
    ]
    assert page.index == 3


def test_runner_stops_on_unknown_module_without_clicking():
    page = _Page([_State("https://smartapply.indeed.com/new-layout", "Unknown", {})])

    result = run_indeed_smart_apply_until_gate(page, _resume())

    assert result.status == IndeedSmartApplyRunStatus.HUMAN_HANDOFF
    assert "AI sampling" in result.stop_reason
    assert page.index == 0


def test_runner_waits_for_delayed_module_navigation():
    root = "https://smartapply.indeed.com/beta/indeedapply/form"
    page = _DelayedPage(
        [
            _State(f"{root}/profile-location", "Country Philippines", {}),
            _State(f"{root}/review-module", "Submit your application", {}),
        ]
    )

    result = run_indeed_smart_apply_until_gate(page, _resume())

    assert result.status == IndeedSmartApplyRunStatus.REVIEW_READY
    assert page.waits >= 2


def test_runner_waits_for_unknown_hydration_route_before_handoff():
    root = "https://smartapply.indeed.com/beta/indeedapply/form"
    page = _HydratingPage(
        [
            _State(f"{root}/resume-selection-module", "Loading", {}),
            _State(f"{root}/review-module", "Submit your application", {}),
        ]
    )

    result = run_indeed_smart_apply_until_gate(page, _resume())

    assert result.status == IndeedSmartApplyRunStatus.REVIEW_READY
    assert page.waits == 2


def test_runner_executes_one_accepted_question_plan_then_stops_at_review():
    root = "https://smartapply.indeed.com/beta/indeedapply/form"
    page = _Page(
        [
            _State(f"{root}/questions-module/questions/1", "Bachelor degree? Yes No", {}),
            _State(f"{root}/review-module", "Submit your application", {}),
        ]
    )
    plan = QuestionPlanningResult(
        steps=[
            DynamicInteractionStep(
                step=1,
                action="select",
                selector='fieldset[role="radiogroup"]',
                purpose="answer degree completion question",
                expected_change="No is selected",
                value="No",
                value_source="resume.education",
                action_class="draft_write",
            )
        ]
    )

    result = run_indeed_smart_apply_until_gate(page, _resume(), question_plan=plan)

    assert result.status == IndeedSmartApplyRunStatus.REVIEW_READY
    assert result.actions_executed == ["questions:select", "questions:click"]
    assert page.states[0].fields["question_answer"] == "No"


def test_runner_waits_for_observable_post_apply_after_approved_submit():
    root = "https://smartapply.indeed.com/beta/indeedapply/form"
    page = _Page(
        [
            _State(f"{root}/review-module", "Submit your application", {}),
            _State(f"{root}/post-apply", "Your application has been submitted", {}),
        ]
    )

    result = run_indeed_smart_apply_until_gate(
        page,
        _resume(),
        approvals=SmartApplyApprovals(final_submit=True),
        permission_policy=ApplicationPermissionPolicy(
            autonomous_submit=True,
            allowed_domains={"smartapply.indeed.com"},
        ),
    )

    assert result.status == IndeedSmartApplyRunStatus.POST_APPLY
    assert result.module.value == "post_apply"
    assert result.actions_executed == ["review:final_submit"]
    assert page.index == 1


class _RecaptchaLocator:
    def __init__(self, *, checked: bool):
        self.checked = checked

    def count(self):
        return 1

    def nth(self, _index):
        return self

    def is_visible(self):
        return True

    def get_attribute(self, name):
        if name == "src":
            return "https://www.recaptcha.net/recaptcha/enterprise/anchor"
        if name == "aria-checked":
            return "true" if self.checked else "false"
        return None

    def element_handle(self):
        return self

    def content_frame(self):
        return self

    def locator(self, selector):
        assert selector == "#recaptcha-anchor"
        return self


class _EmptyLocator:
    @property
    def first(self):
        return self

    def count(self):
        return 0

    def inner_text(self):
        return "Review your application"


class _RecaptchaPage:
    def __init__(self, *, checked: bool):
        self.anchor = _RecaptchaLocator(checked=checked)

    def locator(self, selector):
        if selector == 'iframe[src*="recaptcha"]':
            return self.anchor
        return _EmptyLocator()


def test_completed_recaptcha_anchor_is_not_an_active_blocker():
    assert _visible_access_blocker(_RecaptchaPage(checked=True)) == ""


def test_unchecked_recaptcha_anchor_requires_human_handoff():
    assert _visible_access_blocker(_RecaptchaPage(checked=False)) == "captcha"


def test_runner_queues_active_captcha_without_storing_query_values(tmp_path):
    page = _RecaptchaPage(checked=False)
    page.url = (
        "https://smartapply.indeed.com/beta/indeedapply/form/review-module"
        "?iaUid=private-session"
    )
    queue = HumanVerificationQueue(tmp_path / "verification.json")

    result = run_indeed_smart_apply_until_gate(
        page,
        _resume(),
        verification_queue=queue,
        application_reference="Backend Developer - AI Trainer",
    )

    assert result.status == IndeedSmartApplyRunStatus.HUMAN_HANDOFF
    assert len(queue.pending()) == 1
    assert queue.pending()[0].reason == "captcha"
    assert "private-session" not in queue.path.read_text(encoding="utf-8")
