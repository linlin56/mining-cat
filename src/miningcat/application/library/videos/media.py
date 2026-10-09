"""The audio of subtitle lines and the pictures of a video, for cards."""
from miningcat.application.library.videos.catalog import file_path
from miningcat.application.library.videos.player_settings import get_settings
from miningcat.domain.library.errors import AudioError, VideoError
from miningcat.infrastructure.media.audio_clip import cut_mp3
from miningcat.infrastructure.media.browser_video import grab_frame

CLIP_MAX_S = 180


def clip(video_id: str, start, end, exact: bool = False, fmt: str = "mp3") -> bytes:
    """The audio of one or more subtitle lines as MP3, with the margins of the settings, cut from the file the browser
    plays (its first audio stream is the chosen track). `exact`: the span as given, without margins (chosen on the
    card creator's waveform). `fmt` "wav": for that waveform."""
    try:
        start, end = float(start), float(end)
    except (TypeError, ValueError):
        raise VideoError("Invalid time span.")
    if fmt not in ("mp3", "wav"):
        raise VideoError("Invalid audio format.")
    if end - start > CLIP_MAX_S:
        raise VideoError(f"The audio can't be longer than {CLIP_MAX_S // 60} minutes.")
    settings = get_settings()
    before, after = (0.0, 0.0) if exact else (settings["audio_before"] / 1000, settings["audio_after"] / 1000)
    try:
        return cut_mp3(file_path(video_id), start, end, before=before, after=after, fmt=fmt)
    except AudioError as exc:
        raise VideoError(str(exc))


SCREENSHOT_MAX_WIDTH = 1280


def frame(video_id: str, position) -> bytes:
    """The picture at `position` (seconds) as JPEG, for the card of a line that isn't on screen. Grabbing it in the
    browser needs a second, hidden <video>, which Safari doesn't load reliably."""
    try:
        position = max(0.0, float(position))
    except (TypeError, ValueError):
        raise VideoError("Invalid position.")
    return grab_frame(file_path(video_id), position, SCREENSHOT_MAX_WIDTH)
