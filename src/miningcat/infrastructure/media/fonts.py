from PIL import ImageDraw, ImageFont

# Font candidates for video overlay (ordered by Unicode/CJK coverage)
FONT_CANDIDATES = [
    # macOS - CJK support
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    # Linux - CJK support
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJKsc-Regular.otf",
    # Windows - CJK support
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simsun.ttc",
    # Latin fallbacks
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    """The first available font of the candidates, else Pillow's default."""
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def fit_font(draw: ImageDraw.ImageDraw, text: str, base_size: int, max_width: int, min_size: int = 12) -> ImageFont.FreeTypeFont:
    """The largest font (from base_size down to min_size) in which `text` fits in max_width."""
    size = base_size
    while size >= min_size:
        font = load_font(size)
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return font
        size -= 2
    return load_font(min_size)

