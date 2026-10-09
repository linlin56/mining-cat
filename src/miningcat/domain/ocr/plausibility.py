from miningcat.domain.languages import Language


# Frames with no real subtitle sometimes still OCR
# Rejecting text that doesn't contain at least one character from the target language's script is a cheap filter since the language is already known ahead of time.
def is_plausible_text(text: str, language: Language) -> bool:
    if not text:
        return False
    return bool(language.profile.ocr_script.search(text))
