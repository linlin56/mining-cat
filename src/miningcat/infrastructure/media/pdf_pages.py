"""Pages of a PDF (a scanned book or manga) rendered as pictures, with PyMuPDF; and the text of a PDF that has some
(selectable text, not a scan), where it is on the pictures: no need to read it by OCR."""
import json
from pathlib import Path

import pymupdf

from miningcat.infrastructure.files.archives import ArchiveError

# Pieces of text on the same row (a bracket, an inline formula) are one line when they overlap this much in height,
# and are no further apart than this many times their height (two columns side by side stay apart)…
SAME_ROW = 0.5
MAX_ROW_GAP = 2.0
# …with a space between them when they're further apart than this share of their height.
SPACE_GAP = 0.25
# A scanned page (an image over most of it) with less text than this has no real text layer (a watermark, a page
# number…): it's read by OCR.
MIN_SCAN_TEXT = 50

# Zoom of a page without images (1 = 72 dpi), and the bounds of the zoom read from its scans.
DEFAULT_ZOOM = 2.5
MIN_ZOOM, MAX_ZOOM = 1.5, 5.0
# The longest side of a page, in pixels: a poster scanned at 600 dpi would be hundreds of MB.
MAX_SIDE = 4000
JPEG_QUALITY = 90


# The images' boxes are those of the unrotated page, as the text's (page.rect is the page as it's shown).
def _is_scan(page: pymupdf.Page) -> bool:
    area = page.rect.width * page.rect.height
    return any((pymupdf.Rect(info["bbox"]) * page.rotation_matrix).intersect(page.rect).get_area() > area / 2
               for info in page.get_image_info())


def _zoom(page: pymupdf.Page) -> float:
    """The zoom that renders the page at the resolution of its scans (no detail lost, none made up)."""
    zooms = []
    width = page.rect.height if page.rotation % 180 else page.rect.width  # of the unrotated page
    for info in page.get_image_info():
        box = pymupdf.Rect(info["bbox"])  # the image's pixels per point: the same whichever way the page is turned
        if info.get("width") and box.width > width / 2:  # a scan, not a logo
            zooms.append(info["width"] / box.width)
    zoom = min(max(max(zooms, default=DEFAULT_ZOOM), MIN_ZOOM), MAX_ZOOM)
    longest = max(page.rect.width, page.rect.height)
    return min(zoom, MAX_SIDE / longest) if longest else zoom


def page_lines(page: pymupdf.Page, zoom: float) -> list[list]:
    """The lines of text of a page, as the OCR gives them: [text, x, y, w, h] in pixels of the page rendered at `zoom`
    (and turned as it's shown, when the page is rotated). Horizontal pieces on the same row are joined (a PDF often
    cuts a line at its punctuation or formulas)."""
    rows = []  # {"horizontal", "box": [x0, y0, x1, y1], "pieces": [(x0, x1, text)]}
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            text = "".join(span["text"] for span in line["spans"])
            if not text.strip():
                continue
            box = list(line["bbox"])
            horizontal = abs(line["dir"][0]) >= abs(line["dir"][1])
            row = next((r for r in rows if horizontal and r["horizontal"] and _same_row(r["box"], box)), None)
            if row is None:
                rows.append({"horizontal": horizontal, "box": box, "pieces": [(box[0], box[2], text)]})
            else:
                row["pieces"].append((box[0], box[2], text))
                row["box"] = [min(row["box"][0], box[0]), min(row["box"][1], box[1]),
                              max(row["box"][2], box[2]), max(row["box"][3], box[3])]
    lines = []
    shown = page.rotation_matrix * pymupdf.Matrix(zoom, zoom)  # the text's coordinates are those of the unrotated page
    for row in rows:
        x0, y0, x1, y1 = row["box"]
        text, end = "", None
        for a, b, piece in sorted(row["pieces"]) if row["horizontal"] else row["pieces"]:
            if end is not None and a - end > SPACE_GAP * (y1 - y0) and not text.endswith(" ") and not piece.startswith(" "):
                text += " "
            text += piece
            end = b if end is None else max(end, b)
        box = pymupdf.Rect(x0, y0, x1, y1) * shown
        lines.append([text.strip(), box.x0, box.y0, box.width, box.height])
    return lines


def _same_row(row: list, box: list) -> bool:
    overlap = min(row[3], box[3]) - max(row[1], box[1])
    height = min(row[3] - row[1], box[3] - box[1])
    gap = max(box[0] - row[2], row[0] - box[2])
    return overlap > SAME_ROW * height and gap < MAX_ROW_GAP * height


def render_pages(pdf: Path, target: Path, text_target: Path | None = None) -> list[dict]:
    """Renders each page of the PDF to target/<number>.jpg, as {file, width, height}; and with `text_target`, the
    lines of text of the pages that have some to text_target/<number>.json ({width, height, lines}). A page without
    text, images nor drawings (a blank page) gets one too, with no lines: there's nothing to read by OCR (drawn
    lettering, or text turned into outlines, is)."""
    try:
        doc = pymupdf.open(pdf, filetype="pdf")
    except (pymupdf.FileDataError, RuntimeError, ValueError):
        raise ArchiveError("This PDF is damaged, or isn't a PDF.")
    with doc:
        if doc.needs_pass:
            raise ArchiveError("This PDF is protected by a password.")
        target.mkdir(parents=True, exist_ok=True)
        pages = []
        for number, page in enumerate(doc, 1):
            try:
                zoom = _zoom(page)
                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csRGB, alpha=False)
                lines = page_lines(page, zoom) if text_target is not None else None
                blank = lines == [] and not page.get_image_info() and not page.get_drawings()
                if lines and _is_scan(page) and sum(len(line[0]) for line in lines) < MIN_SCAN_TEXT:
                    lines = []
            except Exception as exc:  # MuPDF's errors of a damaged page aren't all RuntimeErrors
                raise ArchiveError(f"Page {number} of this PDF is damaged and couldn't be shown.") from exc
            name = f"{number:04d}.jpg"
            (target / name).write_bytes(pixmap.tobytes("jpg", jpg_quality=JPEG_QUALITY))
            pages.append({"file": name, "width": pixmap.width, "height": pixmap.height})
            if lines or blank:
                text_target.mkdir(parents=True, exist_ok=True)
                (text_target / f"{number:04d}.json").write_text(json.dumps(
                    {"width": pixmap.width, "height": pixmap.height, "lines": lines}, ensure_ascii=False), encoding="utf-8")
        return pages
