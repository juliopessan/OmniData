"""Vela: proposal HTML/PDF generation. No network, no DB — pure rendering."""
from datetime import date

from omnidata.proposals.pdf import render_pdf
from omnidata.proposals.template import (
    brl_full,
    client_name,
    file_slug,
    logo_data_uri,
    render_html,
    scope_blocks,
    scope_front,
)


def test_client_name_never_carries_the_crm_tag():
    assert client_name("Uniconte [Tax Partner_Licenciamento]") == "Uniconte"
    assert client_name("SOS Reforma<>FIND [Tax_Partner_Licenciamento]") == "SOS Reforma"
    assert client_name("Ágere TI -[Tax partners_Licenciamento]") == "Ágere TI"
    assert client_name("Acme – Renovação") == "Acme"
    assert client_name("TPC Group - Novo(a) Deal") == "TPC Group"
    assert client_name("Invent Software") == "Invent Software"


def test_scope_front_reads_the_bracketed_demand_and_ignores_crm_noise():
    assert scope_front("Uniconte [Tax Partner_Licenciamento]") == "Tax Partner Licenciamento"
    assert scope_front("TPC Group - Novo(a) Deal") is None
    assert scope_front("Invent Software") is None


def test_scope_blocks_splits_prose_from_items():
    paras, items = scope_blocks("Parceria na vitrine.\n- Anuidade de exposição\n• Comissionamento de 15%\n\nBriefings.")
    assert paras == ["Parceria na vitrine.", "Briefings."]
    assert items == ["Anuidade de exposição", "Comissionamento de 15%"]


def test_brl_full_states_cents():
    assert brl_full(5000) == "R$ 5.000,00"
    assert brl_full(1234567.5) == "R$ 1.234.567,50"


def test_file_slug_is_ascii_and_uses_the_clean_client():
    assert file_slug("Ágere TI -[Tax partners_Licenciamento]") == "agere-ti"


def test_missing_or_unsupported_logo_falls_back_to_the_monogram(tmp_path):
    assert logo_data_uri("") is None
    assert logo_data_uri(str(tmp_path / "nope.png")) is None
    (tmp_path / "logo.gif").write_bytes(b"GIF89a")
    assert logo_data_uri(str(tmp_path / "logo.gif")) is None
    (tmp_path / "logo.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    assert logo_data_uri(str(tmp_path / "logo.svg")).startswith("data:image/svg+xml;base64,")


def test_render_html_is_client_facing():
    html = render_html("Uniconte [Tax Partner_Licenciamento]", 5000, "Parceria.\n- Anuidade\n- Comissão", "Ana Souza",
                       company_name="Find", today=date(2026, 9, 25), ref="3F2A9C1B")
    assert "[Tax Partner" not in html  # the pipeline tag never reaches the client
    assert "R$ 5.000,00" in html and "Ana Souza" in html and "Find" in html
    assert "10/10/2026" in html  # valid 15 days
    assert "3F2A9C1B" in html
    assert "nunca escreve o número" not in html  # internal product copy has no place in a client document


def test_render_pdf_produces_a_real_pdf():
    html = render_html("Acme – Renovação", 85000, "Licença anual.", "Ana Souza")
    pdf = render_pdf(html)
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 1000
