"""Statistical forecast (layer 1). ML (layer 2) stays off until the data can support it."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from omnidata.forecast import spec
from omnidata.forecast.compute import forecast, ml_status, mulberry32, trials_for

from ..insights.test_insights import ask, ins  # noqa: F401  (fixture reuse)

TS = Path(__file__).resolve().parents[2] / "web" / "src" / "lib" / "forecast.ts"
OPEN = [100_000, 50_000, 20_000, 5_000, 0, 0]


def test_no_forecast_below_the_minimum_of_closed_deals_and_no_percentage_is_invented():
    f = forecast(OPEN, wins=3, losses=2, quota=100_000)
    assert f["status"] == "insufficient" and "scenarios" not in f and "win_rate" not in f
    assert forecast([], wins=30, losses=10)["status"] == "no_pipeline"
    assert forecast([0, 0], wins=30, losses=10)["status"] == "no_pipeline"          # deals without value add nothing


def test_indicative_below_twenty_closed_and_ok_from_twenty():
    assert forecast(OPEN, wins=6, losses=4)["status"] == "indicative"
    assert forecast(OPEN, wins=15, losses=10)["status"] == "ok"


def test_a_backlog_much_larger_than_the_history_is_flagged_and_never_shown_as_reliable():
    f = forecast([5_000] * 130, wins=27, losses=14, quota=100_000)             # 130 open with value for 41 closed (limit: 3 x 41 = 123)
    assert f["backlog"] is True and f["status"] == "indicative"
    ok = forecast([5_000] * 20, wins=27, losses=14)
    assert ok["backlog"] is False and ok["status"] == "ok"


def test_same_input_same_answer_and_scenarios_are_ordered_in_every_statistic():
    a = forecast(OPEN, 27, 14, realized=30_000, quota=120_000)
    assert a == forecast(list(reversed(OPEN)), 27, 14, realized=30_000, quota=120_000)   # order of the deals does not matter
    lo, mid, hi = (a["scenarios"][k] for k in ("low", "mid", "high"))
    for key in ("p", "expected", "p10", "p50", "p90", "prob_target"):
        assert lo[key] <= mid[key] <= hi[key], key                                        # same random numbers: monotone by construction
    assert lo["p10"] <= lo["p50"] <= lo["p90"] and a["win_rate_ci"][0] < a["win_rate"] < a["win_rate_ci"][1]


def test_target_already_reached_is_certain_and_no_quota_means_no_probability():
    assert forecast(OPEN, 27, 14, realized=200_000, quota=120_000)["scenarios"]["low"]["prob_target"] == 1.0
    assert "prob_target" not in forecast(OPEN, 27, 14)["scenarios"]["mid"]


def test_trials_shrink_with_many_open_deals_but_never_below_the_floor():
    assert trials_for(100) == spec.TRIALS and trials_for(20_000) == spec.MIN_TRIALS and trials_for(0) == spec.TRIALS
    assert forecast([1.0] * 100, 27, 14)["trials"] == spec.TRIALS


def test_ml_stays_off_and_says_what_is_missing():
    m = ml_status(closed=41)
    assert m["implemented"] is False and m["data_ready"] is False and len(m["missing"]) == 3
    assert ml_status(400, True, True)["missing"] == [] and ml_status(400, True, True)["implemented"] is False   # data alone is not enough: not built


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_typescript_port_gives_the_same_numbers_as_python_bit_for_bit():
    cases = [([100_000, 50_000, 20_000, 5_000, 0, 0], 27, 14, 30_000, 120_000), ([1_272_720, 540_000, 159_000, 152_000, 5_000], 6, 17, 0, None),
             ([5_000] * 173, 27, 14, 0, 500_000), ([250.0] * 60 + [1_000.0] * 40, 6, 4, 10_000, 40_000)]   # indicative sample, 100 deals
    script = (f"import {{ forecast, SPEC, mulberry32 }} from {TS.as_uri()!r};\n"
              f"const r = mulberry32(1); const out = {{spec: SPEC, rng: [r(), r(), r()], cases: {json.dumps(cases)}.map(([o, w, l, re, q]) => forecast(o, w, l, re, q))}};\n"
              "console.log(JSON.stringify(out));")
    res = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, env={"NODE_NO_WARNINGS": "1", "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"})
    assert res.returncode == 0, res.stderr
    ts = json.loads(res.stdout)
    assert ts["spec"] == spec.spec_json()
    r = mulberry32(1)
    assert ts["rng"] == [r(), r(), r()]
    for (o, w, lo_, re, q), t in zip(cases, ts["cases"], strict=True):
        py = forecast(o, w, lo_, re, q)
        assert t["status"] == py["status"] and t["trials"] == py["trials"] and t.get("backlog") == py.get("backlog")
        for name in ("low", "mid", "high"):
            for key, val in py["scenarios"][name].items():
                assert t["scenarios"][name][{"prob_target": "probTarget"}.get(key, key)] == pytest.approx(val, rel=1e-12), (name, key)


async def test_vega_answers_the_forecast_signed_and_never_invents_a_probability(ins):  # noqa: F811
    out = await ask(ins, "vou bater a meta esse mês?")
    b = out["body"]
    assert b.startswith("*Vega*:") and ("Ainda não há base para prever" in b or "Com base em" in b)
    assert "otimista" in b or "chute" in b                                          # the honest caveat is always there
    with ins[0].cursor() as cur:
        cur.execute("select agent, tool, status from app.agent_step order by id desc limit 1")
        assert (cur.fetchone()["agent"], "get_forecast") == ("vega", "get_forecast")
