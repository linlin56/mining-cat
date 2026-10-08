import html
import re

def plain_field_text(value: str) -> str:
    """The text of an Anki field: without sounds, HTML tags, entities and furigana."""
    text = re.sub(r"\[sound:[^\]]*\]", "", value or "")
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).replace("\xa0", " ").strip()
    # furigana written as 漢字[かんじ] in a field
    return re.sub(r"\[[^\]]*\]", "", text).replace(" ", "") if re.search(r"\S\[[^\]]+\]", text) else text
