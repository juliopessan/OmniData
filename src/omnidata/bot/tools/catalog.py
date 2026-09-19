"""Closed tool catalog (D8, §11.2). Arguments validated by pydantic; scope comes from the Principal, never from the model."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Period(BaseModel):
    period: Literal["this_month", "last_month"] = "this_month"


class NoArgs(BaseModel):
    pass


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
    "get_pipeline_summary": (NoArgs, "Negócios abertos por etapa: quantidade, valor e parados."),
    "get_deal": (GetDeal, "Detalhes de um negócio pelo nome."),
    "list_deals_needing_action": (ListNeedingAction, "Negócios que mais pedem atenção agora."),
    "get_morning_brief": (NoArgs, "Resumo do dia: meta e negócios prioritários."),
    "add_note": (AddNote, "Registrar uma nota em um negócio."),
    "create_task": (CreateTask, "Criar uma tarefa em um negócio."),
    "propose_deal_update": (ProposeDealUpdate, "Propor alteração de etapa, data de fechamento ou valor (exige confirmação)."),
    "undo_last": (UndoLast, "Desfazer a última ação registrada (até 24h)."),
}
READ_TOOLS = {"get_kpis", "get_quota_status", "get_pipeline_summary", "get_deal", "list_deals_needing_action", "get_morning_brief"}


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
