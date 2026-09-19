"""Number guard (§11.3): every number in the narration must appear in the tool JSON, else fall back to a template."""
from __future__ import annotations

import json
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

# 1.234,56 | 1234.5 | 12,5% | R$ 9.000 | 3,2x
_NUM = re.compile(r"\d[\d.,]*")


def _parse(tok: str) -> Decimal | None:
    tok = tok.rstrip(".,")
    if "," in tok:
        tok = tok.replace(".", "").replace(",", ".")
    elif tok.count(".") > 1 or re.fullmatch(r"\d{1,3}(\.\d{3})+", tok):
        tok = tok.replace(".", "")  # pt-BR thousands
    try:
        return Decimal(tok)
    except InvalidOperation:
        return None


def _collect(obj: Any, out: set[Decimal]) -> None:
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, (int, float, Decimal)):
        out.add(Decimal(str(obj)))
    elif isinstance(obj, str):
        for tok in _NUM.findall(obj):
            v = _parse(tok)
            if v is not None:
                out.add(v)
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collect(v, out)


def _rounded(a: Decimal, places: int) -> Decimal:
    return a.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def _matches(v: Decimal, allowed: set[Decimal]) -> bool:
    """Exact, or equal to an allowed value rounded to 0-2 places, or its percentage form (0.583 -> 58,3)."""
    for a in allowed:
        candidates = [a, *(_rounded(a, p) for p in (0, 1, 2))]
        if abs(a) <= 1:
            candidates += [_rounded(a * 100, p) for p in (0, 1, 2)]
        if any(v == c for c in candidates):
            return True
    return False


def numbers_ok(narration: str, tool_json: Any) -> bool:
    """True iff every numeric token in `narration` is present (after normalization) in `tool_json`."""
    allowed: set[Decimal] = set()
    _collect(tool_json if not isinstance(tool_json, str) else json.loads(tool_json), allowed)
    for tok in _NUM.findall(narration):
        v = _parse(tok)
        if v is None:
            continue
        if not _matches(v, allowed):
            return False
    return True
