"""Personal goal tracking (Aurora): closed set of measurable goal types, never a free-form objective the LLM judges."""
from datetime import date

from omnidata.agents.team import TOOL_OWNER
from omnidata.bot import repo
from omnidata.bot import strings_ptbr as S
from omnidata.bot.tools import catalog
from omnidata.security.principal import Principal


def principal(user_id: str, owner: str) -> Principal:
    return Principal(user_id=user_id, role="rep", hs_owner_id=owner, display_name=None, owner_ids=frozenset({owner}))


def set_goal(conn, user_id, owner, goal_type, target, deadline, created_at=None, status="active"):
    with conn.cursor() as cur:
        cur.execute("insert into app.seller_goal (user_id, hs_owner_id, goal_type, target, deadline, status, created_at) "
                    "values (%s,%s,%s,%s,%s,%s, coalesce(%s, now())) returning id",
                    (user_id, owner, goal_type, target, deadline, status, created_at))
        return cur.fetchone()["id"]


def add_won_deal(conn, deal_id, owner, closed_at):
    with conn.cursor() as cur:
        cur.execute("insert into silver.deal (hs_deal_id, name, hs_pipeline_id, hs_stage_id, hs_owner_id, is_open, is_won, "
                    "closed_at, hs_updated_at) values (%s,%s,'default','won',%s,false,true,%s,now())",
                    (deal_id, deal_id, owner, closed_at))
    conn.commit()


def test_no_active_goal(conn):
    with conn.cursor() as cur:
        cur.execute("insert into app.app_user (hs_owner_id, phone_e164, display_name, role, status) "
                    "values ('9700','+5511900000700','Ana','rep','active') returning id")
        uid = str(cur.fetchone()["id"])
    conn.commit()
    d = repo.goal_status(conn, principal(uid, "9700"), date(2026, 9, 20))
    assert d == {"active": False}
    assert S.tpl_goal_status(d) == "Você não tem uma meta pessoal ativa. Diga algo como “quero fechar 3 negócios até sexta” pra eu acompanhar."


def test_deals_won_progress_only_counts_deals_closed_after_the_goal(conn):
    with conn.cursor() as cur:
        cur.execute("insert into app.app_user (hs_owner_id, phone_e164, display_name, role, status) "
                    "values ('9701','+5511900000701','Bruno','rep','active') returning id")
        uid = str(cur.fetchone()["id"])
    conn.commit()
    add_won_deal(conn, "before", "9701", date(2026, 9, 1))   # closed before the goal: must not count
    set_goal(conn, uid, "9701", "deals_won", 3, date(2026, 9, 30), created_at="2026-09-10")
    add_won_deal(conn, "after1", "9701", date(2026, 9, 15))
    add_won_deal(conn, "after2", "9701", date(2026, 9, 20))

    d = repo.goal_status(conn, principal(uid, "9701"), date(2026, 9, 20))
    assert d["active"] and d["goal_type"] == "deals_won" and d["progress"] == 2.0 and d["target"] == 3.0 and not d["done"]
    assert "2" in S.tpl_goal_status(d) and "3" in S.tpl_goal_status(d)


def test_expired_goal_is_ignored(conn):
    with conn.cursor() as cur:
        cur.execute("insert into app.app_user (hs_owner_id, phone_e164, display_name, role, status) "
                    "values ('9702','+5511900000702','Carla','rep','active') returning id")
        uid = str(cur.fetchone()["id"])
    conn.commit()
    set_goal(conn, uid, "9702", "deals_won", 1, date(2026, 9, 1), status="expired")
    assert repo.goal_status(conn, principal(uid, "9702"), date(2026, 9, 20)) == {"active": False}


def test_set_goal_is_owned_by_aurora_and_validates():
    assert TOOL_OWNER["set_goal"] == "aurora" and TOOL_OWNER["get_goal_status"] == "aurora"
    parsed = catalog.validate("set_goal", {"goal_type": "deals_won", "target": 3, "deadline_in_days": 5})
    assert parsed is not None and parsed.model_dump() == {"goal_type": "deals_won", "target": 3.0, "deadline_in_days": 5}
    assert catalog.validate("set_goal", {"goal_type": "made_up", "target": 3}) is None


def test_goal_desc_formatting():
    assert S.goal_desc("deals_won", 3) == "fechar 3 negócio(s)"
    assert S.goal_desc("quota_pct", 80) == "chegar a 80% de atingimento"
