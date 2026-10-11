import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# Never read or write the user's files (sources/, output/, library/ and its database): everything goes to a
# temporary folder. Every page reads the language studied from the database.
@pytest.fixture(autouse=True)
def _isolated_paths(tmp_path, monkeypatch):
    from miningcat.config.paths import paths
    from miningcat.infrastructure.persistence.database import database
    monkeypatch.setattr(paths, "root", tmp_path)
    database.reset_cache()
    yield
    database.reset_cache()


# Never start the real OmniVoice (its model takes GBs of memory): it isn't installed, unless a test fakes it.
@pytest.fixture(autouse=True)
def _no_omnivoice(tmp_path, monkeypatch):
    from miningcat.infrastructure.speech import omnivoice_tts
    venv = tmp_path / "no-omnivoice-venv"
    monkeypatch.setattr(omnivoice_tts, "VENV", venv)
    monkeypatch.setattr(omnivoice_tts, "PYTHON", venv / "bin" / "python3")

