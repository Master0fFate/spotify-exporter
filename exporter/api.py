"""Read-only Spotify access with bounded, cancellable retry and pagination."""

import math
from threading import Event
from urllib.parse import urlparse

import requests
from spotipy.exceptions import SpotifyException

from .models import playlist_from_api, track_from_api


class Cancelled(Exception):
    """An operation was cancelled before its next side effect."""


class ExportError(Exception):
    """A user-facing error that contains no credentials or request URLs."""


def check_cancelled(cancel):
    if cancel.is_set():
        raise Cancelled()


def retry_delay(value, fallback):
    try:
        delay = float(value)
        return delay if math.isfinite(delay) and delay >= 0 else fallback
    except (ValueError, TypeError):
        return fallback


class SpotifyReader:
    def __init__(self, client, cancel=None, max_retries=3, legacy=False):
        self.client = client
        self.cancel = cancel if cancel is not None else Event()
        self.max_retries = max_retries
        self.legacy = legacy

    def call(self, operation, *args, **kwargs):
        for attempt in range(self.max_retries + 1):
            check_cancelled(self.cancel)
            try:
                result = operation(*args, **kwargs)
                check_cancelled(self.cancel)
                return result
            except SpotifyException as exc:
                status = exc.http_status
                if getattr(exc, "reason", None) == "QUOTA_EXCEEDED":
                    raise ExportError(
                        "Spotify's developer account quota is exhausted. Try again later."
                    ) from None
                if status not in (429, 500, 502, 503, 504):
                    messages = {
                        401: "Spotify authorization expired. Reconnect to Spotify.",
                        403: "Spotify denied access. Development apps can only export owned or collaborative playlists; check the app owner's Premium subscription and allowed users.",
                        404: "This playlist or API endpoint is unavailable. Check access and API mode in Settings.",
                    }
                    raise ExportError(
                        messages.get(status, f"Spotify request failed (HTTP {status}).")
                    ) from None
                delay = retry_delay((exc.headers or {}).get("Retry-After"), 2**attempt)
                if delay > 120:
                    raise ExportError(
                        f"Spotify requested a {delay:g}-second wait. Retry later; completed files are safe."
                    ) from None
            except (requests.Timeout, requests.ConnectionError):
                delay = 2**attempt
            if attempt == self.max_retries:
                raise ExportError(
                    "Spotify could not complete the request after retries. Check your connection and retry."
                )
            if self.cancel.wait(delay):
                raise Cancelled()

    def pages(self, first, *args, **kwargs):
        page = self.call(first, *args, **kwargs)
        seen = set()
        count = 0
        expected = page.get("total") if isinstance(page, dict) else None
        while True:
            if not isinstance(page, dict) or not isinstance(page.get("items"), list):
                raise ExportError(
                    "Spotify returned an unexpected page; no partial export was saved."
                )
            for item in page["items"]:
                check_cancelled(self.cancel)
                if not isinstance(item, dict):
                    raise ExportError("Spotify returned an invalid playlist entry.")
                count += 1
                yield item
            next_url = page.get("next")
            if not next_url:
                if isinstance(expected, int) and count != expected:
                    raise ExportError(
                        "Spotify returned an incomplete or changing list. Refresh and retry."
                    )
                return
            parsed = urlparse(next_url)
            if (
                parsed.scheme != "https"
                or parsed.netloc != "api.spotify.com"
                or not parsed.path.startswith("/v1/")
            ):
                raise ExportError("Spotify returned an unexpected pagination URL.")
            if next_url in seen:
                raise ExportError("Spotify repeated a page; no partial export was saved.")
            seen.add(next_url)
            page = self.call(self.client.next, page)

    def playlists(self):
        return [
            playlist_from_api(p) for p in self.pages(self.client.current_user_playlists, limit=50)
        ]

    def tracks(self, playlist_id):
        before = self.call(self.client.playlist, playlist_id, fields="snapshot_id")
        if not isinstance(before, dict) or not before.get("snapshot_id"):
            raise ExportError("Spotify did not return a playlist snapshot; no export was saved.")
        if self.legacy:
            # Explicit opt-in for extended-quota apps, never a permission bypass.
            def first(**kwargs):
                return self.client._get(f"playlists/{playlist_id}/tracks", **kwargs)
        else:

            def first(**kwargs):
                return self.client.playlist_items(playlist_id, **kwargs)

        tracks = [track_from_api(item, i) for i, item in enumerate(self.pages(first, limit=50), 1)]
        after = self.call(self.client.playlist, playlist_id, fields="snapshot_id")
        if before.get("snapshot_id") != after.get("snapshot_id"):
            raise ExportError(
                "The playlist changed while it was being exported. Retry to get a consistent copy."
            )
        return tracks
