"""ALL bot-facing text lives here (D16). Templates for deterministic fallbacks are here too."""
from __future__ import annotations

from typing import Any

REFUSAL_UNKNOWN = "Não consegui identificar este número. Fale com o administrador da sua conta para receber o convite."
OUT_OF_SCOPE = "Eu cuido só do seu trabalho de vendas: meta, negócios, notas e tarefas. Posso ajudar com algum deles?"
NOT_CONFIRMED = "Não consegui confirmar esse número agora. Tento de novo em alguns minutos?"
RATE_LIMITED = "Muitas mensagens em pouco tempo. Tente de novo daqui a pouco."
MENU_TITLE = "O que você quer ver?"
MENU_BODY = "Não entendi bem. Escolha uma opção:"
LLM_DOWN_NOTE = "Estou em modo simples agora."
ONBOARDING_OK = "Tudo certo, {name}! Você já pode falar comigo. Pergunte “como estou na meta?” para começar."
ONBOARDING_ASK = "Para ativar, responda *Aceito*. Vou usar seus dados de vendas do HubSpot para ajudar você."
LOW_N = "Só tenho {n} negócios fechados no período, pouco para comparar com segurança. Prefere ver o mês anterior?"
NO_DATA = "Não encontrei dados para isso no período."
NO_MATCH_DEAL = "Não achei nenhum negócio seu parecido com “{q}”."
PICK_DEAL = "Achei mais de um negócio. Qual deles?"
HUBSPOT_DOWN = "O HubSpot não respondeu agora, então não registrei nada. Tente de novo em alguns minutos."
EXPIRED = "Essa confirmação expirou. Peça de novo se ainda quiser."
ALREADY_DONE = "Isso já foi feito."
CANCELLED = "Cancelado. Nada foi alterado."
UNDO_DONE = "Desfeito ✅"
UNDO_STALE = "Não desfiz porque o valor mudou depois: agora está *{current}*. Não sobrescrevo alterações de outras pessoas."
UNDO_EXPIRED = "O prazo de 24h para desfazer terminou."
UNDO_FAILED = "Não consegui desfazer agora. Tente de novo em alguns minutos."
SNOOZED = "Certo, não aviso sobre esse negócio por 3 dias."
NO_ATTENTION = "Nenhum negócio pede atenção agora. 👏"

BTN_CONFIRM, BTN_ADJUST, BTN_CANCEL = "Confirmar", "Ajustar", "Cancelar"
BTN_EDIT, BTN_UNDO, BTN_SEE_DAY, BTN_SEE_DEAL, BTN_SNOOZE = "Editar", "Desfazer", "Ver meu dia", "Ver deal", "Soneca 3 dias"

MENU_ROWS = [("kpis", "Meus números", "Win rate, meta e ciclo"), ("quota", "Como estou na meta", "Atingimento e gap"),
             ("pipeline", "Meu pipeline", "Por etapa"), ("attention", "Negócios p/ agir", "Os que mais pedem atenção"),
             ("brief", "Meu dia", "Resumo de hoje")]

FLAG_TEXT = {
    "stalled": "parado na etapa", "no_next_step": "sem próximo passo", "close_date_overdue": "fechamento vencido",
    "gone_quiet": "sem atividade recente", "amount_swing": "valor mudou muito",
}


def brl(v: float | int | None) -> str:
    if v is None:
        return "—"
    return "R$ " + f"{float(v):,.0f}".replace(",", ".")


def pct(v: float | None, digits: int = 1) -> str:
    return "—" if v is None else f"{float(v) * 100:.{digits}f}".replace(".", ",") + "%"


def receipt(kind: str, deal: str, detail: str) -> str:
    label = {"note": "Nota", "task": "Tarefa"}.get(kind, kind)
    return f"Registrei ✅ *{label}* em *{deal}*: “{detail}”. Você pode *Editar* ou *Desfazer* por 24h."


def confirm_update(deal: str, field: str, old: str, new: str) -> str:
    names = {"stage": "a etapa", "close_date": "a data de fechamento", "amount": "o valor"}
    return f"Alterar {names.get(field, field)} de *{deal}* de *{old}* para *{new}*?"


def tpl_kpis(d: dict[str, Any]) -> str:
    if d.get("low_n"):
        return LOW_N.format(n=d.get("n_closed", 0))
    return (f"Win rate *{pct(d.get('win_rate'))}* (IC 95%: {pct(d.get('ci_low'), 0)}–{pct(d.get('ci_high'), 0)}) "
            f"em {d.get('n_closed')} fechados. Ganho {brl(d.get('won_amount'))}; ciclo mediano {d.get('median_cycle_days') or '—'} dias.")


def tpl_quota(d: dict[str, Any]) -> str:
    if d.get("quota_amount") is None:
        return "Não tenho meta cadastrada para você neste período."
    cov = ""
    if d.get("coverage") is not None:
        cov = f" Cobertura {str(d['coverage']).replace('.', ',')}x"
        cov += f" (necessária {str(d['required_coverage']).replace('.', ',')}x)." if d.get("required_coverage") is not None else "."
    return (f"Você está em *{pct(d.get('attainment'))}* da meta de {brl(d.get('quota_amount'))}. "
            f"Ganho {brl(d.get('won_amount'))}; falta {brl(d.get('gap'))}.{cov}")


def tpl_pipeline(d: dict[str, Any]) -> str:
    rows = d.get("stages", [])
    if not rows:
        return NO_DATA
    lines = [f"• {r['stage']}: {r['count']} negócios, {brl(r['amount'])}" + (f" ({r['stalled']} parados)" if r["stalled"] else "")
             for r in rows]
    return "Seu pipeline:\n" + "\n".join(lines)


def tpl_attention(d: dict[str, Any]) -> str:
    deals = d.get("deals", [])
    if not deals:
        return NO_ATTENTION
    lines = [f"{i}. *{x['name']}* ({brl(x['amount'])}) — " + ", ".join(FLAG_TEXT.get(f, f) for f in x["flags"])
             for i, x in enumerate(deals, 1)]
    return "Negócios que pedem ação:\n" + "\n".join(lines)


def tpl_brief(d: dict[str, Any]) -> str:
    head = f"Bom dia{', ' + d['name'] if d.get('name') else ''}! "
    return head + tpl_quota(d["quota"]) + "\n\n" + tpl_attention(d["attention"])


def tpl_deal(d: dict[str, Any]) -> str:
    flags = ", ".join(FLAG_TEXT.get(f, f) for f in d["flags"]) or "sem alertas"
    return f"*{d['name']}* — {d['stage']}, {brl(d['amount'])}. {d['days_in_stage']} dias na etapa; {flags}."
