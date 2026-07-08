"""qbo_oauth_reconnect.py - reconnect one QBO sandbox realm via OAuth.

Usage:
    python scripts/qbo_oauth_reconnect.py --realm A
    python scripts/qbo_oauth_reconnect.py --realm B
    python scripts/qbo_oauth_reconnect.py --realm B --redirect-uri "https://..." --manual-callback
    python scripts/qbo_oauth_reconnect.py --realm B --callback-url "http://localhost:8765/callback?..."

This opens the Intuit consent page, receives the localhost callback, exchanges
the authorization code, persists the new refresh token, then runs a read-only
CompanyInfo sanity check. Token values are never printed.
"""

import base64
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from qbo_common import (
    OAUTH_TOKEN_URL,
    TOKEN_CACHE,
    Realm,
    _persist_rotated_refresh_token,
    _register_secret,
    audit,
    guard_sandbox,
    load_env,
    redact,
)


AUTH_URL = "https://appcenter.intuit.com/connect/oauth2"
DEFAULT_SCOPE = "com.intuit.quickbooks.accounting"
DEFAULT_REDIRECT_URI = "http://localhost:8765/callback"


class CallbackHandler(BaseHTTPRequestHandler):
    result = {}

    def log_message(self, fmt, *args):  # noqa: D401 - suppress noisy HTTP logs.
        return

    def do_GET(self):  # noqa: N802 - stdlib callback name.
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        CallbackHandler.result = {k: v[0] for k, v in params.items()}
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<html><body><h1>QBO reconnect captured.</h1>"
            b"<p>You can return to Codex now.</p></body></html>"
        )


def _arg(name):
    if name not in sys.argv:
        return None
    try:
        return sys.argv[sys.argv.index(name) + 1]
    except IndexError:
        sys.exit(f"FATAL: {name} requires a value")


def _has_flag(name):
    return name in sys.argv


def _listen_once(redirect_uri, timeout_seconds=300):
    parsed = urllib.parse.urlparse(redirect_uri)
    if parsed.scheme != "http" or parsed.hostname not in ("localhost", "127.0.0.1"):
        sys.exit("FATAL: this local reconnect helper only supports localhost http redirect URIs.")
    server = HTTPServer((parsed.hostname, parsed.port or 80), CallbackHandler)
    server.timeout = timeout_seconds
    server.handle_request()
    server.server_close()
    if not CallbackHandler.result:
        sys.exit("FATAL: timed out waiting for Intuit OAuth callback.")
    return CallbackHandler.result


def _manual_callback():
    print("After Intuit redirects, paste the full callback URL here.")
    print("The URL must include code=..., state=..., and realmId=....")
    raw = input("Callback URL: ").strip()
    parsed = urllib.parse.urlparse(raw)
    params = urllib.parse.parse_qs(parsed.query)
    if not params and raw.startswith("code="):
        params = urllib.parse.parse_qs(raw)
    return {k: v[0] for k, v in params.items()}


def _parse_callback_url(raw):
    parsed = urllib.parse.urlparse(raw.strip())
    params = urllib.parse.parse_qs(parsed.query)
    if not params and raw.startswith("code="):
        params = urllib.parse.parse_qs(raw)
    return {k: v[0] for k, v in params.items()}


def _exchange_code(env, code, redirect_uri):
    client_id = env.get("QB_CLIENT_ID", "")
    client_secret = env.get("QB_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        sys.exit("FATAL: QB_CLIENT_ID and QB_CLIENT_SECRET must be set in .env")
    _register_secret(client_secret)
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    data = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }
    ).encode()
    req = urllib.request.Request(
        OAUTH_TOKEN_URL,
        data=data,
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"token exchange failed: HTTP {e.code}: {redact(body)}") from e


def _save_cache(realm_id, token):
    cache = {}
    if os.path.exists(TOKEN_CACHE):
        try:
            with open(TOKEN_CACHE, encoding="utf-8") as f:
                cache = json.load(f)
        except (json.JSONDecodeError, OSError):
            cache = {}
    expires_at = time.time() + int(token.get("expires_in", 3600)) - 120
    cache[realm_id] = {
        "access_token": token["access_token"],
        "expires_at": expires_at,
        "refresh_token": token["refresh_token"],
    }
    with open(TOKEN_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f)


def main():
    realm_key = (_arg("--realm") or "").upper()
    if realm_key not in ("A", "B"):
        sys.exit("FATAL: pass --realm A or --realm B")

    env = load_env()
    guard_sandbox(env)
    realm = Realm(realm_key, env)
    redirect_uri = _arg("--redirect-uri") or env.get("QB_REDIRECT_URI", DEFAULT_REDIRECT_URI)
    manual_callback = _has_flag("--manual-callback")
    callback_url = _arg("--callback-url")
    state = secrets.token_urlsafe(32)
    scope = env.get("QB_SCOPE", DEFAULT_SCOPE)
    auth_url = AUTH_URL + "?" + urllib.parse.urlencode(
        {
            "client_id": env["QB_CLIENT_ID"],
            "scope": scope,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
        }
    )

    if callback_url:
        callback = _parse_callback_url(callback_url)
    else:
        print(f"Opening Intuit authorization for {realm.label}.")
        print(f"Redirect URI must be registered in the Intuit app: {redirect_uri}")
        if manual_callback:
            print("Manual callback mode is ON; paste the final redirected URL back here.")
        print("If the browser does not open, paste this URL into the browser:")
        print(auth_url)
        if os.name == "nt":
            os.startfile(auth_url)  # noqa: S606 - intentional user-facing browser launch.
        else:
            webbrowser.open(auth_url)
        callback = _manual_callback() if manual_callback else _listen_once(redirect_uri)

    if not callback_url and callback.get("state") != state:
        sys.exit("FATAL: OAuth state mismatch; token was not saved.")
    if callback.get("error"):
        sys.exit(f"FATAL: Intuit returned OAuth error: {callback.get('error')}")
    returned_realm = callback.get("realmId", "")
    if returned_realm != realm.realm_id:
        sys.exit(
            f"FATAL: selected realmId {returned_realm or '[missing]'} does not match "
            f"{realm.label}; token was not saved."
        )

    token = _exchange_code(env, callback.get("code", ""), redirect_uri)
    _register_secret(token.get("access_token"))
    _register_secret(token.get("refresh_token"))
    _persist_rotated_refresh_token(realm.refresh_env_key, token["refresh_token"])
    _save_cache(realm.realm_id, token)
    audit({"event": "oauth_reconnect_ok", "realm": realm.key, "realm_id": realm.realm_id})

    ok, name = realm.assert_company()
    print(f"{realm.label}: reconnect OK - company '{name}' "
          f"({'matches expected' if ok else 'NAME MISMATCH'})")


if __name__ == "__main__":
    main()
