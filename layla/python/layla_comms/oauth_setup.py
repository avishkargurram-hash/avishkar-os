"""One-time helper, run on your own machine (not the server).

Usage: python -m layla_comms.oauth_setup <client_id> <client_secret>
Opens Google's consent page, catches the redirect on localhost, prints the
refresh token to store as GMAIL_REFRESH_TOKEN.
"""

from __future__ import annotations

import http.server
import json
import sys
import urllib.parse
import urllib.request
import webbrowser

SCOPE = "https://www.googleapis.com/auth/gmail.modify"
PORT = 8765


def main(client_id: str, client_secret: str) -> int:
    redirect = f"http://localhost:{PORT}/"
    got = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            got["code"] = (q.get("code") or [""])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Done. You can close this tab.")

        def log_message(self, *a):
            pass

    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect, "response_type": "code",
        "scope": SCOPE, "access_type": "offline", "prompt": "consent"})
    print("Opening browser; if nothing opens, visit:\n" + url)
    webbrowser.open(url)
    srv = http.server.HTTPServer(("localhost", PORT), H)
    srv.handle_request()
    if not got.get("code"):
        print("No authorization code received.")
        return 1
    data = urllib.parse.urlencode({
        "code": got["code"], "client_id": client_id, "client_secret": client_secret,
        "redirect_uri": redirect, "grant_type": "authorization_code"}).encode()
    with urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token", data=data)) as r:
        tok = json.loads(r.read())
    if "refresh_token" not in tok:
        print("No refresh token returned; revoke the app at myaccount.google.com/permissions and retry.")
        return 1
    print("\nGMAIL_REFRESH_TOKEN=" + tok["refresh_token"])
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
