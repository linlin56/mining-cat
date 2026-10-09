"""The text of comic pages, read by OCR (in its own process) the first time and kept next to the pages."""
from miningcat.application.library.comics.library import comic_folder, page_path
from miningcat.application.library.comics.progress import right_to_left
from miningcat.domain.languages import LANGUAGES, Language, is_no_space, language_key
from miningcat.domain.library.errors import ComicError
from miningcat.domain.ocr import layout
from miningcat.domain.ocr.plausibility import is_plausible_text
from miningcat.infrastructure.files.json_files import read_json, write_json
from miningcat.infrastructure.ocr.worker_client import OcrWorker, OcrWorkerError

# Bump when the OCR's output changes: pages read with an older version are read again.
OCR_VERSION = 1

_worker = OcrWorker()


def ocr_language(tag: str):
    """The OCR language (Language) of a text tagged `tag`: zh-Hans reads simplified characters."""
    lang = Language.for_tag(tag)
    if lang is None:
        key = language_key(tag)
        raise ComicError(f"Text recognition isn't available for {LANGUAGES.get(key, tag or 'this language')} yet.")
    return lang


def page_text(comic_id: str, number: int, language: str, again: bool = False) -> dict:
    """The text blocks of a page, read by OCR the first time (or `again`): {"blocks": [...], "engine_error"?}."""
    lang = ocr_language(language)
    path = page_path(comic_id, number)
    cache = comic_folder(comic_id) / "ocr" / f"{number:04d}.json"
    data = None if again else read_json(cache, None)
    if not data or data.get("version") != OCR_VERSION or data.get("language") != lang.name:
        try:
            result = _worker.read(lang, path)
        except OcrWorkerError as exc:
            raise ComicError(str(exc))
        data = {"version": OCR_VERSION, "language": lang.name, "width": result["width"], "height": result["height"],
                "lines": result["lines"]}
        write_json(cache, data)
    lines = [layout.Line(text, x, y, w, h) for text, x, y, w, h in data["lines"]]
    blocks = layout.group_lines(lines, right_to_left=right_to_left(comic_id, language))
    blocks = [b for b in blocks if is_plausible_text(layout.block_text(b, True), lang)]
    no_space = is_no_space(language_key(language))
    return {"blocks": layout.to_json(blocks, data["width"], data["height"], no_space)}
