import json

from game_ocr.settings import GameOcrSettings


def _ready_settings() -> GameOcrSettings:
    return GameOcrSettings(
        backend="macos", backend_state={"id": 7, "owner": "Game"}, window_label="Game",
        screenshot_region=(0.0, 0.1, 1.0, 0.9), text_region=(0.0, 0.7, 1.0, 0.3),
    )


def test_load_missing_file_returns_defaults(tmp_path):
    settings = GameOcrSettings.load(tmp_path / "missing.json")
    assert settings == GameOcrSettings()
    assert not settings.has_window
    assert not settings.is_ready


def test_save_then_load_roundtrip_restores_region_tuples(tmp_path):
    path = tmp_path / "sub" / "game.json"
    _ready_settings().save(path)
    loaded = GameOcrSettings.load(path)
    assert loaded == _ready_settings()
    assert isinstance(loaded.text_region, tuple)


def test_load_default_path_is_redirected_by_conftest(_isolated_game_ocr_settings):
    _ready_settings().save()
    assert _isolated_game_ocr_settings.exists()
    assert GameOcrSettings.load() == _ready_settings()


def test_load_corrupted_file_returns_defaults(tmp_path):
    path = tmp_path / "game.json"
    path.write_text("{not json", encoding="utf-8")
    assert GameOcrSettings.load(path) == GameOcrSettings()


def test_load_ignores_unknown_keys(tmp_path):
    path = tmp_path / "game.json"
    path.write_text(json.dumps({"window_label": "Game", "future_option": 1}), encoding="utf-8")
    assert GameOcrSettings.load(path).window_label == "Game"


def test_is_ready_needs_window_and_text_region():
    settings = _ready_settings()
    assert settings.is_ready
    settings.text_region = None
    assert settings.has_window and not settings.is_ready


def test_has_window_needs_backend_state():
    assert not GameOcrSettings(backend="macos", backend_state={}).has_window


def test_set_window_resets_areas():
    settings = _ready_settings()
    settings.set_window("macos", {"id": 8, "owner": "Other"}, "Other")
    assert settings.window_label == "Other"
    assert settings.screenshot_region is None
    assert settings.text_region is None


def test_set_screenshot_region_resets_text_region_when_changed():
    settings = _ready_settings()
    settings.set_screenshot_region((0.0, 0.0, 0.5, 0.5))
    assert settings.screenshot_region == (0.0, 0.0, 0.5, 0.5)
    assert settings.text_region is None


def test_set_screenshot_region_keeps_text_region_when_unchanged():
    settings = _ready_settings()
    settings.set_screenshot_region((0.0, 0.1, 1.0, 0.9))
    assert settings.text_region == (0.0, 0.7, 1.0, 0.3)
