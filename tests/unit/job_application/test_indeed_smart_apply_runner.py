from dataclasses import dataclass

from resume_builder.core.models import ContactInfo, Resume, RoleSpec
from resume_builder.job_application import (
    IndeedSmartApplyRunStatus,
    SmartApplyApprovals,
    run_indeed_smart_apply_until_gate,
)


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

    def nth(self, _index):
        return self

    def count(self):
        if self.selector.startswith(("iframe", "[data-testid=challenge")):
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
        self.page.index += 1

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
