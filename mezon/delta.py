"""What changed in the law after the model's training cutoff (Boss's design, 21 Nov 2026).

    from mezon.delta import changed_since
    changed_since(law, "2026-11-22")                      # every act with a new edition after the cutoff
    changed_since(law, "2026-11-22", acts=["nla", "lsp"])  # only the acts a question touches

The model answers from its own knowledge of the law up to its cutoff. Before it answers, the system (not the model)
runs this one cheap query: if none of the acts the question touches has an edition that started after the cutoff,
no tool call is needed; if one has, only that new wording goes into the context. Not a model tool, so the frozen
exam's tool list is unchanged.
"""

from datetime import date

from mezon.lawstore.store import LawStore, iso


def changed_since(law: LawStore, cutoff: str | date, acts: list[str] | None = None, until: str | date | None = None) -> list[dict]:
    """Editions that started after `cutoff` (and on or before `until`, default: no limit), newest first."""
    sql = ("SELECT e.act_key, a.title, a.number, e.valid_from FROM editions e JOIN acts a ON a.act_key = e.act_key "
           "WHERE e.valid_from > ?")
    args: list = [iso(cutoff)]
    if until is not None:
        sql += " AND e.valid_from <= ?"
        args.append(iso(until))
    if acts:
        sql += f" AND e.act_key IN ({','.join('?' * len(acts))})"
        args += list(acts)
    sql += " ORDER BY e.valid_from DESC"
    return [dict(r) for r in law.con.execute(sql, args)]


def needs_lookup(law: LawStore, cutoff: str | date, acts: list[str]) -> bool:
    """True when any act the question touches changed after the cutoff: then (and only then) fetch the new wording."""
    return bool(changed_since(law, cutoff, acts))
