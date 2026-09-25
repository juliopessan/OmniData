"""HTML -> PDF bytes (Vela), via WeasyPrint. Kept as its own function (not folded into template.py) so a caller
can render the HTML alone for a test or preview without paying WeasyPrint's render cost."""
from __future__ import annotations

from weasyprint import HTML


def render_pdf(html: str) -> bytes:
    return bytes(HTML(string=html).write_pdf())
