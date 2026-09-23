"""Synthetic meeting transcripts (ADR 0009) for testing Atlas end to end: deterministic templates, not an LLM, tied to real
deals already in the target database (real name/amount/owner) — never a freestanding invented company."""
from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg

Conn = psycopg.Connection[Any]

_PAINS = ["o time perde tempo consolidando planilha", "a integração com o sistema atual é manual", "o processo de aprovação é lento",
          "não tem visibilidade do funil hoje", "o time cresceu e o controle ficou difícil"]
_OBJECTIONS = ["o preço está acima do orçamento deste trimestre", "querem comparar com o concorrente antes de decidir",
               "precisam da aprovação de mais uma pessoa", "o timing não é ideal, projeto interno prioritário agora"]
_NEXT_STEPS = ["enviar a proposta revisada até sexta", "marcar uma demo com o time técnico", "confirmar orçamento com o financeiro",
               "mandar cases de clientes do mesmo segmento"]


def _transcript_text(rng: random.Random, deal_name: str, amount: float | None) -> str:
    pain, obj, nxt = rng.choice(_PAINS), rng.choice(_OBJECTIONS), rng.choice(_NEXT_STEPS)
    valor = f"cerca de R$ {amount:,.0f}".replace(",", ".") if amount else "um valor ainda não definido"
    return (f"Reunião com {deal_name}. O cliente comentou que {pain}. Perguntado sobre orçamento, mencionou {valor} como faixa "
            f"considerada. Como objeção principal, disse que {obj}. Combinamos como próximo passo: {nxt}.")


def synth_transcripts(conn: Conn, hs_owner_id: str, n: int = 5, seed_value: int = 42, now: datetime | None = None) -> list[dict[str, Any]]:
    """Picks up to n real deals owned by hs_owner_id and builds one synthetic transcript per deal. Returns the rows inserted
    (id, hs_deal_id, deal_name, occurred_at, text) so the caller can chunk/embed them without a second read."""
    rng = random.Random(seed_value)
    now = now or datetime.now(UTC)
    with conn.cursor() as cur:
        cur.execute("select hs_deal_id, name, amount from silver.deal where hs_owner_id = %s and not is_archived order by hs_deal_id limit %s",
                    (hs_owner_id, n))
        deals = cur.fetchall()
    rows = []
    for d in deals:
        text = _transcript_text(rng, d["name"], float(d["amount"]) if d["amount"] is not None else None)
        occurred = now - timedelta(days=rng.randint(1, 30))
        with conn.cursor() as cur:
            cur.execute("insert into app.meeting_transcript (hs_deal_id, hs_owner_id, deal_name, occurred_at, text, synthetic) "
                        "values (%s,%s,%s,%s,%s,true) returning id", (d["hs_deal_id"], hs_owner_id, d["name"], occurred, text))
            tid = cur.fetchone()["id"]
        rows.append({"id": str(tid), "hs_deal_id": d["hs_deal_id"], "hs_owner_id": hs_owner_id, "deal_name": d["name"],
                     "occurred_at": occurred, "text": text})
    conn.commit()
    return rows
