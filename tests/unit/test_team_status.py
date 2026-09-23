"""get_team_status (Vega): per-rep attainment + hygiene backlog, scoped by Principal.owner_clause() like everything else."""
from datetime import date

from omnidata.agents.team import TOOL_OWNER
from omnidata.bot import repo
from omnidata.bot import strings_ptbr as S
from omnidata.bot.tools import catalog
from omnidata.security.principal import Principal


def add_owner(conn, owner: str, first: str, last: str = "") -> None:
    with conn.cursor() as cur:
        cur.execute("insert into silver.owner (hs_owner_id, email, first_name, last_name, is_active) values (%s,%s,%s,%s,true)",
                    (owner, f"{owner}@x.invalid", first, last))
    conn.commit()


def add_quota(conn, owner: str, period_start: date, amount: float) -> None:
    with conn.cursor() as cur:
        cur.execute("insert into silver.quota (hs_owner_id, period_start, period_end, amount, source) values (%s,%s,%s,%s,'test')",
                    (owner, period_start, date(period_start.year, period_start.month % 12 + 1, 1), amount))
    conn.commit()


def add_won_deal(conn, deal_id: str, owner: str, amount: float, closed_at: date, next_activity=None) -> None:
    with conn.cursor() as cur:
        cur.execute("insert into silver.deal (hs_deal_id, name, amount, hs_pipeline_id, hs_stage_id, hs_owner_id, is_open, is_won, "
                    "closed_at, next_activity_at, hs_updated_at) values (%s,%s,%s,'default','won',%s,false,true,%s,%s,now())",
                    (deal_id, deal_id, amount, owner, closed_at, next_activity))
    conn.commit()


def principal(owner: str, owner_ids) -> Principal:
    return Principal(user_id="u", role="manager", hs_owner_id=owner, display_name=None, owner_ids=owner_ids)


def test_team_status_sorts_worst_attainment_first(conn):
    period = date(2026, 9, 1)
    add_owner(conn, "9500", "Ana", "Souza")
    add_owner(conn, "9501", "Bruno", "Lima")
    add_quota(conn, "9500", period, 10000)
    add_quota(conn, "9501", period, 10000)
    add_won_deal(conn, "D1", "9500", 2000, date(2026, 9, 5))   # 20% attainment
    add_won_deal(conn, "D2", "9501", 8000, date(2026, 9, 5))   # 80% attainment

    d = repo.team_status(conn, principal("9999", frozenset({"9500", "9501"})), period)
    assert [r["hs_owner_id"] for r in d["reps"]] == ["9500", "9501"]  # worst first
    assert d["reps"][0]["name"] == "Ana Souza" and round(d["reps"][0]["attainment"], 2) == 0.2


def test_team_status_scopes_to_a_single_rep_like_every_other_tool(conn):
    period = date(2026, 9, 1)
    add_owner(conn, "9600", "Carla", "Mendes")
    add_owner(conn, "9601", "Diego", "Rocha")
    add_quota(conn, "9600", period, 5000)
    add_quota(conn, "9601", period, 5000)
    add_won_deal(conn, "D3", "9600", 5000, date(2026, 9, 5))
    add_won_deal(conn, "D4", "9601", 1000, date(2026, 9, 5))

    d = repo.team_status(conn, principal("9600", frozenset({"9600"})), period)
    assert [r["hs_owner_id"] for r in d["reps"]] == ["9600"]  # never sees a colleague's row


def test_tpl_team_status_single_rep_vs_team_view():
    one = S.tpl_team_status({"reps": [{"name": "Ana", "quota_amount": 10000.0, "won_amount": 3500.0, "gap": 6500.0, "attainment": 0.35, "open_issues": 2}]})
    assert "Ana" in one and "35" in one
    team = S.tpl_team_status({"reps": [
        {"name": "Ana", "quota_amount": 10000.0, "won_amount": 2000.0, "gap": 8000.0, "attainment": 0.2, "open_issues": 3},
        {"name": "Bruno", "quota_amount": 10000.0, "won_amount": 8000.0, "gap": 2000.0, "attainment": 0.8, "open_issues": 0},
    ]})
    assert "Ana" in team and "Bruno" in team and "Priorize 1:1" in team
    assert S.tpl_team_status({"reps": []}) == S.NO_DATA


def test_get_team_status_is_owned_by_vega_and_validates():
    assert TOOL_OWNER["get_team_status"] == "vega"
    assert catalog.validate("get_team_status", {}) is not None
