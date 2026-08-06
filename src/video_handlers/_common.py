from pathlib import Path

# Add retries to yt-dlp to avoid fails that can happen with large files or slow connections.
BASE_YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "retries": 10,
    "fragment_retries": 10,
}


# yt-dlp sets info["__real_download"] to False (or leaves it unset) when the destination file already existed and the download was skipped
# by default this is only reported via yt-dlp's own (suppressed, quiet=True) logging, 
# so without this the GUI/CLI log gives no indication a download was skipped.
def resolve_downloaded_path(ydl, info: dict) -> Path:
    if info.get("requested_downloads"):
        path = Path(info["requested_downloads"][0]["filepath"])
    else:
        path = Path(ydl.prepare_filename(info))
    if not info.get("__real_download"):
        print(f"Skipped download (already downloaded): {path}")
    return path
