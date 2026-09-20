"""Closed tool catalog (D8, §11.2). Arguments validated by pydantic; scope comes from the Principal, never from the model."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Period(BaseModel):
    period: Literal["this_month", "last_month"] = "this_month"


class NoArgs(BaseModel):
    pass


class InsightLimit(BaseModel):
    limit: int = Field(default=5, ge=1, le=10)


class SystemsArgs(BaseModel):
    category: Literal["erp", "crm", "all"] = "all"
    limit: int = Field(default=6, ge=1, le=10)


class SegmentArgs(BaseModel):
    dimension: Literal["segment", "campaign", "loss_reason"] = "segment"
    limit: int = Field(default=5, ge=1, le=10)


class GetDeal(BaseModel):
    query: str = Field(min_length=2, max_length=120)


class ListNeedingAction(BaseModel):
    limit: int = Field(default=5, ge=1, le=10)


class AddNote(BaseModel):
    deal: str = Field(min_length=2, max_length=120)
    text: str = Field(min_length=1, max_length=2000)


class CreateTask(BaseModel):
    deal: str = Field(min_length=2, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    due_in_days: int = Field(default=1, ge=0, le=365)


class ProposeDealUpdate(BaseModel):
    deal: str = Field(min_length=2, max_length=120)
    field: Literal["stage", "close_date", "amount"]
    value: str = Field(min_length=1, max_length=60)


class UndoLast(BaseModel):
    pass


TOOLS: dict[str, tuple[type[BaseModel], str]] = {
    "get_kpis": (Period, "Win rate com intervalo de confiança, ganho, ciclo e ticket do período."),
    "get_quota_status": (Period, "Atingimento da meta, gap, cobertura de pipeline."),
    "get_forecast": (NoArgs, "Previsão: quanto o pipeline aberto ainda pode render e a chance de bater a meta, com faixa de incerteza."),
    "get_pipeline_summary": (NoArgs, "Negócios abertos por etapa: quantidade, valor e parados."),
    "get_deal": (GetDeal, "Detalhes de um negócio pelo nome."),
    "list_deals_needing_action": (ListNeedingAction, "Negócios que mais pedem atenção agora."),
    "get_morning_brief": (NoArgs, "Resumo do dia: meta e negócios prioritários."),
    "get_data_quality": (NoArgs, "Qualidade dos dados: próximo passo, motivos de perda e confiança das análises."),
    "get_pains": (InsightLimit, "Dores das empresas mais citadas nas notas dos negócios."),
    "get_recurring_terms": (InsightLimit, "Termos e frases que mais se repetem nas notas, com a taxa de ganho associada."),
    "get_demand_types": (InsightLimit, "Tipos de demanda (o que as empresas compram): negócios, valor em aberto e conversão."),
    "get_systems_landscape": (SystemsArgs, "ERPs e outros sistemas citados nas contas, com quantos negócios e contra quem se ganhou."),
    "get_segment_insights": (SegmentArgs, "Outros insights: conversão por segmento, por campanha ou motivos de perda."),
    "get_insight_coverage": (NoArgs, "Cobertura dos dados por insight: quanto do que foi dito é sustentado pelas notas."),
    "get_fix_queue": (InsightLimit, "Fila de correção dos dados: negócios abertos com lacunas (valor, data vencida, próximo passo, nota, nome) e quem corrige."),
    "get_insight_digest": (NoArgs, "Insight do dia: dor, demanda e sistema mais frequentes."),
    "add_note": (AddNote, "Registrar uma nota em um negócio."),
    "create_task": (CreateTask, "Criar uma tarefa em um negócio."),
    "propose_deal_update": (ProposeDealUpdate, "Propor alteração de etapa, data de fechamento ou valor (exige confirmação)."),
    "undo_last": (UndoLast, "Desfazer a última ação registrada (até 24h)."),
}
READ_TOOLS = {"get_forecast", "get_kpis", "get_quota_status", "get_pipeline_summary", "get_deal", "list_deals_needing_action", "get_morning_brief", "get_data_quality", "get_pains", "get_recurring_terms", "get_demand_types", "get_systems_landscape", "get_segment_insights", "get_insight_coverage", "get_insight_digest", "get_fix_queue"}


def schemas() -> list[dict[str, Any]]:
    out = []
    for name, (model, desc) in TOOLS.items():
        sch = model.model_json_schema()
        sch.pop("title", None)
        out.append({"name": name, "description": desc, "parameters": {"type": "object", **{k: v for k, v in sch.items() if k != "type"}}})
    return out


def validate(name: str, args: dict[str, Any]) -> BaseModel | None:
    """Returns validated args or None (unknown tool / invalid arguments -> caller degrades to menu)."""
    entry = TOOLS.get(name)
    if not entry:
        return None
    args = {k: v for k, v in args.items() if k not in ("owner", "owner_id", "user", "user_id", "hs_owner_id")}  # scope is never model-supplied
    try:
        return entry[0](**args)
    except Exception:
        return None
