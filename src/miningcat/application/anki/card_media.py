import base64
import mimetypes
import re
import urllib.request
import uuid
from pathlib import Path

from miningcat.config.paths import paths
from miningcat.domain.cards.errors import AnkiError


def card_media_dir() -> Path:
    """Where the images and sounds of the cards are kept."""
    return paths.card_media


def _data_url_bytes(data_url: str) -> tuple[bytes, str]:
    match = re.match(r"^data:([\w/+.-]+)?(;base64)?,(.*)$", data_url, re.S)
    if not match:
        raise AnkiError("Invalid media data.")
    mime = match.group(1) or "application/octet-stream"
    payload = match.group(3)
    raw = base64.b64decode(payload) if match.group(2) else urllib.request.unquote(payload).encode("utf-8")
    return raw, mime


def _extension(mime: str, fallback: str) -> str:
    ext = mimetypes.guess_extension(mime or "") or fallback
    return {".jpe": ".jpg", ".mpga": ".mp3", ".oga": ".ogg"}.get(ext, ext)


def store_media(kind: str, value: dict | None) -> dict | None:
    """Keeps a media file of a card: {data: data URL} is saved locally, {url} is kept as a link."""
    if not value:
        return None
    if value.get("data"):
        raw, mime = _data_url_bytes(value["data"])
        if len(raw) > 30 * 1024 * 1024:
            raise AnkiError("Media files are limited to 30 MB.")
        name = re.sub(r"[^\w.-]", "_", value.get("name") or "")[:60]
        ext = Path(name).suffix or _extension(mime, ".jpg" if kind == "image" else ".mp3")
        filename = f"miningcat_{uuid.uuid4().hex[:16]}{ext}"
        folder = card_media_dir()
        folder.mkdir(parents=True, exist_ok=True)
        (folder / filename).write_bytes(raw)
        return {"filename": filename, "mime": mime}
    if value.get("url"):
        url = str(value["url"])
        if not re.match(r"^https?://", url):
            raise AnkiError("Media links must start with http:// or https://")
        ext = Path(urllib.request.urlparse(url).path).suffix[:6] or (".jpg" if kind == "image" else ".mp3")
        return {"filename": f"miningcat_{uuid.uuid4().hex[:16]}{ext}", "url": url}
    return None


def anki_payload(media: dict) -> dict:
    """The storeMediaFile parameters of a media file: its data, or the link Anki downloads it from."""
    if media.get("url"):
        return {"filename": media["filename"], "url": media["url"]}
    data = (card_media_dir() / media["filename"]).read_bytes()
    return {"filename": media["filename"], "data": base64.b64encode(data).decode("ascii")}
