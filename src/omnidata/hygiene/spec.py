"""What "clean CRM data" means for an open deal, in one place (shared with the web UI via `omnidata hygiene spec`).
Nothing here is a model judgement: each issue is a yes/no test on a field."""
from __future__ import annotations

# code -> (label, who fixes it, the tool that can register the fix, how to fix). Order = priority when ranking.
ISSUES: dict[str, dict[str, str]] = {
    "no_amount": {"label": "Sem valor", "who": "seller", "tool": "propose_deal_update", "how": "informar o valor estimado"},
    "close_date_past": {"label": "Data de fechamento vencida", "who": "seller", "tool": "propose_deal_update", "how": "reagendar a data de fechamento"},
    "no_next_step": {"label": "Sem próximo passo", "who": "seller", "tool": "create_task", "how": "criar uma tarefa com data"},
    "no_notes": {"label": "Sem nota", "who": "seller", "tool": "add_note", "how": "registrar o que foi combinado"},
    "name_format": {"label": "Nome fora do padrão", "who": "seller", "tool": "", "how": "corrigir o nome no HubSpot (Cliente<>Parceiro [Demanda])"},
    "owner_inactive": {"label": "Dono desativado", "who": "manager", "tool": "", "how": "redistribuir o negócio"},
    "duplicate": {"label": "Possível duplicata", "who": "manager", "tool": "", "how": "conferir e mesclar ou arquivar"},
}
# An issue present in at least this share of open deals is more likely the export or a CRM default than a habit of the seller.
SYSTEMIC_SHARE = 0.9
SPEC_VERSION = 1


def spec_json() -> dict[str, object]:
    return {"issues": [{"code": c, **v} for c, v in ISSUES.items()], "systemicShare": SYSTEMIC_SHARE}
