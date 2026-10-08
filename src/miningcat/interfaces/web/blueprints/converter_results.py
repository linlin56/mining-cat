"""What the converter made: frequency lists, opening it in the reader or the player, the output folder."""
from flask import Blueprint, jsonify

from miningcat.application.converter import source_files
from miningcat.application.converter.frequency_lists import MAKERS
from miningcat.application.library import book_audio, books, videos
from miningcat.config.paths import paths
from miningcat.infrastructure.files.srt_files import srt_file_text
from miningcat.infrastructure.system.desktop import open_folder
from miningcat.interfaces.web.blueprints.converter import refs
from miningcat.interfaces.web.errors import UserError
from miningcat.interfaces.web.jobs import current_state
from miningcat.interfaces.web.requests import converter_language, json_body

bp = Blueprint("converter_results", __name__)


def _selected_chapters(indices, total: int) -> list[int]:
    if not isinstance(indices, list):
        return []
    return sorted({i for i in indices if isinstance(i, int) and 0 <= i < total})


def _not_running() -> None:
    if current_state().running:
        raise UserError("Busy", "Wait for the current job to finish.", 409)


def _source_text(body: dict) -> tuple[str, str]:
    """The text a frequency list is made of, and its name: the last video's subtitles, or chapters of a book."""
    if body.get("source") == "video":
        srt_path = current_state().last_video_srt
        if srt_path is None or not srt_path.exists():
            raise UserError("No video processed", "Generate a video first.")
        return srt_file_text(srt_path), srt_path.stem
    ebook_files = source_files.normalize_ebook_selection(refs(body.get("ebook")))
    chapters = source_files.load_chapters(ebook_files) if ebook_files else []
    if not chapters:
        raise UserError("No chapters", "Load an EPUB or TXT file first.")
    selected = _selected_chapters(body.get("chapters"), len(chapters))
    if not selected:
        raise UserError("No chapters selected", "Select at least one chapter.")
    return "\n".join(chapters[i][1] for i in selected), ebook_files[0].stem


@bp.post("/api/frequency")
def api_frequency():
    body = json_body()
    maker = MAKERS.get(body.get("kind"))
    if maker is None:
        raise UserError("Unknown list", f"Unknown frequency list: {body.get('kind')!r}")
    lang = converter_language(body.get("language"))
    if not maker.supports(lang):
        raise UserError("Not supported", f"Character lists are not available for {lang.profile.label}.")
    text, name = _source_text(body)
    state = current_state()
    try:
        saved = maker.make(text, lang, name)
    except Exception as exc:
        state.info(f"{maker.label} error: {exc}\n")
        raise UserError(f"{maker.label} error", str(exc), 500)
    state.info(saved.log + "\n")
    return jsonify(message=saved.message, path=str(saved.path))


# After a conversion: imports its book into the reader's library, with the chapters' audio and subtitles.
@bp.post("/api/reader/from-output")
def api_reader_from_output():
    _not_running()
    ebook_files = source_files.normalize_ebook_selection(refs(json_body().get("ebook")))
    if not ebook_files:
        raise UserError("No book", "This conversion has no book to open in the reader.")
    source = ebook_files[0]
    try:
        meta = books.import_book(source.name, source.read_bytes())
        audio = book_audio.attach_from_output(meta["id"])
    except (books.BookError, book_audio.AudioError) as exc:
        raise UserError("Reader", str(exc))
    return jsonify(id=meta["id"], audio=audio)


# After a video conversion: imports its video, with the subtitles it now carries, into the player's library.
@bp.post("/api/player/from-output")
def api_player_from_output():
    _not_running()
    body = json_body()
    finals = sorted(paths.final.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True) if paths.final.exists() else []
    if not finals:
        raise UserError("No video", "No converted video found in output/final: generate one first.")
    language = converter_language(body["language"]).profile.tag if body.get("language") else None
    try:
        meta = videos.import_file(finals[0], language=language)
    except videos.VideoError as exc:
        raise UserError("Player", str(exc))
    return jsonify(id=meta["id"])


@bp.post("/api/clear-output")
def api_clear_output():
    if current_state().running:
        raise UserError("Busy", "Wait for the current job to finish before clearing the output folder.", 409)
    source_files.clear_output()
    current_state().last_video_srt = None
    current_state().info("Output folder cleared.\n")
    return jsonify(cleared=True)


@bp.post("/api/open-folder")
def api_open_folder():
    path = paths.frequency if json_body().get("which") == "frequency" else paths.final
    try:
        open_folder(path)
    except Exception as exc:
        raise UserError("Could not open the folder", f"{exc}\n\nThe files are in: {path}", 500)
    return jsonify(path=str(path))
