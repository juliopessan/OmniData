from omnidata.ingest.audit import Readiness, decide, render_readiness_md
from omnidata.ingest.backup import pg_dump_cmd


def base(**kw):
    d = dict(generated_at="x", closed_per_pipeline={"p": {"won": 200, "lost": 150}}, pct_intact_stage_history=0.9,
             pct_lost_with_reason=0.4, lost_deals=150, avg_contacts_per_deal=2.0, pct_calls_with_transcript=0.0,
             calls_with_transcript=0, quota_rows=0, owners_active=5, owners_mapped_to_phone=0)
    d.update(kw)
    return Readiness(**d)


def test_go_no_go_thresholds():  # M0 exit criteria
    ucs = {u.name: u.decision for u in decide(base())}
    assert ucs == {"Predictive scoring": "go", "Win/loss analysis": "conditional",
                   "Script adherence": "no-go", "Quota forecast": "no-go"}
    small = {u.name: u.decision for u in decide(base(closed_per_pipeline={"p": {"won": 5, "lost": 5}}))}
    assert small["Predictive scoring"] == "no-go"


def test_report_renders_decisions():
    r = base()
    r.use_cases = decide(r)
    assert "**conditional**" in render_readiness_md(r)


def test_backup_targets_only_irreplaceable_tables():
    cmd = pg_dump_cmd("postgresql://x", __import__("pathlib").Path("o.dump"))
    assert "--table=silver.deal_snapshot" in cmd and "--schema=app" in cmd and cmd[-1] == "postgresql://x"
    assert not any("silver.deal_stage_history" in c for c in cmd)  # rebuildable from HubSpot
