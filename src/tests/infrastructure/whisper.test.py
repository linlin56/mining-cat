from miningcat.infrastructure.speech.whisper import device, segments_of

# --- get_device ---

def test_get_device_returns_valid_string():
    result = device()
    assert result in ("cpu", "cuda")


# --- segments_of ---

def test_extract_segments_attr_style():
    class FakeSeg:
        start = 0.0
        end = 1.0
        text = "Hello"

    class FakeResult:
        segments = [FakeSeg()]

    segs = segments_of(FakeResult())
    assert len(segs) == 1
    assert segs[0].text == "Hello"
    assert segs[0].start == 0.0
    assert segs[0].end == 1.0


def test_extract_segments_dict_style():
    fake = {"segments": [{"start": 0.5, "end": 2.0, "text": "World"}]}
    segs = segments_of(fake)
    assert len(segs) == 1
    assert segs[0].text == "World"


def test_extract_segments_skips_empty_text():
    fake = {"segments": [
        {"start": 0.0, "end": 1.0, "text": "   "},
        {"start": 1.0, "end": 2.0, "text": "Valid"},
    ]}
    segs = segments_of(fake)
    assert len(segs) == 1
    assert segs[0].text == "Valid"
