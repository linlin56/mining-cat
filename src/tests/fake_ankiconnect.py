import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeAnki:
    def __init__(self):
        self.lock = threading.Lock()
        self.decks = {"Default": 1, "Mining::Chinese": 2, "Mining::Japanese": 3}
        self.models = {
            "Basic": ["Front", "Back"],
            "Chinese (MiningCat test)": ["Hanzi", "Zhuyin", "Meaning", "Sentence", "Picture", "Sentence Audio"],
        }
        self.templates: dict[str, dict] = {}  # model -> {"css", "templates": {name: {"Front", "Back"}}}
        self.notes: dict[int, dict] = {}
        self.cards: dict[int, dict] = {}
        self.media: dict[str, dict] = {}
        self.next_id = 1_700_000_000_000

    def _id(self) -> int:
        self.next_id += 1
        return self.next_id

    def add_existing(self, deck: str, model: str, fields: dict, interval: int = 0, suspended: bool = False) -> int:
        with self.lock:
            note_id = self._id()
            card_id = self._id()
            self.notes[note_id] = {"deck": deck, "model": model, "fields": fields, "cards": [card_id], "tags": []}
            self.cards[card_id] = {"note": note_id, "interval": interval, "queue": -1 if suspended else 2, "deck": deck}
            return note_id

    def handle(self, action: str, params: dict):
        with self.lock:
            if action == "version":
                return 6
            if action == "deckNames":
                return list(self.decks)
            if action == "modelNames":
                return list(self.models)
            if action == "modelFieldNames":
                if params["modelName"] not in self.models:
                    raise ValueError(f"model was not found: {params['modelName']}")
                return self.models[params["modelName"]]
            if action == "createDeck":
                return self.decks.setdefault(params["deck"], self._id())
            if action == "createModel":
                if params["modelName"] in self.models:
                    raise ValueError("Model name already exists")
                self.models[params["modelName"]] = list(params["inOrderFields"])
                self.templates[params["modelName"]] = {"css": params.get("css", ""), "templates": {
                    t["Name"]: {"Front": t["Front"], "Back": t["Back"]} for t in params["cardTemplates"]}}
                return {"name": params["modelName"]}
            if action == "modelFieldAdd":
                self.models[params["modelName"]].insert(params.get("index", len(self.models[params["modelName"]])), params["fieldName"])
                return None
            if action == "updateModelTemplates":
                model = params["model"]
                existing = self.templates.setdefault(model["name"], {"css": "", "templates": {}})["templates"]
                for name, template in model["templates"].items():
                    if name not in existing:
                        raise ValueError(f"template not found: {name}")
                    existing[name].update(template)
                return None
            if action == "updateModelStyling":
                self.templates.setdefault(params["model"]["name"], {"css": "", "templates": {}})["css"] = params["model"]["css"]
                return None
            if action == "storeMediaFile":
                self.media[params["filename"]] = {k: v for k, v in params.items() if k != "filename"}
                return params["filename"]
            if action == "addNote":
                note = params["note"]
                if note["deckName"] not in self.decks:
                    raise ValueError(f"deck was not found: {note['deckName']}")
                fields = self.models.get(note["modelName"])
                if fields is None:
                    raise ValueError(f"model was not found: {note['modelName']}")
                first = note["fields"].get(fields[0], "")
                if not first:
                    raise ValueError("cannot create note because it is empty")
                allowed = (note.get("options") or {}).get("allowDuplicate")
                for existing in self.notes.values():
                    if not allowed and existing["deck"] == note["deckName"] and existing["fields"].get(fields[0]) == first:
                        raise ValueError("cannot create note because it is a duplicate")
                note_id = self._id()
                card_id = self._id()
                self.notes[note_id] = {"deck": note["deckName"], "model": note["modelName"],
                                       "fields": note["fields"], "cards": [card_id], "tags": note.get("tags", [])}
                self.cards[card_id] = {"note": note_id, "interval": 0, "queue": 0, "deck": note["deckName"]}
                return note_id
            if action == "findNotes":
                match = re.search(r'deck:([^"]+)', params["query"])
                deck = match.group(1) if match else None
                return [nid for nid, n in self.notes.items() if deck is None or n["deck"] == deck or n["deck"].startswith(deck + "::")]
            if action == "notesInfo":
                return [
                    {"noteId": nid, "modelName": self.notes[nid]["model"], "tags": self.notes[nid]["tags"],
                     "fields": {k: {"value": v, "order": i} for i, (k, v) in enumerate(self.notes[nid]["fields"].items())},
                     "cards": self.notes[nid]["cards"]}
                    for nid in params["notes"] if nid in self.notes
                ]
            if action == "findCards":
                ids = {int(x) for x in re.findall(r"\d+", params["query"])}
                return [cid for cid, c in self.cards.items() if c["note"] in ids]
            if action == "cardsInfo":
                return [{"cardId": cid, "note": self.cards[cid]["note"], "interval": self.cards[cid]["interval"],
                         "queue": self.cards[cid]["queue"], "deckName": self.cards[cid]["deck"]}
                        for cid in params["cards"] if cid in self.cards]
            raise ValueError(f"unsupported action: {action}")


def serve(port: int = 0, anki: FakeAnki | None = None):
    """Starts the server in a thread. Returns (server, anki, url)."""
    anki = anki or FakeAnki()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            try:
                result, error = anki.handle(body.get("action"), body.get("params") or {}), None
            except Exception as exc:
                result, error = None, str(exc)
            payload = json.dumps({"result": result, "error": error}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, anki, f"http://127.0.0.1:{server.server_address[1]}"


if __name__ == "__main__":
    import sys
    import time
    server, anki, url = serve(int(sys.argv[1]) if len(sys.argv) > 1 else 8765)
    anki.add_existing("Mining::Chinese", "Chinese (MiningCat test)", {"Hanzi": "我們", "Zhuyin": "", "Meaning": "we",
                      "Sentence": "", "Picture": "", "Sentence Audio": ""}, interval=40)
    anki.add_existing("Mining::Chinese", "Chinese (MiningCat test)", {"Hanzi": "天氣", "Zhuyin": "", "Meaning": "weather",
                      "Sentence": "", "Picture": "", "Sentence Audio": ""}, interval=3)
    print(f"Fake AnkiConnect on {url}")
    while True:
        time.sleep(3600)
