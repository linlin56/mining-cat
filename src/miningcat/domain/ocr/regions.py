"""Areas of a frame, as (x, y, width, height) fractions: they survive resizes and Retina scaling."""
Region = tuple[float, float, float, float]

# The whole frame.
FULL_REGION: Region = (0.0, 0.0, 1.0, 1.0)


# Converts a normalized (x, y, w, h) region (fractions in [0, 1]) to pixel coordinates for the given frame size, clamping so the crop never runs past the frame edges.
def region_to_pixels(
    region: tuple[float, float, float, float], width: int, height: int,
) -> tuple[int, int, int, int]:
    x_frac, y_frac, w_frac, h_frac = region
    x = max(0, min(round(x_frac * width), width))
    y = max(0, min(round(y_frac * height), height))
    w = max(1, min(round(w_frac * width), width - x))
    h = max(1, min(round(h_frac * height), height - y))
    return x, y, w, h


def valid_region(value) -> Region:
    """A region of the frame as (x, y, width, height) fractions between 0 and 1. Raises ValueError otherwise."""
    region = tuple(float(v) for v in value)
    if len(region) != 4 or not all(0.0 <= v <= 1.0 for v in region) or region[2] <= 0 or region[3] <= 0:
        raise ValueError(f"invalid region: {value!r}")
    return region
