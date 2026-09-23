"""ALL bot-facing text lives here (D16). Templates for deterministic fallbacks are here too."""
from __future__ import annotations

from typing import Any

REFUSAL_UNKNOWN = "Não consegui identificar este número. Fale com o administrador da sua conta para receber o convite."
OUT_OF_SCOPE = "Eu cuido só do seu trabalho de vendas: meta, negócios, notas e tarefas. Posso ajudar com algum deles?"
NEEDS_INFO = "Claro! Só me falta o negócio e o que registrar. Manda assim: “{hint}”."
NOT_CONFIRMED = "Não consegui confirmar esse número agora. Tento de novo em alguns minutos?"
RATE_LIMITED = "Muitas mensagens em pouco tempo. Tente de novo daqui a pouco."
MENU_TITLE = "O que você quer ver?"
MENU_BODY = "Não entendi bem. Escolha uma opção:"
LLM_DOWN_NOTE = "Estou em modo simples agora."
ONBOARDING_OK = ("Oi, {name}! Orion aqui, coordenador do Observatório — sua equipe de assessores de vendas no WhatsApp. "
                  "Posso te ajudar com: meus números, como estou na meta, meu pipeline, negócios que pedem ação ou o resumo do meu dia. "
                  "É só perguntar, por exemplo “como estou na meta?”.")
ONBOARDING_ASK = ("Oi, {name}! Eu sou o Orion, do Observatório — sua equipe de assistentes de vendas aqui no WhatsApp, sem nada "
                   "para instalar ou aprender. Responda *Aceito* para eu ativar seu acesso usando seus dados de vendas do HubSpot; "
                   "depois é só escrever como numa conversa normal, por exemplo “como estou na meta?”.")
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
HEARD = "🎤 Entendi: “{t}”"
AUDIO_TOO_LONG = "Esse áudio é longo demais (máximo {max} segundos). Pode mandar em partes ou escrever?"
AUDIO_TOO_BIG = "Esse áudio é grande demais. Pode mandar um mais curto ou escrever?"
AUDIO_EMPTY = "Não ouvi nada nesse áudio. Pode tentar de novo ou escrever?"
AUDIO_FAIL = "Não consegui entender o áudio agora. Pode escrever ou tentar de novo em alguns minutos?"
AUDIO_BUDGET = "Por hoje já usei o limite de transcrição de áudios. Pode escrever, que eu respondo normalmente."
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


def tpl_quality(d: dict[str, Any]) -> str:
    if not d.get("open_deals") and not d.get("lost_deals"):
        return NO_DATA
    out = f"{d['open_deals']} negócios abertos; {pct(d.get('pct_next_step'), 0)} com próximo passo."
    if d.get("lost_deals"):
        out += f" Perdas em 24 meses: {d['lost_deals']}, {pct(d.get('pct_lost_with_reason'), 0)} com motivo estruturado"
        out += " (meta: 80%). Análises por motivo ainda não são confiáveis." if (d.get("pct_lost_with_reason") or 0) < 0.8 else "."
    return out


def tpl_team(members: list[tuple[str, str, str]]) -> str:
    lines = [f"• *{n}* — {t}. {g}" for n, t, g in members]
    return "Este é o *Observatório*, a sua equipe:\n" + "\n".join(lines) + "\nChame pelo nome, como “Vega, como estou na meta?”, ou fale comigo que eu direciono."


NOT_MINE = "Isso não é comigo. Fale com *{other}* ({title}): “{other}, {hint}”."
NICK_OK = "Combinado, {nick}. É assim que a equipe te chama daqui em diante."
AGENT_INTRO = "{name} aqui, {title}. {tagline} Exemplo: “{example}”."


# ---- insights de empresas ----
NO_INSIGHT = "Ainda não tenho dados suficientes para esse insight. Envie negócios com notas em Datasets ou conecte o HubSpot."
CAUTION_OUTCOME = "Termos como “contrato assinado” descrevem o resultado, não a causa."


def _cov(v: float | None) -> str:
    return "—" if v is None else pct(v, 0)


def tpl_pains(d: dict[str, Any]) -> str:
    items = d.get("items", [])
    if not items:
        return NO_INSIGHT
    lines = " · ".join(f"{i}. {x['pain']} ({x['deals']})" for i, x in enumerate(items[:5], 1))
    warn = " Amostra pequena: trate como indicativo." if d.get("low_n") else ""
    return f"Dores mais citadas ({d['with_pain']} de {d['deals']} negócios têm dor registrada): {lines}.{warn}"


def tpl_terms(d: dict[str, Any]) -> str:
    ph, w = d.get("phrases", []), d.get("words", [])
    if not ph and not w:
        return NO_INSIGHT
    words = ", ".join(f"{x['term']} ({x['deals']})" for x in w[:6])
    phrases = ", ".join(f"{x['term']} ({x['deals']})" for x in ph[:4])
    return f"Termos que mais se repetem nas notas: {words}. Frases: {phrases}. {CAUTION_OUTCOME}"


def tpl_demand(d: dict[str, Any]) -> str:
    items = d.get("items", [])
    if not items:
        return NO_INSIGHT
    lines = " · ".join(f"{x['key']}: {x['deals']} negócios, {brl(x['open_amount'])} em aberto" + (f", ganho {pct(x['win_rate'], 0)}" if x.get("win_rate") is not None else "")
                       for x in items[:5])
    return f"Tipos de demanda: {lines}."


def tpl_systems(d: dict[str, Any]) -> str:
    items = d.get("items", [])
    if not items:
        return NO_INSIGHT
    lines = " · ".join(f"{x['system']} ({'ERP' if x['category'] == 'erp' else 'CRM/vendas'}): {x['deals']} negócios" + (f", ganhamos contra em {x['won_against']}" if x.get("won_against") else "")
                       for x in items[:6])
    return f"Sistemas citados nas contas: {lines}."


def tpl_segments(d: dict[str, Any]) -> str:
    items = d.get("items", [])
    if not items and d.get("dimension") == "segment":
        return (f"Não identifiquei segmentos: nenhuma palavra final dos nomes de empresa se repete em pelo menos {d.get('min_segment_deals', 8)} negócios. "
                "Tente por campanha ou por motivo de perda.")
    if not items:
        return NO_INSIGHT
    if d.get("dimension") == "loss_reason":
        return "Motivos de perda: " + " · ".join(f"{x['label']}: {x['deals']}" for x in items[:6]) + "."
    dim = "Campanhas" if d.get("dimension") == "campaign" else "Segmentos"
    lines = " · ".join(f"{x['key']}: {x['deals']} negócios" + (f", ganho {pct(x['win_rate'], 0)}" if x.get("win_rate") is not None else "") + (" (amostra pequena)" if x.get("low_n") else "")
                       for x in items[:5])
    return f"{dim} por volume: {lines}."


def tpl_coverage(d: dict[str, Any]) -> str:
    if not d.get("deals"):
        return NO_INSIGHT
    parts = [f"notas {_cov(d.get('with_notes'))}", f"dor {_cov(d.get('with_pain'))}", f"sistema {_cov(d.get('with_system'))}", f"demanda {_cov(d.get('with_demand_type'))}",
             f"segmento {_cov(d.get('with_segment'))}", f"campanha {_cov(d.get('with_campaign'))}"]
    weak = [n for n, v in (("dores", d.get("with_pain")), ("sistemas", d.get("with_system"))) if v is not None and v < 0.3]
    tail = f" Cuidado: {' e '.join(weak)} aparecem em poucas notas, então o ranking mostra o que foi anotado, não o mercado todo." if weak else ""
    return f"Cobertura dos {d['deals']} negócios: {', '.join(parts)}.{tail}"


def tpl_digest(d: dict[str, Any]) -> str:
    bits = []
    if d.get("pain"):
        bits.append(f"dor mais citada: {d['pain']['pain']} ({d['pain']['deals']} negócios)")
    elif d.get("pains_recorded") is not None:
        bits.append(f"dores: só {d['pains_recorded']} negócio(s) com dor registrada, pouco para destacar")
    if d.get("demand"):
        bits.append(f"demanda que mais aparece: {d['demand']['key']} ({d['demand']['deals']})")
    if d.get("system"):
        bits.append(f"sistema mais citado: {d['system']['system']} ({d['system']['deals']})")
    return ("Insight do dia — " + "; ".join(bits) + ".") if bits else NO_INSIGHT


_FIX_WHY = {"no_amount": "sem valor o negócio some da previsão", "close_date_past": "com a data vencida ele parece atrasado sem estar",
            "no_next_step": "sem próximo passo ninguém sabe o que fazer", "no_notes": "sem nota o histórico se perde",
            "name_format": "o padrão do nome alimenta os insights"}


def tpl_fix_queue(d: dict[str, Any]) -> str:
    if not d.get("open_deals"):
        return NO_DATA
    head = f"{d['clean']} de {d['open_deals']} negócios abertos estão completos."
    sys_lbl = [i["label"].lower() for i in d.get("issues", []) if i.get("systemic")]
    lines = []
    if sys_lbl:
        lines.append("Atenção: " + ", ".join(sys_lbl) + " aparece em quase todos os negócios. Pode ser do export ou um padrão do CRM, então confira antes de cobrar cada vendedor.")
    q = d.get("queue") or []
    if q:
        lines.append(f"Comece por estes ({len(q)} de {d.get('queue_total', len(q))}):")
        lines += [f"• {r['name']}{' (' + brl(r['amount']) + ')' if r.get('amount') else ''}: {r['first_fix']}" for r in q]
        top = q[0]["issues"][0]
        if top in _FIX_WHY:
            lines.append(f"Por quê: {_FIX_WHY[top]}. Se quiser, peça à Lyra para registrar, por exemplo “Lyra, nota na {q[0]['name'].split(' [')[0]}: …”.")
    m = d.get("manager") or {}
    if m.get("owner_inactive"):
        lines.append(f"Para o gestor: {len(m['owner_inactive'])} negócio(s) com dono desativado, para redistribuir.")
    if m.get("duplicates"):
        lines.append(f"Para o gestor: {len(m['duplicates'])} nome(s) possivelmente duplicado(s).")
    return "\n".join([head, *lines]) if lines else head + " Nada a corrigir agora."


def tpl_forecast(d: dict[str, Any]) -> str:
    if d.get("status") == "insufficient":
        return (f"Ainda não há base para prever: só {d['closed']} negócio(s) fechado(s) (o mínimo é {d['min_closed']}). "
                "Com tão pouco histórico, qualquer porcentagem seria chute.")
    if d.get("status") == "no_pipeline":
        return "Não há negócios abertos com valor para prever. Preencha o valor dos negócios abertos (a Polaris mostra quais)."
    sc, lo, hi = d["scenarios"]["mid"], d["win_rate_ci"][0], d["win_rate_ci"][1]
    out = (f"Com base em {d['closed']} negócios fechados (taxa de ganho {pct(d['win_rate'], 0)}, entre {pct(lo, 0)} e {pct(hi, 0)}), "
           f"os {d['open_with_value']} negócios abertos com valor ({brl(d['open_amount'])}) devem render cerca de {brl(sc['expected'])}, "
           f"numa faixa provável de {brl(sc['p10'])} a {brl(sc['p90'])}.")
    if d.get("quota") is not None and d.get("target") is not None:
        if d["target"] <= 0:
            out += f" A meta de {brl(d['quota'])} já foi batida."
        else:
            lo_p, mid_p, hi_p = (d["scenarios"][k]["prob_target"] for k in ("low", "mid", "high"))
            what = "a chance seria no máximo" if d.get("backlog") else "a chance é"
            out += (f" Para a meta de {brl(d['quota'])} (faltam {brl(d['target'])}), {what} *{pct(mid_p, 0)}*, "
                    f"entre {pct(lo_p, 0)} e {pct(hi_p, 0)} conforme a taxa de ganho.")
    else:
        out += " Sem meta cadastrada, não calculo a chance de bater."
    if d.get("backlog"):
        out += (f" Cuidado: há {d['open_with_value']} negócios abertos com valor para só {d['closed']} fechados no histórico. "
                "A taxa de ganho do passado não descreve esse acúmulo (a maioria pode nunca fechar), então trate isto como um teto, não como previsão.")
    elif d.get("status") == "indicative":
        out += " Atenção: com menos de 20 fechados isto é só indicativo."
    return out + " A taxa vem só dos negócios fechados e tende a ser otimista, pois negócios parados não entram como perdidos."
