"""The files of a translation model, downloaded from Hugging Face at a fixed revision to library/translation_models/<name>/
(the user sees them in the settings, and removes them there). Once downloaded, nothing is asked to huggingface.co."""
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from miningcat.config.paths import paths
from miningcat.infrastructure import http
from miningcat.infrastructure.translation.errors import TranslateError


@dataclass(frozen=True)
class PinnedModel:
    name: str
    label: str
    repo: str
    revision: str
    size: int  # bytes, to tell the user before the download
    files: tuple[str, ...]  # the largest last: a folder with it is complete


def folder(model: PinnedModel) -> Path:
    return paths.translation_models / model.name


def downloaded(model: PinnedModel) -> bool:
    return (folder(model) / model.files[-1]).is_file()


def size_on_disk(model: PinnedModel) -> int:
    return sum(f.stat().st_size for f in folder(model).rglob("*") if f.is_file())


def download(model: PinnedModel, progress: Callable[[int, int], None] | None = None) -> None:
    """Downloads the model's files, `progress(bytes, total)` over all of them. A file is written whole or not at all."""
    target = folder(model)
    target.mkdir(parents=True, exist_ok=True)
    done = 0
    for file in model.files:
        part = target / f"{file}.part"
        url = f"https://huggingface.co/{model.repo}/resolve/{model.revision}/{file}"

        def on_chunk(read: int, total: int, before: int = done):
            if progress:
                progress(before + read, max(model.size, before + total))

        try:
            http.download_to(url, part, progress=on_chunk)
        except OSError as exc:
            part.unlink(missing_ok=True)
            raise TranslateError(f"The translation model couldn't be downloaded: {exc}") from exc
        done += part.stat().st_size
        part.replace(target / file)


def remove(model: PinnedModel) -> None:
    if not downloaded(model):
        raise TranslateError("This model isn't installed.")
    shutil.rmtree(folder(model))
