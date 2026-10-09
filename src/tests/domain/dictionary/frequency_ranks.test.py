import json

from miningcat.domain.dictionary.frequency_ranks import combine, ranks_from_rows


def rows(*pairs):
    return [(expression, json.dumps(data)) for expression, data in pairs]


def test_numbers_and_objects_are_ranks():
    table = ranks_from_rows(rows(("的", 1), ("是", {"value": 2, "displayValue": "2㋕"}),
                                 ("我", {"reading": "wo3", "frequency": 3})), occurrences=False)
    assert table == {"的": 1, "是": 2, "我": 3}


def test_ranks_written_as_text_are_read():
    # the Sinica list writes ["了", "freq", "1"]
    table = ranks_from_rows(rows(("了", "1"), ("的", "2"), ("道", {"value": "4"}), ("?", "n/a")), occurrences=False)
    assert table == {"了": 1, "的": 2, "道": 4}


def test_occurrence_counts_are_ordered():
    table = ranks_from_rows(rows(("的", "500"), ("了", 900)), occurrences=True)
    assert table == {"了": 1, "的": 2}


def test_combined_lists_rank_words_by_their_best_rank():
    a = {"的": 1, "是": 2, "說": 3}
    b = {"是": 1, "我": 2, "的": 3}
    # best ranks: 的 1, 是 1, 我 2, 說 3; 是 (1, 2) is ahead of 的 (1, 3) in the average
    assert combine([a, b]) == {"是": 1, "的": 2, "我": 3, "說": 4}


def test_a_single_list_is_kept():
    a = {"的": 1, "是": 5}
    assert combine([a]) is a


def test_combined_lists_share_their_words_once_respelled():
    simplified = {"的": 1, "说": 2}
    traditional = {"說": 1, "的": 2}
    spell = lambda word: word.replace("说", "說")
    # without respelling, 说 and 說 would be two words
    assert combine([simplified, traditional], spell) == {"的": 1, "說": 2}
