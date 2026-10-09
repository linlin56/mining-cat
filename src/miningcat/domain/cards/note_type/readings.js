/* MiningCat note type: the readings written in brackets after their words, shown above them.
   字[zi4]  日本[にほん]  word[wɜːd]  台語[Tâi-gí]: the word is the run of Chinese characters before the bracket, else
   everything since the last space or punctuation mark. A space before a word in characters only separates it (Anki's
   furigana: 今日は 日本[にほん]). Mandarin readings with tone numbers are shown in pinyin or zhuyin, and colored by
   tone like Cantonese ones. When the readings of a word in characters are as many as its characters, each character
   gets its own. */
(function () {
  "use strict";
  const OPTIONS = __OPTIONS__;

  const HAN = /[\p{Script=Han}々〆ヶ]/u;
  const NO_SPACE = /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}々〆ヶー]/u;
  const WORD_END = /[\s\p{P}\p{S}]/u;
  const INSIDE_WORD = /['’\-‐·]/u;  // l'école, peut-être
  const BRACKETS = /\[([^\[\]\n]*)\]/g;

  // ------------------------------------------------------------ pinyin (ported from MiningCat's zhuyin.py)

  const ZHUYIN = (function () {
    const initials = {
      b: "ㄅ", p: "ㄆ", m: "ㄇ", f: "ㄈ", d: "ㄉ", t: "ㄊ", n: "ㄋ", l: "ㄌ", g: "ㄍ", k: "ㄎ", h: "ㄏ", j: "ㄐ", q: "ㄑ",
      x: "ㄒ", zh: "ㄓ", ch: "ㄔ", sh: "ㄕ", r: "ㄖ", z: "ㄗ", c: "ㄘ", s: "ㄙ",
    };
    const finals = {
      a: "ㄚ", o: "ㄛ", e: "ㄜ", ai: "ㄞ", ei: "ㄟ", ao: "ㄠ", ou: "ㄡ", an: "ㄢ", en: "ㄣ", ang: "ㄤ", eng: "ㄥ",
      ong: "ㄨㄥ", i: "ㄧ", ia: "ㄧㄚ", ie: "ㄧㄝ", iao: "ㄧㄠ", iu: "ㄧㄡ", ian: "ㄧㄢ", in: "ㄧㄣ", iang: "ㄧㄤ",
      ing: "ㄧㄥ", iong: "ㄩㄥ", u: "ㄨ", ua: "ㄨㄚ", uo: "ㄨㄛ", uai: "ㄨㄞ", ui: "ㄨㄟ", uan: "ㄨㄢ", un: "ㄨㄣ",
      uang: "ㄨㄤ", "ü": "ㄩ", "üe": "ㄩㄝ",
    };
    const jqxFinals = { u: "ㄩ", ue: "ㄩㄝ", uan: "ㄩㄢ", un: "ㄩㄣ" };  // j, q and x write ü as u
    const combinations = {
      b: "a o ai ei ao an en ang eng i ie iao ian in ing u",
      p: "a o ai ei ao ou an en ang eng i ie iao ian in ing u",
      m: "a o e ai ei ao ou an en ang eng i ie iao iu ian in ing u",
      f: "a o ei ou an en ang eng u",
      d: "a e ai ei ao ou an en ang eng ong i ia ie iao iu ian ing u uo ui uan un",
      t: "a e ai ei ao ou an ang eng ong i ie iao ian ing u uo ui uan un",
      n: "a e ai ei ao ou an en ang eng ong i ie iao iu ian in iang ing u uo uan un ü üe",
      l: "a o e ai ei ao ou an ang eng ong i ia ie iao iu ian in iang ing u uo uan un ü üe",
      g: "a e ai ei ao ou an en ang eng ong u ua uo uai ui uan un uang",
      k: "a e ai ei ao ou an en ang eng ong u ua uo uai ui uan un uang",
      h: "a e ai ei ao ou an en ang eng ong u ua uo uai ui uan un uang",
      j: "i ia ie iao iu ian in iang ing iong u ue uan un",
      q: "i ia ie iao iu ian in iang ing iong u ue uan un",
      x: "i ia ie iao iu ian in iang ing iong u ue uan un",
      zh: "a e ai ei ao ou an en ang eng ong i u ua uo uai ui uan un uang",
      ch: "a e ai ao ou an en ang eng ong i u ua uo uai ui uan un uang",
      sh: "a e ai ei ao ou an en ang eng i u ua uo uai ui uan un uang",
      r: "e ao ou an en ang eng ong i u ua uo ui uan un",
      z: "a e ai ei ao ou an en ang eng ong i u uo ui uan un",
      c: "a e ai ao ou an en ang eng ong i u uo ui uan un",
      s: "a e ai ao ou an en ang eng ong i u uo ui uan un",
    };
    const table = new Map(Object.entries({
      a: "ㄚ", o: "ㄛ", e: "ㄜ", "ê": "ㄝ", ai: "ㄞ", ei: "ㄟ", ao: "ㄠ", ou: "ㄡ", an: "ㄢ", en: "ㄣ", ang: "ㄤ",
      eng: "ㄥ", er: "ㄦ", yi: "ㄧ", ya: "ㄧㄚ", yo: "ㄧㄛ", ye: "ㄧㄝ", yai: "ㄧㄞ", yao: "ㄧㄠ", you: "ㄧㄡ", yan: "ㄧㄢ",
      yin: "ㄧㄣ", yang: "ㄧㄤ", ying: "ㄧㄥ", yong: "ㄩㄥ", wu: "ㄨ", wa: "ㄨㄚ", wo: "ㄨㄛ", wai: "ㄨㄞ", wei: "ㄨㄟ",
      wan: "ㄨㄢ", wen: "ㄨㄣ", wang: "ㄨㄤ", weng: "ㄨㄥ", yu: "ㄩ", yue: "ㄩㄝ", yuan: "ㄩㄢ", yun: "ㄩㄣ",
      m: "ㄇ", n: "ㄋ", ng: "ㄫ", hm: "ㄏㄇ", hng: "ㄏㄫ",
    }));
    const syllabic = ["zh", "ch", "sh", "r", "z", "c", "s"];  // zhi, chi, shi, ri, zi, ci, si: the initial alone
    for (const [initial, list] of Object.entries(combinations)) {
      for (const final of list.split(" ")) {
        let zhuyin = initials[initial] + finals[final];
        if (final === "i" && syllabic.includes(initial)) zhuyin = initials[initial];
        else if ("jqx".includes(initial) && jqxFinals[final]) zhuyin = initials[initial] + jqxFinals[final];
        table.set(initial + final, zhuyin);
      }
    }
    return table;
  })();
  const ZHUYIN_TONES = ["", "", "ˊ", "ˇ", "ˋ"];
  const TONE_MARKS = ["", "̄", "́", "̌", "̀"];  // combining macron, acute, caron, grave

  function withUmlaut(letters) {
    return letters.replace(/u:|v/g, "ü").replace(/U:|V/g, "Ü");
  }

  // "zhong", 1 -> "ㄓㄨㄥ"; the neutral tone's dot before the syllable, an erhua's ㄦ after it. null if not pinyin.
  function zhuyin(letters, tone) {
    let syllable = withUmlaut(letters).toLowerCase();
    let erhua = "";
    if (!ZHUYIN.has(syllable) && syllable.length > 1 && syllable.endsWith("r") && ZHUYIN.has(syllable.slice(0, -1))) {
      syllable = syllable.slice(0, -1);
      erhua = "ㄦ";
    }
    const spelled = ZHUYIN.get(syllable);
    if (!spelled) return null;
    return (tone === 5 ? "˙" + spelled : spelled + (ZHUYIN_TONES[tone] || "")) + erhua;
  }

  // "zhong", 1 -> "zhōng": the mark on a or e, on the o of ou, else on the last vowel (liú, guǐ).
  function markedPinyin(letters, tone) {
    const syllable = withUmlaut(letters);
    if (!(tone >= 1 && tone <= 4)) return syllable;
    const lower = syllable.toLowerCase();
    let at = lower.search(/[ae]/);
    if (at < 0) at = lower.indexOf("ou");
    if (at < 0) {
      for (let i = lower.length - 1; i >= 0 && at < 0; i--) if ("iouü".includes(lower[i])) at = i;
    }
    if (at < 0) at = lower.search(/[mn]/);  // m, ng, hm
    if (at < 0) return syllable;
    return (syllable.slice(0, at + 1) + TONE_MARKS[tone] + syllable.slice(at + 1)).normalize("NFC");
  }

  // ------------------------------------------------------------ readings

  // The syllables of a reading: those with a tone number (ni3hao3, ni3 hao3, tai5-gi2), else its space or hyphen
  // separated parts (Tâi-gí).
  function syllablesOf(reading) {
    const numbered = reading.match(/[^\s\d\-'’]+[1-6]/g);
    if (numbered && numbered.join("") === reading.replace(/[\s\-'’]+/g, "")) return { numbered: true, list: numbered };
    return { numbered: false, list: reading.split(/[\s\-‐]+/).filter(Boolean) };
  }

  // A syllable as shown: {text, tone}, tone 0 when it isn't colored.
  function shown(syllable, language) {
    const match = /^(.*?)([1-6])$/.exec(syllable);
    if (!match || !language) return { text: syllable, tone: 0 };
    const tone = Number(match[2]);
    if (language === "zh") {
      const text = OPTIONS.readings.zh === "zhuyin" ? zhuyin(match[1], tone) : markedPinyin(match[1], tone);
      return { text: text || syllable, tone };
    }
    return { text: syllable, tone };  // Cantonese: jyutping keeps its numbers
  }

  function rubyOf(base, reading, tone) {
    const ruby = document.createElement("ruby");
    ruby.appendChild(document.createTextNode(base));
    const rt = document.createElement("rt");
    rt.textContent = reading;
    ruby.appendChild(rt);
    if (tone && OPTIONS.toneColors) ruby.classList.add("mc-tone" + tone);
    return ruby;
  }

  // [character, index of its syllable] when each character has its syllable, null if not. In Mandarin, the 兒 of an
  // erhua (一點兒[yi4 dianr3]) has none: the r is in the syllable before it.
  function pairs(chars, syllables, language) {
    const out = [];
    let s = 0;
    for (const c of chars) {
      const erhua = language === "zh" && "兒儿".includes(c) && s > 0 && /[^e]r\d$/i.test(syllables[s - 1]);
      if (erhua && chars.length - out.length > syllables.length - s) {
        out.push([c, null]);
      } else {
        if (s >= syllables.length) return null;
        out.push([c, s++]);
      }
    }
    return s === syllables.length ? out : null;
  }

  // A word with its reading above it. `lang`: the card's language (the Language field), "" when unknown.
  function wordWithReading(base, reading, lang) {
    const word = document.createElement("span");
    word.className = "mc-word";
    const chars = Array.from(base);
    const inCharacters = chars.every((c) => HAN.test(c));
    const { numbered, list } = syllablesOf(reading);
    let language = "";
    if (numbered && (lang === "zh" || lang === "yue")) language = lang;
    else if (numbered && !lang && inCharacters && list.every((s) => Number(s.slice(-1)) <= 5)) language = "zh";  // another note type's 字[zi4]
    const syllables = list.map((s) => shown(s, language));
    const paired = inCharacters && pairs(chars, list, language);
    if (paired) {
      paired.forEach(([c, i]) => word.appendChild(i === null ? document.createTextNode(c) : rubyOf(c, syllables[i].text, syllables[i].tone)));
    } else {
      const joined = numbered ? syllables.map((s) => s.text).join(OPTIONS.readings.zh === "zhuyin" && language === "zh" ? "" : " ") : reading;
      word.appendChild(rubyOf(base, joined, 0));
    }
    return word;
  }

  // Replaces the bracketed readings of a text node with the words and their readings.
  function annotateText(node, lang) {
    const text = node.nodeValue;
    const out = document.createDocumentFragment();
    let pos = 0;
    for (const match of text.matchAll(BRACKETS)) {
      const reading = match[1].split(";")[0].trim();  // 漢字[かんじ;h]: what follows a ";" isn't the reading
      const before = Array.from(text.slice(pos, match.index));
      let start = before.length;
      if (start && HAN.test(before[start - 1])) {
        while (start && HAN.test(before[start - 1])) start--;
      } else {
        while (start && (!WORD_END.test(before[start - 1]) || INSIDE_WORD.test(before[start - 1]))) start--;
      }
      if (start === before.length || /^\d*$/.test(reading)) continue;  // no word before it, or a note call ([1])
      let lead = before.slice(0, start).join("");
      if (NO_SPACE.test(before[start]) && lead.endsWith(" ")) lead = lead.slice(0, -1);
      out.appendChild(document.createTextNode(lead));
      out.appendChild(wordWithReading(before.slice(start).join(""), reading, lang));
      pos = match.index + match[0].length;
    }
    if (pos === 0) return;
    out.appendChild(document.createTextNode(text.slice(pos)));
    node.parentNode.replaceChild(out, node);
  }

  function languageOf(elem) {
    const tagged = elem.closest("[lang]");
    return tagged ? tagged.lang.trim().toLowerCase().split("-")[0] : "";
  }

  function annotate(elem) {
    if (elem.dataset.mcDone) return;  // Anki may run the script again on the same card
    elem.dataset.mcDone = "1";
    const lang = languageOf(elem);
    const walker = document.createTreeWalker(elem, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) {
      const node = walker.currentNode;
      if (node.nodeValue.includes("[") && !node.parentNode.closest("ruby, script, style")) nodes.push(node);
    }
    nodes.forEach((node) => annotateText(node, lang));
  }

  document.querySelectorAll(".mc-card .mc-readings").forEach(annotate);

  // A word in characters without readings in brackets: its Reading field above it.
  document.querySelectorAll(".mc-card .mc-word-field").forEach((field) => {
    const reading = field.parentNode.querySelector(".mc-reading");
    const word = field.textContent.trim();
    if (!reading || field.querySelector("ruby") || !word) return;
    const text = reading.textContent.trim();
    if (!text || text === word || !Array.from(word).every((c) => NO_SPACE.test(c))) return;
    field.textContent = "";
    field.appendChild(wordWithReading(word, text, languageOf(field)));
    reading.hidden = true;
  });

  // On the front, a word's reading is a hint above it, out of the line (hidden readings above the characters would
  // spread them apart): a tap shows it, hovering it too with a mouse.
  document.querySelectorAll(".mc-front .mc-word").forEach((word) => {
    const hint = document.createElement("span");
    hint.className = "mc-hint";
    word.querySelectorAll("ruby").forEach((ruby) => {
      const part = document.createElement("span");
      part.className = ruby.className;
      part.textContent = ruby.querySelector("rt").textContent;
      hint.appendChild(part);
    });
    word.appendChild(hint);
    word.addEventListener("click", () => word.classList.toggle("mc-shown"));
  });
})();
