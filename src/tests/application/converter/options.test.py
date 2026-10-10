import pytest

from miningcat.application.converter import options
from miningcat.domain.languages import Language
from miningcat.infrastructure.speech import engine_install, qwen3_asr


@pytest.fixture(autouse=True)
def qwen_not_installed(monkeypatch):
    monkeypatch.setattr(qwen3_asr, "installed", lambda: False)


def test_convert_labels_follow_the_script():
    assert options.convert_labels_for(Language.MANDARIN_TW) == ["No conversion", "Simplified - China"]
    assert options.convert_labels_for(Language.MANDARIN_CN)[1:] == ["Traditional - Taiwan", "Traditional - Chinese"]
    assert options.convert_labels_for(Language.FRENCH) == ["No conversion"]


def test_cantonese_only_offers_large_models():
    assert options.precision_values_for(Language.CANTONESE_HK) == ["Large", "Turbo (fast, large-v3)"]
    assert options.precision_values_for(Language.FRENCH) == options.PRECISION_VALUES


def test_qwen3_asr_is_offered_when_installed(monkeypatch):
    monkeypatch.setattr(qwen3_asr, "installed", lambda: True)
    assert options.precision_values_for(Language.FRENCH) == options.PRECISION_VALUES + options.OPTIONAL_QWEN3_VALUES
    assert options.precision_values_for(Language.CANTONESE_HK)[-2:] == options.OPTIONAL_QWEN3_VALUES
    # it only transcribes: a book is aligned with Whisper
    assert options.precision_values_for(Language.FRENCH, aligning=True) == options.PRECISION_VALUES
    assert options.model_for("Qwen3-ASR 1.7B (more accurate, slower)", Language.JAPANESE) == "qwen3-1.7b"
    assert options.model_for("Qwen3-ASR 1.7B (more accurate, slower)", Language.JAPANESE, aligning=True) == "base"
    assert options.language_options(Language.FRENCH)["align_precision"] == options.PRECISION_VALUES


def test_taigi_needs_its_engines_installed(monkeypatch):
    assert options.language_options(Language.TAIGI)["needs_install"] == "taigi"  # Qwen3-ASR and MMS
    assert options.language_options(Language.FRENCH)["needs_install"] is None  # Whisper and Edge do its speech
    monkeypatch.setattr(engine_install, "installed", lambda engines: True)
    assert options.language_options(Language.TAIGI)["needs_install"] is None


def test_model_from_precision():
    assert options.model_from_precision("Base (default)") == "base"
    assert options.model_from_precision("Turbo (fast, large-v3)") == "turbo"


def test_audio_track_label_prefers_title():
    track = {"index": 1, "language": "chi", "title": "Mandarin (Taiwan)", "channels": 2}
    assert options.audio_track_label(track) == "Track 1 - Mandarin (Taiwan) - stereo"
    assert options.audio_track_label({"index": 0, "language": "", "title": "", "channels": 6}) == "Track 0 - unknown language"


def test_convert_target_of_a_label():
    assert options.convert_target("Simplified - China", Language.MANDARIN_TW) == "s"
    assert options.convert_target("No conversion", Language.MANDARIN_TW) is None
    assert options.convert_target("Traditional - Taiwan", Language.MANDARIN_TW) is None  # not offered for it


def test_model_for_unknown_precision_is_the_default():
    assert options.model_for("Small (oops, not a value)", Language.FRENCH) == "base"
    assert options.model_for("Base (default)", Language.CANTONESE_HK) == "large"


def test_validate_video_url():
    assert options.validate_video_url("https://youtu.be/x", "YouTube") is None
    assert "doesn't match" in options.validate_video_url("https://youtu.be/x", "Bilibili")
    assert "supported" in options.validate_video_url("https://example.com/x", "YouTube")
    assert options.validate_video_url("", "YouTube") is None
