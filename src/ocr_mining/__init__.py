# Only re-exports the lightweight `frames` constant here 
# `pipeline` is intentionally NOT imported, so that `from ocr_mining.frames import ...` 
# (used by the GUI's region-selection preview) stays cheap. 
# Import `ocr_mining.pipeline` directly where `generate_segments` is actually needed.
from ocr_mining.frames import DEFAULT_REGION

__all__ = ["DEFAULT_REGION"]
