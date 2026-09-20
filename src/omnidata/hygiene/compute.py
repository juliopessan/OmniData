"""Fix queue: which open deals have which data gaps, and who should fix them. Pure functions, no I/O, no LLM.
The Coach only reads this; a fix is registered by Lyra (with confirmation), never by the Coach."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from ..datasets.spec import norm
from . import spec

_DEMAND = re.compile(r"\[[^\[\]]+\]\s*$|\s[–—-]\s\S")


@dataclass
class Deal:
    id: str
    name: str
    amount: Decimal | float | None = None
    owner: str | None = None
    owner_active: bool | None = None      # None = unknown (not reported by the source)
    close_date: date | datetime | None = None
    next_activity: date | datetime | None = None
    notes: int = 0


def _day(d: date | datetime | None) -> date | None:
    return d.date() if isinstance(d, datetime) else d


def _amt(d: Deal) -> float:
    return float(d.amount or 0)


def name_ok(name: str) -> bool:
    n = name.strip()
    return n.count("[") == n.count("]") and bool(_DEMAND.search(n))


def _key(name: str) -> str:
    return re.sub(r"\W+", "", norm(name))


def issues_of(d: Deal, today: date, dup: set[str]) -> list[str]:
    found = []
    if not _amt(d):
        found.append("no_amount")
    cd = _day(d.close_date)
    if cd is not None and cd < today:
        found.append("close_date_past")
    if d.next_activity is None:
        found.append("no_next_step")
    if not d.notes:
        found.append("no_notes")
    if not name_ok(d.name):
        found.append("name_format")
    if d.owner_active is False:
        found.append("owner_inactive")
    if d.id in dup:
        found.append("duplicate")
    return found


def fix_queue(deals: list[Deal], today: date, *, is_manager: bool, limit: int = 8) -> dict[str, Any]:
    """`deals` are OPEN deals the caller may see. Managers also get the items only a manager can settle."""
    groups: dict[str, list[str]] = defaultdict(list)
    for d in deals:
        groups[_key(d.name)].append(d.id)
    dup = {i for ids in groups.values() if len(ids) > 1 for i in ids}
    per: dict[str, list[str]] = {d.id: issues_of(d, today, dup) for d in deals}
    n = len(deals)
    counts = Counter(c for v in per.values() for c in v)
    issues = [{"code": c, "label": spec.ISSUES[c]["label"], "who": spec.ISSUES[c]["who"], "deals": counts[c],
               "share": counts[c] / n if n else 0.0, "systemic": bool(n) and counts[c] / n >= spec.SYSTEMIC_SHARE}
              for c in spec.ISSUES if counts[c]]
    systemic = {i["code"] for i in issues if i["systemic"]}
    mine = {c for c, v in spec.ISSUES.items() if v["who"] == "seller"}
    # Per-deal queue: gaps the seller can fix. A gap on ~everything is more likely a source problem than a habit, so it is dropped
    # for deals without value (bulk noise) but kept for deals with value (few, and the ones that matter).
    rows = []
    for d in deals:
        fixable = [c for c in per[d.id] if c in mine and (c not in systemic or _amt(d) > 0)]
        if fixable:
            rows.append((d, fixable))
    rows.sort(key=lambda r: (-_amt(r[0]), -len(r[1]), r[0].name))
    queue = [{"id": d.id, "name": d.name, "amount": _amt(d), "issues": fx,
              "first_fix": spec.ISSUES[fx[0]]["how"], "tool": spec.ISSUES[fx[0]]["tool"]} for d, fx in rows[:limit]]
    out: dict[str, Any] = {"open_deals": n, "clean": sum(1 for v in per.values() if not v), "issues": issues, "systemic": sorted(systemic),
                           "queue": queue, "queue_total": len(rows), "with_amount": sum(1 for d in deals if _amt(d))}
    if is_manager:
        out["manager"] = {"owner_inactive": [{"id": d.id, "name": d.name, "owner": d.owner} for d in deals if "owner_inactive" in per[d.id]][:limit],
                          "duplicates": [{"name": next(d.name for d in deals if d.id == ids[0]), "deals": len(ids)}
                                         for ids in groups.values() if len(ids) > 1][:limit]}
    return out
