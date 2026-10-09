"""The player's library of videos."""
from miningcat.application.library.videos.catalog import delete_video, file_path, list_videos, thumb_path
from miningcat.application.library.videos.importing import VIDEO_EXTENSIONS, fingerprint, import_file, import_stream
from miningcat.application.library.videos.media import clip, frame
from miningcat.application.library.videos.online import dismiss_download, downloads, start_download
from miningcat.application.library.videos.player_settings import DEFAULT_SETTINGS, get_settings, save_settings
from miningcat.application.library.videos.preparation import audio_tracks, get_meta, start_prepare
from miningcat.application.library.videos.progress import get_prefs, get_progress, save_prefs, save_progress
from miningcat.application.library.videos.store import video_folder, videos_dir
from miningcat.application.library.videos.subtitles import (
    SUBTITLE_EXTENSIONS,
    add_subtitles,
    cues,
    parse_subtitles,
    remove_subtitles,
)
from miningcat.domain.library.errors import VideoError
from miningcat.infrastructure.media.browser_video import play_plan

__all__ = [
    "DEFAULT_SETTINGS", "SUBTITLE_EXTENSIONS", "VIDEO_EXTENSIONS", "VideoError", "add_subtitles", "audio_tracks",
    "clip", "cues", "delete_video", "dismiss_download", "downloads", "file_path", "fingerprint", "frame", "get_meta",
    "get_prefs", "get_progress", "get_settings", "import_file", "import_stream", "list_videos", "parse_subtitles",
    "play_plan", "remove_subtitles", "save_prefs", "save_progress", "save_settings", "start_download",
    "start_prepare", "thumb_path", "video_folder", "videos_dir",
]
