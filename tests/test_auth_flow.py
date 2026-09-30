import io
from threading import Event
from unittest.mock import Mock

import pytest
from spotipy.cache_handler import MemoryCacheHandler

from exporter.api import Cancelled, ExportError
from exporter.auth import authenticate


@pytest.fixture
def auth_stubs(monkeypatch):
    options = {}
    manager = Mock()
    manager.get_authorize_url.return_value = "https://accounts.spotify.com/authorize?fake"

    def factory(**kwargs):
        options.update(kwargs)
        return manager

    monkeypatch.setattr("exporter.auth.SpotifyPKCE", factory)
    client = Mock()
    monkeypatch.setattr("exporter.auth.spotipy.Spotify", client)
    servers = []

    class Server:
        def __init__(self, address, handler):
            assert address == ("127.0.0.1", 8888)
            self.handler = handler
            self.closed = False
            servers.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.closed = True

        def handle_request(self):
            handler = self.handler.__new__(self.handler)
            handler.path = f"/callback?state={options['state']}&code=mock_code"
            handler.send_response = Mock()
            handler.send_header = Mock()
            handler.end_headers = Mock()
            handler.wfile = io.BytesIO()
            handler.do_GET()

    monkeypatch.setattr("exporter.auth.HTTPServer", Server)
    return manager, client, options, servers


def test_mocked_pkce_flow_uses_memory_cache(auth_stubs):
    manager, client, options, servers = auth_stubs
    authenticate("client", Event(), open_browser=lambda url: True)
    manager.get_access_token.assert_called_once_with(code="mock_code", check_cache=False)
    assert isinstance(options["cache_handler"], MemoryCacheHandler)
    assert "client_secret" not in options and len(options["state"]) >= 32
    assert client.call_args.kwargs["retries"] == 0
    assert all(server.closed for server in servers)


def test_cancel_then_restart_auth(auth_stubs):
    manager, client, options, servers = auth_stubs
    cancel = Event()

    def cancel_browser(url):
        cancel.set()
        return True

    with pytest.raises(Cancelled):
        authenticate("client", cancel, open_browser=cancel_browser)
    manager.get_access_token.assert_not_called()
    authenticate("client", Event(), open_browser=lambda url: True)
    manager.get_access_token.assert_called_once()
    assert all(server.closed for server in servers)


def test_login_timeout_releases_port(auth_stubs):
    with pytest.raises(ExportError, match="timed out"):
        authenticate("client", Event(), timeout=0, open_browser=lambda url: True)
    assert auth_stubs[3][0].closed
    auth_stubs[0].get_access_token.assert_not_called()


def test_browser_failure_releases_port(auth_stubs):
    with pytest.raises(ExportError, match="browser"):
        authenticate("client", Event(), open_browser=lambda url: False)
    assert auth_stubs[3][0].closed
