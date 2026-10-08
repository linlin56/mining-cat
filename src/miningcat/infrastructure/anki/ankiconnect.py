import json
import urllib.error
import urllib.request

from miningcat.domain.cards.errors import AnkiError, AnkiUnavailable


class AnkiConnect:
    """A client of the AnkiConnect add-on, listening in the running Anki."""

    VERSION = 6

    def __init__(self, url: str):
        self.url = url

    def invoke(self, action: str, timeout: float = 10, **params):
        """Runs an AnkiConnect action. Raises AnkiUnavailable when Anki doesn't answer, AnkiError when it refuses."""
        payload = json.dumps({"action": action, "version": self.VERSION, "params": params}).encode("utf-8")
        request = urllib.request.Request(self.url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as exc:
            raise AnkiUnavailable(f"Anki isn't reachable at {self.url} ({getattr(exc, 'reason', exc)}). "
                                  "Is Anki open with AnkiConnect installed?")
        except ValueError:
            raise AnkiUnavailable(f"{self.url} didn't answer like AnkiConnect.")
        if not isinstance(data, dict) or "error" not in data:
            raise AnkiUnavailable(f"{self.url} didn't answer like AnkiConnect.")
        if data["error"]:
            raise AnkiError(str(data["error"]))
        return data["result"]

    def in_batches(self, action: str, key: str, ids: list, size: int, **params) -> list:
        """Runs an action taking a list of ids (notesInfo, cardsInfo...) on `size` ids at a time."""
        results = []
        for start in range(0, len(ids), size):
            results += self.invoke(action, **params, **{key: ids[start:start + size]})
        return results
