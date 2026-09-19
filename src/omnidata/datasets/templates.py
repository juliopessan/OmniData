"""Downloadable CSV templates (UTF-8 with BOM so Excel opens accents correctly)."""
TEMPLATES = {
    "deals": ("ID do registro,Nome do negócio,Etapa do negócio,Valor,Data de fechamento,Proprietário do negócio,Próxima atividade,Associated Note\r\n"
              "1001,Acme – Renovação,Negociação,84000,2026-10-15,Ana Souza,2026-10-01 14:00,Cliente pediu ajuste de escopo.\r\n"
              "1002,Nuvem Sul – Novo,Qualificação,22000,2026-11-30,Bruno Lima,,\r\n"
              "1003,Kappa Retail,Fechado ganho,68000,2026-08-20,Ana Souza,,Contrato assinado.\r\n"
              "1004,Prisma,Fechado perdido,44000,2026-07-11,Bruno Lima,,Motivo da perda: Preço acima do orçamento aprovado.\r\n"),
    "quotas": ("Proprietário,Início do período,Fim do período,Meta\r\n"
               "Ana Souza,2026-09-01,2026-09-30,100000\r\n"
               "Bruno Lima,2026-09-01,2026-09-30,100000\r\n"),
}


def template_bytes(kind: str) -> bytes:
    return ("﻿" + TEMPLATES[kind]).encode("utf-8")
