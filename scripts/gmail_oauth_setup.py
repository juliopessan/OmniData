#!/usr/bin/env python
"""One-time setup: get a Gmail API refresh token for Vela's e-mail sending (mailer/gmail.py::GmailApiSender).

  export GMAIL_CLIENT_ID=...           # Google Cloud Console -> APIs & Services -> Credentials -> OAuth client
  export GMAIL_CLIENT_SECRET=...       # never paste these into a chat or commit them
  uv run python scripts/gmail_oauth_setup.py

Starts a local HTTP listener, prints a Google consent URL — open it YOURSELF in your own browser (this script never
sees your Google password), sign in as the account that should send proposals, and approve the "send e-mail" scope.
Google redirects back to this local listener with a one-time code, which this script exchanges for a refresh token.
That refresh token is what goes into GMAIL_REFRESH_TOKEN in the deploy .env — it never expires unless revoked.

Needs the OAuth client's type to be "Desktop app" in Google Cloud Console (it accepts a loopback http://127.0.0.1
redirect on any port with no pre-registration). A "Web application" client will reject this with redirect_uri_mismatch;
add http://127.0.0.1:PORT_SHOWN_BELOW as an authorized redirect URI there instead, or create a Desktop app client."""
from __future__ import annotations

import http.server
import os
import sys
import threading
import urllib.parse
import webbrowser

import httpx

SCOPE = "https://www.googleapis.com/auth/gmail.send"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def main() -> None:
    client_id = os.environ.get("GMAIL_CLIENT_ID", "")
    client_secret = os.environ.get("GMAIL_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        print("Set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET first (see the module docstring).", file=sys.stderr)
        raise SystemExit(1)

    code_holder: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            qs = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(qs)
            if "code" in params:
                code_holder["code"] = params["code"][0]
                body = b"<html><body>Autorizado. Pode fechar esta aba e voltar ao terminal.</body></html>"
            else:
                body = b"<html><body>Sem 'code' na resposta. Confira o erro no terminal.</body></html>"
                code_holder["error"] = params.get("error", ["unknown"])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a: object) -> None:  # silence the default stderr access log
            pass

    port = int(os.environ.get("GMAIL_OAUTH_PORT", "8765"))
    server = http.server.HTTPServer(("127.0.0.1", port), Handler)
    redirect_uri = f"http://127.0.0.1:{port}"

    auth_url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent"})

    print(f"\nAbra esta URL no SEU navegador (faça login com a conta que vai mandar as propostas) e aprove:\n\n{auth_url}\n")
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass  # headless environment: the user just copies the URL above

    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    thread.join(timeout=300)
    server.server_close()

    if "error" in code_holder:
        print(f"Google recusou: {code_holder['error']}", file=sys.stderr)
        raise SystemExit(1)
    if "code" not in code_holder:
        print("Tempo esgotado esperando a autorização (5 min).", file=sys.stderr)
        raise SystemExit(1)

    r = httpx.post(TOKEN_URL, data={"client_id": client_id, "client_secret": client_secret, "code": code_holder["code"],
                                    "grant_type": "authorization_code", "redirect_uri": redirect_uri}, timeout=20)
    if r.status_code >= 400:
        print(f"Erro trocando o código por token: {r.status_code} {r.text}", file=sys.stderr)
        raise SystemExit(1)
    d = r.json()
    refresh_token = d.get("refresh_token")
    if not refresh_token:
        print("Google não devolveu refresh_token (provavelmente essa conta já autorizou este app antes sem "
              "'prompt=consent' surtir efeito). Revogue o acesso em myaccount.google.com/permissions e rode de novo.",
              file=sys.stderr)
        raise SystemExit(1)
    print(f"\nGMAIL_REFRESH_TOKEN={refresh_token}\n\nGuarde isso no .env (nunca em um chat ou commit).")


if __name__ == "__main__":
    main()
