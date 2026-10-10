import sys
import types

import pytest

from miningcat.infrastructure.translation import nllb, nllb_install
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

    monkeypatch.setattr(nllb.http, "download_to", download_to)
    return asked


def test_install_downloads_the_model_at_its_revision(fake_hub):
    model = nllb.Nllb()
    assert not model.installed("nllb-600m") and model.installed_models() == []
    steps = []
    model.install("nllb-600m", lambda done, total: steps.append(done))
    info = nllb.MODELS["nllb-600m"]
    assert fake_hub == [f"https://huggingface.co/{info.repo}/resolve/{info.revision}/{f}" for f in nllb.FILES]
    assert model.installed("nllb-600m") and not model.installed("nllb-1.3b")
    assert steps == sorted(steps) and steps[-1] == sum(len(f) for f in nllb.FILES)  # over all the files
    assert model.installed_models() == [{"name": "nllb-600m", "label": "NLLB-200 600M", "size": steps[-1]}]
    model.uninstall("nllb-600m")
    assert not model.installed("nllb-600m")
    with pytest.raises(TranslateError, match="isn't installed"):
        model.uninstall("nllb-600m")


def test_failed_download_leaves_no_model(fake_hub, monkeypatch):
    monkeypatch.setattr(nllb, "FILES", ["config.json", "broken"])
    model = nllb.Nllb()
    with pytest.raises(TranslateError, match="connection reset"):
        model.install("nllb-600m")
    assert not model.installed("nllb-600m")
    assert [f.name for f in model.folder("nllb-600m").iterdir()] == ["config.json"]  # no half file


def test_translate_with_the_languages_codes(fake_hub, fake_packages):
    model = nllb.Nllb()
    with pytest.raises(TranslateError, match="isn't installed"):
        model.translate("nllb-600m", ["a"], "zh", "en")
    model.install("nllb-600m")
    assert model.translate("nllb-600m", ["我們 去", "公園"], "zt", "fr") == ["我們 去", "公園"]
    assert model.translate("nllb-600m", ["neih hou"], "yue", "en") == ["NEIH HOU"]
    assert len(fake_packages) == 1  # loaded once
    tokens, prefix = fake_packages[0].asked[0]
    assert tokens == [["zho_Hant", "我們", "去", "</s>"], ["zho_Hant", "公園", "</s>"]]
    assert prefix == [["fra_Latn"], ["fra_Latn"]]
    with pytest.raises(TranslateError, match="can't translate"):
        model.translate("nllb-600m", ["a"], "nan", "en")  # Taigi
    model.uninstall("nllb-600m")  # unloaded too
    with pytest.raises(TranslateError, match="isn't installed"):
        model.translate("nllb-600m", ["a"], "zh", "en")


def test_missing_packages_tell_how_to_install(fake_hub, monkeypatch):
    monkeypatch.setitem(sys.modules, "ctranslate2", None)
    model = nllb.Nllb()
    model.install("nllb-600m")
    with pytest.raises(TranslateError, match="make install-nllb"):
        model.translate("nllb-600m", ["a"], "zh", "en")
    monkeypatch.setattr(nllb.importlib.util, "find_spec", lambda name: None)
    assert not model.available()


def test_install_runs_pip_then_downloads(fake_hub, monkeypatch):
    ran = []
    returncode = [0]
    monkeypatch.setattr(nllb_install.subprocess, "run",
                        lambda command, check: ran.append(command[3:]) or types.SimpleNamespace(returncode=returncode[0]))
    assert nllb_install.install("nllb-1.3b") == 0
    assert ran == [["install", "-r", str(nllb_install.PROJECT_ROOT / "requirements-nllb.txt")]]
    assert nllb.Nllb().installed("nllb-1.3b") and len(fake_hub) == len(nllb.FILES)
    assert nllb_install.install("nllb-1.3b") == 0 and len(fake_hub) == len(nllb.FILES)  # already downloaded
    returncode[0] = 2
    assert nllb_install.install("nllb-600m") == 2 and not nllb.Nllb().installed("nllb-600m")


def test_cli_install_command(fake_hub, monkeypatch, capsys):
    from miningcat.application.converter.errors import ConverterError
    from miningcat.interfaces.cli.main import build_parser
    from miningcat.interfaces.cli.translation_command import NllbInstallCommand
    monkeypatch.setattr(nllb_install, "install_packages", lambda: 0)
    args = build_parser().parse_args(["install-nllb"])
    NllbInstallCommand().run(args)
    assert nllb.Nllb().installed("nllb-600m") and "is installed" in capsys.readouterr().out
    monkeypatch.setattr(nllb_install, "install_packages", lambda: 1)
    with pytest.raises(ConverterError, match="pip"):
        NllbInstallCommand().run(build_parser().parse_args(["install-nllb", "--model", "nllb-1.3b"]))
