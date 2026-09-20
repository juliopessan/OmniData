"""Canonical dataset kinds and the header aliases that map real-world exports onto them.
The `deals` aliases are built from an actual HubSpot UI export in pt-BR ("ID do registro", "Etapa do negócio", ...)."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def norm(s: str) -> str:
    """'Etapa do negócio' -> 'etapa do negocio'. Accent-, case- and punctuation-insensitive."""
    s = unicodedata.normalize("NFD", s.replace("﻿", "")).lower()
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


@dataclass(frozen=True)
class Column:
    name: str
    aliases: tuple[str, ...]
    required: bool = False
    stored: bool = True  # False = recognised but intentionally not imported
    hint: str = ""


@dataclass(frozen=True)
class Kind:
    key: str
    title: str
    description: str
    columns: tuple[Column, ...]

    def alias_map(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for c in self.columns:
            for a in (c.name, *c.aliases):
                out.setdefault(norm(a), c.name)
        return out


DEALS = Kind("deals", "Negócios", "Exportação de negócios do CRM (HubSpot em pt-BR ou en). Vira silver.deal.", (
    Column("id", ("ID do registro", "Record ID", "Deal ID", "hs_object_id", "ID do negócio"), True, hint="único por linha"),
    Column("name", ("Nome do negócio", "Deal Name", "dealname", "Nome", "Título", "Title"), True),
    Column("stage", ("Etapa do negócio", "Deal Stage", "dealstage", "Etapa", "Fase"), True,
           hint="ganho/perdido saem do nome da etapa (ex.: Fechado ganho)"),
    Column("amount", ("Valor", "Amount", "Valor do negócio", "Value", "Montante")),
    Column("close_date", ("Data de fechamento", "Close Date", "closedate", "Data prevista de fechamento")),
    Column("created_at", ("Data de criação", "Create Date", "createdate", "Created At")),
    Column("owner", ("Proprietário do negócio", "Deal owner", "hubspot_owner_id", "Proprietário", "Owner", "Responsável", "Vendedor"),
           hint="nome ou id do dono; nomes já existentes no HubSpot são reaproveitados"),
    Column("status", ("Status", "Situação"), hint="opcional: aberto/ganho/perdido (sobrescreve a etapa)"),
    Column("next_activity", ("Próxima atividade", "Next Activity Date", "notes_next_activity_date")),
    Column("lost_reason", ("Motivo da perda", "Closed Lost Reason", "closed_lost_reason", "Motivo de perda"),
           hint="se ausente, tenta extrair de “Motivo da perda: …” nas notas"),
    Column("notes", ("Associated Note", "Nota associada", "Notas", "Notes", "Anotações")),
    Column("note_ids", ("Associated Note IDs", "IDs das notas associadas", "Note IDs")),
    Column("campaign", ("Campanha do último agendamento na ferramenta de reuniões", "Campanha", "Campaign", "Fonte", "Source", "Origem")),
    Column("deal_score", ("Pontuação do negócio", "Deal Score", "hs_deal_score"), stored=False,
           hint="reconhecida mas não importada: é uma previsão do CRM, não um fato"),
))

QUOTAS = Kind("quotas", "Metas", "Meta por vendedor e período. Vira silver.quota.", (
    Column("owner", ("Proprietário", "Owner", "Vendedor", "Responsável", "hubspot_owner_id", "Owner ID"), True),
    Column("period_start", ("Início do período", "Period Start", "Início", "Start", "Data início"), True),
    Column("period_end", ("Fim do período", "Period End", "Fim", "End", "Data fim"), True),
    Column("amount", ("Meta", "Quota", "Valor", "Amount", "Meta do período"), True),
))

KINDS: dict[str, Kind] = {k.key: k for k in (DEALS, QUOTAS)}

# Funnel-order hints for OPEN stage labels when the caller does not give an explicit order.
STAGE_RANKS: tuple[tuple[str, int], ...] = (
    (r"qualific", 1), (r"descoberta|discovery", 2), (r"reuni|meeting", 3), (r"apresent|demo|presentation", 4),
    (r"propost|proposal", 5), (r"negocia|negotiat", 6), (r"contrat|contract|jurid|legal|assinat", 7),
)
WON_RE = re.compile(r"\b(fechado ganho|negocio fechado|closed won|ganho|ganha|won)\b")
LOST_RE = re.compile(r"\b(fechado perdido|closed lost|perdido|perdida|lost)\b")
STATUS_WORDS = {"aberto": "open", "open": "open", "ganho": "won", "won": "won", "ganha": "won", "perdido": "lost", "lost": "lost", "perdida": "lost"}


def spec_json() -> dict[str, object]:
    """Shared with the web UI (web/src/lib/dataset-spec.json); a test keeps them in sync."""
    return {"stageRanks": [[p, r] for p, r in STAGE_RANKS], "won": WON_RE.pattern, "lost": LOST_RE.pattern,
            "statusWords": STATUS_WORDS, "kinds": [{
        "key": k.key, "title": k.title, "description": k.description,
        "columns": [{"name": c.name, "required": c.required, "stored": c.stored, "hint": c.hint,
                     "aliases": [norm(a) for a in (c.name, *c.aliases)]} for c in k.columns]} for k in KINDS.values()]}
