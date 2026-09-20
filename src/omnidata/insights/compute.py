"""Company insights from deals + their notes. Pure functions, no I/O, no LLM: every number is a count over the records.
Heuristics are explicit and listed in spec.py; each section reports coverage so a reader can judge how far to trust it."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from ..datasets.spec import norm
from . import spec

MIN_N = 20  # below this many closed deals (or pain mentions) a ranking is only indicative (MIN_N_RANKING)


@dataclass
class Rec:
    """One deal as seen by the insights engine."""
    id: str
    name: str
    status: str                      # open | won | lost
    amount: Decimal | float | None = None
    campaign: str | None = None
    lost_reason: str | None = None
    notes: list[str] = field(default_factory=list)


_SYS_RES = {k: [re.compile(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])") for a in aliases] for k, (_, aliases) in spec.SYSTEMS.items()}
_PAIN_RE = re.compile(spec.PAIN_LABELS, re.IGNORECASE)
_CUE_RES = [re.compile(c, re.IGNORECASE) for c in spec.PAIN_CUES]
_ROLE_RES = {k: re.compile(p, re.IGNORECASE) for k, p in spec.ROLE_PATTERNS.items()}
_WORD = re.compile(r"[a-zà-ú]+")
_SENT = re.compile(r"[.;:!?|\n]+")
_MENTION = re.compile(spec.MENTION)


def _amt(r: Rec) -> float:
    return float(r.amount or 0)


def _rate(won: int, lost: int) -> float | None:
    return (won / (won + lost)) if (won + lost) else None


def group_stats(recs: Iterable[Rec], key: Callable[[Rec], str | None]) -> list[dict[str, Any]]:
    g: dict[str, list[Rec]] = defaultdict(list)
    for r in recs:
        k = key(r)
        if k:
            g[k].append(r)
    out: list[dict[str, Any]] = []
    for k, rs in g.items():
        won = sum(1 for r in rs if r.status == "won")
        lost = sum(1 for r in rs if r.status == "lost")
        out.append({"key": k, "deals": len(rs), "open": sum(1 for r in rs if r.status == "open"), "won": won, "lost": lost,
                    "closed": won + lost, "win_rate": _rate(won, lost), "low_n": (won + lost) < MIN_N,
                    "open_amount": sum(_amt(r) for r in rs if r.status == "open"), "won_amount": sum(_amt(r) for r in rs if r.status == "won")})
    return sorted(out, key=lambda x: (-x["deals"], x["key"]))


# ---------- extractors ----------
def pains_of(r: Rec) -> list[str]:
    """Pains written in a note. Labelled ("Dor validada: X") first; cue phrases only for notes without a label."""
    found: list[str] = []
    for n in r.notes:
        m = _PAIN_RE.search(n)
        if m:
            found.append(m.group(1).strip().rstrip("."))
            continue
        for rx in _CUE_RES:
            cm = rx.search(n)
            if cm:
                found.append(cm.group(1).strip().rstrip("."))
                break
    return found


def systems_of(r: Rec) -> dict[str, set[str]]:
    """system -> roles ('mention', 'won_against', 'internal') found in the deal's notes and loss reason."""
    texts = [*r.notes, *([r.lost_reason] if r.lost_reason else [])]
    out: dict[str, set[str]] = defaultdict(set)
    for t in texts:
        n = norm(t)
        for name, rxs in _SYS_RES.items():
            if any(rx.search(n) for rx in rxs):
                out[name].add("mention")
        for role, rx in _ROLE_RES.items():
            m = rx.search(t)
            if m:
                n2 = norm(m.group(1))
                for name, rxs in _SYS_RES.items():
                    if any(rx2.search(n2) for rx2 in rxs):
                        out[name].add(role)
    return out


_BRACKET = re.compile(spec.DEMAND_BRACKET)
_CO_SPLIT = re.compile(spec.COMPANY_SPLIT)


def demand_type(name: str) -> str | None:
    m = _BRACKET.search(name.strip())
    if m and m.group(1).strip():
        return m.group(1).strip()
    parts = re.split(spec.DEMAND_SPLIT, name.strip())
    return parts[-1].strip() if len(parts) >= 2 and parts[-1].strip() else None


def company(name: str) -> str | None:
    n = name.strip()
    if "<>" in n:
        return _CO_SPLIT.split(n)[0].strip() or None
    parts = re.split(spec.DEMAND_SPLIT, n)
    return parts[0].strip() if len(parts) >= 2 else None


def classify_loss(reason: str) -> tuple[str, str]:
    n = norm(reason)
    for code, label, kws in spec.LOSS_TAXONOMY:
        if any(k in n for k in kws):
            return code, label
    return "other", "Outro"


def _sentences(text: str) -> list[list[tuple[str, str]]]:
    """Words of each sentence as (accent-free key, original). Bigrams never cross punctuation or dropped short words."""
    return [[(norm(w), w) for w in _WORD.findall(sent.lower())] for sent in _SENT.split(_MENTION.sub(" ", text)) if sent.strip()]


def _keep(k: str, w: str) -> bool:
    return len(w) >= 4 and k not in spec.STOPWORDS


def terms(recs: list[Rec], limit: int = 10) -> dict[str, list[dict[str, Any]]]:
    """Recurring words and two-word phrases, counted by number of DEALS that mention them (not raw repetitions)."""
    uni: dict[str, set[int]] = defaultdict(set)
    bi: dict[str, set[int]] = defaultdict(set)
    disp: dict[str, str] = {}
    for i, r in enumerate(recs):
        for note in r.notes:
            for toks in _sentences(note):
                for k, w in toks:
                    if _keep(k, w):
                        uni[k].add(i)
                        disp.setdefault(k, w)
                for (k1, w1), (k2, w2) in zip(toks, toks[1:], strict=False):
                    if _keep(k1, w1) and _keep(k2, w2):
                        key = f"{k1} {k2}"
                        bi[key].add(i)
                        disp.setdefault(key, f"{w1} {w2}")

    def rank(d: dict[str, set[int]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for k, idx in d.items():
            if len(idx) < 3:
                continue
            won = sum(1 for i in idx if recs[i].status == "won")
            lost = sum(1 for i in idx if recs[i].status == "lost")
            rows.append({"term": disp[k], "deals": len(idx), "won": won, "lost": lost, "win_rate": _rate(won, lost) if won + lost >= 10 else None})
        return sorted(rows, key=lambda x: (-x["deals"], x["term"]))[:limit]
    return {"words": rank(uni), "phrases": rank(bi)}


# ---------- the analysis ----------
def analyze(recs: list[Rec], limit: int = 10) -> dict[str, Any]:
    n = len(recs)
    pain_by: dict[str, list[Rec]] = defaultdict(list)
    pain_disp: dict[str, str] = {}
    for r in recs:
        for p in {norm(x): x for x in pains_of(r)}.items():
            pain_by[p[0]].append(r)
            pain_disp.setdefault(p[0], p[1])
    with_pain = len({r.id for rs in pain_by.values() for r in rs})
    pains: list[dict[str, Any]] = []
    for k, rs in pain_by.items():
        won, lost = sum(1 for r in rs if r.status == "won"), sum(1 for r in rs if r.status == "lost")
        pains.append({"pain": pain_disp[k], "deals": len(rs), "share": len(rs) / with_pain if with_pain else 0.0,
                      "closed": won + lost, "win_rate": _rate(won, lost) if won + lost >= 10 else None})
    pains.sort(key=lambda x: (-x["deals"], x["pain"]))

    sys_by: dict[str, dict[str, list[Rec]]] = defaultdict(lambda: defaultdict(list))
    for r in recs:
        for sname, found_roles in systems_of(r).items():
            sys_by[sname]["mention"].append(r)
            for role in found_roles - {"mention"}:
                sys_by[sname][role].append(r)
    systems: list[dict[str, Any]] = []
    for s, roles in sys_by.items():
        ms = roles["mention"]
        won, lost = sum(1 for r in ms if r.status == "won"), sum(1 for r in ms if r.status == "lost")
        systems.append({"system": s, "category": spec.SYSTEMS[s][0], "deals": len(ms), "won_against": len(roles["won_against"]),
                        "internal": len(roles["internal"]), "closed": won + lost, "win_rate": _rate(won, lost) if won + lost >= 10 else None})
    systems.sort(key=lambda x: (-x["deals"], x["system"]))

    demand = group_stats(recs, lambda r: demand_type(r.name))
    seg_counts = Counter((company(r.name) or "").split(" ")[-1] for r in recs if company(r.name))
    seg_ok = {w for w, c in seg_counts.items() if c >= spec.MIN_SEGMENT_DEALS and w.isalpha()}
    segments = group_stats(recs, lambda r: (company(r.name) or "").split(" ")[-1] if (company(r.name) or "").split(" ")[-1] in seg_ok else None)
    campaigns = group_stats(recs, lambda r: r.campaign)
    lost_recs = [r for r in recs if r.status == "lost" and r.lost_reason]
    taxo = Counter(classify_loss(r.lost_reason or "") for r in lost_recs)
    raw_reasons = Counter(r.lost_reason for r in lost_recs)
    n_lost = sum(1 for r in recs if r.status == "lost")

    def cov(k: int, base: int) -> float | None:
        return (k / base) if base else None
    coverage = {
        "deals": n, "with_notes": cov(sum(1 for r in recs if r.notes), n), "with_pain": cov(with_pain, n),
        "with_system": cov(sum(1 for r in recs if systems_of(r)), n), "with_demand_type": cov(sum(1 for r in recs if demand_type(r.name)), n),
        "with_segment": cov(sum(1 for r in recs if r.id and (company(r.name) or "").split(" ")[-1] in seg_ok), n),
        "with_campaign": cov(sum(1 for r in recs if r.campaign), n), "lost_with_reason": cov(len(lost_recs), n_lost), "lost": n_lost,
    }
    return {
        "coverage": coverage,
        "pains": {"with_pain": with_pain, "items": pains[:limit], "low_n": with_pain < MIN_N},
        "terms": terms(recs, limit),
        "demand_types": {"items": demand[:limit], "total": len(demand)},
        "systems": {"items": systems[:limit * 2], "erp": [s for s in systems if s["category"] == "erp"][:limit],
                    "crm": [s for s in systems if s["category"] == "crm"][:limit]},
        "segments": {"items": segments[:limit]}, "campaigns": {"items": campaigns[:limit]},
        "loss_reasons": {"raw": [{"reason": k, "deals": v} for k, v in raw_reasons.most_common(limit)],
                         "taxonomy": [{"code": c, "label": lbl, "deals": v} for (c, lbl), v in taxo.most_common()], "lost": n_lost},
    }
