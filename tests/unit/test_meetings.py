"""Atlas (ADR 0009): synthetic transcripts tie to real deals, Chroma is only a candidate list, Postgres decides who sees what."""
from datetime import UTC, datetime

from omnidata.agents.team import TOOL_OWNER
from omnidata.bot import strings_ptbr as S
from omnidata.bot.repo import meeting_transcripts_by_ids
from omnidata.bot.tools import catalog
from omnidata.security.principal import Principal
from omnidata.transcripts.ingest import index_transcripts
from omnidata.transcripts.synth import synth_transcripts

from ..fakes import FakeEmbeddings, FakeVectorStore


def add_deal(conn, deal_id: str, name: str, owner: str, amount: float = 5000.0) -> None:
    with conn.cursor() as cur:
        cur.execute("insert into silver.deal (hs_deal_id, name, amount, hs_pipeline_id, hs_stage_id, hs_owner_id, is_open, hs_updated_at) "
                    "values (%s,%s,%s,'default','s1',%s,true,now())", (deal_id, name, amount, owner))
    conn.commit()


def principal(owner: str) -> Principal:
    return Principal(user_id="u", role="rep", hs_owner_id=owner, display_name=None, owner_ids=frozenset({owner}))


def test_synth_transcripts_reference_real_deals_only(conn):
    add_deal(conn, "T1", "Acme – Expansão", "9100")
    rows = synth_transcripts(conn, "9100", n=5, now=datetime(2026, 9, 1, tzinfo=UTC))
    assert len(rows) == 1 and rows[0]["hs_deal_id"] == "T1" and rows[0]["deal_name"] == "Acme – Expansão"
    assert "Acme" in rows[0]["text"]


def test_search_never_returns_another_owners_transcript(conn):
    add_deal(conn, "T2", "Beta Log", "9200")
    add_deal(conn, "T3", "Gamma Corp", "9300")
    rows_a = synth_transcripts(conn, "9200", n=1, seed_value=1, now=datetime(2026, 9, 1, tzinfo=UTC))
    rows_b = synth_transcripts(conn, "9300", n=1, seed_value=2, now=datetime(2026, 9, 1, tzinfo=UTC))
    store = FakeVectorStore()
    index_transcripts(FakeEmbeddings(), store, rows_a + rows_b)

    # even asking for BOTH ids, owner 9200's Principal must only ever get their own transcript back
    both_ids = [r["id"] for r in rows_a + rows_b]
    visible = meeting_transcripts_by_ids(conn, principal("9200"), both_ids)
    assert {str(r["id"]) for r in visible} == {rows_a[0]["id"]}


def test_tpl_meetings_never_invents_beyond_the_payload():
    d = {"items": [{"deal_name": "Acme – Expansão", "occurred_at": "2026-09-01", "excerpt": "cliente pediu desconto"}]}
    out = S.tpl_meetings(d)
    assert "Acme – Expansão" in out and "cliente pediu desconto" in out
    assert S.tpl_meetings({"items": []}) == "Não achei nada nas reuniões registradas sobre isso."


def test_search_meeting_notes_is_owned_by_atlas_and_validates():
    assert TOOL_OWNER["search_meeting_notes"] == "atlas"
    parsed = catalog.validate("search_meeting_notes", {"query": "preço"})
    assert parsed is not None and parsed.model_dump() == {"query": "preço", "deal": "", "limit": 3}
    assert catalog.validate("search_meeting_notes", {"query": "a"}) is None  # below min_length
