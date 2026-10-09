from pathlib import Path

from PIL import Image, ImageDraw

from miningcat.infrastructure.media.fonts import fit_font

WHITE = (255, 255, 255, 255)
GREY = (200, 200, 200, 255)


class TitleCardRenderer:
    """The still image of a chapter's video: the book's cover centred on black, with the titles of the book and of
    the chapter in a box at the top left."""

    def __init__(self, width: int = 1920, height: int = 1080):
        self.width = width
        self.height = height

    def render(self, cover: Path | None = None, book_title: str | None = None,
               chapter_title: str | None = None) -> Image.Image:
        frame = Image.new("RGB", (self.width, self.height), color="black")
        if cover:
            try:
                image = Image.open(cover).convert("RGB")
                image.thumbnail((self.width, self.height), Image.LANCZOS)
                frame.paste(image, ((self.width - image.width) // 2, (self.height - image.height) // 2))
            except Exception:
                pass
        return self.draw_titles(frame, book_title, chapter_title)

    def draw_titles(self, frame: Image.Image, book_title: str | None, chapter_title: str | None) -> Image.Image:
        lines_spec = []
        if book_title:
            lines_spec.append((book_title, 34, WHITE))
        if chapter_title:
            lines_spec.append((chapter_title, 26, GREY))
        if not lines_spec:
            return frame

        max_text_w = self.width // 4
        padding = 18
        margin = 28
        line_gap = 8

        overlay = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        rendered = []
        for text, size, color in lines_spec:
            font = fit_font(draw, text, size, max_text_w - 2 * padding)
            bbox = draw.textbbox((0, 0), text, font=font)
            rendered.append((text, font, color, bbox[2] - bbox[0], bbox[3] - bbox[1]))

        box_w = max(tw for *_, tw, _ in rendered) + 2 * padding
        box_h = sum(th for *_, th in rendered) + line_gap * (len(rendered) - 1) + 2 * padding

        x0, y0 = margin, margin
        draw.rounded_rectangle([x0, y0, x0 + box_w, y0 + box_h], radius=8, fill=(0, 0, 0, 160))

        y = y0 + padding
        for text, font, color, _, lh in rendered:
            draw.text((x0 + padding, y), text, font=font, fill=color)
            y += lh + line_gap

        return Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB")
