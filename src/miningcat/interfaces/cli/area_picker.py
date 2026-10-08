"""Where `game setup` draws the screenshot and text areas on a capture of the game: a page opened in the browser,
served on 127.0.0.1 until the user answers."""
import html
import io
import json
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image

from miningcat.domain.ocr.regions import FULL_REGION, Region, valid_region

SCREENSHOT_AREA_TITLE = "Select the window's full size (screenshot sent to the page)"
TEXT_AREA_TITLE = "Select the text area (read by OCR)"

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>MiningCat - {title}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 24px; background: #fdfbf7; color: #2d2d2d; }}
  .frame {{ position: relative; display: inline-block; cursor: crosshair; user-select: none; }}
  .frame img {{ display: block; max-width: min(100%, 1200px); max-height: 75vh; }}
  #rect {{ position: absolute; border: 2px solid #ff3b30; box-sizing: border-box; pointer-events: none; }}
  .buttons {{ margin-top: 12px; display: flex; gap: 8px; }}
  button {{ font: inherit; padding: 6px 14px; }}
</style>
</head>
<body>
<h1>{title}</h1>
<p>Drag a rectangle on the capture, then press OK.</p>
<div class="frame" id="frame"><img id="image" src="frame.jpg" alt="Capture of the game" draggable="false"><div id="rect"></div></div>
<div class="buttons">
  <button id="reset">Reset</button><button id="full">Full frame</button>
  <button id="cancel">Cancel</button><button id="ok">OK</button>
</div>
<p id="done" hidden>Done: you can close this page and go back to the terminal.</p>
<script>
const defaultRegion = {default_region};
let region = {initial_region};
let start = null;
const image = document.getElementById("image"), rect = document.getElementById("rect");
const clamp = (v) => Math.min(1, Math.max(0, v));

function draw(r) {{
  rect.style.left = `${{r[0] * 100}}%`; rect.style.top = `${{r[1] * 100}}%`;
  rect.style.width = `${{r[2] * 100}}%`; rect.style.height = `${{r[3] * 100}}%`;
}}
function point(event) {{
  const box = image.getBoundingClientRect();
  return [clamp((event.clientX - box.left) / box.width), clamp((event.clientY - box.top) / box.height)];
}}
function dragged(end) {{
  const [x0, x1] = [start[0], end[0]].sort((a, b) => a - b), [y0, y1] = [start[1], end[1]].sort((a, b) => a - b);
  return [x0, y0, x1 - x0, y1 - y0];
}}
image.addEventListener("load", () => draw(region));
document.getElementById("frame").addEventListener("mousedown", (e) => {{ start = point(e); }});
window.addEventListener("mousemove", (e) => {{ if (start) draw(dragged(point(e))); }});
window.addEventListener("mouseup", (e) => {{
  if (!start) return;
  const r = dragged(point(e));
  start = null;
  // too small to be an intentional selection
  if (r[2] * image.width >= 4 && r[3] * image.height >= 4) region = r;
  draw(region);
}});
document.getElementById("reset").onclick = () => {{ region = defaultRegion; draw(region); }};
document.getElementById("full").onclick = () => {{ region = [0, 0, 1, 1]; draw(region); }};

async function answer(body) {{
  await fetch("answer", {{ method: "POST", headers: {{ "Content-Type": "application/json" }}, body: JSON.stringify(body) }});
  document.querySelector(".buttons").hidden = true;
  document.getElementById("done").hidden = false;
}}
document.getElementById("ok").onclick = () => answer({{ region }});
document.getElementById("cancel").onclick = () => answer({{ cancel: true }});
</script>
</body>
</html>
"""


class AreaPicker:
    """Serves the page of one area to draw, and waits for the user's answer."""

    def __init__(self, image: Image.Image, title: str, default_region: Region = FULL_REGION,
                 initial_region: Region | None = None):
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="JPEG", quality=90)
        self._jpeg = buffer.getvalue()
        self._page = _PAGE.format(
            title=html.escape(title), default_region=json.dumps(list(default_region)),
            initial_region=json.dumps(list(initial_region or default_region)),
        ).encode("utf-8")
        # Only the page opened by this command can answer: its URL holds a random token.
        self.token = secrets.token_urlsafe(16)
        self.result: Region | None = None
        self._answered = threading.Event()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/{self.token}/"

    def _handler(self):
        picker = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args) -> None:
                pass

            def _send(self, status: int, body: bytes = b"", content_type: str = "text/plain") -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                if self.path == f"/{picker.token}/":
                    self._send(200, picker._page, "text/html; charset=utf-8")
                elif self.path == f"/{picker.token}/frame.jpg":
                    self._send(200, picker._jpeg, "image/jpeg")
                else:
                    self._send(404)

            def do_POST(self) -> None:
                if self.path != f"/{picker.token}/answer":
                    self._send(404)
                    return
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
                    region = None if body.get("cancel") else valid_region(body.get("region"))
                except (TypeError, ValueError, AttributeError):
                    self._send(400, b"Invalid region.")
                    return
                self._send(204)
                picker.result = region
                picker._answered.set()

        return Handler

    def wait(self) -> Region | None:
        """Serves the page until the user presses OK (returns the region) or Cancel (returns None)."""
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        try:
            self._answered.wait()
        finally:
            self.server.shutdown()
            self.server.server_close()
        return self.result


def pick_region(image: Image.Image, title: str, default_region: Region = FULL_REGION,
                initial_region: Region | None = None) -> Region | None:
    """Asks the user to draw a region on the image, in the browser. None when cancelled."""
    picker = AreaPicker(image, title, default_region, initial_region)
    print(f"{title}: draw it in your browser ({picker.url})", flush=True)
    webbrowser.open(picker.url)
    return picker.wait()
