"""Timing a subtitle track on another one of the video: a file found online, on the video's own subtitles."""
from miningcat.application.library.videos.progress import save_prefs
from miningcat.application.library.videos.store import read_meta
from miningcat.application.library.videos.subtitles import cues
from miningcat.domain.library.errors import VideoError
from miningcat.domain.subtitles.alignment import align


def align_track(video_id: str, track_id: str, reference_id: str = "") -> dict:
    """Times the track on `reference_id`, else on the video's own subtitles that match it best (they are timed for
    it), else on any other track. Saves the timing found and returns it, with the prefs."""
    tracks = read_meta(video_id).get("tracks", [])
    if not any(t["id"] == track_id for t in tracks):
        raise VideoError("No such subtitle track.")
    others = [t for t in tracks if t["id"] != track_id]
    if reference_id:
        references = [t for t in others if t["id"] == reference_id]
        if not references:
            raise VideoError("No such subtitle track.")
    else:
        references = [t for t in others if t.get("origin") == "embedded"] or others
    if not references:
        raise VideoError("No other subtitles to align these on: add the video's own subtitles first.")
    starts = [c["start"] for c in cues(video_id, track_id)]
    found = []
    for track in references:
        timing = align([c["start"] for c in cues(video_id, track["id"])], starts)
        if timing:
            found.append((timing.matched, timing, track))
    if not found:
        raise VideoError("These subtitles don't match the others (another cut or another episode?): "
                         "set their timing by hand.")
    _, timing, reference = max(found, key=lambda f: f[0])
    value = {"offset": timing.offset, "scale": timing.scale}
    prefs = save_prefs(video_id, {"timings": {track_id: value}})
    return {"timing": value, "reference": reference["label"], "matched": timing.matched, "lines": timing.lines,
            "prefs": prefs}
