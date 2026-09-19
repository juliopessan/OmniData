import csv

from typer.testing import CliRunner

from omnidata.cli import app

from ..helpers import add_user

runner = CliRunner()


def test_quota_import_validates_before_writing(conn, tmp_path, monkeypatch):  # FR-ING-7
    from ..conftest import TEST_DSN
    monkeypatch.setenv("DATABASE_URL", TEST_DSN)
    from omnidata.config import get_settings
    get_settings.cache_clear()
    good, bad = tmp_path / "good.csv", tmp_path / "bad.csv"
    for f, rows in ((good, [["9000", "2026-09-01", "2026-09-30", "100000"]]), (bad, [["9000", "2026-09-01", "2026-09-30", "100000"], ["", "x", "y", "-1"]])):
        with f.open("w", newline="") as fh:
            w = csv.writer(fh); w.writerow(["owner", "period_start", "period_end", "amount"]); w.writerows(rows)
    assert runner.invoke(app, ["quota", "import", str(bad)]).exit_code == 2
    with conn.cursor() as cur:
        cur.execute("select count(*) n from silver.quota"); assert cur.fetchone()["n"] == 0  # nothing partially written
    assert runner.invoke(app, ["quota", "import", str(good)]).exit_code == 0
    with conn.cursor() as cur:
        cur.execute("select amount from silver.quota"); assert int(cur.fetchone()["amount"]) == 100000
    get_settings.cache_clear()


def test_user_invite_and_erase_lgpd(conn, monkeypatch):  # FR-BOT-1, US-15
    from ..conftest import TEST_DSN
    monkeypatch.setenv("DATABASE_URL", TEST_DSN)
    from omnidata.config import get_settings
    get_settings.cache_clear()
    assert runner.invoke(app, ["user", "invite", "--phone", "12345", "--owner", "1"]).exit_code == 2  # not E.164
    r = runner.invoke(app, ["user", "invite", "--phone", "+5511955550000", "--owner", "9100", "--name", "Nova"])
    assert r.exit_code == 0
    with conn.cursor() as cur:
        cur.execute("select status from app.app_user where phone_e164='+5511955550000'"); assert cur.fetchone()["status"] == "invited"
    uid = add_user(conn, "+5511955551111", "9101")
    with conn.cursor() as cur:
        cur.execute("insert into app.audit_log (user_id, event) values (%s,'x')", (uid,))
    conn.commit()
    assert runner.invoke(app, ["user", "erase", "+5511955551111"]).exit_code == 0
    with conn.cursor() as cur:
        cur.execute("select (select count(*) from app.app_user where id=%s) u, (select count(*) from app.audit_log where user_id=%s) a", (uid, uid))
        r2 = cur.fetchone()
    assert r2["u"] == 0 and r2["a"] == 0
    get_settings.cache_clear()
