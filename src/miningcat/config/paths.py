from dataclasses import dataclass
from pathlib import Path

# config/ -> miningcat/ -> src/ -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class ProjectPaths:
    """Every folder and file MiningCat reads or writes, all under one root.

    `sources/` holds the user's inputs, `output/` what the converter makes (safe to clear), `library/` what the
    reader, the player and the dictionaries keep, `user/` the user's own settings. Tests point `root` to a temporary
    folder.
    """

    root: Path

    # Sources: the user's inputs

    @property
    def sources(self) -> Path:
        return self.root / "sources"

    @property
    def audiobook(self) -> Path:
        return self.sources / "audiobook"

    @property
    def ebook(self) -> Path:
        return self.sources / "ebook"

    @property
    def staging(self) -> Path:
        """Files uploaded from the browser, before a pipeline copies them where it needs them."""
        return self.sources / ".staging"

    @property
    def game_ocr_settings(self) -> Path:
        """The window and areas of the video game capture. Kept in sources/, so that "Clear output" keeps them."""
        return self.sources / "game_ocr.json"

    # Output: what the converter makes

    @property
    def output(self) -> Path:
        return self.root / "output"

    @property
    def chapters_audio(self) -> Path:
        return self.output / "chapters_audio"

    @property
    def chapters_text(self) -> Path:
        return self.output / "chapters_text"

    @property
    def srt(self) -> Path:
        return self.output / "srt"

    @property
    def final(self) -> Path:
        return self.output / "final"

    @property
    def temp(self) -> Path:
        return self.output / "temp"

    @property
    def videos(self) -> Path:
        """Downloaded online videos."""
        return self.output / "videos"

    @property
    def ocr_frames(self) -> Path:
        """Scratch space for the frames of a video read by OCR."""
        return self.temp / "ocr_frames"

    @property
    def frequency(self) -> Path:
        """Word frequency and character lists."""
        return self.output / "frequency"

    # Library: what the reader, the player and the dictionaries keep

    @property
    def library(self) -> Path:
        return self.root / "library"

    @property
    def database(self) -> Path:
        return self.library / "miningcat.db"

    @property
    def books(self) -> Path:
        return self.library / "books"

    @property
    def comics(self) -> Path:
        return self.library / "comics"

    @property
    def library_videos(self) -> Path:
        return self.library / "videos"

    @property
    def card_media(self) -> Path:
        return self.library / "card_media"

    @property
    def card_exports(self) -> Path:
        return self.library / "exports"

    def dictionary_media(self, dict_id: int) -> Path:
        return self.library / "dictionaries" / str(dict_id)

    @property
    def reader_settings(self) -> Path:
        return self.library / "reader_settings.json"

    @property
    def comic_settings(self) -> Path:
        return self.library / "comic_settings.json"

    @property
    def player_settings(self) -> Path:
        return self.library / "player_settings.json"

    # User: the user's own settings

    @property
    def user(self) -> Path:
        return self.root / "user"

    @property
    def user_config(self) -> Path:
        """The preferences of every page (Settings › User preferences): theme, highlight colours."""
        return self.user / "user-config.json"

    # References to files under the root

    def to_ref(self, path: Path) -> str:
        """A path relative to the root, as the web GUI shows it."""
        return path.resolve().relative_to(self.root.resolve()).as_posix()


paths = ProjectPaths(PROJECT_ROOT)
