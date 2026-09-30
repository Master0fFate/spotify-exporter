from threading import Event
from unittest.mock import Mock

import pytest
import requests
from spotipy.exceptions import SpotifyException

from exporter.api import Cancelled, ExportError, SpotifyReader, retry_delay
from exporter.models import playlist_from_api, track_from_api

NEXT = "https://api.spotify.com/v1/playlists/p/items?offset=50"


def client(pages):
    sp = Mock()
    sp.playlist.return_value = {"snapshot_id": "stable"}
    sp.playlist_items.return_value = pages[0]
    sp.next.side_effect = pages[1:]
    return sp


def test_current_endpoint_and_legacy_payload_preserve_order():
    sp = client(
        [
            {
                "items": [{"item": {"name": "é", "type": "track"}}, {"track": {"name": "é"}}],
                "next": NEXT,
                "total": 3,
            },
            {"items": [{"item": None}], "next": None},
        ]
    )
    records = SpotifyReader(sp).tracks("p")
    assert [t.name for t in records] == ["é", "é", "Unavailable item"]
    assert [t.position for t in records] == [1, 2, 3]
    assert not records[-1].available
    sp.playlist_items.assert_called_once_with("p", limit=50)
    assert sp.playlist.call_count == 2


def test_extended_mode_is_explicit():
    sp = client([{"items": [], "next": None}])
    sp._get.return_value = {"items": [], "next": None}
    assert SpotifyReader(sp, legacy=True).tracks("p") == []
    sp._get.assert_called_once_with("playlists/p/tracks", limit=50)
    sp.playlist_items.assert_not_called()


def test_episode_local_and_missing_fields():
    record = track_from_api(
        {
            "item": {
                "type": "episode",
                "name": "Episode",
                "show": {"name": "Show"},
                "is_local": True,
                "is_playable": False,
                "duration_ms": None,
            }
        },
        7,
    )
    assert record.album == "Show" and record.artist == "Show"
    assert record.type == "episode" and record.is_local and not record.available
    assert record.duration_ms == 0 and record.url == ""


@pytest.mark.parametrize("summary", ["items", "tracks"])
def test_playlist_shapes(summary):
    p = playlist_from_api(
        {
            "id": "p",
            "owner": {"id": "owner", "display_name": None},
            summary: {"total": 12},
            "description": None,
        }
    )
    assert p.owner == "owner" and p.track_count == 12 and p.description == ""


def test_missing_playlist_contents_is_not_a_crash():
    assert playlist_from_api({"id": "p", "owner": None}).track_count == 0


@pytest.mark.parametrize(
    "page", [{}, {"items": None}, {"items": [None]}, {"items": [], "total": 2}]
)
def test_invalid_or_incomplete_page_fails(page):
    with pytest.raises(ExportError):
        SpotifyReader(client([page])).tracks("p")


def test_failed_second_page_does_not_return_partial_data():
    sp = client([{"items": [{"track": {"name": "first"}}], "next": NEXT}])
    sp.next.side_effect = SpotifyException(403, -1, "secret should not escape")
    with pytest.raises(ExportError, match="denied access"):
        SpotifyReader(sp).tracks("p")


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/steal",
        "http://api.spotify.com/v1/playlists/p/items",
        "https://api.spotify.com.evil/v1/x",
    ],
)
def test_pagination_url_guard(url):
    sp = client([{"items": [], "next": url}])
    with pytest.raises(ExportError, match="pagination URL"):
        SpotifyReader(sp).tracks("p")
    sp.next.assert_not_called()


def test_repeated_page_is_bounded():
    page = {"items": [], "next": NEXT}
    with pytest.raises(ExportError, match="repeated"):
        SpotifyReader(client([page, page])).tracks("p")


def test_changed_snapshot_fails():
    sp = client([{"items": [], "next": None}])
    sp.playlist.side_effect = [{"snapshot_id": "before"}, {"snapshot_id": "after"}]
    with pytest.raises(ExportError, match="changed"):
        SpotifyReader(sp).tracks("p")


def test_missing_snapshot_fails():
    sp = client([{"items": [], "next": None}])
    sp.playlist.return_value = {}
    with pytest.raises(ExportError, match="snapshot"):
        SpotifyReader(sp).tracks("p")


def fake_cancel():
    cancel = Mock()
    cancel.is_set.return_value = False
    cancel.wait.return_value = False
    return cancel


def test_rate_limit_honors_retry_after():
    cancel = fake_cancel()
    op = Mock(
        side_effect=[SpotifyException(429, -1, "limit", headers={"Retry-After": "12"}), {"ok": 1}]
    )
    assert SpotifyReader(Mock(), cancel).call(op) == {"ok": 1}
    cancel.wait.assert_called_once_with(12)


def test_retry_exhaustion_is_bounded():
    op = Mock(side_effect=requests.Timeout("private-url"))
    with pytest.raises(ExportError, match="after retries"):
        SpotifyReader(Mock(), fake_cancel()).call(op)
    assert op.call_count == 4


def test_403_never_retries_or_falls_back():
    sp = client([{}])
    sp.playlist_items.side_effect = SpotifyException(403, -1, "access_token=secret")
    with pytest.raises(ExportError) as error:
        SpotifyReader(sp).tracks("p")
    assert "secret" not in str(error.value)
    assert sp.playlist_items.call_count == 1
    sp._get.assert_not_called()


def test_quota_exceeded_does_not_retry():
    op = Mock(side_effect=SpotifyException(429, -1, "limit", reason="QUOTA_EXCEEDED"))
    with pytest.raises(ExportError, match="quota"):
        SpotifyReader(Mock(), fake_cancel()).call(op)
    assert op.call_count == 1


def test_long_wait_is_not_shortened():
    op = Mock(side_effect=SpotifyException(429, -1, "limit", headers={"Retry-After": "900"}))
    cancel = fake_cancel()
    with pytest.raises(ExportError, match="900-second"):
        SpotifyReader(Mock(), cancel).call(op)
    cancel.wait.assert_not_called()


def test_cancellation_during_backoff():
    cancel = fake_cancel()
    cancel.wait.return_value = True
    op = Mock(side_effect=requests.ConnectionError())
    with pytest.raises(Cancelled):
        SpotifyReader(Mock(), cancel).call(op)
    assert op.call_count == 1


def test_precancelled_operation_never_fetches():
    cancel = Event()
    cancel.set()
    op = Mock()
    with pytest.raises(Cancelled):
        SpotifyReader(Mock(), cancel).call(op)
    op.assert_not_called()


@pytest.mark.parametrize("value", [None, "bad", "nan", "inf", "-1"])
def test_invalid_retry_values(value):
    assert retry_delay(value, 2) == 2
