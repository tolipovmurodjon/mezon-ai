"""The shared contract: every check, the agent, the API and the UI speak in these shapes."""

from dataclasses import asdict, dataclass, field
from typing import Literal

Severity = Literal["high", "medium", "low"]
FlagStatus = Literal["possible_violation", "unclear_needs_expert"]
Verdict = Literal["positive", "positive_with_fixable_defects", "negative", "not_checked"]
Gate = Literal["0_draft", "1_slipped", "2_adopted"]
Review = Literal["pending", "approved", "rejected"]


@dataclass
class Citation:
    """A pointer into the law store. The validator rejects it unless the article exists and is in force on `on_date`."""

    act_id: str
    act_title: str
    article: str
    quote: str
    on_date: str
    url: str = ""


@dataclass
class Evidence:
    """A verbatim excerpt from the decision itself (or its draft / a related decision)."""

    source: str
    locator: str
    quote: str
    url: str = ""


@dataclass
class Flag:
    check: str
    title: str
    explanation: str
    severity: Severity
    status: FlagStatus = "possible_violation"
    evidence: list[Evidence] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    impact: str = ""
    review: Review = "pending"


@dataclass
class Report:
    decision_id: str
    reg_number: str
    title: str
    body: str
    date: str
    gate: Gate
    verdict: Verdict
    flags: list[Flag] = field(default_factory=list)
    checks_run: list[str] = field(default_factory=list)
    affected: list[str] = field(default_factory=list)
    url: str = ""
    note: str = "Possible violations flagged for expert review. A human expert decides every flag."

    def to_dict(self) -> dict:
        return asdict(self)


def verdict_for(flags: list[Flag]) -> Verdict:
    """Adliya's own three-verdict format: any high possible violation is negative, any other flag is fixable."""
    if any(f.severity == "high" and f.status == "possible_violation" for f in flags):
        return "negative"
    if flags:
        return "positive_with_fixable_defects"
    return "positive"
