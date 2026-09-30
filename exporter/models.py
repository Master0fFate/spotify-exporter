"""Stable export records. Original fields remain available in every format."""

from dataclasses import asdict, dataclass


@dataclass
class Track:
    name: str
    artist: str
    album: str
    duration_ms: int
    url: str
    position: int = 0
    type: str = "track"
    uri: str = ""
    is_local: bool = False
    available: bool = True
    added_at: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class Playlist:
    id: str
    name: str
    track_count: int
    owner: str
    description: str = ""
    snapshot_id: str = ""


def playlist_from_api(item):
    owner = item.get("owner") or {}
    summary = item.get("items", item.get("tracks")) or {}
    return Playlist(
        id=item["id"],
        name=item.get("name") or "Untitled playlist",
        track_count=summary.get("total") or 0,
        owner=owner.get("display_name") or owner.get("id") or "Unknown owner",
        description=item.get("description") or "",
        snapshot_id=item.get("snapshot_id") or "",
    )


def track_from_api(entry, position):
    # Preserve unavailable entries, duplicates and order rather than silently
    # shortening a backup. Both development and extended-quota shapes occur.
    item = entry.get("item", entry.get("track")) or {}
    kind = item.get("type") or ("track" if item else "unavailable")
    show = item.get("show") or {}
    artists = ", ".join(a.get("name") or "Unknown artist" for a in item.get("artists") or [])
    return Track(
        name=item.get("name") or "Unavailable item",
        artist=artists or show.get("publisher") or show.get("name") or "Unknown artist",
        album=(item.get("album") or {}).get("name") or show.get("name") or "",
        duration_ms=item.get("duration_ms") or 0,
        url=(item.get("external_urls") or {}).get("spotify") or "",
        position=position,
        type=kind,
        uri=item.get("uri") or "",
        is_local=bool(entry.get("is_local") or item.get("is_local")),
        available=bool(item) and item.get("is_playable") is not False,
        added_at=entry.get("added_at") or "",
    )
