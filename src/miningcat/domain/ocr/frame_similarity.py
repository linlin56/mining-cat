"""Whether two frames (or crops of the subtitle area) show the same thing."""
from PIL import Image, ImageChops, ImageStat

MAX_PIXEL_DIFF_RATIO = 0.02

# A pixel that changed by more than this (out of 255) changed for real, not from compression noise...
STRONG_PIXEL_DIFF = 64

# ...and frames differ as soon as this share of their pixels did. A subtitle line appearing on a plain
# background (black bars, a game's dialog box) barely moves the mean difference, but changes these pixels a lot.
MAX_STRONG_DIFF_RATIO = 0.005

# Preserve aspect ratio and use a larger downscale size 
# so subtitle text remains distinguishable and real changes do not get mistaken for identical frames.
_DIFF_MAX_DIM = 256


def _downscale_for_diff(image: Image.Image) -> Image.Image:
    width, height = image.size
    scale = _DIFF_MAX_DIM / max(width, height)
    if scale < 1:
        image = image.resize((max(1, round(width * scale)), max(1, round(height * scale))))
    return image.convert("L")


# Compares two frames cheaply: downscales both to a grayscale thumbnail (preserving aspect ratio)
# measures the mean per-pixel difference
# Uses a similarity threshold rather than an exact/hash match, since lossy video compression means visually-identical frames aren't byte-identical.
def frames_are_similar(a: Image.Image, b: Image.Image, threshold: float = MAX_PIXEL_DIFF_RATIO) -> bool:
    a_small = _downscale_for_diff(a)
    b_small = _downscale_for_diff(b)
    diff = ImageChops.difference(a_small, b_small)
    mean_diff = ImageStat.Stat(diff).mean[0]
    if mean_diff / 255 > threshold:
        return False
    strong = sum(diff.histogram()[STRONG_PIXEL_DIFF + 1:])
    return strong / (diff.width * diff.height) <= MAX_STRONG_DIFF_RATIO
