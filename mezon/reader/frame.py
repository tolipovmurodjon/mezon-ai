"""Read a clause the way a lawyer does: who must/may/must-not do what, by when, under what sanction, at what cost."""

from dataclasses import asdict, dataclass

from mezon import llm
from research.textnorm import fold

MODALITIES = {"obligation", "permission", "prohibition", "definition", "repeal", "other"}

SYSTEM = (
    "You are a meticulous Uzbek legal analyst. Read ONE clause of a local government decision and list every norm in it. "
    "Return JSON {\"frames\": [...]} where each frame has: who (the addressee), modality (obligation | permission | "
    "prohibition | definition | repeal | other), action, deadline, condition, exception, sanction, money (amounts, fees, "
    "tariffs), affects_business (true only if the norm adds a duty, cost, fee, restriction or liability for businesses), "
    "and quote: the exact words from the clause that state this norm, copied character for character. "
    "Use only words that are in the clause. If something is not stated, use an empty string. Never add law from memory."
)


@dataclass
class Frame:
    who: str
    modality: str
    action: str
    deadline: str
    condition: str
    exception: str
    sanction: str
    money: str
    affects_business: bool
    quote: str


def _valid(raw: dict, clause: str) -> Frame | None:
    quote = str(raw.get("quote", "")).strip()
    if raw.get("modality") not in MODALITIES or len(quote) < 8 or fold(quote) not in fold(clause):
        return None
    return Frame(
        who=str(raw.get("who", "")), modality=raw["modality"], action=str(raw.get("action", "")),
        deadline=str(raw.get("deadline", "")), condition=str(raw.get("condition", "")),
        exception=str(raw.get("exception", "")), sanction=str(raw.get("sanction", "")),
        money=str(raw.get("money", "")), affects_business=raw.get("affects_business") is True, quote=quote,
    )


def read_clause(clause: str) -> tuple[list[Frame], int]:
    """Frames the model proposed AND grounded in a verbatim quote, plus how many proposals were dropped."""
    out = llm.chat_json(SYSTEM, clause)
    proposed = out.get("frames", []) if isinstance(out, dict) else []
    frames = [f for f in (_valid(r, clause) for r in proposed if isinstance(r, dict)) if f]
    return frames, len(proposed) - len(frames)


__all__ = ["Frame", "asdict", "read_clause"]
