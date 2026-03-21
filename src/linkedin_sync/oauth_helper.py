#!/usr/bin/env python3
"""Helper script to obtain a LinkedIn OAuth2 access token.

This implements the 3-legged OAuth2 flow for LinkedIn:
1. Opens a browser for user authorization
2. Starts a local HTTP server to receive the callback
3. Exchanges the authorization code for an access token
4. Prints the access token for you to save

Usage:
    python oauth_helper.py

Requires LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET environment variables.
"""

import http.server
import os
import sys
import threading
import urllib.parse
import webbrowser

import requests
from dotenv import load_dotenv

load_dotenv()

AUTHORIZATION_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
REDIRECT_PORT = 8585
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"
SCOPES = ["openid", "profile", "w_member_social"]


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler that captures the OAuth callback."""

    auth_code = None
    error = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            OAuthCallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h1>Authorization successful!</h1>"
                b"<p>You can close this window and return to the terminal.</p>"
                b"</body></html>"
            )
        elif "error" in params:
            OAuthCallbackHandler.error = params.get(
                "error_description", params["error"]
            )[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                f"<html><body><h1>Authorization failed</h1>"
                f"<p>{OAuthCallbackHandler.error}</p></body></html>".encode()
            )
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress default logging


def get_access_token():
    """Run the full OAuth2 flow and return an access token."""
    client_id = os.environ.get("LINKEDIN_CLIENT_ID")
    client_secret = os.environ.get("LINKEDIN_CLIENT_SECRET")

    if not client_id or not client_secret:
        print(
            "ERROR: Set LINKEDIN_CLIENT_ID and"
            " LINKEDIN_CLIENT_SECRET env vars."
        )
        print(
            "See SETUP.md for instructions on"
            " creating a LinkedIn Developer App."
        )
        sys.exit(1)

    # Step 1: Build authorization URL
    auth_params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
    }
    auth_url = f"{AUTHORIZATION_URL}?{urllib.parse.urlencode(auth_params)}"

    # Step 2: Start local server for callback
    server = http.server.HTTPServer(
        ("localhost", REDIRECT_PORT), OAuthCallbackHandler
    )
    server_thread = threading.Thread(target=server.handle_request)
    server_thread.start()

    # Step 3: Open browser for authorization
    print("\nOpening browser for LinkedIn authorization...")
    print("If the browser doesn't open, visit this URL manually:\n")
    print(f"  {auth_url}\n")
    webbrowser.open(auth_url)

    # Step 4: Wait for callback
    print("Waiting for authorization callback...")
    server_thread.join(timeout=120)
    server.server_close()

    if OAuthCallbackHandler.error:
        print(f"\nAuthorization failed: {OAuthCallbackHandler.error}")
        sys.exit(1)

    if not OAuthCallbackHandler.auth_code:
        print("\nTimeout waiting for authorization. Please try again.")
        sys.exit(1)

    auth_code = OAuthCallbackHandler.auth_code
    print("Authorization code received. Exchanging for access token...")

    # Step 5: Exchange code for access token
    token_data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id,
        "client_secret": client_secret,
    }

    resp = requests.post(TOKEN_URL, data=token_data)
    if resp.status_code != 200:
        print(f"\nToken exchange failed: {resp.status_code}")
        print(resp.text)
        sys.exit(1)

    token_info = resp.json()
    access_token = token_info["access_token"]
    expires_in = token_info.get("expires_in", "unknown")

    print("\nAccess token obtained successfully!")
    print(
        f"Expires in: {expires_in} seconds ({int(expires_in) // 86400} days)"
    )
    print("\nYour access token:\n")
    print(f"  {access_token}")
    print("\nAdd this to your .env file:")
    print(f'  LINKEDIN_ACCESS_TOKEN="{access_token}"')

    # Step 6: Fetch person URN
    print("\nFetching your LinkedIn person URN...")
    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": "202602",
    }
    me_resp = requests.get("https://api.linkedin.com/rest/me", headers=headers)
    if me_resp.status_code == 200:
        me_data = me_resp.json()
        person_id = me_data.get("id", "")
        person_urn = f"urn:li:person:{person_id}"
        first = me_data.get("localizedFirstName", "")
        last = me_data.get("localizedLastName", "")
        name = f"{first} {last}".strip()
        print(f"  Authenticated as: {name}")
        print(f"  Person URN: {person_urn}")
        print(f'\n  LINKEDIN_PERSON_URN="{person_urn}"')
    else:
        print(f"  Could not fetch profile: {me_resp.status_code}")
        print("  You'll need to find your person URN manually.")

    return access_token


if __name__ == "__main__":
    get_access_token()
