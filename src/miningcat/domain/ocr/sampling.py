"""How a video is sampled for the OCR of its subtitles."""
# Normalized (x, y, w, h) fractions of the frame
# bottom third, minimizes OCR noise from on-screen visual content compared to e.g. bottom half.
DEFAULT_REGION: tuple[float, float, float, float] = (0.0, 2 / 3, 1.0, 1 / 3)

# User-adjustable OCR sampling rate range (GUI slider / --ocr-fps CLI flag).
OCR_FPS_MIN = 2

OCR_FPS_MAX = 12

OCR_FPS_DEFAULT = 4
