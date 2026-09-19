from decimal import Decimal

from omnidata.crm.hubspot import mapping as m

FLAGS = {("default", "won"): (True, Decimal("1.0")), ("default", "lost"): (True, Decimal("0.0")),
         ("default", "s1"): (False, Decimal("0.2"))}


def deal(stage, **extra):
    return {"id": 1, "properties": {"pipeline": "default", "dealstage": stage, "amount": "1500.5",
                                     "closedate": "2026-03-01T00:00:00Z", "hs_lastmodifieddate": "1772323200000", **extra}}


def test_parse_ts_iso_and_epoch_ms():
    assert m.parse_ts("2026-03-01T00:00:00.000Z") == m.parse_ts("1772323200000")
    assert m.parse_ts(None) is None and m.parse_ts("") is None


def test_won_lost_come_from_stage_metadata_not_names():  # FR-ING-1, §10.1
    won, lost, op = (m.map_deal(deal(s), FLAGS) for s in ("won", "lost", "s1"))
    assert (won["is_won"], won["is_open"]) == (True, False)
    assert (lost["is_lost"], lost["is_won"]) == (True, False)
    assert (op["is_open"], op["closed_at"]) == (True, None)


def test_lost_reason_only_kept_for_lost_deals():
    assert m.map_deal(deal("lost", closed_lost_reason="price"), FLAGS)["lost_reason_hs"] == "price"
    assert m.map_deal(deal("won", closed_lost_reason="price"), FLAGS)["lost_reason_hs"] is None


def test_contact_email_is_hashed_never_stored():
    row = m.map_contact({"id": 7, "properties": {"email": " Foo@Bar.com "}})
    assert "email" not in row and len(row["email_hash"]) == 64
    assert row["email_hash"] == m.map_contact({"id": 8, "properties": {"email": "foo@bar.com"}})["email_hash"]


def test_email_activity_is_metadata_only():
    row = m.map_activity("emails", {"id": 3, "properties": {"hs_email_direction": "EMAIL", "hs_email_text": "secret body"}})
    assert row["summary"] is None and row["activity_type"] == "email" and row["hs_activity_id"] == "email:3"


def test_stage_history_timeline():  # FR-ING-2
    hist = [{"value": "s2", "timestamp": "2026-02-10T00:00:00Z"}, {"value": "s1", "timestamp": "2026-02-01T00:00:00Z"},
            {"value": "won", "timestamp": "2026-03-01T00:00:00Z"}]
    rows = m.stage_history("D1", hist, {"s1": "default", "s2": "default", "won": "default"})
    assert [r["hs_stage_id"] for r in rows] == ["s1", "s2", "won"]
    assert rows[0]["exited_at"] == rows[1]["entered_at"] and rows[-1]["exited_at"] is None


def test_close_date_pushes_counts_only_later_dates():
    h = [{"value": "2026-03-01T00:00:00Z", "timestamp": "1"}, {"value": "2026-04-01T00:00:00Z", "timestamp": "2"},
         {"value": "2026-03-15T00:00:00Z", "timestamp": "3"}, {"value": "2026-05-01T00:00:00Z", "timestamp": "4"}]
    assert m.close_date_pushes(h) == 2


def test_employee_band():
    assert [m.employee_band(x) for x in ("5", "40", "500", "5000", None)] == ["1-10", "11-50", "201-1000", "1000+", None]
