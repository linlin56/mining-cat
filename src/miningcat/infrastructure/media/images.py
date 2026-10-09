"""Pictures of comics, with Pillow."""
import shutil
from pathlib import Path

from PIL import Image

# Formats browsers don't show: converted to PNG.
CONVERTED_EXTENSIONS = ("bmp", "tif", "tiff", "avif", "jxl")


def add_page(source: Path, target: Path, number: int) -> dict | None:
    """Moves (or converts) an image to target/<number>.<ext>. Returns {file, width, height}, None when it isn't an
    image after all."""
    ext = source.suffix.lower().lstrip(".")
    try:
        with Image.open(source) as img:
            width, height = img.size
            if ext in CONVERTED_EXTENSIONS:
                name = f"{number:04d}.png"
                img.convert("RGB").save(target / name)
                return {"file": name, "width": width, "height": height}
    except (OSError, ValueError, Image.DecompressionBombError):
        return None
    name = f"{number:04d}.{'jpg' if ext == 'jpeg' else ext}"
    shutil.move(source, target / name)
    return {"file": name, "width": width, "height": height}


def make_thumbnail(page: Path, target: Path, width: int) -> None:
    with Image.open(page) as img:
        img = img.convert("RGB")
        img.thumbnail((width, width * 2))
        img.save(target, "JPEG", quality=85)
