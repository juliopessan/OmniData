"""Proposal HTML (Vela): Jinja2 over the Ledger-styled template in templates/proposal.html. Every value here is
already known (deal name, amount, seller, free-text scope) — the LLM never fills this in directly, only chooses the
tool args upstream (bot/tools/catalog.py::SendProposal), same boundary as every other narrated number in this app.

The deal name is a CRM label, not something to show a client as-is ("Uniconte [Tax Partner_Licenciamento]"): the
client and the scope front come from the same parser the insights use (insights/compute.py), so a proposal never
carries a pipeline tag in its title."""
from __future__ import annotations

import base64
import re
import unicodedata
from datetime import date, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..insights.compute import company, demand_type

_ENV = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"), autoescape=select_autoescape())
VALIDITY_DAYS = 15
_BULLET = re.compile(r"^\s*[-•*·–—]\s+")
_NOISE = re.compile(r"\bnovo\(a\) deal\b", re.IGNORECASE)


def client_name(deal_name: str) -> str:
    """"Uniconte [Tax Partner_Licenciamento]" -> "Uniconte"; "SOS Reforma<>FIND [x]" -> "SOS Reforma"."""
    base = company(deal_name) or re.sub(r"\[[^\]]*\]?\s*$", "", deal_name)
    base = _NOISE.sub("", base)
    return base.strip(" -–—<>·") or deal_name.strip()


def scope_front(deal_name: str) -> str | None:
    """The bracketed/trailing demand ("Tax Partner_Licenciamento" -> "Tax Partner Licenciamento"), if there is one."""
    d = demand_type(deal_name)
    if not d or _NOISE.search(d):
        return None
    return re.sub(r"[_\s]+", " ", d).strip() or None


def scope_blocks(summary: str) -> tuple[list[str], list[str]]:
    """Free text -> (paragraphs, bullet items). A line starting with -, •, * or · is an item; everything else prose."""
    paras: list[str] = []
    items: list[str] = []
    for line in (ln.strip() for ln in summary.splitlines()):
        if not line:
            continue
        if _BULLET.match(line):
            items.append(_BULLET.sub("", line))
        else:
            paras.append(line)
    return paras, items


def valid_until(today: date | None = None) -> str:
    return ((today or date.today()) + timedelta(days=VALIDITY_DAYS)).strftime("%d/%m/%Y")


def file_slug(deal_name: str) -> str:
    """"Uniconte [Tax Partner_Licenciamento]" -> "uniconte" (the client sees this filename)."""
    s = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", client_name(deal_name)).encode("ascii", "ignore").decode().lower())
    return s.strip("-") or "proposta"


def brl_full(v: float) -> str:
    """R$ 5.000,00 — a proposal states the exact amount, cents included (the chat's S.brl rounds for readability)."""
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


_MIME = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def logo_data_uri(path: str) -> str | None:
    """PROPOSAL_LOGO (a file on disk) as a data: URI, so the PDF never depends on base_url resolving it. Missing or
    unsupported file -> None, and the header falls back to the monogram + wordmark instead of a broken image."""
    if not path:
        return None
    p = Path(path)
    mime = _MIME.get(p.suffix.lower())
    if not mime or not p.is_file():
        return None
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"


def render_html(deal_name: str, amount: float, summary: str, seller_name: str, company_name: str = "OmniData",
                today: date | None = None, logo_path: str = "", ref: str = "") -> str:
    d = today or date.today()
    paras, items = scope_blocks(summary)
    tpl = _ENV.get_template("proposal.html")
    return tpl.render(client=client_name(deal_name), front=scope_front(deal_name), amount=brl_full(amount),
                      paras=paras, items=items, seller_name=seller_name, company_name=company_name,
                      initial=(company_name.strip()[:1] or "·").upper(), logo=logo_data_uri(logo_path),
                      date=d.strftime("%d/%m/%Y"), valid_until=valid_until(d),
                      validity_days=VALIDITY_DAYS, ref=ref)
