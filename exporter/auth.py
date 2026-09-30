"""Desktop PKCE: no client secret, no disk token cache, bounded loopback login."""

import secrets
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import spotipy
from spotipy.cache_handler import MemoryCacheHandler
from spotipy.oauth2 import SpotifyPKCE

from .api import ExportError, check_cancelled
from .logging_utils import protect_transport_logs

REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPE = "playlist-read-private playlist-read-collaborative"


def callback_code(path, state):
    parsed = urlparse(path)
    query = parse_qs(parsed.query)
    if parsed.path != "/callback" or not secrets.compare_digest(
        query.get("state", [""])[0].encode("utf-8"), state.encode("utf-8")
    ):
        raise ValueError("Invalid callback")
    if "error" in query:
        raise ExportError("Spotify authorization was declined. You can try again.")
    code = query.get("code", [""])[0]
    if not code:
        raise ValueError("Missing authorization code")
    return code


def authenticate(client_id, cancel, timeout=180, open_browser=None):
    protect_transport_logs()
    check_cancelled(cancel)
    open_browser = open_browser or webbrowser.open
    state = secrets.token_urlsafe(32)
    manager = SpotifyPKCE(
        client_id=client_id,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE,
        state=state,
        cache_handler=MemoryCacheHandler(),
        requests_timeout=30,
        open_browser=False,
    )
    result = {}

    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Authorization codes must never enter logs.

        def do_GET(self):
            try:
                result["code"] = callback_code(self.path, state)
            except ValueError:
                self.send_error(400, "Invalid OAuth callback")
                return
            except ExportError as exc:
                result["error"] = exc
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"You can close this tab and return to Spotify Exporter.")

    class LoopbackServer(HTTPServer):
        def get_request(self):
            connection, address = super().get_request()
            connection.settimeout(1)
            return connection, address

    try:
        server = LoopbackServer(("127.0.0.1", 8888), Callback)
    except OSError:
        raise ExportError(
            "Cannot listen on 127.0.0.1:8888. Close other Spotify login windows and try again."
        ) from None
    with server:
        server.timeout = 0.25
        if not open_browser(manager.get_authorize_url()):
            raise ExportError("Could not open your browser. Set a default browser and try again.")
        deadline = time.monotonic() + timeout
        while not result:
            check_cancelled(cancel)
            if time.monotonic() >= deadline:
                raise ExportError("Spotify login timed out. Click Connect to try again.")
            server.handle_request()
    check_cancelled(cancel)
    if "error" in result:
        raise result["error"]
    manager.get_access_token(code=result["code"], check_cache=False)
    check_cancelled(cancel)
    return spotipy.Spotify(
        auth_manager=manager,
        requests_timeout=(5, 30),
        retries=0,
        status_retries=0,
        backoff_factor=0,
    )
