"""Takes the documentation's screenshots (docs/assets/screenshots/).

MiningCat runs from a temporary copy of src/, on demo data: a short story, small Mandarin and Taigi dictionaries, a
generated video with its subtitles, and a fake AnkiConnect. The user's library never shows up: only the frequency list
given with --frequency is read from it (read-only), and the translation models already downloaded are linked into the
copy, so that the card creator and Settings › Translation work. Chrome (installed) is driven with Playwright.

    python tools/screenshots.py                          # every screenshot
    python tools/screenshots.py --only reader            # only the reader's (see GROUPS)
    python tools/screenshots.py --frequency TOCFL        # with a frequency list: a file, or the title of one of library/

Needs Playwright (pip install playwright, it uses the installed Chrome) and ffmpeg.
"""
import argparse
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "assets" / "screenshots"
GROUPS = ["home", "reader", "card", "player", "settings", "converter", "taigi"]

# ------------------------------------------------------------------ demo data

TITLE = "書店的貓"
CHAPTERS = [
    ("第1章 書店的貓", [
        "在台北的一條小巷子裡，有一家很老的書店。書店的老闆姓林，他每天早上八點開門。",
        "店裡住著一隻橘色的貓，名字叫做「年糕」。年糕最喜歡睡在窗邊的書架上，曬著溫暖的太陽。",
        "客人來的時候，年糕會慢慢地抬起頭，看他們一眼，然後又睡著了。林老闆常常說：「這隻貓比我還懂書。」",
    ]),
    ("第2章 下雨天", [
        "今天下了一整天的雨。巷子裡很安靜，書店裡一個客人也沒有。",
        "林老闆泡了一杯熱茶，坐在窗邊看書。年糕躺在他的腳邊，聽著雨聲。",
    ]),
    ("第3章 新朋友", [
        "雨停了以後，一個小女孩走進了書店。她的頭髮濕濕的，手裡拿著一本舊書。",
        "年糕站起來，走到她的身邊。小女孩笑了：「你好，我可以跟你做朋友嗎？」",
    ]),
]
CUES = [
    "在台北的一條小巷子裡，有一家很老的書店。",
    "店裡住著一隻橘色的貓，名字叫做「年糕」。",
    "年糕最喜歡睡在窗邊的書架上，曬著溫暖的太陽。",
    "林老闆常常說：「這隻貓比我還懂書。」",
    "今天下了一整天的雨。",
]
# The word looked up and made a card of, its sentence and the sentence's translation
WORD = "太陽"
SENTENCE_TRANSLATION = "Niangao loves to sleep on the bookshelf by the window, in the warm sun."

TERMS = [  # word, pinyin, definition
    ("台北", "táiběi", "Taipei"), ("巷子", "xiàngzi", "lane, alley"), ("小", "xiǎo", "small, little"),
    ("很", "hěn", "very"), ("老", "lǎo", "old"), ("書店", "shūdiàn", "bookshop"), ("書", "shū", "book"),
    ("老闆", "lǎobǎn", "boss, shop owner"), ("姓", "xìng", "to be surnamed"), ("每天", "měitiān", "every day"),
    ("早上", "zǎoshang", "morning"), ("開門", "kāimén", "to open (a shop)"), ("住", "zhù", "to live"),
    ("橘色", "júsè", "orange (colour)"), ("貓", "māo", "cat"), ("名字", "míngzi", "name"),
    ("叫做", "jiàozuò", "to be called"), ("年糕", "niángāo", "nian gao, sticky rice cake eaten at New Year"),
    ("最", "zuì", "most"), ("喜歡", "xǐhuan", "to like"), ("睡", "shuì", "to sleep"),
    ("窗邊", "chuāngbiān", "by the window"), ("書架", "shūjià", "bookshelf"), ("曬", "shài", "to bask in the sun"),
    ("溫暖", "wēnnuǎn", "warm"), ("太陽", "tàiyáng", "sun"), ("客人", "kèrén", "customer, guest"),
    ("時候", "shíhou", "time, moment"), ("慢慢", "mànmàn", "slowly"), ("抬起", "táiqǐ", "to raise"),
    ("頭", "tóu", "head"), ("看", "kàn", "to look, to read"), ("然後", "ránhòu", "then, afterwards"),
    ("睡著", "shuìzháo", "to fall asleep"), ("常常", "chángcháng", "often"), ("說", "shuō", "to say"),
    ("懂", "dǒng", "to understand"), ("今天", "jīntiān", "today"), ("下雨", "xiàyǔ", "to rain"),
    ("雨", "yǔ", "rain"), ("安靜", "ānjìng", "quiet"), ("熱茶", "rèchá", "hot tea"), ("朋友", "péngyou", "friend"),
    ("女孩", "nǚhái", "girl"), ("學", "xué", "to learn"), ("舊", "jiù", "old (not new)"),
]
KNOWN = ["書", "看", "朋友", "學", "小", "很", "老", "說", "今天", "的", "在", "一", "有", "家", "他", "我", "這",
         "名字", "書店", "每天", "早上", "喜歡", "時候", "客人", "他們", "一眼", "還", "比", "林", "八點"]
LEARNING = ["安靜", "書架", "巷子", "老闆", "年糕"]

# Taigi: Hanji with their Tâi-lô reading (the Ministry of Education's dictionary)
TAIGI_TEXT = "今仔日天氣真好。\n我欲去臺北食飯，你食飽未？\n阮阿媽愛啉茶。\nGóa beh khì Tâi-pak chia̍h-pn̄g."
TAIGI_TERMS = [
    ("今仔日", "kin-á-ji̍t", "today"), ("天氣", "thinn-khì", "weather"), ("真", "tsin", "very; true"),
    ("好", "hó", "good"), ("我", "guá", "I, me"), ("欲", "beh", "to want to; about to"), ("去", "khì", "to go"),
    ("臺北", "Tâi-pak", "Taipei"), ("食飯", "tsia̍h-pn̄g", "to eat, to have a meal"), ("你", "lí", "you"),
    ("食飽", "tsia̍h-pá", "to have eaten one's fill"), ("未", "buē", "not yet (at the end of a question)"),
    ("阮", "guán", "we (not including you); my"), ("阿媽", "a-má", "grandmother"), ("愛", "ài", "to love, to like"),
    ("啉", "lim", "to drink"), ("茶", "tê", "tea"),
]
TAIGI_KNOWN = ["好", "我", "你", "去", "真", "愛", "茶"]
TAIGI_LEARNING = ["今仔日", "天氣", "欲"]


def write_epub(path: Path) -> None:
    def chapter(title, paragraphs):
        body = "".join(f"<p>{p}</p>" for p in paragraphs)
        return (f'<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh-TW">'
                f"<head><title>{title}</title></head><body><h1>{title}</h1>{body}</body></html>")

    numbers = range(1, len(CHAPTERS) + 1)
    manifest = "".join(f'<item id="c{i}" href="c{i}.xhtml" media-type="application/xhtml+xml"/>' for i in numbers)
    spine = "".join(f'<itemref idref="c{i}"/>' for i in numbers)
    toc = "".join(f'<li><a href="c{i}.xhtml">{t}</a></li>' for i, (t, _) in enumerate(CHAPTERS, 1))
    opf = (f'<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
           f'unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
           f'<dc:identifier id="id">miningcat-demo</dc:identifier><dc:title>{TITLE}</dc:title>'
           f"<dc:creator>MiningCat</dc:creator><dc:language>zh-TW</dc:language></metadata>"
           f'<manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
           f"{manifest}</manifest><spine>{spine}</spine></package>")
    nav = (f'<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" '
           f'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>{TITLE}</title></head>'
           f'<body><nav epub:type="toc"><ol>{toc}</ol></nav></body></html>')
    container = ('<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                 '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                 "</rootfiles></container>")
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container)
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/nav.xhtml", nav)
        for i, (title, paragraphs) in enumerate(CHAPTERS, 1):
            z.writestr(f"OEBPS/c{i}.xhtml", chapter(title, paragraphs))


def write_dictionary(path: Path, title: str, language: str, terms: list[tuple[str, str, str]]) -> None:
    index = {"title": title, "revision": "1", "format": 3, "sourceLanguage": language, "targetLanguage": "en"}
    bank = [[word, reading, "", "", 0, [definition], i, ""] for i, (word, reading, definition) in enumerate(terms, 1)]
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("index.json", json.dumps(index, ensure_ascii=False))
        z.writestr("term_bank_1.json", json.dumps(bank, ensure_ascii=False))


def write_video(path: Path, srt: Path) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", "gradients=s=1280x720:c0=0x274466:c1=0xe39a63:x0=300:y0=0:x1=900:y1=720:d=20:speed=0.004",
                    "-f", "lavfi", "-i", "sine=frequency=220:duration=20:sample_rate=44100",
                    "-filter:a", "volume=0.05", "-t", "20", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-shortest", str(path)], check=True)
    srt.write_text("\n".join(f"{i}\n00:00:{4 * (i - 1):02d},000 --> 00:00:{4 * i:02d},000\n{cue}\n"
                             for i, cue in enumerate(CUES, 1)), encoding="utf-8")


def write_audio(path: Path, text: str, seconds: float) -> None:
    """The text read by macOS's Taiwanese voice, else a quiet tone: only its player shows in the card creator."""
    aiff = path.with_suffix(".aiff")
    if shutil.which("say") and subprocess.run(["say", "-v", "Meijia", "-o", str(aiff), text]).returncode == 0:
        source = ["-i", str(aiff), "-af", f"adelay=200,apad=whole_dur={seconds}"]
    else:
        source = ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-af", "volume=0.1"]
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *source, str(path)], check=True)


def frequency_list(name: str, folder: Path) -> Path:
    """The frequency list: a file, or a list of the user's library exported to JSON (most frequent first)."""
    if Path(name).is_file():
        return Path(name)
    database = ROOT / "library" / "miningcat.db"
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as db:
        row = db.execute("SELECT id FROM dictionaries WHERE title = ? AND meta_count > 0", (name,)).fetchone()
        if row is None:
            sys.exit(f"No frequency list {name!r} in {database}, and no such file.")
        ranks = db.execute("SELECT expression, data FROM term_meta WHERE dict_id = ? AND mode = 'freq'", row).fetchall()

    def rank(data: str) -> float:
        value = json.loads(data)
        if isinstance(value, dict):
            value = value.get("value", value.get("frequency", 0))
            value = value.get("value", 0) if isinstance(value, dict) else value
        return float(value)

    words = list(dict.fromkeys(word for word, _ in sorted(ranks, key=lambda r: rank(r[1]))))
    path = folder / f"{name}.json"
    path.write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
    return path


# ------------------------------------------------------------------ servers

class FakeAnki(BaseHTTPRequestHandler):
    """AnkiConnect with a few decks and note types; notes are not kept."""

    MODELS = {"Chinese sentence mining": ["Hanzi", "Zhuyin", "Meaning", "Sentence", "Picture", "Sentence Audio"],
              "Basic": ["Front", "Back"]}
    ANSWERS = {"version": 6, "deckNames": ["Default", "Mining::Chinese", "Mining::Japanese"],
               "modelNames": sorted(MODELS), "findNotes": [], "findCards": [], "notesInfo": [], "cardsInfo": [],
               "requestPermission": {"permission": "granted"}}

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        action, params = request.get("action"), request.get("params") or {}
        result = self.MODELS.get(params.get("modelName"), []) if action == "modelFieldNames" else self.ANSWERS.get(action)
        body = json.dumps({"result": result, "error": None}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Demo:
    """The GUI on its own copy of src/, and its API."""

    def __init__(self, folder: Path):
        self.root = folder / "root"
        self.data = folder / "data"
        self.data.mkdir()
        shutil.copytree(ROOT / "src", self.root / "src", ignore=shutil.ignore_patterns("__pycache__", "tests"))
        models = ROOT / "library" / "translation_models"
        if models.is_dir():
            (self.root / "library" / "translation_models").mkdir(parents=True)
            for model in models.iterdir():
                try:
                    (self.root / "library" / "translation_models" / model.name).symlink_to(model, model.is_dir())
                except OSError:  # no symbolic links (Windows without the right): no translation
                    pass
        self.anki = HTTPServer(("127.0.0.1", free_port()), FakeAnki)
        threading.Thread(target=self.anki.serve_forever, daemon=True).start()
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.server = subprocess.Popen([sys.executable, "-m", "miningcat.interfaces.web", "--port", str(self.port), "--no-browser"],
                                       cwd=self.root, env={**os.environ, "PYTHONPATH": str(self.root / "src")},
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                self.call("/api/profile")
                break
            except OSError:
                time.sleep(0.2)
        else:
            sys.exit("MiningCat didn't start.")

    def stop(self):
        self.server.terminate()
        self.server.wait()
        self.anki.shutdown()

    def call(self, path, body=None, data=None, content_type=None):
        headers = {"X-MiningCat": "1"}
        if body is not None:
            data, content_type = json.dumps(body).encode(), "application/json"
        if content_type:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method="POST" if data is not None else "GET")
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read())

    def upload(self, path, field, file: Path):
        boundary = uuid.uuid4().hex
        data = (f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{file.name}"\r\n'
                f"Content-Type: application/octet-stream\r\n\r\n").encode() + file.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        return self.call(path, data=data, content_type=f"multipart/form-data; boundary={boundary}")

    def import_dictionary(self, file: Path):
        job = self.upload("/api/dict/import", "file", file)["job"]
        for _ in range(300):
            status = self.call(f"/api/dict/import/{job}")
            if status.get("done"):
                if status.get("error"):
                    sys.exit(f"{file.name}: {status['error']}")
                return status
            time.sleep(0.2)
        sys.exit(f"{file.name}: the import didn't finish.")

    def study(self, language):
        self.call("/api/profile", {"language": language})

    def statuses(self, language, known, learning):
        for status, words in (("known", known), ("learning", learning)):
            for word in words:
                self.call("/api/words/status", {"language": language, "expression": word, "status": status})

    def seed(self, frequency: Path | None):
        """Mandarin: the dictionary, the words, the book, the video, Anki; Taigi: its dictionary and words."""
        write_epub(self.data / f"{TITLE}.epub")
        write_dictionary(self.data / "demo-mandarin.zip", "Demo Mandarin dictionary", "zh", TERMS)
        write_dictionary(self.data / "demo-taigi.zip", "Demo Taigi dictionary", "nan", TAIGI_TERMS)
        write_video(self.data / f"{TITLE}.mp4", self.data / f"{TITLE}.srt")
        write_audio(self.data / "word.mp3", WORD, 1.3)
        write_audio(self.data / "sentence.mp3", CUES[2], 4.5)

        self.study("nan")
        self.import_dictionary(self.data / "demo-taigi.zip")
        self.statuses("nan", TAIGI_KNOWN, TAIGI_LEARNING)

        self.study("zh")
        self.call("/api/mining/script", {"language": "zh", "script": "both"})
        self.import_dictionary(self.data / "demo-mandarin.zip")
        if frequency:
            title = self.import_dictionary(frequency)["dictionary"]["title"]
            lists = self.call("/api/frequency/lists?language=zh")["lists"]
            self.call("/api/frequency/list", {"language": "zh", "ids": [l["id"] for l in lists if l["title"] == title]})
        self.statuses("zh", KNOWN, LEARNING)
        self.book = self.upload("/reader/api/books", "files", self.data / f"{TITLE}.epub")["added"][0]["id"]
        name = urllib.parse.quote(f"{TITLE}.mp4")
        self.video = self.call(f"/player/api/videos?name={name}", data=(self.data / f"{TITLE}.mp4").read_bytes(),
                               content_type="video/mp4")["video"]["id"]
        self.upload(f"/player/api/videos/{self.video}/subtitles", "files", self.data / f"{TITLE}.srt")
        anki = f"http://127.0.0.1:{self.anki.server_address[1]}"
        self.call("/api/anki/config", {"url": anki})
        guess = self.call("/api/anki/fields?model=Chinese%20sentence%20mining&language=zh")["guess"]
        self.call("/api/anki/config", {"notes": {"zh": {"deck": "Mining::Chinese", "model": "Chinese sentence mining",
                                                         "fields": guess, "tags": "mining-cat"}}})

    def ensure_card(self):
        """The card waiting for Anki, when the card creator didn't make it (--only)."""
        if not self.call("/api/cards?language=zh")["cards"]:
            self.call("/api/cards", {"language": "zh", "send": False, "fields": {
                "word": WORD, "reading": "tàiyáng", "definition": "sun", "sentence": CUES[2],
                "sentence_translation": SENTENCE_TRANSLATION}})


# ------------------------------------------------------------------ screenshots

# Clicks a character of a text: the popup looks the word up where it's clicked.
TEXT_POSITION = """([root, text, nth]) => {
  const walker = document.createTreeWalker(document.querySelector(root), NodeFilter.SHOW_TEXT);
  const nodes = []; let all = "", node;
  while ((node = walker.nextNode())) { nodes.push([node, all.length]); all += node.data; }
  let index = -1;
  for (let i = 0; i <= nth; i++) index = all.indexOf(text, index + 1);
  if (index < 0) return null;
  for (const [n, start] of nodes) if (index < start + n.data.length) {
    const range = document.createRange(); range.setStart(n, index - start); range.setEnd(n, index - start + 1);
    const box = range.getBoundingClientRect(); return {x: box.x + box.width / 2, y: box.y + box.height / 2};
  }
}"""


class Shooter:
    def __init__(self, demo: Demo, page):
        self.demo, self.page = demo, page

    def go(self, path, wait=1200):
        self.page.goto(self.demo.base + path)
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(wait)

    def shot(self, name, full=False):
        self.page.wait_for_timeout(400)
        self.page.screenshot(path=str(OUT / f"{name}.png"), full_page=full)
        print(f"  {name}.png")

    def click_text(self, root, text, nth=0, wait=1500):
        position = self.page.evaluate(TEXT_POSITION, [root, text, nth])
        if not position:
            sys.exit(f"{text!r} isn't in {root}.")
        self.page.mouse.click(position["x"], position["y"])
        self.page.wait_for_timeout(wait)

    def home(self):
        self.go("/")
        self.shot("home-hub")

    def reader(self):
        self.go("/reader/")
        self.shot("reader-library")
        self.go(f"/reader/{self.demo.book}", 1500)
        self.shot("reader-reading")
        self.page.click("#toc-btn")
        self.shot("reader-contents")
        self.page.keyboard.press("Escape")
        self.page.click("#settings-btn")
        self.shot("reader-settings")
        self.page.keyboard.press("Escape")
        self.click_text("#content", WORD)
        self.shot("reader-lookup")

    def card(self):
        self.go(f"/reader/{self.demo.book}", 1500)
        self.click_text("#content", WORD)
        self.page.get_by_role("button", name="Card").first.click()
        self.page.wait_for_timeout(6000)  # readings, translation
        translation = self.page.get_by_label("Sentence translation")
        translation = translation if translation.count() else self.page.locator("textarea").first
        translation.fill(SENTENCE_TRANSLATION)  # the same in every screenshot, whichever model translates
        translation.evaluate("t => t.spellcheck = false")
        audio = self.page.locator('input[type=file][accept*="audio"]')
        audio.nth(0).set_input_files(str(self.demo.data / "word.mp3"))
        audio.nth(1).set_input_files(str(self.demo.data / "sentence.mp3"))
        self.page.wait_for_function("() => [...document.querySelectorAll('audio')].filter(a => a.duration > 0).length >= 2")
        self.page.evaluate("() => document.activeElement && document.activeElement.blur()")
        self.shot("card-creator")
        self.page.get_by_role("button", name="Save for later").click()
        self.page.wait_for_timeout(1500)

    def player(self):
        self.demo.ensure_card()
        self.go("/player/")
        self.shot("player-library")
        self.go(f"/player/{self.demo.video}", 1500)
        self.page.evaluate("() => { const v = document.querySelector('#video'); v.pause(); v.currentTime = 9.5; }")
        self.page.wait_for_timeout(1200)
        self.shot("player-watch")
        self.click_text("#sub-primary", WORD)
        self.shot("player-lookup")

    def settings(self):
        self.demo.ensure_card()
        for tab, name, full in [("dictionaries", "settings-dictionaries", True), ("languages", "settings-languages", True),
                                ("anki", "settings-anki", True), ("translation", "settings-translation", False),
                                ("cards", "settings-cards", False), ("preferences", "settings-preferences", False)]:
            self.go("/settings/")
            self.page.click(f'[data-tab="{tab}"]')
            self.page.wait_for_timeout(2000)
            self.shot(name, full)

    def converter(self):
        self.go("/converter/")
        source = self.page.locator("#source")
        source.get_by_text("Audiobook / Ebook").click()
        self.page.set_input_files("#ebook-input", str(self.demo.data / f"{TITLE}.epub"))
        self.page.wait_for_timeout(3000)
        self.shot("converter-audiobook", True)
        source.get_by_text("Video", exact=True).click()
        self.page.wait_for_timeout(800)
        self.shot("converter-video", True)
        source.get_by_text("Video game / Screen share").click()
        self.page.wait_for_timeout(1200)
        self.shot("converter-game", True)

    def taigi(self):
        self.demo.study("nan")
        self.go("/clipboard/")
        self.page.fill("#editor", TAIGI_TEXT)
        self.page.click("#toggle")
        self.page.wait_for_timeout(1500)
        self.click_text("#text", "食飯")
        self.shot("taigi-lookup")
        self.page.evaluate("() => MiningCatMining.hide()")
        self.click_text("#text", "chia̍h")
        self.shot("taigi-lookup-romanized")
        self.page.evaluate("() => MiningCatMining.hide()")
        self.page.click("#toggle")  # Edit
        self.page.select_option("#taigi-convert", "poj")
        self.page.wait_for_function("() => document.querySelector('#editor').value.startsWith('Kin')")
        self.page.evaluate("() => document.activeElement && document.activeElement.blur()")
        self.shot("taigi-convert")
        self.go("/settings/")
        self.page.click('[data-tab="languages"]')
        self.page.wait_for_timeout(2000)
        self.shot("taigi-settings")
        self.demo.study("zh")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", choices=GROUPS, help="take only the screenshots of one screen")
    parser.add_argument("--frequency", help="a frequency list: a file, or the title of a frequency list of library/")
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright

    with tempfile.TemporaryDirectory(prefix="miningcat-screenshots-") as folder:
        demo = Demo(Path(folder))
        try:
            frequency = frequency_list(args.frequency, demo.data) if args.frequency else None
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome")
                page = browser.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=2,
                                           color_scheme="light", locale="en-US").new_page()
                shooter = Shooter(demo, page)
                OUT.mkdir(parents=True, exist_ok=True)
                if args.only in (None, "home"):  # before a language is chosen
                    shooter.go("/")
                    shooter.shot("home-language-picker")
                print("Demo data...")
                demo.seed(frequency)
                for group in GROUPS:
                    if args.only in (None, group):
                        print(f"{group}:")
                        getattr(shooter, group)()
                browser.close()
        finally:
            demo.stop()


if __name__ == "__main__":
    main()
