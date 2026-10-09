import json

from miningcat.application import user_preferences
from miningcat.config.paths import paths


def test_defaults_without_a_file():
    assert user_preferences.get_preferences() == {"theme": "system", "highlights": "default"}
    assert not paths.user_config.exists()


def test_saved_in_user_config_json():
    assert user_preferences.save_preferences({"theme": "dark"}) == {"theme": "dark", "highlights": "default"}
    assert user_preferences.save_preferences({"highlights": "tritan"}) == {"theme": "dark", "highlights": "tritan"}
    assert paths.user_config == paths.root / "user" / "user-config.json"
    assert json.loads(paths.user_config.read_text(encoding="utf-8")) == {"theme": "dark", "highlights": "tritan"}


def test_unknown_values_are_ignored():
    user_preferences.save_preferences({"theme": "light"})
    assert user_preferences.save_preferences({"theme": "pink", "highlights": 3, "other": "x"}) \
        == {"theme": "light", "highlights": "default"}


def test_a_broken_file_gives_the_defaults():
    paths.user_config.parent.mkdir(parents=True)
    paths.user_config.write_text("[1, 2", encoding="utf-8")
    assert user_preferences.get_preferences() == {"theme": "system", "highlights": "default"}
    paths.user_config.write_text('{"theme": "sepia", "highlights": "deutan"}', encoding="utf-8")
    assert user_preferences.get_preferences() == {"theme": "system", "highlights": "deutan"}
