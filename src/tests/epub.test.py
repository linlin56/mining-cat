import shutil
import pytest
import epub
from shared import (
    MOCK_EPUB_TW, MOCK_EPUB_CN, MOCK_EPUB_JA, MOCK_EPUB_FR, MOCK_EPUB_EN_US, MOCK_EPUB_EN_GB, MOCK_EPUB_IT, MOCK_EPUB_ES,
    skip_if_no_epub_tw, skip_if_no_epub_cn, skip_if_no_epub_ja, skip_if_no_epub_fr, skip_if_no_epub_en_us, skip_if_no_epub_en_gb, skip_if_no_epub_it, skip_if_no_epub_es,
    MOCK_TXT_TW, MOCK_TXT_CN, MOCK_TXT_JA, MOCK_TXT_FR, MOCK_TXT_EN_US, MOCK_TXT_EN_GB, MOCK_TXT_IT, MOCK_TXT_ES,
    skip_if_no_txt_tw, skip_if_no_txt_cn, skip_if_no_txt_ja, skip_if_no_txt_fr, skip_if_no_txt_en_us, skip_if_no_txt_en_gb, skip_if_no_txt_it, skip_if_no_txt_es,
    MOCK_SRT_JA, skip_if_no_srt_ja,
    MOCK_SRT_FR, skip_if_no_srt_fr,
    MOCK_SRT_EN_US, skip_if_no_srt_en_us,
    MOCK_SRT_EN_GB, skip_if_no_srt_en_gb,
    MOCK_SRT_IT, skip_if_no_srt_it,
    MOCK_SRT_ES, skip_if_no_srt_es,
)

EXPECTED_LINES_TW = [
    "你好。",
    "我是測試檔案。",
    "我是用來測試軟體是否正常運作的。",
    "「這是一句非常有趣的句子，裡面包含了標點符號。」",
]

EXPECTED_LINES_CN = [
    "你好。",
    "我是测试文件。",
    "我是用来测试软件是否正常运行的。",
    "“这是一句非常有趣的句子，里面包含了标点符号。”",
]

EXPECTED_LINES_JA = [
    "こんにちは。",
    "私はテストファイルです。",
    "ソフトウェアが正常に動作するかをテストするために使われます。",
    "「これはとても興味深い文で、句読点が含まれています。」",
]

EXPECTED_LINES_FR = [
    "Bonjour.",
    "Je suis un fichier de test.",
    "Je suis utilisé pour tester le bon fonctionnement du logiciel.",
    "« C'est une phrase très intéressante, qui contient de la ponctuation. »",
]

EXPECTED_LINES_EN_US = [
    "Hello.",
    "I'm a test file.",
    "I am used to test the proper functioning of the software.",
    '"This is a very interesting sentence that contains punctuation."',
]

EXPECTED_LINES_EN_GB = [
    "Hello.",
    "I'm a test file.",
    "I am used to test the proper functioning of the software.",
    "‘This is a very interesting sentence that contains punctuation.’",
]

EXPECTED_LINES_IT = [
    "Ciao.",
    "Sono un file di test.",
    "Vengo utilizzato per verificare il corretto funzionamento del software.",
    "«Questa è una frase molto interessante, che contiene della punteggiatura.»",
]

EXPECTED_LINES_ES = [
    "Hola.",
    "Soy un archivo de prueba.",
    "Soy utilizado para probar el correcto funcionamiento del software.",
    "«Es una frase muy interesante, que contiene puntuación.»",
    "¿Esto es una pregunta?",
    "¡Esto es una exclamación!",
]

EPUB_PARAMS = [
    pytest.param(MOCK_EPUB_TW, marks=skip_if_no_epub_tw, id="zh-TW"),
    pytest.param(MOCK_EPUB_CN, marks=skip_if_no_epub_cn, id="zh-CN"),
    pytest.param(MOCK_EPUB_JA, marks=skip_if_no_epub_ja, id="ja"),
    pytest.param(MOCK_EPUB_FR, marks=skip_if_no_epub_fr, id="fr"),
    pytest.param(MOCK_EPUB_EN_US, marks=skip_if_no_epub_en_us, id="en-US"),
    pytest.param(MOCK_EPUB_EN_GB, marks=skip_if_no_epub_en_gb, id="en-GB"),
    pytest.param(MOCK_EPUB_IT, marks=skip_if_no_epub_it, id="it"),
    pytest.param(MOCK_EPUB_ES, marks=skip_if_no_epub_es, id="es"),
]


@pytest.fixture
def epub_dir(tmp_path, request):
    epub_src = request.param
    shutil.copy(epub_src, tmp_path / epub_src.name)
    return tmp_path


@pytest.mark.parametrize("epub_dir", EPUB_PARAMS, indirect=True)
def test_run_list_only(epub_dir, monkeypatch):
    monkeypatch.setattr(epub, "DIR_EBOOK", epub_dir)
    monkeypatch.setattr(epub, "DIR_CHAPTERS_TEXT", epub_dir / "chapters_text")
    monkeypatch.setattr(epub, "DIR_TEMP", epub_dir / "temp")
    epub.run(list_only=True)
    assert not (epub_dir / "chapters_text").exists()


@pytest.mark.parametrize("epub_dir", EPUB_PARAMS, indirect=True)
def test_run_saves_chapters(epub_dir, monkeypatch):
    monkeypatch.setattr(epub, "DIR_EBOOK", epub_dir)
    monkeypatch.setattr(epub, "DIR_CHAPTERS_TEXT", epub_dir / "chapters_text")
    monkeypatch.setattr(epub, "DIR_TEMP", epub_dir / "temp")
    epub.run()
    assert (epub_dir / "chapters_text").exists()
    assert len(list((epub_dir / "chapters_text").glob("chapter_*.txt"))) > 0


@pytest.mark.parametrize("epub_dir,expected", [
    pytest.param(MOCK_EPUB_TW, EXPECTED_LINES_TW, marks=skip_if_no_epub_tw, id="zh-TW"),
    pytest.param(MOCK_EPUB_CN, EXPECTED_LINES_CN, marks=skip_if_no_epub_cn, id="zh-CN"),
    pytest.param(MOCK_EPUB_JA, EXPECTED_LINES_JA, marks=skip_if_no_epub_ja, id="ja"),
    pytest.param(MOCK_EPUB_FR, EXPECTED_LINES_FR, marks=skip_if_no_epub_fr, id="fr"),
    pytest.param(MOCK_EPUB_EN_US, EXPECTED_LINES_EN_US, marks=skip_if_no_epub_en_us, id="en-US"),
    pytest.param(MOCK_EPUB_EN_GB, EXPECTED_LINES_EN_GB, marks=skip_if_no_epub_en_gb, id="en-GB"),
    pytest.param(MOCK_EPUB_IT, EXPECTED_LINES_IT, marks=skip_if_no_epub_it, id="it"),
    pytest.param(MOCK_EPUB_ES, EXPECTED_LINES_ES, marks=skip_if_no_epub_es, id="es"),
], indirect=["epub_dir"])
def test_run_chapter_content(epub_dir, expected, monkeypatch):
    monkeypatch.setattr(epub, "DIR_EBOOK", epub_dir)
    monkeypatch.setattr(epub, "DIR_CHAPTERS_TEXT", epub_dir / "chapters_text")
    monkeypatch.setattr(epub, "DIR_TEMP", epub_dir / "temp")
    epub.run()

    all_text = "".join(
        f.read_text(encoding="utf-8")
        for f in sorted((epub_dir / "chapters_text").glob("chapter_*.txt"))
    )
    for line in expected:
        assert line in all_text, f"Expected line not found in output: {line!r}"


# TXT tests

TXT_PARAMS = [
    pytest.param(MOCK_TXT_TW, marks=skip_if_no_txt_tw, id="zh-TW"),
    pytest.param(MOCK_TXT_CN, marks=skip_if_no_txt_cn, id="zh-CN"),
    pytest.param(MOCK_TXT_JA, marks=skip_if_no_txt_ja, id="ja"),
    pytest.param(MOCK_TXT_FR, marks=skip_if_no_txt_fr, id="fr"),
    pytest.param(MOCK_TXT_EN_US, marks=skip_if_no_txt_en_us, id="en-US"),
    pytest.param(MOCK_TXT_EN_GB, marks=skip_if_no_txt_en_gb, id="en-GB"),
    pytest.param(MOCK_TXT_IT, marks=skip_if_no_txt_it, id="it"),
    pytest.param(MOCK_TXT_ES, marks=skip_if_no_txt_es, id="es"),
]


@pytest.fixture
def txt_dir(tmp_path, request):
    txt_src = request.param
    shutil.copy(txt_src, tmp_path / txt_src.name)
    return tmp_path


@pytest.mark.parametrize("txt_dir", TXT_PARAMS, indirect=True)
def test_txt_list_only(txt_dir, monkeypatch):
    monkeypatch.setattr(epub, "DIR_EBOOK", txt_dir)
    monkeypatch.setattr(epub, "DIR_CHAPTERS_TEXT", txt_dir / "chapters_text")
    monkeypatch.setattr(epub, "DIR_TEMP", txt_dir / "temp")
    epub.run(list_only=True)
    assert not (txt_dir / "chapters_text").exists()


@pytest.mark.parametrize("txt_dir", TXT_PARAMS, indirect=True)
def test_txt_saves_single_chapter(txt_dir, monkeypatch):
    monkeypatch.setattr(epub, "DIR_EBOOK", txt_dir)
    monkeypatch.setattr(epub, "DIR_CHAPTERS_TEXT", txt_dir / "chapters_text")
    monkeypatch.setattr(epub, "DIR_TEMP", txt_dir / "temp")
    epub.run()
    chapters = sorted((txt_dir / "chapters_text").glob("chapter_*.txt"))
    assert len(chapters) == 1


@pytest.mark.parametrize("txt_dir,expected", [
    pytest.param(MOCK_TXT_TW, EXPECTED_LINES_TW, marks=skip_if_no_txt_tw, id="zh-TW"),
    pytest.param(MOCK_TXT_CN, EXPECTED_LINES_CN, marks=skip_if_no_txt_cn, id="zh-CN"),
    pytest.param(MOCK_TXT_JA, EXPECTED_LINES_JA, marks=skip_if_no_txt_ja, id="ja"),
    pytest.param(MOCK_TXT_FR, EXPECTED_LINES_FR, marks=skip_if_no_txt_fr, id="fr"),
    pytest.param(MOCK_TXT_EN_US, EXPECTED_LINES_EN_US, marks=skip_if_no_txt_en_us, id="en-US"),
    pytest.param(MOCK_TXT_EN_GB, EXPECTED_LINES_EN_GB, marks=skip_if_no_txt_en_gb, id="en-GB"),
    pytest.param(MOCK_TXT_IT, EXPECTED_LINES_IT, marks=skip_if_no_txt_it, id="it"),
    pytest.param(MOCK_TXT_ES, EXPECTED_LINES_ES, marks=skip_if_no_txt_es, id="es"),
], indirect=["txt_dir"])
def test_txt_chapter_content(txt_dir, expected, monkeypatch):
    monkeypatch.setattr(epub, "DIR_EBOOK", txt_dir)
    monkeypatch.setattr(epub, "DIR_CHAPTERS_TEXT", txt_dir / "chapters_text")
    monkeypatch.setattr(epub, "DIR_TEMP", txt_dir / "temp")
    epub.run()

    all_text = "".join(
        f.read_text(encoding="utf-8")
        for f in sorted((txt_dir / "chapters_text").glob("chapter_*.txt"))
    )
    for line in expected:
        assert line in all_text, f"Expected line not found in output: {line!r}"


# SRT tests

@skip_if_no_srt_ja
def test_srt_ja_segment_count():
    segments = [b for b in MOCK_SRT_JA.read_text(encoding="utf-8").strip().split("\n\n") if b.strip()]
    assert len(segments) == len(EXPECTED_LINES_JA)


@skip_if_no_srt_ja
def test_srt_ja_content():
    text = MOCK_SRT_JA.read_text(encoding="utf-8")
    for line in EXPECTED_LINES_JA:
        assert line in text


@skip_if_no_srt_ja
def test_srt_ja_timecodes():
    timecodes = [l for l in MOCK_SRT_JA.read_text(encoding="utf-8").splitlines() if "-->" in l]
    assert len(timecodes) == len(EXPECTED_LINES_JA)
    for tc in timecodes:
        start, end = tc.split(" --> ")
        assert start < end


@skip_if_no_srt_fr
def test_srt_fr_segment_count():
    segments = [b for b in MOCK_SRT_FR.read_text(encoding="utf-8").strip().split("\n\n") if b.strip()]
    assert len(segments) == len(EXPECTED_LINES_FR)


@skip_if_no_srt_fr
def test_srt_fr_content():
    text = MOCK_SRT_FR.read_text(encoding="utf-8")
    for line in EXPECTED_LINES_FR:
        assert line in text


@skip_if_no_srt_fr
def test_srt_fr_timecodes():
    timecodes = [l for l in MOCK_SRT_FR.read_text(encoding="utf-8").splitlines() if "-->" in l]
    assert len(timecodes) == len(EXPECTED_LINES_FR)
    for tc in timecodes:
        start, end = tc.split(" --> ")
        assert start < end


@skip_if_no_srt_en_us
def test_srt_en_segment_count():
    segments = [b for b in MOCK_SRT_EN_US.read_text(encoding="utf-8").strip().split("\n\n") if b.strip()]
    assert len(segments) == len(EXPECTED_LINES_EN_US)


@skip_if_no_srt_en_us
def test_srt_en_content():
    text = MOCK_SRT_EN_US.read_text(encoding="utf-8")
    for line in EXPECTED_LINES_EN_US:
        assert line in text


@skip_if_no_srt_en_us
def test_srt_en_timecodes():
    timecodes = [l for l in MOCK_SRT_EN_US.read_text(encoding="utf-8").splitlines() if "-->" in l]
    assert len(timecodes) == len(EXPECTED_LINES_EN_US)
    for tc in timecodes:
        start, end = tc.split(" --> ")
        assert start < end


@skip_if_no_srt_en_gb
def test_srt_en_gb_segment_count():
    segments = [b for b in MOCK_SRT_EN_GB.read_text(encoding="utf-8").strip().split("\n\n") if b.strip()]
    assert len(segments) == len(EXPECTED_LINES_EN_GB)


@skip_if_no_srt_en_gb
def test_srt_en_gb_content():
    text = MOCK_SRT_EN_GB.read_text(encoding="utf-8")
    for line in EXPECTED_LINES_EN_GB:
        assert line in text


@skip_if_no_srt_en_gb
def test_srt_en_gb_timecodes():
    timecodes = [l for l in MOCK_SRT_EN_GB.read_text(encoding="utf-8").splitlines() if "-->" in l]
    assert len(timecodes) == len(EXPECTED_LINES_EN_GB)
    for tc in timecodes:
        start, end = tc.split(" --> ")
        assert start < end


@skip_if_no_srt_it
def test_srt_it_segment_count():
    segments = [b for b in MOCK_SRT_IT.read_text(encoding="utf-8").strip().split("\n\n") if b.strip()]
    assert len(segments) == len(EXPECTED_LINES_IT)


@skip_if_no_srt_it
def test_srt_it_content():
    text = MOCK_SRT_IT.read_text(encoding="utf-8")
    for line in EXPECTED_LINES_IT:
        assert line in text


@skip_if_no_srt_it
def test_srt_it_timecodes():
    timecodes = [l for l in MOCK_SRT_IT.read_text(encoding="utf-8").splitlines() if "-->" in l]
    assert len(timecodes) == len(EXPECTED_LINES_IT)
    for tc in timecodes:
        start, end = tc.split(" --> ")
        assert start < end


@skip_if_no_srt_es
def test_srt_es_segment_count():
    segments = [b for b in MOCK_SRT_ES.read_text(encoding="utf-8").strip().split("\n\n") if b.strip()]
    assert len(segments) == len(EXPECTED_LINES_ES)


@skip_if_no_srt_es
def test_srt_es_content():
    text = MOCK_SRT_ES.read_text(encoding="utf-8")
    for line in EXPECTED_LINES_ES:
        assert line in text


@skip_if_no_srt_es
def test_srt_es_timecodes():
    timecodes = [l for l in MOCK_SRT_ES.read_text(encoding="utf-8").splitlines() if "-->" in l]
    assert len(timecodes) == len(EXPECTED_LINES_ES)
    for tc in timecodes:
        start, end = tc.split(" --> ")
        assert start < end
