"""`omnidata dev seed`: a realistic fake CRM so dev and the free-tier pilot hold no real PII."""
from __future__ import annotations

import hashlib
import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import psycopg

from ..db import upsert

Conn = psycopg.Connection[Any]
FIRST = ["Ana", "Bruno", "Carla", "Diego", "Elisa", "Fábio"]
LAST = ["Souza", "Lima", "Mendes", "Rocha", "Alves", "Pires"]
STAGES = [("s1", "Qualificação", 0.2, False), ("s2", "Proposta", 0.4, False), ("s3", "Negociação", 0.7, False),
          ("won", "Fechado ganho", 1.0, True), ("lost", "Fechado perdido", 0.0, True)]
REASONS = ["price", "competitor", "no_decision", "product_fit", "budget_timing", None, None, "Other"]


def seed(conn: Conn, deals: int = 2000, seed_value: int = 42, now: datetime | None = None) -> dict[str, int]:
    rng = random.Random(seed_value)
    now = now or datetime.now(UTC)
    owners = [{"hs_owner_id": f"9{i:03d}", "email": f"rep{i}@example.invalid", "first_name": FIRST[i % 6],
               "last_name": LAST[i % 6], "is_active": True} for i in range(6)]
    upsert(conn, "silver.owner", owners, ["hs_owner_id"])
    upsert(conn, "silver.pipeline", [{"hs_pipeline_id": "default", "label": "Vendas"}], ["hs_pipeline_id"])
    upsert(conn, "silver.stage", [{"hs_pipeline_id": "default", "hs_stage_id": sid, "label": lbl, "display_order": i,
                                    "is_closed": closed, "probability": Decimal(str(p))}
                                   for i, (sid, lbl, p, closed) in enumerate(STAGES)], ["hs_pipeline_id", "hs_stage_id"])
    open_ids = ["s1", "s2", "s3"]
    d_rows, hist, changes, acts, contacts, dcs = [], [], [], [], [], []
    for i in range(deals):
        did = f"D{100000 + i}"
        created = now - timedelta(days=rng.randint(5, 700))
        outcome = rng.choices(["open", "won", "lost"], [0.15, 0.35, 0.5])[0] if created < now - timedelta(days=40) \
            else "open"
        if outcome == "open":
            cur_stage = rng.choice(open_ids)
        else:
            cur_stage = "won" if outcome == "won" else "lost"
        path = open_ids[: open_ids.index(cur_stage) + 1] if cur_stage in open_ids else open_ids[: rng.randint(1, 3)] + [cur_stage]
        t = created
        for j, sid in enumerate(path):
            nxt = t + timedelta(days=rng.randint(3, 25))
            last = j == len(path) - 1
            hist.append({"hs_deal_id": did, "hs_pipeline_id": "default", "hs_stage_id": sid, "entered_at": t,
                         "exited_at": None if last else nxt})
            t = nxt
        amount = Decimal(rng.choice([8, 15, 22, 35, 50, 80, 120]) * 1000)
        close = t if outcome != "open" else now + timedelta(days=rng.randint(-10, 60))
        pushes = rng.choice([0, 0, 0, 1, 2]) if outcome != "won" else rng.choice([0, 0, 1])
        d_rows.append({
            "hs_deal_id": did, "name": f"Empresa {i} – {rng.choice(['Novo', 'Renovação', 'Expansão'])}",
            "amount": amount, "currency": "BRL", "hs_pipeline_id": "default", "hs_stage_id": cur_stage,
            "hs_owner_id": owners[i % 6]["hs_owner_id"], "created_at": created, "close_date": close,
            "closed_at": close if outcome != "open" else None, "is_open": outcome == "open",
            "is_won": outcome == "won", "is_lost": outcome == "lost",
            "lost_reason_hs": rng.choice(REASONS) if outcome == "lost" else None, "source": rng.choice(["ORGANIC", "PAID", "REFERRALS"]),
            "last_activity_at": now - timedelta(days=rng.randint(0, 20)) if outcome == "open" else None,
            "next_activity_at": (now + timedelta(days=rng.randint(1, 10))) if outcome == "open" and rng.random() < 0.6 else None,
            "num_contacts": rng.randint(1, 4), "close_date_pushes": pushes, "hs_updated_at": t, "is_archived": False})
        changes.append({"hs_deal_id": did, "property": "amount", "old_value": None, "new_value": str(amount), "changed_at": created})
        cid = f"C{100000 + i}"
        contacts.append({"hs_contact_id": cid, "email_hash": hashlib.sha256(f"{cid}@example.invalid".encode()).hexdigest(),
                         "job_title": rng.choice(["CFO", "CTO", "Head de Vendas", "Compras"]), "lifecycle_stage": "opportunity",
                         "hs_owner_id": owners[i % 6]["hs_owner_id"], "hs_updated_at": created})
        dcs.append({"hs_deal_id": did, "hs_contact_id": cid, "is_primary": True})
        for k in range(rng.randint(1, 5)):
            kind = rng.choice(["call", "meeting", "email", "note", "task"])
            acts.append({"hs_activity_id": f"{kind}:{did}-{k}", "activity_type": kind, "hs_deal_id": did, "hs_contact_id": cid,
                         "hs_owner_id": owners[i % 6]["hs_owner_id"], "occurred_at": created + timedelta(days=k * 3),
                         "due_at": None, "is_completed": True if kind == "task" else None,
                         "duration_sec": rng.randint(60, 1800) if kind == "call" else None, "direction": None, "outcome": None,
                         "summary": None, "transcript_path": None, "hs_updated_at": created})
    for table, rows, pk in (
        ("silver.deal", d_rows, ["hs_deal_id"]), ("silver.deal_stage_history", hist, ["hs_deal_id", "hs_stage_id", "entered_at"]),
        ("silver.deal_property_change", changes, ["hs_deal_id", "property", "changed_at"]),
        ("silver.contact", contacts, ["hs_contact_id"]), ("silver.deal_contact", dcs, ["hs_deal_id", "hs_contact_id"]),
        ("silver.activity", acts, ["hs_activity_id"]),
    ):
        upsert(conn, table, rows, pk)
    month = now.date().replace(day=1)
    upsert(conn, "silver.quota", [{"hs_owner_id": o["hs_owner_id"], "period_start": month,
                                    "period_end": (month + timedelta(days=32)).replace(day=1) - timedelta(days=1),
                                    "amount": Decimal("100000"), "source": "seed"} for o in owners],
           ["hs_owner_id", "period_start", "period_end"])
    conn.commit()
    return {"owners": len(owners), "deals": len(d_rows), "stage_history": len(hist), "activities": len(acts)}
