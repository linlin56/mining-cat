"""Choosing the reading of a Mandarin word from its neighbours: 得 is dé, de or děi, 還 hái or huán..."""
from miningcat.domain.text.scripts import HAN_CHARACTER

PRONOUNS = frozenset("我 你 妳 您 他 她 它 牠 我們 你們 妳們 他們 她們 它們 咱 咱們 大家 自己 誰 人家 別人 這 那".split())

# Before 得, these make it děi ("must"): 還得去, 就得走.
_DEI_AFTER = frozenset("就 還 也 都 總 可 非 只 真 又 必 才 先 一定 還是 總是 恐怕 可能 大概 也許".split())

_NUMERALS = frozenset("一 二 三 四 五 六 七 八 九 十 兩 幾 每 半 這 那 哪 好幾".split())

# Verbs after which 著 is zháo (reached the result): 睡著, 找著, 猜著.
_ZHAO_VERBS = frozenset("睡 找 猜 點 燒 碰 見 摸 夠 搆 撈 逮".split())

# The reading of characters said alone, when no rule decides and the dictionary can't tell.
USUAL = {
    "了": "le5", "著": "zhe5", "的": "de5", "地": "di4", "都": "dou1", "看": "kan4", "還": "hai2", "長": "chang2",
    "行": "xing2", "重": "zhong4", "好": "hao3", "要": "yao4", "為": "wei4", "給": "gei3", "教": "jiao1",
    "種": "zhong3", "少": "shao3", "數": "shu4", "只": "zhi3", "覺": "jue2", "樂": "le4", "差": "cha4", "便": "bian4",
    "應": "ying1", "當": "dang1", "和": "he2", "會": "hui4", "倒": "dao4", "中": "zhong1", "說": "shuo1", "發": "fa1",
    "分": "fen1", "相": "xiang1", "乾": "gan1", "空": "kong1", "處": "chu4", "曾": "ceng2", "將": "jiang1",
    "興": "xing1", "沒": "mei2", "那": "na4", "哪": "na3", "誰": "shei2", "嗎": "ma5", "吧": "ba5", "呢": "ne5",
    "啊": "a5", "麼": "me5", "量": "liang4", "調": "diao4", "背": "bei4", "藏": "cang2", "傳": "chuan2",
    "解": "jie3", "角": "jiao3", "散": "san4", "難": "nan2", "正": "zheng4", "轉": "zhuan3", "強": "qiang2",
    "降": "jiang4", "省": "sheng3", "假": "jia3", "間": "jian1", "落": "luo4", "得": "de2", "一": "yi1", "不": "bu4",
}


class Context:
    """The words around word `i`: text of the previous and next ones (and their readings, chosen left to right).
    Words separated by punctuation or a space aren't neighbours."""

    def __init__(self, tokens: list[dict], i: int):
        self.tokens, self.i = tokens, i

    def _at(self, k: int) -> dict | None:
        j = self.i + k
        if not 0 <= j < len(self.tokens):
            return None
        # every word in between must touch the next one
        for m in range(min(j, self.i), max(j, self.i)):
            if self.tokens[m]["end"] != self.tokens[m + 1]["start"]:
                return None
        return self.tokens[j]

    def prev(self, k: int = 1) -> str:
        token = self._at(-k)
        return token["text"] if token else ""

    def next(self, k: int = 1) -> str:
        token = self._at(k)
        return token["text"] if token else ""

    def prev_reading(self, k: int = 1) -> str:
        token = self._at(-k)
        return token.get("pinyin") or "" if token else ""


def _is_han(word: str) -> bool:
    return bool(word) and bool(HAN_CHARACTER.match(word[-1]))


def _de(c: Context) -> str | None:
    p, n = c.prev(), c.next()
    if p in PRONOUNS or not p:
        if n[:1] in ("了", "到"):
            return "de2"           # 他得了第一名
        return "dei3" if _is_han(n) else "de2"  # 我得走了
    if p in _DEI_AFTER:
        return "dei3"              # 還得去
    return "de5" if _is_han(p) else None  # 跑得很快, 看得懂


def _le(c: Context) -> str | None:
    p = c.prev()
    if p == "不" or (p == "得" and c.prev_reading() == "de5"):
        return "liao3"             # 吃不了, 受得了
    return "le5"


def _zhe(c: Context) -> str | None:
    p, n = c.prev(), c.next()
    if n[:1] == "了" or p[-1:] in _ZHAO_VERBS:
        return "zhao2"             # 找著了, 睡著
    return "zhe5" if _is_han(p) else None  # 看著我


def _chang(c: Context) -> str | None:
    p, n = c.prev(), c.next()
    if n[:1] and n[:1] in "大得成出了著滿高胖":
        return "zhang3"            # 長大, 長得很高
    if (p[-1:] and p[-1:] in "很太好多真更最麼越比夠還") or n[:1] in ("長", "的", "度", "久", "期"):
        return "chang2"            # 很長, 長長的
    return None


def _huan(c: Context) -> str | None:
    n = c.next()
    if n[:1] and n[:1] in "給錢債款清書":
        return "huan2"             # 還給我, 還錢
    if n in PRONOUNS and not _is_han(c.next(2)):
        return "huan2"             # 我明天還你。
    return "hai2"


def _hang(c: Context) -> str | None:
    return "hang2" if c.prev() in _NUMERALS else None  # 一行字


def _di(c: Context) -> str | None:
    p, n = c.prev(), c.next()
    if _is_han(p) and _is_han(n) and p not in _NUMERALS and p[-1:] not in "塊片":
        return "de5"               # 慢慢地走
    return "di4"                   # 這塊地


def _chong(c: Context) -> str | None:
    n = c.next()
    return "chong2" if n[:1] and n[:1] in "新複來做寫逢播建組" else None


def _shu(c: Context) -> str | None:
    n = c.next()
    if (n[:1] and n[:1] in "一不過到著了數") or c.prev() in PRONOUNS:
        return "shu3"              # 數一數, 我數到十
    return None


def _wei(c: Context) -> str | None:
    n = c.next()
    if n.startswith(("了", "什麼", "何", "此", "誰")) or n in PRONOUNS or n == "大家":
        return "wei4"              # 為你, 為了
    return None


RULES = {"得": _de, "了": _le, "著": _zhe, "長": _chang, "還": _huan, "行": _hang, "地": _di, "重": _chong,
         "數": _shu, "為": _wei}


def choose_reading(candidates: list[dict], text: str, context: Context) -> str:
    readings = [c["pinyin"] for c in candidates]
    if len(readings) == 1:
        return readings[0]
    # 數一數, 看一看: read like the first one
    if context.prev() == "一" and context.prev(2) == text and context.prev_reading(2) in readings:
        return context.prev_reading(2)
    rule = RULES.get(text)
    chosen = rule(context) if rule else None
    if chosen in readings:
        return chosen
    if USUAL.get(text) in readings:
        return USUAL[text]
    return max(candidates, key=lambda c: c["weight"])["pinyin"]  # the first on equal weights
