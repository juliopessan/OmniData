"""Vela: proposal HTML/PDF generation. No network, no DB — pure rendering."""
from omnidata.proposals.pdf import render_pdf
from omnidata.proposals.template import render_html


def test_render_html_includes_deal_amount_and_summary():
    html = render_html("Acme – Renovação", "R$ 85.000", "Licença anual, 10 usuários.", "Ana Souza")
    assert "Acme" in html
    assert "R$ 85.000" in html
    assert "Licença anual, 10 usuários." in html
    assert "Ana Souza" in html


def test_render_pdf_produces_a_real_pdf():
    html = render_html("Acme – Renovação", "R$ 85.000", "Licença anual.", "Ana Souza")
    pdf = render_pdf(html)
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 1000
