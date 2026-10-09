_DECODE_CANDIDATES = ("big5", "gb18030", "shift_jis", "euc-kr", "cp1252")


def decode_text(data: bytes) -> str:
    """The text of a file in UTF-8 (with or without BOM), UTF-16, or a legacy CJK or Western encoding."""
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    # Legacy CJK encodings: keep the strict decodings and prefer the one that reads as the most
    # "ordinary" text (common CJK, kana, hangul or ASCII), since several of them accept the same bytes.
    best, best_score = None, -1.0
    for encoding in _DECODE_CANDIDATES:
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        sample = text[:20_000]
        ordinary = sum(
            1 for ch in sample
            if ch.isascii() or "一" <= ch <= "鿿" or "぀" <= ch <= "ヿ"
            or "가" <= ch <= "힯" or "　" <= ch <= "〿" or "＀" <= ch <= "￯"
        )
        score = ordinary / max(1, len(sample))
        if score > best_score:
            best, best_score = text, score
    return best if best is not None else data.decode("utf-8", errors="replace")
