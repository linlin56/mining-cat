from miningcat.domain.text.sentences import sentence_around


def test_the_sentence_of_the_word_is_cut_from_the_text_around_it():
    assert sentence_around("前の文だ。「吾輩は", "猫", "である」と言った。次の文。") == "「吾輩は猫である」と言った。"
    assert sentence_around("He left. Then she ", "smiled", " at him. The end") == "Then she smiled at him."


def test_a_paragraph_ends_a_sentence():
    assert sentence_around("第一章\n他一邊走一邊", "說話", "，聲音很小\n第二段") == "他一邊走一邊說話，聲音很小"


def test_without_text_around_the_word_is_the_sentence():
    assert sentence_around("", " 猫 ", "") == "猫"
    assert sentence_around("終わり。", "猫", "") == "猫"
