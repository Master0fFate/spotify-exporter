import csv
import io
import json
from pathlib import Path
from threading import Event
from unittest.mock import Mock

import pytest
import requests

from exporter.api import Cancelled, ExportError
from exporter.formats import (
    discord_messages,
    render,
    sanitize_filename,
    send_discord,
    validate_webhook,
    write_export,
)
from exporter.models import Playlist, Track

P = Playlist("id", "Playlist 🎵", 1, "owner", "Description")
T = Track("=SUM(A1:A2)", "Artist, é", "Album\nline", 123, "https://open.spotify.com/track/example")
WEBHOOK = "https://discord.com/api/webhooks/123/fake_test_value"


@pytest.mark.parametrize("format_name", ["csv", "json", "txt", "md"])
def test_all_formats_support_empty_playlists(tmp_path, format_name):
    path = write_export(P, [], format_name, tmp_path, Event())
    assert Path(path).is_file() and Path(path).stat().st_size > 0
    assert not list(tmp_path.glob("*.tmp"))


def test_json_is_lossless_and_keeps_original_keys():
    data = json.loads(render(P, [T, T], "json"))
    assert data["tracks"][0]["name"] == T.name
    assert data["tracks"][0]["album"] == T.album
    assert len(data["tracks"]) == 2
    assert data["playlist"]["track_count"] == 2
    assert data["exported_at"].endswith("+00:00")


def test_csv_escapes_formulas_and_newlines():
    row = next(csv.DictReader(io.StringIO(render(P, [T], "csv"))))
    assert row["name"] == "'=SUM(A1:A2)"
    assert row["artist"] == "Artist, é" and row["album"] == "Album\nline"


@pytest.mark.parametrize("name", ["CON", "NUL.txt", "COM1", "LPT9", "../", "a/b:c*?", "😀" * 300])
def test_portable_filenames(name):
    result = sanitize_filename(name)
    assert result and not any(c in result for c in "/\\:*?")
    assert len(result) <= 90
    assert result.upper().split(".")[0] not in {"CON", "NUL", "COM1", "LPT9"}


def test_duplicate_playlist_names_never_overwrite(tmp_path):
    a = write_export(P, [T], "json", tmp_path, Event())
    b = write_export(P, [T], "json", tmp_path, Event())
    assert a != b and Path(a).exists() and Path(b).exists()


def test_cancellation_does_not_publish_partial_file(tmp_path, monkeypatch):
    cancel = Event()
    monkeypatch.setattr("exporter.formats.os.fsync", lambda _: cancel.set())
    with pytest.raises(Cancelled):
        write_export(P, [T], "json", tmp_path, cancel)
    assert not list(tmp_path.iterdir())


def test_write_failure_cleans_up_temporary_file(tmp_path, monkeypatch):
    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr("exporter.formats.os.replace", fail)
    with pytest.raises(OSError):
        write_export(P, [T], "json", tmp_path, Event())
    assert not list(tmp_path.iterdir())


def test_markdown_escapes_untrusted_content():
    p = Playlist("p", "<script>[click](evil)", 0, "**owner**")
    value = render(p, [], "md")
    assert r"\<script\>\[click\]\(evil\)" in value
    assert r"\*\*owner\*\*" in value


@pytest.mark.parametrize(
    "url",
    [
        "http://discord.com/api/webhooks/123/token",
        "https://discord.com.evil/api/webhooks/123/token",
        "https://example.com",
        "https://discord.com/api/webhooks/123/token?wait=true",
    ],
)
def test_webhook_validation(url):
    with pytest.raises(ExportError):
        validate_webhook(url)


def test_discord_chunks_long_unicode_names():
    p = Playlist("p", "😀" * 3000, 1, "@everyone")
    chunks = list(discord_messages(p, [T]))
    assert len(chunks) > 3
    assert all(len(part.encode("utf-16-le")) // 2 <= 1800 for part in chunks)


def test_discord_blocks_mentions_and_redirects():
    post = Mock(return_value=Mock(status_code=204))
    assert send_discord(P, [T], WEBHOOK, Event(), post) == 1
    args = post.call_args.kwargs
    assert args["json"]["allowed_mentions"] == {"parse": []}
    assert args["timeout"] == (5, 30) and args["allow_redirects"] is False


def test_discord_timeout_is_not_retried():
    post = Mock(side_effect=requests.Timeout("secret"))
    with pytest.raises(ExportError, match="uncertain") as error:
        send_discord(P, [T], WEBHOOK, Event(), post)
    assert "secret" not in str(error.value)
    assert post.call_count == 1


def test_discord_retries_only_rate_limits():
    limited = Mock(status_code=429, headers={})
    limited.json.return_value = {"retry_after": 0}
    post = Mock(side_effect=[limited, Mock(status_code=204)])
    assert send_discord(P, [T], WEBHOOK, Event(), post) == 1
    assert post.call_count == 2


def test_long_unicode_filename_can_be_written(tmp_path):
    p = Playlist("p", "😀" * 300, 0, "owner")
    assert Path(write_export(p, [], "json", tmp_path, Event())).exists()
