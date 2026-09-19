"""Map headers onto a canonical kind, then validate and normalise every row. Pure: no database access."""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any

from . import coerce
from .parse import Table
from .spec import Kind, norm

MAX_ERRORS = 200
_LOSS_NOTE = re.compile(r"^\s*motivo (?:da|de) perda:\s*(.+?)\.?\s*$", re.IGNORECASE)


@dataclass
class RowError:
    line: int
    column: str
    message: str


@dataclass
class Report:
    kind: str
    filename: str
    sha256: str
    size_bytes: int
    encoding: str
    delimiter: str | None
    total_rows: int = 0
    valid_rows: int = 0
    error_count: int = 0
    errors: list[RowError] = field(default_factory=list)
    mapping: dict[str, str] = field(default_factory=dict)          # canonical column -> your header
    ignored_columns: list[str] = field(default_factory=list)       # headers we do not know: never imported
    unstored_columns: list[str] = field(default_factory=list)      # known but deliberately not imported
    missing_required: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stage_order: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.missing_required and self.error_count == 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["ok"] = self.ok
        return d


def _add(rep: Report, line: int, col: str, msg: str) -> None:
    rep.error_count += 1
    if len(rep.errors) < MAX_ERRORS:
        rep.errors.append(RowError(line, col, msg))


def map_headers(kind: Kind, headers: list[str], rep: Report) -> dict[str, int]:
    """canonical name -> column index. First match wins; unknown headers are reported and never read."""
    amap = kind.alias_map()
    idx: dict[str, int] = {}
    for i, h in enumerate(headers):
        canon = amap.get(norm(h))
        if canon is None:
            if h:
                rep.ignored_columns.append(h)
        elif canon in idx:
            rep.warnings.append(f"coluna repetida para “{canon}”: uso “{headers[idx[canon]]}” e ignoro “{h}”")
        else:
            idx[canon] = i
    stored = {c.name: c for c in kind.columns}
    for name, i in idx.items():
        rep.mapping[name] = headers[i]
        if not stored[name].stored:
            rep.unstored_columns.append(headers[i])
    rep.missing_required = [c.name for c in kind.columns if c.required and c.name not in idx]
    return idx


def _split(v: str, sep: str) -> list[str]:
    return [p.strip() for p in v.split(sep) if p.strip()]


def _validate_deals(t: Table, idx: dict[str, int], rep: Report, stage_order: list[str] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    ids_misaligned = 0
    first_seen: dict[str, int] = {}
    counts = {"open": 0, "won": 0, "lost": 0}
    reasons = 0
    owners: set[str] = set()

    def col(row: list[str], name: str) -> str:
        return row[idx[name]] if name in idx else ""

    for row, line in zip(t.rows, t.lines, strict=True):
        n0 = rep.error_count
        rid, name, stage = col(row, "id"), col(row, "name"), col(row, "stage")
        for cname, val, limit in (("id", rid, 64), ("name", name, 300), ("stage", stage, 120)):
            if not val:
                _add(rep, line, rep.mapping.get(cname, cname), "campo obrigatório vazio")
            elif len(val) > limit:
                _add(rep, line, rep.mapping[cname], f"texto longo demais (máximo {limit})")
        if rid and rid in seen:
            _add(rep, line, rep.mapping["id"], f"id repetido: {rid}")
        seen.add(rid)

        def parse(cname: str, fn: Any, _row: list[str] = row, _line: int = line) -> Any:
            try:
                return fn(col(_row, cname))
            except ValueError as e:
                _add(rep, _line, rep.mapping[cname], str(e))
                return None
        amount = parse("amount", coerce.parse_amount) if "amount" in idx else None
        close = parse("close_date", coerce.parse_datetime) if "close_date" in idx else None
        created = parse("created_at", coerce.parse_datetime) if "created_at" in idx else None
        nxt = parse("next_activity", coerce.parse_datetime) if "next_activity" in idx else None
        status = parse("status", coerce.parse_status) if "status" in idx else None
        status = status or (coerce.classify_stage(stage) if stage else "open")
        if status in ("won", "lost") and close is None and "close_date" in idx and not col(row, "close_date"):
            _add(rep, line, rep.mapping["close_date"], "negócio fechado sem data de fechamento")
        if status in ("won", "lost") and "close_date" not in idx:
            _add(rep, line, "close_date", "negócio fechado, mas o arquivo não tem coluna de data de fechamento")
        notes = _split(col(row, "notes"), " | ") if "notes" in idx else []
        note_ids = [x for x in re.split(r"[;,]", col(row, "note_ids")) if x.strip()] if "note_ids" in idx else []
        note_ids = [x.strip() for x in note_ids]
        if note_ids and len(note_ids) != len(notes):
            ids_misaligned += 1
            note_ids = []
        reason = col(row, "lost_reason") or None
        if status == "lost" and not reason:
            for seg in notes:
                m = _LOSS_NOTE.match(seg)
                if m:
                    reason = m.group(1).strip()
                    break
        if status != "lost":
            reason = None
        if status == "lost" and reason:
            reasons += 1
        owner = col(row, "owner") or None
        if owner:
            owners.add(owner)
        if stage and status == "open":
            first_seen.setdefault(stage, len(first_seen))
        if rep.error_count == n0:
            counts[status] += 1
            out.append({"id": rid, "name": name, "stage": stage, "status": status, "amount": amount, "close_date": close,
                        "created_at": created, "owner": owner, "next_activity": nxt, "lost_reason": reason,
                        "notes": notes, "note_ids": note_ids, "campaign": col(row, "campaign") or None, "_line": line})
    if ids_misaligned:
        rep.warnings.append(f"{ids_misaligned} linha(s) com quantidade de IDs de notas diferente da de notas: IDs ignorados nessas linhas")
    missing_amount = sum(1 for r in out if r["amount"] is None)
    if missing_amount:
        rep.warnings.append(f"{missing_amount} negócio(s) sem valor: entram com valor vazio")
    if counts["lost"] and reasons < counts["lost"]:
        rep.warnings.append(f"{counts['lost'] - reasons} negócio(s) perdido(s) sem motivo identificável")
    rep.stage_order = _order_stages(list(first_seen), stage_order, rep)
    rep.summary = {**counts, "owners": len(owners), "open_stages": len(rep.stage_order),
                   "lost_with_reason": reasons, "lost_reason_coverage": (reasons / counts["lost"]) if counts["lost"] else None}
    return out


def _order_stages(found: list[str], requested: list[str] | None, rep: Report) -> list[str]:
    ordered: list[str] = []
    if requested:
        lookup = {norm(s): s for s in found}
        for r in requested:
            s = lookup.get(norm(r))
            if s and s not in ordered:
                ordered.append(s)
            elif not s:
                rep.warnings.append(f"etapa “{r}” de stage_order não existe no arquivo: ignorada")
    rest = [s for s in found if s not in ordered]
    rest.sort(key=lambda s: (coerce.stage_rank(s), found.index(s)))
    return ordered + rest


def _validate_quotas(t: Table, idx: dict[str, int], rep: Report) -> list[dict[str, Any]]:
    out, seen = [], set()
    for row, line in zip(t.rows, t.lines, strict=True):
        n0 = rep.error_count
        owner = row[idx["owner"]]
        if not owner:
            _add(rep, line, rep.mapping["owner"], "campo obrigatório vazio")
        vals: dict[str, Any] = {}
        for c, fn in (("period_start", coerce.parse_datetime), ("period_end", coerce.parse_datetime), ("amount", coerce.parse_amount)):
            try:
                vals[c] = fn(row[idx[c]])
                if vals[c] is None:
                    raise ValueError("campo obrigatório vazio")
            except ValueError as e:
                _add(rep, line, rep.mapping[c], str(e))
        if rep.error_count == n0:
            ps = vals["period_start"].astimezone(coerce.LOCAL_TZ).date()
            pe = vals["period_end"].astimezone(coerce.LOCAL_TZ).date()
            if pe < ps:
                _add(rep, line, rep.mapping["period_end"], "o fim do período é anterior ao início")
            elif (owner, ps, pe) in seen:
                _add(rep, line, rep.mapping["owner"], "meta repetida para o mesmo vendedor e período")
            else:
                seen.add((owner, ps, pe))
                out.append({"owner": owner, "period_start": ps, "period_end": pe, "amount": vals["amount"], "_line": line})
    rep.summary = {"rows": len(out), "owners": len({r["owner"] for r in out}),
                   "total_amount": str(sum((r["amount"] for r in out), Decimal(0)))}
    return out


def validate(kind: Kind, table: Table, filename: str, data: bytes, *, stage_order: list[str] | None = None) -> tuple[Report, list[dict[str, Any]]]:
    rep = Report(kind.key, filename, hashlib.sha256(data).hexdigest(), len(data), table.encoding, table.delimiter,
                 total_rows=len(table.rows))
    idx = map_headers(kind, table.headers, rep)
    if rep.missing_required:
        return rep, []
    rows = _validate_deals(table, idx, rep, stage_order) if kind.key == "deals" else _validate_quotas(table, idx, rep)
    rep.valid_rows = len(rows)
    return rep, rows

