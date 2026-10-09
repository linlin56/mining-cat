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

