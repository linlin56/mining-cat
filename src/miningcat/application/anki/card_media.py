import base64
import mimetypes
import re
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from miningcat.config.paths import paths
from miningcat.domain.cards.errors import AnkiError, MediaUnavailable
from miningcat.infrastructure import http


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


# A linked media (an online recording) is downloaded by MiningCat once, then sent as a file: Anki downloading every
# link itself gets refused by Wikimedia (429) during a big import, and the card would fail.
def media_file(media: dict) -> Path:
    """The local file of a card's media, downloaded first when it's a link."""
    path = card_media_dir() / media["filename"]
    if media.get("url") and not path.exists():
        try:
            data = http.get(media["url"], timeout=30)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise MediaUnavailable(f"Couldn't download {media['url']} ({getattr(exc, 'reason', exc)}): "
                                   "the card will be sent at the next sync.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return path


def anki_payload(media: dict) -> dict:
    """The storeMediaFile parameters of a media file: its data (a link's file is downloaded first)."""
    data = media_file(media).read_bytes()
    return {"filename": media["filename"], "data": base64.b64encode(data).decode("ascii")}
