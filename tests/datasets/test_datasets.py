"""Dataset upload: parsing, validation, import. Fixture = a real HubSpot pt-BR export (synthetic data), BOM + CRLF."""
from pathlib import Path

import pytest

from omnidata.datasets import coerce
from omnidata.datasets.importer import ImportOptions, import_file
from omnidata.datasets.parse import UploadError, read_table
from omnidata.datasets.spec import DEALS, KINDS, QUOTAS, norm, spec_json
from omnidata.datasets.validate import validate

FX = Path(__file__).parent / "fixtures" / "hubspot_deals_sample.csv"
DATA = FX.read_bytes()


def check(kind, data, name="x.csv", **kw):
    return validate(KINDS[kind], read_table(data, name), name, data, **kw)


# ---------- parsing ----------
def test_hubspot_export_is_read_with_bom_and_crlf():
    t = read_table(DATA, "deals.csv")
    assert t.encoding == "utf-8-sig" and t.delimiter == "," and t.headers[0] == "ID do registro" and len(t.rows) == 63


def test_semicolon_and_windows1252_files_are_read():
    raw = "ID;Nome;Etapa\r\n1;Café Ltda;Qualificação\r\n".encode("cp1252")
    t = read_table(raw, "a.csv")
    assert t.delimiter == ";" and t.encoding == "cp1252" and t.rows[0][1] == "Café Ltda"


@pytest.mark.parametrize("data,name,code", [
    (b"", "a.csv", "empty"), (b"   \n", "a.csv", "empty"), (b"\x00\x01\x02binary", "a.csv", "binary"),
    (b"\xd0\xcf\x11\xe0legacy", "a.xls", "legacy_xls"), (b"a,b\n1,2\n", "a.pdf", "bad_type"),
    (b"a,b\n" + b"1,2\n" * 5, "a.csv", "too_many_rows"), (b"x" * 200, "a.csv", "too_big"),
])
def test_whole_file_rejections(data, name, code):
    with pytest.raises(UploadError) as e:
        read_table(data, name, max_bytes=100, max_rows=3)
    assert e.value.code == code


def test_xlsx_is_supported(tmp_path):
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active
    ws.append(["ID do registro", "Nome do negócio", "Etapa do negócio", "Valor", "Data de fechamento"])
    ws.append([1, "Acme", "Fechado ganho", 1500.5, __import__("datetime").datetime(2026, 5, 3)])
    p = tmp_path / "d.xlsx"; wb.save(p)
    rep, rows = check("deals", p.read_bytes(), "d.xlsx")
    assert rep.ok and rows[0]["status"] == "won" and str(rows[0]["amount"]) == "1500.50" and rep.encoding == "xlsx"


def test_fake_xlsx_is_rejected_cleanly():
    with pytest.raises(UploadError) as e:
        read_table(b"PK\x03\x04garbage", "a.xlsx")
    assert e.value.code == "bad_xlsx"


# ---------- coercion ----------
@pytest.mark.parametrize("raw,expected", [("78500", "78500.00"), ("R$ 1.234,56", "1234.56"), ("1,234.56", "1234.56"), ("1.234", "1234.00"),
                                          ("1,5", "1.50"), ("12,345", "12345.00"), ("(10)", None)])
def test_amounts_pt_br_and_en(raw, expected):
    if expected is None:
        with pytest.raises(ValueError):
            coerce.parse_amount(raw)
    else:
        assert str(coerce.parse_amount(raw)) == expected


def test_amount_rejects_garbage_and_negative():
    for bad in ("abc", "-5", "1e99"):
        with pytest.raises(ValueError):
            coerce.parse_amount(bad)


def test_dates_are_sao_paulo_local_then_utc():
    assert coerce.parse_datetime("2026-04-05").isoformat() == "2026-04-05T03:00:00+00:00"
    assert coerce.parse_datetime("05/04/2026 14:00").isoformat() == "2026-04-05T17:00:00+00:00"
    assert coerce.parse_datetime("2026-04-05T10:00:00Z").isoformat() == "2026-04-05T10:00:00+00:00"
    with pytest.raises(ValueError):
        coerce.parse_datetime("31/31/2026")


def test_stage_classification_and_order_hints():
    assert [coerce.classify_stage(s) for s in ("Fechado ganho", "Closed Won", "Fechado perdido", "Negociação", "Winner")] == ["won", "won", "lost", "open", "open"]
    order = sorted(["Contrato enviado", "Negociação", "Qualificação", "Proposta enviada", "Reunião agendada", "Apresentação agendada"], key=coerce.stage_rank)
    assert order == ["Qualificação", "Reunião agendada", "Apresentação agendada", "Proposta enviada", "Negociação", "Contrato enviado"]


# ---------- validation ----------
def test_real_export_maps_every_column_and_is_valid():
    rep, rows = check("deals", DATA)
    assert rep.ok and rep.valid_rows == rep.total_rows == 63 and not rep.ignored_columns
    assert rep.mapping["owner"] == "Proprietário do negócio" and rep.unstored_columns == ["Pontuação do negócio"]
    assert rep.stage_order[0] == "Qualificação" and rep.stage_order[-1] == "Contrato enviado"
    s = rep.summary
    assert s["open"] + s["won"] + s["lost"] == 63 and s["lost_with_reason"] == s["lost"] and s["lost_reason_coverage"] == 1.0


def test_loss_reason_is_extracted_from_notes_only_for_lost_deals():
    rep, rows = check("deals", DATA)
    lost = [r for r in rows if r["status"] == "lost"]
    assert lost and all(r["lost_reason"] for r in lost) and all(r["lost_reason"] is None for r in rows if r["status"] != "lost")
    assert not any(r["lost_reason"].endswith(".") for r in lost)


def test_missing_required_column_is_reported_without_reading_rows():
    rep, rows = check("deals", "Nome do negócio,Valor\nAcme,10\n".encode())
    assert rep.missing_required == ["id", "stage"] and rows == [] and not rep.ok


def test_row_errors_carry_line_and_header():
    csv_ = ("ID do registro,Nome do negócio,Etapa do negócio,Valor,Data de fechamento\n"
            "1,Acme,Qualificação,abc,\n"              # line 2: bad amount
            "2,,Proposta enviada,100,\n"              # line 3: empty name
            "1,Dup,Qualificação,5,\n"                 # line 4: duplicate id
            "4,Fechada,Fechado ganho,5,\n").encode()  # line 5: closed without close date
    rep, rows = check("deals", csv_)
    got = {(e.line, e.column) for e in rep.errors}
    assert {(2, "Valor"), (3, "Nome do negócio"), (4, "ID do registro"), (5, "Data de fechamento")} <= got
    assert rows == [] and rep.error_count == 4 and not rep.ok


def test_error_list_is_capped_but_counted():
    body = "ID do registro,Nome do negócio,Etapa do negócio,Valor\n" + "".join(f"{i},N,Qualificação,zzz\n" for i in range(500))
    rep, _ = check("deals", body.encode())
    assert rep.error_count == 500 and len(rep.errors) == 200


def test_unknown_columns_are_never_imported_and_are_reported():
    rep, rows = check("deals", "ID,Nome,Etapa,Telefone,CPF\n1,Acme,Qualificação,11999999999,123.456.789-09\n".encode())
    assert rep.ok and rep.ignored_columns == ["Telefone", "CPF"] and all("Telefone" not in r and "CPF" not in r for r in rows)


def test_stage_order_override_and_unknown_stage_warning():
    rep, _ = check("deals", DATA, stage_order=["Contrato enviado", "Inexistente"])
    assert rep.stage_order[0] == "Contrato enviado" and any("Inexistente" in w for w in rep.warnings)


def test_status_column_overrides_stage_label():
    rep, rows = check("deals", "ID,Nome,Etapa,Status,Data de fechamento\n1,A,Negociação,ganho,2026-01-05\n".encode())
    assert rep.ok and rows[0]["status"] == "won"


def test_quotas_validation():
    good = "Proprietário,Início do período,Fim do período,Meta\nAna Souza,2026-09-01,2026-09-30,\"R$ 100.000,00\"\n".encode()
    rep, rows = check("quotas", good)
    assert rep.ok and str(rows[0]["amount"]) == "100000.00" and str(rows[0]["period_end"]) == "2026-09-30"
    bad = ("Proprietário,Início,Fim,Meta\nAna,2026-09-30,2026-09-01,10\nAna,2026-09-01,2026-09-30,10\nAna,2026-09-01,2026-09-30,10\n").encode()
    rep, _ = check("quotas", bad)
    assert rep.error_count == 2


def test_spec_json_matches_web_copy():
    import json
    web = json.loads((Path(__file__).parents[2] / "web/src/lib/dataset-spec.json").read_text())
    assert web == json.loads(json.dumps(spec_json())), "run: uv run omnidata dataset spec > web/src/lib/dataset-spec.json"
    assert norm("Etapa do negócio") == "etapa do negocio" and DEALS.key == "deals" and QUOTAS.key == "quotas"


# ---------- import (needs Postgres) ----------
def counts(conn):
    with conn.cursor() as cur:
        cur.execute("select (select count(*) from silver.deal where hs_deal_id like 'up:%') d, (select count(*) from silver.activity where hs_deal_id like 'up:%') a,"
                    " (select count(*) from silver.owner where hs_owner_id like 'up:%') o, (select count(*) from silver.stage where hs_pipeline_id='upload') s")
        return dict(cur.fetchone())


def test_dry_run_writes_nothing(conn):
    r = import_file(conn, "deals", DATA, "d.csv", ImportOptions(dry_run=True))
    assert r.status == "validated" and counts(conn) == {"d": 0, "a": 0, "o": 0, "s": 0}
    with conn.cursor() as cur:
        cur.execute("select count(*) n from app.dataset_upload"); assert cur.fetchone()["n"] == 0


def test_import_populates_silver_and_serving_views(conn):
    r = import_file(conn, "deals", DATA, "d.csv", ImportOptions(dry_run=False))
    assert r.status == "imported" and r.imported["deals"] == 63 and r.upload_id
    c = counts(conn)
    assert c["d"] == 63 and c["s"] == 8 and c["o"] >= 1 and c["a"] > 63  # 6 open stages + won + lost; notes + next-step tasks
    with conn.cursor() as cur:
        cur.execute("select is_open, is_won, is_lost, lost_reason_hs, hs_stage_id from silver.deal where is_lost limit 1")
        lost = cur.fetchone()
        cur.execute("select count(*) n from serving.v_deal_health where hs_deal_id like 'up:%'"); healthy = cur.fetchone()["n"]
        cur.execute("select won_count, lost_count, won_amount from serving.v_rep_kpis where won_count > 0 limit 1"); k = cur.fetchone()
        cur.execute("select status, imported_rows, sha256 from app.dataset_upload"); up = cur.fetchone()
        cur.execute("select probability from silver.stage where hs_pipeline_id='upload' and not is_closed order by display_order")
        probs = [float(x["probability"]) for x in cur.fetchall()]
    assert lost["lost_reason_hs"] and lost["hs_stage_id"] == "up:lost" and not lost["is_open"]
    assert healthy == r.report.summary["open"] and k["won_amount"] > 0 and up["status"] == "imported" and up["imported_rows"] == 63
    assert probs == sorted(probs) and 0 < probs[0] < probs[-1] < 1   # later stages are likelier to close


def test_reimport_is_idempotent_and_replace_swaps_the_set(conn):
    opts = ImportOptions(dry_run=False)
    import_file(conn, "deals", DATA, "d.csv", opts)
    first = counts(conn)
    import_file(conn, "deals", DATA, "d.csv", opts)
    assert counts(conn) == first
    small = DATA.split(b"\r\n")
    small = b"\r\n".join(small[:4]) + b"\r\n"
    import_file(conn, "deals", small, "s.csv", ImportOptions(dry_run=False, replace=True))
    assert counts(conn)["d"] == 3


def test_owner_names_reuse_existing_hubspot_owners(conn):
    with conn.cursor() as cur:
        cur.execute("insert into silver.owner (hs_owner_id, first_name, last_name) values ('9001','Larissa','Menezes')")
    conn.commit()
    import_file(conn, "deals", DATA, "d.csv", ImportOptions(dry_run=False))
    with conn.cursor() as cur:
        cur.execute("select count(*) n from silver.deal where hs_owner_id='9001'"); assert cur.fetchone()["n"] > 0
        cur.execute("select count(*) n from silver.owner where hs_owner_id='up:larissa-menezes'"); assert cur.fetchone()["n"] == 0


def test_errors_block_import_unless_allow_partial(conn):
    bad = DATA + "999,Ruim,Qualificação,xyz,\r\n".encode()
    r = import_file(conn, "deals", bad, "b.csv", ImportOptions(dry_run=False))
    assert r.status == "rejected" and counts(conn)["d"] == 0
    with conn.cursor() as cur:
        cur.execute("select status, error_count from app.dataset_upload"); u = cur.fetchone()
    assert u["status"] == "rejected" and u["error_count"] == 1
    r2 = import_file(conn, "deals", bad, "b.csv", ImportOptions(dry_run=False, allow_partial=True))
    assert r2.status == "imported" and counts(conn)["d"] == 63


def test_notes_can_be_left_out(conn):
    import_file(conn, "deals", DATA, "d.csv", ImportOptions(dry_run=False, import_notes=False))
    with conn.cursor() as cur:
        cur.execute("select count(*) n from silver.activity where activity_type='note' and hs_deal_id like 'up:%'"); assert cur.fetchone()["n"] == 0


def test_quota_import_feeds_attainment(conn):
    import_file(conn, "deals", DATA, "d.csv", ImportOptions(dry_run=False))
    q = "Proprietário,Início do período,Fim do período,Meta\nLarissa Menezes,2026-06-01,2026-06-30,100000\n".encode()
    r = import_file(conn, "quotas", q, "q.csv", ImportOptions(dry_run=False))
    assert r.status == "imported"
    with conn.cursor() as cur:
        cur.execute("select quota_amount from serving.v_rep_kpis where quota_amount is not null"); assert int(cur.fetchone()["quota_amount"]) == 100000
