from miningcat.domain.text.fullwidth_punctuation import fullwidth_punctuation


def test_traditional_chinese():
    assert fullwidth_punctuation("你好,我是小明. 你呢?", "zh-Hant") == "你好，我是小明。你呢？"
    assert fullwidth_punctuation('他說"走吧",然後...', "zh-TW") == "他說「走吧」，然後……"
    assert fullwidth_punctuation("真的?!", "zh-Hant") == "真的？！"
    assert fullwidth_punctuation("台北 (臺灣) 很好", "zh-Hant") == "台北（臺灣）很好"


def test_simplified_chinese_quotes():
    assert fullwidth_punctuation('他说"走吧".', "zh-Hans") == "他说“走吧”。"


def test_japanese():
    assert fullwidth_punctuation("はい,そうです.", "ja") == "はい、そうです。"


def test_cantonese_and_taigi():
    assert fullwidth_punctuation("係呀,好嘢!", "yue-Hant") == "係呀，好嘢！"
    assert fullwidth_punctuation("我是台灣人,Guá sī Tâi-uân-lâng.", "nan") == "我是台灣人，Guá sī Tâi-uân-lâng."


def test_latin_and_numbers_kept():
    assert fullwidth_punctuation("價錢是3.5元, OK?", "zh-Hant") == "價錢是3.5元， OK?"
    assert fullwidth_punctuation('He said "hi", then (laughs).', "zh-Hant") == 'He said "hi", then (laughs).'


def test_other_languages_unchanged():
    assert fullwidth_punctuation("你好,我是", "ko") == "你好,我是"
    assert fullwidth_punctuation("Bonjour, ça va?", "fr") == "Bonjour, ça va?"
