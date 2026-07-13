"""One-time TickTick OAuth2 (authorization-code) flow with a local callback server."""
from __future__ import annotations

import json
import secrets
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx

AUTHORIZE_URL = "https://ticktick.com/oauth/authorize"
TOKEN_URL = "https://ticktick.com/oauth/token"
SCOPE = "tasks:write tasks:read"


class _CallbackHandler(BaseHTTPRequestHandler):
    code: str | None = None
    state: str | None = None

    def do_GET(self) -> None:  # noqa: N802
        qs = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        _CallbackHandler.code = params.get("code", [None])[0]
        _CallbackHandler.state = params.get("state", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(
            b"<h2>doing2done: TickTick connected.</h2>"
            b"<p>You can close this tab and return to the terminal.</p>"
        )

    def log_message(self, *args: object) -> None:  # silence
        return


def _callback_port(redirect_uri: str) -> int:
    return urllib.parse.urlparse(redirect_uri).port or 8080


def authorize(client_id: str, client_secret: str, redirect_uri: str, token_path: str) -> dict:
    """Run the interactive flow once; persist and return the token dict."""
    state = secrets.token_urlsafe(16)
    auth_url = AUTHORIZE_URL + "?" + urllib.parse.urlencode(
        {
            "client_id": client_id,
            "scope": SCOPE,
            "state": state,
            "redirect_uri": redirect_uri,
            "response_type": "code",
        }
    )

    port = _callback_port(redirect_uri)
    server = HTTPServer(("localhost", port), _CallbackHandler)
    t = threading.Thread(target=server.handle_request, daemon=True)
    t.start()

    print(f"Opening browser to authorize TickTick...\n  {auth_url}")
    webbrowser.open(auth_url)
    t.join(timeout=300)
    server.server_close()

    code = _CallbackHandler.code
    if not code:
        raise RuntimeError("No authorization code received (timed out or denied).")
    if _CallbackHandler.state != state:
        raise RuntimeError("OAuth state mismatch — aborting for safety.")

    resp = httpx.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "scope": SCOPE,
            "redirect_uri": redirect_uri,
        },
        auth=(client_id, client_secret),
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.json()
    Path(token_path).write_text(json.dumps(token, indent=2))
    print(f"Token saved -> {token_path}")
    return token


def load_token(token_path: str) -> dict | None:
    p = Path(token_path)
    if not p.exists():
        return None
    return json.loads(p.read_text())


def refresh(client_id: str, client_secret: str, token_path: str) -> dict | None:
    """Refresh the access token using the stored refresh_token, if present."""
    tok = load_token(token_path)
    if not tok or "refresh_token" not in tok:
        return None
    resp = httpx.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": tok["refresh_token"],
            "scope": SCOPE,
        },
        auth=(client_id, client_secret),
        timeout=30,
    )
    if resp.status_code != 200:
        return None
    new = resp.json()
    new.setdefault("refresh_token", tok["refresh_token"])
    Path(token_path).write_text(json.dumps(new, indent=2))
    return new
