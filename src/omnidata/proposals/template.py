"""Proposal HTML (Vela): Jinja2 over the Ledger-styled template in templates/proposal.html. Every value here is
already known (deal name, amount, seller, free-text scope) — the LLM never fills this in directly, only chooses the
tool args upstream (bot/tools/catalog.py::SendProposal), same boundary as every other narrated number in this app."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_ENV = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"), autoescape=select_autoescape())
VALIDITY_DAYS = 15


def render_html(deal_name: str, amount_brl: str, summary: str, seller_name: str, company_name: str = "OmniData",
                today: date | None = None) -> str:
    d = today or date.today()
    tpl = _ENV.get_template("proposal.html")
    return tpl.render(deal_name=deal_name, amount=amount_brl, summary=summary, seller_name=seller_name,
                       company_name=company_name, date=d.strftime("%d/%m/%Y"),
                       valid_until=(d + timedelta(days=VALIDITY_DAYS)).strftime("%d/%m/%Y"))
