from pathlib import Path


class OpenCcConverter:
    """OpenCC's conversions and character tables, loaded on first use. Without opencc, nothing is converted."""

    def __init__(self):
        self._converters: dict[str, object] = {}
        self._tables: tuple[set[str], set[str]] | None = None

    def converter(self, config: str):
        """The OpenCC converter of a configuration (s2tw, t2s...), or None when opencc or the config is missing."""
        if config not in self._converters:
            try:
                import opencc
                self._converters[config] = opencc.OpenCC(config)
            except Exception:
                self._converters[config] = None
        return self._converters[config]

    def convert(self, text: str, config: str) -> str:
        converter = self.converter(config)
        return converter.convert(text) if converter else text

    def tables(self) -> tuple[set[str], set[str]]:
        """(simplified only, traditional only) characters, from OpenCC's character tables. A character that converts
        to several candidates including itself (了 → 了 瞭, 台 → 臺 檯 颱 台, 里 → 裏 里) is valid in both scripts: a
        round trip through the converters would wrongly call 了解 or 台灣 simplified. Empty without the tables."""
        if self._tables is None:
            try:
                import opencc
                folder = Path(opencc.__file__).parent / "dictionary"
                simplified_only = self._single_script(folder / "STCharacters.txt")
                traditional_only = self._single_script(folder / "TSCharacters.txt")
                self._tables = (simplified_only, traditional_only)
            except Exception:
                self._tables = (set(), set())
        return self._tables

    @staticmethod
    def _single_script(table: Path) -> set[str]:
        only = set()
        for line in table.read_text(encoding="utf-8").splitlines():
            char, _, candidates = line.partition("\t")
            if len(char) == 1 and char not in candidates.split():
                only.add(char)
        return only


class ChineseScripts:
    """Traditional and simplified characters: which script a word is written in, and its form in the other one."""

    def __init__(self, converter: OpenCcConverter | None = None):
        self.converter = converter or OpenCcConverter()

    def to_traditional(self, text: str, language: str = "zh") -> str:
        # Taiwan forms for Mandarin (裡, 台), Hong Kong forms for Cantonese.
        return self.converter.convert(text, "s2hk" if language == "yue" else "s2tw")

    def to_simplified(self, text: str, language: str = "zh") -> str:
        return self.converter.convert(text, "t2s")

    def char_script(self, char: str) -> str:
        simplified_only, traditional_only = self.converter.tables()
        if simplified_only or traditional_only:
            if char in simplified_only:
                return "simplified"
            return "traditional" if char in traditional_only else "both"
        # no character tables: fall back on the converters
        simp, trad = self.to_simplified(char), self.to_traditional(char)
        if simp == trad == char:
            return "both"
        return "traditional" if char == trad else "simplified" if char == simp else "both"

    def script(self, text: str) -> str:
        """'both' when the characters are the same in both scripts, else 'traditional', 'simplified' or 'mixed'."""
        found = {self.char_script(c) for c in text} - {"both"}
        if not found:
            return "both"
        return found.pop() if len(found) == 1 else "mixed"

    def counterpart(self, text: str, language: str = "zh") -> tuple[str, str] | None:
        """The same word in the other script, e.g. 說 -> ('simplified', '说'); None if identical."""
        script = self.script(text)
        if script == "traditional":
            return "simplified", self.to_simplified(text, language)
        if script == "simplified":
            return "traditional", self.to_traditional(text, language)
        return None


# The instance used by the whole app (tests replace it to do without OpenCC).
chinese_scripts = ChineseScripts()


def to_traditional(text: str, language: str = "zh") -> str:
    return chinese_scripts.to_traditional(text, language)


def to_simplified(text: str, language: str = "zh") -> str:
    return chinese_scripts.to_simplified(text, language)


def chinese_script(text: str) -> str:
    return chinese_scripts.script(text)


def chinese_counterpart(text: str, language: str = "zh") -> tuple[str, str] | None:
    return chinese_scripts.counterpart(text, language)
