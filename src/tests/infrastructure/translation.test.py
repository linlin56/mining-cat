import sys
import types

import pytest

from miningcat.infrastructure.translation import install, model_files, nllb, qwen3
from miningcat.infrastructure.translation.errors import TranslateError


class FakeTranslator:
    """CTranslate2's translator: each line's tokens, in the target language ("<code> <tokens>")."""

    def __init__(self, folder, device, compute_type):
        self.folder, self.asked = folder, []

    def translate_batch(self, tokens, target_prefix, **options):
        self.asked.append((tokens, target_prefix))
        return [types.SimpleNamespace(hypotheses=[[prefix[0], *line[1:-1]]]) for line, prefix in zip(tokens, target_prefix)]


class FakeTokenizer:
    def __init__(self, model_file):
        self.model_file = model_file

    def encode(self, text, out_type):
        return text.split()

    def decode(self, tokens):
        return " ".join(tokens).upper()


@pytest.fixture
def fake_packages(monkeypatch):
    loaded = []

    def translator(*args, **kwargs):
        loaded.append(FakeTranslator(*args, **kwargs))
        return loaded[-1]

    monkeypatch.setitem(sys.modules, "ctranslate2", types.SimpleNamespace(
        Translator=translator, get_cuda_device_count=lambda: 0))
    monkeypatch.setitem(sys.modules, "sentencepiece", types.SimpleNamespace(SentencePieceProcessor=FakeTokenizer))
    return loaded


@pytest.fixture
def fake_hub(monkeypatch):
    """Hugging Face, answering each file of a model with its name."""
    asked = []

    def download_to(url, path, progress=None, timeout=300):
        asked.append(url)
        if url.endswith("/broken"):
            path.write_bytes(b"half")
            raise OSError("connection reset")
        data = url.rsplit("/", 1)[1].encode()
        path.write_bytes(data)
        if progress:
            progress(len(data), len(data))

    monkeypatch.setattr(model_files.http, "download_to", download_to)
    return asked


def test_install_downloads_the_model_at_its_revision(fake_hub):
    model = nllb.Nllb()
    assert not model.installed("nllb-600m")
    steps = []
    model.install("nllb-600m", lambda done, total: steps.append(done))
    info = nllb.MODELS["nllb-600m"]
    assert fake_hub == [f"https://huggingface.co/{info.repo}/resolve/{info.revision}/{f}" for f in info.files]
    assert model.installed("nllb-600m") and not model.installed("nllb-1.3b")
    assert steps == sorted(steps) and steps[-1] == sum(len(f) for f in info.files)  # over all the files
    assert model_files.size_on_disk(info) == steps[-1]
    model.uninstall("nllb-600m")
    assert not model.installed("nllb-600m")
    with pytest.raises(TranslateError, match="isn't installed"):
        model.uninstall("nllb-600m")


def test_failed_download_leaves_no_model(fake_hub):
    broken = model_files.PinnedModel("broken", "Broken", "org/broken", "abc", 10, ("config.json", "broken"))
    with pytest.raises(TranslateError, match="connection reset"):
        model_files.download(broken)
    assert not model_files.downloaded(broken)
    assert [f.name for f in model_files.folder(broken).iterdir()] == ["config.json"]  # no half file


def test_translate_with_the_languages_codes(fake_hub, fake_packages, monkeypatch):
    model = nllb.Nllb()
    model.install("nllb-600m")
    assert model.translate("nllb-600m", ["我們 去", "公園"], "zt", "fr") == ["我們 去", "公園"]
    assert model.translate("nllb-600m", ["neih hou"], "yue", "en") == ["NEIH HOU"]
    assert len(fake_packages) == 1  # loaded once
    tokens, prefix = fake_packages[0].asked[0]
    assert tokens == [["zho_Hant", "我們", "去", "</s>"], ["zho_Hant", "公園", "</s>"]]
    assert prefix == [["fra_Latn"], ["fra_Latn"]]
    with pytest.raises(TranslateError, match="can't translate"):
        model.translate("nllb-600m", ["a"], "nan", "en")  # Taigi
    # subtitles, a few lines at a time
    monkeypatch.setattr(nllb, "LINES_PER_STEP", 2)
    steps = []
    assert model.translate_lines("nllb-600m", ["a", "b", "c"], "en", "fr", lambda *s: steps.append(s)) == ["A", "B", "C"]
    assert steps == [(2, 3), (3, 3)]
    model.unload()
    model.translate("nllb-600m", ["a"], "en", "fr")
    assert len(fake_packages) == 2  # loaded again


def test_missing_packages_tell_how_to_install(fake_hub, monkeypatch):
    monkeypatch.setitem(sys.modules, "ctranslate2", None)
    model = nllb.Nllb()
    model.install("nllb-600m")
    with pytest.raises(TranslateError, match="Settings › Translation"):
        model.translate("nllb-600m", ["a"], "zh", "en")
    monkeypatch.setattr(nllb.importlib.util, "find_spec", lambda name: None)
    assert not model.available() and not qwen3.Qwen3().available()


def test_install_runs_the_engines_pip_then_downloads(fake_hub, monkeypatch):
    ran = []
    returncode = [0]
    monkeypatch.setattr(install.subprocess, "run",
                        lambda command, check: ran.append(command[3:]) or types.SimpleNamespace(returncode=returncode[0]))
    assert install.install("nllb-1.3b") == 0
    assert ran == [["install", "-r", str(install.PROJECT_ROOT / "requirements-nllb.txt")]]
    files = nllb.MODELS["nllb-1.3b"].files
    assert nllb.Nllb().installed("nllb-1.3b") and len(fake_hub) == len(files)
    assert install.install("nllb-1.3b") == 0 and len(fake_hub) == len(files)  # already downloaded
    assert install.install("qwen3-4b") == 0 and qwen3.Qwen3().installed("qwen3-4b")
    assert ran[-1] == ["install", "-r", str(install.PROJECT_ROOT / "requirements-qwen.txt")]
    returncode[0] = 2
    assert install.install("nllb-600m") == 2 and not nllb.Nllb().installed("nllb-600m")
    assert set(install.MODELS) == {"nllb-600m", "nllb-1.3b", "qwen3-4b"} and install.DEFAULT_MODEL in install.MODELS


def test_cli_install_command(fake_hub, monkeypatch, capsys):
    from miningcat.application.converter.errors import ConverterError
    from miningcat.interfaces.cli.main import build_parser
    from miningcat.interfaces.cli.translation_command import TranslationInstallCommand
    monkeypatch.setattr(install, "install_packages", lambda name: 0)
    TranslationInstallCommand().run(build_parser().parse_args(["install-translation"]))
    assert nllb.Nllb().installed("nllb-600m") and "is installed" in capsys.readouterr().out
    monkeypatch.setattr(install, "install_packages", lambda name: 1)
    with pytest.raises(ConverterError, match="pip"):
        TranslationInstallCommand().run(build_parser().parse_args(["install-translation", "--model", "qwen3-4b"]))


# Qwen3: subtitles in numbered chunks, after the lines before them
def test_qwen_prompt_and_answer():
    chat = qwen3.messages(["やあ", "旅人さ"], [("おい", "Hey")], "ja", "en")
    assert "from Japanese to English" in chat[0]["content"]
    assert chat[1]["content"] == "Context (already translated):\nおい => Hey\n\nTranslate:\n1. やあ\n2. 旅人さ"
    assert "Context" not in qwen3.messages(["a"], [], "zt", "fr")[1]["content"]
    assert "traditional" in qwen3.messages(["a"], [], "zt", "fr")[0]["content"]
    assert qwen3.parse("1. Hi\n2) I'm a traveler.\n", 2) == ["Hi", "I'm a traveler."]
    assert qwen3.parse("Sure!\n1. Hi\n2. Bye", 2) == ["Hi", "Bye"]  # a line before
    assert qwen3.parse("1. Hi", 2) is None and qwen3.parse("1. Hi\n2. Bye\n3. ?", 2) is None
    assert "nan" in qwen3.LANGUAGES and "zt" not in qwen3.LANGUAGES


class FakeQwen(qwen3.Qwen3):
    """Answers each chat with its lines numbered and upper-cased; `broken` chunk sizes get one line too few."""

    def __init__(self, broken=()):
        super().__init__()
        self.chats, self.broken = [], set(broken)

    def _generate(self, name, chat, max_tokens):
        self.chats.append(chat[1]["content"])
        lines = chat[1]["content"].split("Translate:\n")[1].splitlines()
        answer = [f"{i + 1}. {line.split('. ', 1)[1].upper()}" for i, line in enumerate(lines)]
        return "\n".join(answer[:-1] if len(lines) in self.broken else answer)


def test_qwen_translates_in_chunks_with_context(monkeypatch):
    monkeypatch.setattr(qwen3, "CHUNK", 3)
    monkeypatch.setattr(qwen3, "CONTEXT", 2)
    model = FakeQwen()
    steps = []
    lines = ["a", "b", "c", "d", "e"]
    assert model.translate_lines("qwen3-4b", lines, "en", "fr", lambda *s: steps.append(s)) == ["A", "B", "C", "D", "E"]
    assert steps == [(3, 5), (5, 5)]
    assert model.chats == ["Translate:\n1. a\n2. b\n3. c",
                           "Context (already translated):\nb => B\nc => C\n\nTranslate:\n1. d\n2. e"]
    with pytest.raises(TranslateError, match="can't translate"):
        model.translate_lines("qwen3-4b", ["a"], "xx", "en")


def test_qwen_splits_a_chunk_it_answers_wrong(monkeypatch):
    monkeypatch.setattr(qwen3, "CHUNK", 4)
    model = FakeQwen(broken={4})
    assert model.translate_lines("qwen3-4b", ["a", "b", "c", "d"], "en", "fr") == ["A", "B", "C", "D"]
    # the halves, the second after the first
    assert model.chats[1:] == ["Translate:\n1. a\n2. b",
                               "Context (already translated):\na => A\nb => B\n\nTranslate:\n1. c\n2. d"]
    model = FakeQwen(broken={1})
    assert model.translate_lines("qwen3-4b", ["a"], "en", "fr") == [""]  # nothing to cut: no translation
