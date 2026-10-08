import json
import re

# Senses that don't make a reading likely for a word said alone.
_MINOR_SENSE = re.compile(
    r"^\s*(surname|used in|variant of|old variant|archaic variant|see\b|also written|abbr\.|CL:"
    r"|\((bound form|literary|archaic|old|dialect|classical|Cantonese|onom\.?|slang)\))", re.I)


def senses(glossary) -> list[str]:
    """Senses of a dictionary entry: its list items when it has some (structured content), else its texts."""
    items: list[str] = []
    texts: list[str] = []

    def flatten(node) -> str:
        if isinstance(node, str):
            return node
        if isinstance(node, list):
            return "".join(flatten(n) for n in node)
        if isinstance(node, dict):
            return flatten(node.get("content", node.get("text", "")))
        return ""

    def walk(node):
        if isinstance(node, str):
            texts.append(node)
        elif isinstance(node, list):
            for n in node:
                walk(n)
        elif isinstance(node, dict):
            if (node.get("data") or {}).get("cccedict") == "headword":
                return
            if node.get("tag") == "li":
                items.append(flatten(node.get("content")))
            elif node.get("type") == "text":
                texts.append(str(node.get("text", "")))
            else:
                walk(node.get("content"))

    walk(glossary)
    return [s for s in (items or texts) if s.strip()]



def reading_weight(glossary: str) -> int:
    """How likely a dictionary entry's reading is for the word said alone: its number of senses that aren't
    a surname, a variant, a literary or dialect use..."""
    try:
        found = senses(json.loads(glossary))
    except ValueError:
        found = []
    return sum(1 for s in found if not _MINOR_SENSE.match(s))
