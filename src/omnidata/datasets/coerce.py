"""Forgiving-but-strict value parsers (pt-BR and en). Return None for empty; raise ValueError with a user-facing message otherwise."""
from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from .spec import LOST_RE, STAGE_RANKS, STATUS_WORDS, WON_RE, norm

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
_THOUSANDS_EN = re.compile(r"^\d{1,3}(,\d{3})+$")
_THOUSANDS_PT = re.compile(r"^\d{1,3}(\.\d{3})+$")


def parse_amount(v: str) -> Decimal | None:
    s = re.sub(r"(?i)r\$|us\$|\$|€|\s", "", v.strip())
    if not s:
        return None
    neg = s.startswith("-") or (s.startswith("(") and s.endswith(")"))
    s = s.strip("-()")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", "") if _THOUSANDS_EN.match(s) else s.replace(",", ".")
    elif "." in s and _THOUSANDS_PT.match(s):
        s = s.replace(".", "")
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError(f"valor numérico inválido: “{v}”") from None
    if neg or d < 0:
        raise ValueError("valor negativo não é aceito")
    if d > Decimal("1e13"):
        raise ValueError("valor grande demais")
    return d.quantize(Decimal("0.01"))


_DATE_FORMATS = ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M",
                 "%d/%m/%Y", "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d-%m-%Y")


def parse_datetime(v: str) -> datetime | None:
    s = v.strip()
    if not s:
        return None
    if s.endswith("Z") or re.search(r"[+-]\d{2}:?\d{2}$", s):
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            pass
    s = re.sub(r"\.\d+$", "", s)
    for f in _DATE_FORMATS:
        try:
            return datetime.strptime(s, f).replace(tzinfo=LOCAL_TZ).astimezone(UTC)  # naive = São Paulo local time
        except ValueError:
            continue
    raise ValueError(f"data inválida: “{v}” (use AAAA-MM-DD ou DD/MM/AAAA)")


def classify_stage(label: str) -> str:
    n = norm(label)
    if WON_RE.search(n):
        return "won"
    if LOST_RE.search(n):
        return "lost"
    return "open"


def parse_status(v: str) -> str | None:
    s = norm(v)
    if not s:
        return None
    if s in STATUS_WORDS:
        return STATUS_WORDS[s]
    raise ValueError(f"status inválido: “{v}” (use aberto, ganho ou perdido)")


def stage_rank(label: str) -> int:
    n = norm(label)
    for pat, rank in STAGE_RANKS:
        if re.search(pat, n):
            return rank
    return 50


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", norm(s)).strip("-") or "sem-nome"
