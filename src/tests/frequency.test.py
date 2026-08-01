import json
import pytest
from collections import Counter

from frequency import character_frequency, word_frequency
from language import Language


# --- character_frequency ---

class TestSupportsLanguage:
    def test_mandarin_tw(self):
        assert character_frequency.supports_language(Language.MANDARIN_TW)

    def test_mandarin_cn(self):
        assert character_frequency.supports_language(Language.MANDARIN_CN)

    def test_japanese(self):
        assert character_frequency.supports_language(Language.JAPANESE)

    def test_french_not_supported(self):
        assert not character_frequency.supports_language(Language.FRENCH)

    def test_english_not_supported(self):
        assert not character_frequency.supports_language(Language.ENGLISH_US)


class TestCharacterFrequencyCompute:
    def test_mandarin_counts_cjk(self):
        counter = character_frequency.compute("你好世界！Hello", Language.MANDARIN_TW)
        assert counter["你"] == 1
        assert counter["好"] == 1
        assert "H" not in counter
        assert "!" not in counter

    def test_mandarin_repeated_chars(self):
        counter = character_frequency.compute("你你你好", Language.MANDARIN_CN)
        assert counter["你"] == 3
        assert counter["好"] == 1

    def test_japanese_includes_kana(self):
        counter = character_frequency.compute("こんにちは漢字", Language.JAPANESE)
        assert counter["こ"] == 1
        assert counter["漢"] == 1
        assert counter["字"] == 1

    def test_japanese_excludes_latin(self):
        counter = character_frequency.compute("Hello日本語", Language.JAPANESE)
        assert "H" not in counter
        assert counter["日"] == 1

    def test_unsupported_language_raises(self):
        with pytest.raises(ValueError):
            character_frequency.compute("bonjour", Language.FRENCH)

    def test_empty_text(self):
        counter = character_frequency.compute("", Language.MANDARIN_TW)
        assert len(counter) == 0


class TestBuildJson:
    def test_structure(self):
        counter = Counter({"一": 10, "二": 8, "三": 5})
        data = character_frequency.build_json("My Book", Language.MANDARIN_TW, counter)
        assert data["version"] == 1
        assert data["name"] == "My Book"
        assert data["lang"] == "zh-Hant"
        assert data["leftover_group"] == "Not in book"
        assert isinstance(data["groups"], list)

    def test_lang_code_cn(self):
        data = character_frequency.build_json("x", Language.MANDARIN_CN, Counter())
        assert data["lang"] == "zh-Hans"

    def test_lang_code_ja(self):
        data = character_frequency.build_json("x", Language.JAPANESE, Counter())
        assert data["lang"] == "ja"

    def test_characters_ordered_by_frequency(self):
        counter = Counter({"一": 10, "二": 5, "三": 1})
        data = character_frequency.build_json("x", Language.MANDARIN_TW, counter, group_size=3)
        assert len(data["groups"]) == 1
        assert data["groups"][0]["characters"] == "一二三"

    def test_group_size_splits_correctly(self):
        counter = Counter({str(i): i for i in range(5)})
        data = character_frequency.build_json("x", Language.MANDARIN_TW, counter, group_size=2)
        assert len(data["groups"]) == 3  # 2 + 2 + 1

    def test_empty_counter_produces_no_groups(self):
        data = character_frequency.build_json("x", Language.MANDARIN_TW, Counter())
        assert data["groups"] == []


class TestSaveJson:
    def test_saves_valid_json(self, tmp_path):
        data = {"version": 1, "name": "test"}
        out = tmp_path / "out.json"
        character_frequency.save_json(data, out)
        assert json.loads(out.read_text(encoding="utf-8")) == data

    def test_creates_parent_dirs(self, tmp_path):
        out = tmp_path / "nested" / "dir" / "out.json"
        character_frequency.save_json({"x": 1}, out)
        assert out.exists()

    def test_preserves_cjk_without_escaping(self, tmp_path):
        out = tmp_path / "out.json"
        character_frequency.save_json({"name": "你好"}, out)
        assert "你好" in out.read_text(encoding="utf-8")


# --- word_frequency ---

class TestWordFrequencyCompute:
    def test_generic_french(self):
        counter = word_frequency.compute("Bonjour le monde le", Language.FRENCH)
        assert counter["Bonjour"] == 1
        assert counter["le"] == 2
        assert counter["monde"] == 1

    def test_generic_english(self):
        counter = word_frequency.compute("hello world hello", Language.ENGLISH_US)
        assert counter["hello"] == 2
        assert counter["world"] == 1

    def test_generic_min_length(self):
        counter = word_frequency.compute("a bb ccc", Language.ENGLISH_US, min_length=2)
        assert "a" not in counter
        assert counter["bb"] == 1
        assert counter["ccc"] == 1

    def test_generic_ignores_digits(self):
        counter = word_frequency.compute("chapter 1 hello", Language.ENGLISH_US)
        assert "1" not in counter

    def test_chinese_mandarin_tw(self):
        counter = word_frequency.compute("你好世界你好", Language.MANDARIN_TW)
        assert counter["你好"] == 2
        assert counter["世界"] == 1

    def test_chinese_mandarin_cn(self):
        counter = word_frequency.compute("我爱中国", Language.MANDARIN_CN)
        total = sum(counter.values())
        assert total > 0

    def test_chinese_filters_non_cjk(self):
        counter = word_frequency.compute("你好 Hello 世界", Language.MANDARIN_TW)
        assert "Hello" not in counter

    def test_japanese(self):
        counter = word_frequency.compute("東京は大きな都市です", Language.JAPANESE)
        assert sum(counter.values()) > 0

    def test_empty_text(self):
        counter = word_frequency.compute("", Language.FRENCH)
        assert len(counter) == 0


class TestTotalCount:
    def test_sums_all_occurrences(self):
        counter = word_frequency.compute("hello world hello", Language.ENGLISH_US)
        assert word_frequency.total_count(counter) == 3

    def test_empty_counter(self):
        assert word_frequency.total_count(Counter()) == 0


class TestSaveCsv:
    def test_saves_header_and_rows(self, tmp_path):
        out = tmp_path / "freq.csv"
        word_frequency.save_csv(Counter({"hello": 3, "world": 1}), out)
        lines = out.read_text(encoding="utf-8").splitlines()
        assert lines[0] == "word,count"
        assert "hello,3" in lines
        assert "world,1" in lines

    def test_ordered_by_frequency(self, tmp_path):
        out = tmp_path / "freq.csv"
        word_frequency.save_csv(Counter({"a": 1, "b": 5, "c": 3}), out)
        rows = out.read_text(encoding="utf-8").splitlines()[1:]
        counts = [int(r.split(",")[1]) for r in rows]
        assert counts == sorted(counts, reverse=True)

    def test_min_count_filters(self, tmp_path):
        out = tmp_path / "freq.csv"
        word_frequency.save_csv(Counter({"common": 5, "rare": 1}), out, min_count=2)
        text = out.read_text(encoding="utf-8")
        assert "common" in text
        assert "rare" not in text

    def test_preserves_unicode(self, tmp_path):
        out = tmp_path / "freq.csv"
        word_frequency.save_csv(Counter({"你好": 2}), out)
        assert "你好" in out.read_text(encoding="utf-8")
