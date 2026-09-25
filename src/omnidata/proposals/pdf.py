"""HTML -> PDF bytes (Vela), via WeasyPrint. Kept as its own function (not folded into template.py) so a caller
can render the HTML alone for a test or preview without paying WeasyPrint's render cost.

`base_url` is the templates/ directory so proposal.html's @font-face rules (relative `url("fonts/...")`) resolve
to the bundled Inter Tight / IBM Plex Mono files (templates/fonts/) — the same faces the web app uses (see
web/src/app/layout.tsx) — instead of whatever generic sans happens to be installed on the host. Without this, a
PDF generated on the Debian container (no fonts package beyond WeasyPrint's own deps) falls back to a font that
looks nothing like the brand."""
from __future__ import annotations

from pathlib import Path

from weasyprint import HTML

TEMPLATES_DIR = Path(__file__).parent / "templates"


def render_pdf(html: str) -> bytes:
    return bytes(HTML(string=html, base_url=str(TEMPLATES_DIR)).write_pdf())
