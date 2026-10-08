"""The OCR of comics and manga, in its own process: `python -m miningcat.infrastructure.ocr.worker <language id>`
reads image paths on stdin and answers each one with a line of JSON (see application/library/comics/ocr.py)."""
import json
import sys

RESULT_PREFIX = "@@miningcat-ocr "


def main() -> None:
    from PIL import Image

    from miningcat.domain.languages import Language
    from miningcat.infrastructure.ocr.engine import OcrEngine

    engine = OcrEngine(Language.from_id(sys.argv[1]), vertical=True)
    print(RESULT_PREFIX + json.dumps({"ready": True}), flush=True)
    for request in sys.stdin:
        path = request.strip()
        if not path:
            continue
        try:
            with Image.open(path) as img:
                img.load()
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                lines = engine.read_lines(img)
                answer = {"width": img.width, "height": img.height, "lines": [list(l) for l in lines]}
        except Exception as exc:
            answer = {"error": f"{type(exc).__name__}: {exc}"}
        print(RESULT_PREFIX + json.dumps(answer, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
