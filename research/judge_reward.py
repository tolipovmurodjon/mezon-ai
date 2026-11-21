"""Strict-judge reward (internship_rl_pilot.md section 2.3). Pure functions, no model, no store access.

    from research.judge_reward import reward
    r, outcome = reward(item, answer)          # outcome: right | warranted_abstain | lazy_abstain | wrong | broken

right +1.0 | warranted noaniq (gold is noaniq) +0.2 | lazy noaniq (store has the answer) -0.25 |
wrong and confident (any answer to a gold-noaniq item too) -1.5 | broken format / no answer / over length -1.0.
Grading itself is research.mezonbench.grade (lookup / flip / in_force / hierarchy) and
research.mezonbench_where.grade (where); a "noaniq" answer is detected with the same fold() as the exams.
"""

import re

from research.mezonbench import grade as grade_main
from research.mezonbench_where import grade as grade_where
from research.textnorm import fold

R_RIGHT, R_WARRANTED, R_LAZY, R_WRONG, R_BROKEN = 1.0, 0.2, -0.25, -1.5, -1.0
MAX_CHARS = {"flip": 300, "in_force": 300, "hierarchy": 300, "lookup": 2500, "where": 600}
BINARY = ("flip", "in_force", "hierarchy")


def is_abstain(answer: str) -> bool:
    return "noaniq" in fold(answer or "")


def _binary_parsed(family: str, answer: str) -> bool:
    a = (answer or "").strip()
    if family == "in_force":
        f = fold(a).lstrip(" *\"'")
        return f.startswith(("yo", "yoq", "йў", "нет", "no", "ha", "да", "yes"))
    return re.search(r"\b([AB])\b", a.upper()) is not None


def is_broken(item: dict, answer: str) -> bool:
    a = (answer or "").strip()
    if not a or "<tool_call" in a or "<function=" in a or "<think" in a:
        return True
    if len(a) > MAX_CHARS.get(item["family"], 2500):
        return True
    return bool(item["family"] in BINARY and not is_abstain(a) and not _binary_parsed(item["family"], a))


def grade(item: dict, answer: str) -> str:
    """'right' | 'wrong' | 'abstain' with the exam graders (gold noaniq items are handled in reward())."""
    return (grade_where if item["family"] == "where" else grade_main)(item, answer)


def reward(item: dict, answer: str) -> tuple[float, str]:
    if is_broken(item, answer):
        return R_BROKEN, "broken"
    unanswerable = bool(item.get("unans")) or str(item.get("answer")) == "noaniq"
    if unanswerable:
        return (R_WARRANTED, "warranted_abstain") if is_abstain(answer) else (R_WRONG, "wrong")
    g = grade(item, answer)
    if g == "right":
        return R_RIGHT, "right"
    if g == "abstain":
        return R_LAZY, "lazy_abstain"
    return R_WRONG, "wrong"
