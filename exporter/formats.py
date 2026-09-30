"""Loss-aware local exports and bounded Discord messages."""

import csv
import io
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import requests

from .api import Cancelled, ExportError, check_cancelled, retry_delay
from .models import Track


def sanitize_filename(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f-\x9f]', "", value).strip(". ")[:80]
    if not value or value.split(".")[0].upper() in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *[f"COM{i}" for i in range(1, 10)],
        *[f"LPT{i}" for i in range(1, 10)],
    }:
        value = "playlist_" + value
    while len(value.encode("utf-8")) > 160:
        value = value[:-1]
    return value


def safe_cell(value):
    # Quoting alone does not prevent formula execution in spreadsheet programs.
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def markdown(value):
    return re.sub(
        r"([\\`*_{}\[\]()<>#+.!|~-])", r"\\\1", value.replace("\r", " ").replace("\n", " ")
    )


def render(playlist, tracks, format_name):
    now = datetime.now(timezone.utc).isoformat()
    if format_name == "json":
        return json.dumps(
            {
                "schema_version": 2,
                "playlist": {
                    "id": playlist.id,
                    "name": playlist.name,
                    "owner": playlist.owner,
                    "description": playlist.description,
                    "track_count": len(tracks),
                },
                "tracks": [track.to_dict() for track in tracks],
                "exported_at": now,
            },
            ensure_ascii=False,
            indent=2,
        )
    if format_name == "csv":
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=list(Track.__dataclass_fields__))
        writer.writeheader()
        writer.writerows(
            {key: safe_cell(value) for key, value in t.to_dict().items()} for t in tracks
        )
        return stream.getvalue()
    if format_name == "txt":
        lines = [
            f"Playlist: {playlist.name}",
            f"Owner: {playlist.owner}",
            f"Tracks: {len(tracks)}",
            f"Exported: {now}",
            "",
        ]
        for i, t in enumerate(tracks, 1):
            lines += [
                f"{i}. {t.name}",
                f"   Artist: {t.artist}",
                f"   Album: {t.album}",
                f"   Type: {t.type}; local: {t.is_local}; available: {t.available}",
                f"   URL: {t.url}",
                "",
            ]
        return "\n".join(lines)
    if format_name == "md":
        lines = [
            f"# {markdown(playlist.name)}",
            "",
            f"**Owner:** {markdown(playlist.owner)}",
            f"**Tracks:** {len(tracks)}",
            f"**Exported:** {now}",
            "",
            markdown(playlist.description),
            "",
            "## Tracks",
            "",
        ]
        for i, t in enumerate(tracks, 1):
            lines += [
                f"{i}. **{markdown(t.name)}** - {markdown(t.artist)}",
                f"   {markdown(t.album)}",
                f"   Type: {markdown(t.type)}; local: {t.is_local}; available: {t.available}",
                f"   {markdown(t.url)}",
                "",
            ]
        return "\n".join(lines)
    raise ValueError(f"Unsupported export format: {format_name}")


def write_export(playlist, tracks, format_name, output_dir, cancel):
    check_cancelled(cancel)
    content = render(playlist, tracks, format_name)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    name = f"{sanitize_filename(playlist.name)}_{datetime.now():%Y%m%d_%H%M%S}_{uuid4().hex[:12]}.{format_name}"
    destination = output_dir / name
    # Same-filesystem replacement publishes only a fully written file.
    fd, temporary = tempfile.mkstemp(prefix=".spotify-", suffix=".tmp", dir=output_dir)
    try:
        with os.fdopen(
            fd, "w", encoding="utf-8-sig" if format_name == "csv" else "utf-8", newline=""
        ) as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        check_cancelled(cancel)
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return str(destination)


def validate_webhook(url):
    if not re.fullmatch(
        r"https://(?:discord\.com|discordapp\.com)/api(?:/v\d+)?/webhooks/\d+/[A-Za-z0-9_-]+", url
    ):
        raise ExportError("Use a HTTPS Discord webhook URL from Discord channel settings.")
    return url


def discord_messages(playlist, tracks):
    text = f"{playlist.name}\nBy {playlist.owner} • {len(tracks)} items\n\n"
    text += "\n".join(f"{i}. {t.name} - {t.artist}" for i, t in enumerate(tracks, 1))
    # Stay under Discord's 2,000 UTF-16-unit limit, including long emoji names.
    message, length = [], 0
    for character in text:
        width = len(character.encode("utf-16-le")) // 2
        if length + width > 1800:
            yield "".join(message)
            message, length = [], 0
        message.append(character)
        length += width
    if message:
        yield "".join(message)


def send_discord(playlist, tracks, url, cancel, post=requests.post):
    validate_webhook(url)
    sent = 0
    for message in discord_messages(playlist, tracks):
        for attempt in range(4):
            check_cancelled(cancel)
            try:
                response = post(
                    url,
                    json={"content": message, "allowed_mentions": {"parse": []}},
                    timeout=(5, 30),
                    allow_redirects=False,
                )
            except requests.RequestException:
                # A timeout can happen after delivery. Retrying would duplicate it.
                raise ExportError(
                    f"Discord delivery is uncertain after {sent} confirmed messages. Check the channel before retrying."
                ) from None
            if response.status_code in (200, 204):
                sent += 1
                break
            if response.status_code != 429 or attempt == 3:
                raise ExportError(
                    f"Discord stopped with HTTP {response.status_code} after {sent} confirmed messages."
                )
            try:
                value = response.json().get("retry_after")
            except (ValueError, AttributeError):
                value = None
            delay = retry_delay(value, retry_delay(response.headers.get("Retry-After"), 2**attempt))
            if delay > 120:
                raise ExportError(
                    f"Discord requested a long wait after {sent} confirmed messages. Retry later."
                )
            if cancel.wait(delay):
                raise Cancelled()
    return sent
