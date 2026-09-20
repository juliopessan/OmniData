"""Dictionaries and patterns for company insights. Deterministic: everything here is data, reviewable and shared with the web UI
(`omnidata insights spec > web/src/lib/insights-spec.json`). Built from a real pt-BR HubSpot export; extend as your notes evolve."""
from __future__ import annotations

# canonical name -> (category, aliases). Matching is on accent-free lowercase, whole words only.
# categories: erp (gestão), crm (vendas/marketing). "sap"/"senior" style ambiguities are avoided on purpose.
SYSTEMS: dict[str, tuple[str, tuple[str, ...]]] = {
    "Totvs": ("erp", ("totvs", "protheus", "datasul", "microsiga")),
    "SAP": ("erp", ("sap", "sap b1", "s4hana", "business one")),
    "Oracle": ("erp", ("oracle", "netsuite", "jd edwards")),
    "Sankhya": ("erp", ("sankhya",)),
    "Omie": ("erp", ("omie",)),
    "Bling": ("erp", ("bling",)),
    "Linx": ("erp", ("linx",)),
    "Conta Azul": ("erp", ("conta azul",)),
    "Senior": ("erp", ("senior sistemas",)),
    "ERP (não especificado)": ("erp", ("erp",)),
    "Salesforce": ("crm", ("salesforce",)),
    "Zoho": ("crm", ("zoho",)),
    "Pipedrive": ("crm", ("pipedrive",)),
    "RD Station": ("crm", ("rd station", "rd crm")),
    "HubSpot": ("crm", ("hubspot",)),
    "Agendor": ("crm", ("agendor",)),
    "Ploomes": ("crm", ("ploomes",)),
    "Moskit": ("crm", ("moskit",)),
}

# regex over the ORIGINAL note text. group(1) is the pain.
PAIN_LABELS = r"(?:dor validada|dor principal|dor identificada|principal dor|dor)\s*:\s*([^.;|]+)"
PAIN_CUES = (r"(dificuldade (?:de|em|para) [^.;|]+)", r"(falta de [^.;|]+)", r"(baixa visibilidade [^.;|]+)", r"(retrabalho [^.;|]*)")

# context roles for system mentions
ROLE_PATTERNS = {"won_against": r"ganhamos contra ([^:.;|]+)", "internal": r"solu[cç][aã]o interna\s*\(([^)]+)\)"}

# loss-reason taxonomy (PRD §12.4) by accent-free keywords, first match wins
LOSS_TAXONOMY: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("internal_solution", "Solução interna", ("solucao interna",)),
    ("price", "Preço", ("preco", "caro", "desconto")),
    ("budget_timing", "Orçamento/timing", ("orcamento", "adiado", "proximo ano", "timing", "sem budget")),
    ("champion_lost", "Perdi o champion", ("decisor saiu", "champion", "sponsor saiu")),
    ("no_decision", "Sem decisão/sumiu", ("sem resposta", "sumiu", "sem decisao", "parou de responder")),
    ("product_fit", "Produto não atende", ("escopo", "nao aderente", "funcionalidade", "nao atende")),
    ("competitor", "Concorrente", ("concorrente", "perdemos para", "optou por")),
)

# generic words that carry no insight (accent-free). Boilerplate of CRM notes is included on purpose.
STOPWORDS = frozenset("""
para como mais pela pelo pelos pelas entre ainda apos sobre quando porque tambem cliente clientes empresa contato time dias
com sem uma umas uns dos das nos nas que foi ser sera estao esta estava tem tinha vai vao havia isso essa esse este esta aqui
motivo perda ganhamos contra concluido concluida agendada agendado enviado enviada estimado estimada confirmada confirmado
bem mesmo apenas mais menos muito pouco depois antes durante desde ate hoje amanha semana mes ano anos
proxima proximo primeiro primeira segundo segunda final total valor percebido
segue anexo anexa referente referentes demais documentos negocio mail whatsapp
""".split())

MIN_SEGMENT_DEALS = 8  # a trailing company word only counts as a "segment" if it repeats this much
DEMAND_SPLIT = r"\s[–—-]\s"
# "Cliente<>Parceiro [Demanda]" (HubSpot corporate export): demand in trailing brackets, client before "<>"
DEMAND_BRACKET = r"\[([^\[\]]+)\]?\s*$"
COMPANY_SPLIT = r"\s*<>\s*"
# @mentions of colleagues ("@Ana Souza") are people, not subjects: removed before mining terms
MENTION = r"@[^\s@.;,]+(?:\s+[A-ZÀ-Ú][^\s@.;,]*)?"


def spec_json() -> dict[str, object]:
    return {
        "systems": {k: {"category": c, "aliases": list(a)} for k, (c, a) in SYSTEMS.items()},
        "painLabels": PAIN_LABELS, "painCues": list(PAIN_CUES), "rolePatterns": ROLE_PATTERNS,
        "lossTaxonomy": [{"code": c, "label": lbl, "keywords": list(k)} for c, lbl, k in LOSS_TAXONOMY],
        "stopwords": sorted(STOPWORDS), "minSegmentDeals": MIN_SEGMENT_DEALS, "demandSplit": DEMAND_SPLIT, "demandBracket": DEMAND_BRACKET, "companySplit": COMPANY_SPLIT, "mention": MENTION,
        "owners": {"pains": "lyra", "terms": "lyra", "demand": "altair", "systems": "altair", "other": "vega", "coverage": "argus", "digest": "aurora"},
    }
