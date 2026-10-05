// MiningCat dictionary popup and card creator.
//
// MiningCatMining.attach(container, {getLanguage, getSource, getMode}) makes the text of `container`
// searchable: a click (or Shift + hover) on a word looks it up in the imported dictionaries and shows
// a popup with the definitions, the word's status and a "+ Card" button that opens the card creator.
// Optional: hasAudio(), sentenceAudio(text) -> {url, start, end} and sentenceClip(text) -> {data, name}
// when the text has audio (a book converted by MiningCat): the popup can then play the sentence, and
// the card creator gets the sentence's audio. getImage(node) -> {data, name}: an image for the card, from
// the text node that was looked up (e.g. the screenshot of a video game capture).
"use strict";

(() => {
  const STATUSES = [["new", "New"], ["learning", "Learning"], ["known", "Known"], ["ignored", "Ignored"]];
  const SCAN_CHARS = 40;
  const CJK = /^(ja|zh|yue|nan)/;
  const SENTENCE_END = /[。！？!?…\n]|[.](?=\s|$)/;
  const CLOSERS = /[」』）)】〉》”’"'\s]/;

  let options = null;
  let popup = null;
  let current = null;       // {language, entries, sentence, highlight}
  let lookupToken = 0;
  let hoverTimer = null;

  // ------------------------------------------------------------ helpers

  async function api(path, body) {
    const init = body === undefined ? {} : {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-MiningCat": "1" },
      body: JSON.stringify(body),
    };
    const res = await fetch(path, init);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw Object.assign(new Error(data.error || `Request failed (${res.status})`), { title: data.title || "Error", unavailable: data.unavailable });
    return data;
  }

  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v === undefined || v === null || v === false) continue;
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat()) if (c !== null && c !== undefined && c !== false) node.append(c);
    return node;
  }

  function toast(message, kind = "info") {
    let box = document.getElementById("mc-toast");
    if (!box) {
      box = el("div", { id: "mc-toast", class: "mc-toast", role: "status", "aria-live": "polite" });
      document.body.append(box);
    }
    box.textContent = message;
    box.className = `mc-toast show ${kind}`;
    clearTimeout(box._timer);
    box._timer = setTimeout(() => { box.className = "mc-toast"; }, 3500);
  }

  // ------------------------------------------------------------ text under the cursor

  function caretAt(x, y) {
    if (document.caretPositionFromPoint) {
      const pos = document.caretPositionFromPoint(x, y);
      return pos ? { node: pos.offsetNode, offset: pos.offset } : null;
    }
    if (document.caretRangeFromPoint) {
      const range = document.caretRangeFromPoint(x, y);
      return range ? { node: range.startContainer, offset: range.startOffset } : null;
    }
    return null;
  }

  // The caret API returns the nearest position, even in the margin: check the character is really under the cursor.
  function charUnder(node, offset, x, y) {
    const range = document.createRange();
    for (const start of [offset, offset - 1]) {
      if (start < 0 || start >= node.data.length) continue;
      range.setStart(node, start);
      range.setEnd(node, start + 1);
      for (const r of range.getClientRects()) {
        if (x >= r.left - 1 && x <= r.right + 1 && y >= r.top - 1 && y <= r.bottom + 1) return start;
      }
    }
    return -1;
  }

  const BLOCK = "p, li, h1, h2, h3, h4, h5, h6, td, th, dd, dt, blockquote, figcaption, div, section, article";

  // Text of the block around the cursor (ruby annotations excluded), with each character's position.
  function blockText(block) {
    const chars = [];
    const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT, {
      acceptNode(n) { return n.parentElement.closest("rt, rp") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT; },
    });
    let text = "";
    while (walker.nextNode()) {
      const n = walker.currentNode;
      for (let i = 0; i < n.data.length; i++) chars.push({ node: n, offset: i });
      text += n.data;
    }
    return { text, chars };
  }

  function sentenceAround(text, start, length) {
    let from = start;
    while (from > 0 && !SENTENCE_END.test(text[from - 1])) from--;
    let to = start + length;
    while (to < text.length && !SENTENCE_END.test(text[to])) to++;
    while (to < text.length && (SENTENCE_END.test(text[to]) || CLOSERS.test(text[to])) && text[to] !== "\n") to++;
    const before = text.slice(from, start), word = text.slice(start, start + length), after = text.slice(start + length, to);
    const trim = (s) => s.replace(/^\s+/, "");
    return { text: trim(before + word + after).trim(), before: trim(before), word, after: after.trimEnd() };
  }

  function scanAt(x, y, container) {
    const caret = caretAt(x, y);
    if (!caret || caret.node.nodeType !== Node.TEXT_NODE || !container.contains(caret.node)) return null;
    if (caret.node.parentElement.closest("rt, rp, a[data-chapter]")) return null;
    const offset = charUnder(caret.node, caret.offset, x, y);
    if (offset < 0) return null;
    const block = caret.node.parentElement.closest(BLOCK) || container;
    const { text, chars } = blockText(block);
    let start = chars.findIndex((c) => c.node === caret.node && c.offset === offset);
    if (start < 0) return null;
    const language = options.getLanguage();
    if (!/\S/.test(text[start]) || /[\s\p{P}]/u.test(text[start]) && !/[ー〜]/.test(text[start])) return null;
    if (!CJK.test(language)) {
      while (start > 0 && /[\p{L}\p{M}'’-]/u.test(text[start - 1])) start--;
    }
    return { text, chars, start, language };
  }

  // ------------------------------------------------------------ highlight

  function highlight(scan, length) {
    if (!window.CSS || !CSS.highlights || !window.Highlight) return;
    const a = scan.chars[scan.start], b = scan.chars[Math.min(scan.start + length, scan.chars.length) - 1];
    if (!a || !b) return;
    const range = document.createRange();
    range.setStart(a.node, a.offset);
    range.setEnd(b.node, b.offset + 1);
    const lookup = new Highlight(range);
    lookup.priority = 10;  // above the status colours
    CSS.highlights.set("mc-lookup", lookup);
    return range;
  }

  function clearHighlight() {
    if (window.CSS && CSS.highlights) CSS.highlights.delete("mc-lookup");
  }

  // ------------------------------------------------------------ word colours

  // Words are coloured with CSS highlights: the DOM isn't touched, so the reader's character offsets,
  // its pagination and other tools reading the page (Yomitan) see the same text.
  const COLOURED = ["new", "learning"];
  // Two touching words of the same colour would read as one: every other one gets the "-alt" shade.
  const COLOUR_HIGHLIGHTS = COLOURED.flatMap((status) => [`mc-${status}`, `mc-${status}-alt`]);
  let colours = null;       // {language, words: [{headword, form, status}], tokens: [{index, start, end, range}]}
  let colourToken = 0;

  // Text of `root` sent for segmentation: its text nodes (ruby annotations excluded), with a line break
  // between blocks so that no word spans two paragraphs. `starts[k]` is where node k begins in `text`.
  function segmentText(root) {
    const nodes = [], starts = [];
    let text = "", lastBlock = null;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode(n) { return n.parentElement.closest("rt, rp") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT; },
    });
    while (walker.nextNode()) {
      const node = walker.currentNode;
      const block = node.parentElement.closest(BLOCK);
      if (text && block !== lastBlock) text += "\n";
      lastBlock = block;
      nodes.push(node);
      starts.push(text.length);
      text += node.data;
    }
    return { text, nodes, starts };
  }

  function nodeAt(seg, offset) {
    let lo = 0, hi = seg.nodes.length - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (seg.starts[mid] <= offset) lo = mid; else hi = mid - 1;
    }
    const node = seg.nodes[lo];
    return { node, at: Math.min(offset - seg.starts[lo], node.data.length) };
  }

  function paintColours() {
    if (!colours) return;
    const groups = Object.fromEntries(COLOUR_HIGHLIGHTS.map((name) => [name, []]));
    let previous = null;  // {status, end, alt} of the last coloured word
    for (const token of colours.tokens) {
      const status = colours.words[token.index].status;
      if (!COLOURED.includes(status)) { previous = null; continue; }
      const alt = Boolean(previous && previous.status === status && previous.end === token.start && !previous.alt);
      groups[`mc-${status}${alt ? "-alt" : ""}`].push(token.range);
      previous = { status, end: token.end, alt };
    }
    for (const name of COLOUR_HIGHLIGHTS) CSS.highlights.set(name, new Highlight(...groups[name]));
  }

  function clearColours() {
    colourToken++;
    colours = null;
    if (window.CSS && CSS.highlights) for (const name of COLOUR_HIGHLIGHTS) CSS.highlights.delete(name);
  }

  // Colours the words of `root` (e.g. a reader chapter) by status. Words missing from the dictionaries stay as they are.
  async function colourWords(root, language) {
    clearColours();
    if (!window.CSS || !CSS.highlights || !window.Highlight) return;
    const token = colourToken;
    const seg = segmentText(root);
    if (!seg.text.trim()) return;
    let data;
    try {
      data = await api("/api/words/segment", { language, text: seg.text });
    } catch {
      return;  // e.g. no dictionary language: the text simply stays uncoloured
    }
    if (token !== colourToken) return;
    const tokens = [];
    for (const [start, length, index] of data.tokens) {
      if (index < 0) continue;
      const a = nodeAt(seg, start), b = nodeAt(seg, start + length);
      const range = document.createRange();
      range.setStart(a.node, a.at);
      range.setEnd(b.node, b.at);
      tokens.push({ index, start, end: start + length, range });
    }
    colours = { language: data.language, words: data.words, tokens };
    paintColours();
  }

  // A status changed in the popup or through a new card: recolour that word everywhere in the text.
  function updateColour(form, status) {
    if (!colours) return;
    let changed = false;
    for (const word of colours.words) {
      if (word.form === form && word.status !== status) {
        word.status = status;
        changed = true;
      }
    }
    if (changed) paintColours();
  }

  // ------------------------------------------------------------ dictionary content

  const SC_TAGS = new Set(["br", "ruby", "rt", "rp", "table", "thead", "tbody", "tfoot", "tr", "td", "th", "span",
    "div", "ol", "ul", "li", "details", "summary", "a", "img", "b", "i", "em", "strong", "sub", "sup"]);
  const SC_STYLES = ["fontStyle", "fontWeight", "fontSize", "color", "backgroundColor", "textDecorationLine",
    "textDecorationStyle", "textDecorationColor", "verticalAlign", "textAlign", "textEmphasis", "textShadow",
    "marginTop", "marginLeft", "marginRight", "marginBottom", "paddingTop", "paddingLeft", "paddingRight", "paddingBottom",
    "padding", "margin", "listStyleType", "borderStyle", "borderWidth", "borderColor", "borderRadius", "wordBreak",
    "whiteSpace", "cursor", "clipPath"];

  function imageNode(spec, dictId) {
    const img = el("img", {
      src: `/api/dict/${dictId}/media/${spec.path.split("/").map(encodeURIComponent).join("/")}`,
      alt: spec.alt || spec.description || "", title: spec.title || undefined, loading: "lazy", class: "mc-gloss-img",
    });
    if (spec.width) img.style.maxWidth = `${Math.min(spec.width, 260)}${spec.sizeUnits === "em" ? "em" : "px"}`;
    return img;
  }

  function renderSC(node, dictId) {
    if (node === null || node === undefined) return document.createTextNode("");
    if (typeof node === "string" || typeof node === "number") return document.createTextNode(String(node));
    if (Array.isArray(node)) {
      const frag = document.createDocumentFragment();
      for (const child of node) frag.append(renderSC(child, dictId));
      return frag;
    }
    if (typeof node !== "object") return document.createTextNode("");
    if (node.tag === "img" && node.path) return imageNode(node, dictId);
    const tag = SC_TAGS.has(node.tag) ? node.tag : "span";
    const out = document.createElement(tag);
    if (node.style && typeof node.style === "object") {
      for (const key of SC_STYLES) if (typeof node.style[key] === "string" || typeof node.style[key] === "number") out.style[key] = node.style[key];
    }
    if (node.data && typeof node.data === "object") {
      for (const [k, v] of Object.entries(node.data)) {
        const name = `sc${k.charAt(0).toUpperCase()}${k.slice(1)}`.replace(/[^\w]/g, "");
        if (name) out.dataset[name] = String(v);
      }
    }
    if (node.lang) out.lang = node.lang;
    if (node.title) out.title = node.title;
    if (node.colSpan) out.colSpan = node.colSpan;
    if (node.rowSpan) out.rowSpan = node.rowSpan;
    if (tag === "a" && node.href) {
      if (node.href.startsWith("?")) {
        const query = new URLSearchParams(node.href.slice(1)).get("query");
        out.href = "#";
        if (query) out.dataset.query = query;
      } else if (/^https?:/.test(node.href)) {
        out.href = node.href;
        out.target = "_blank";
        out.rel = "noopener noreferrer";
      }
    }
    if (node.content !== undefined) out.append(renderSC(node.content, dictId));
    return out;
  }

  function renderGlossary(glossary, dictId) {
    const list = el("ul", { class: glossary.length > 1 ? "mc-gloss" : "mc-gloss mc-single" });
    for (const item of glossary) {
      let content;
      if (typeof item === "string") content = document.createTextNode(item);
      else if (Array.isArray(item)) content = document.createTextNode(`→ ${item[0]}`);
      else if (item && item.type === "text") content = document.createTextNode(item.text || "");
      else if (item && item.type === "image") content = imageNode(item, dictId);
      else if (item && item.type === "structured-content") content = renderSC(item.content, dictId);
      else continue;
      list.append(el("li", {}, content));
    }
    return list;
  }

  // ------------------------------------------------------------ sentence audio

  let player = null;
  let playerEnd = 0;

  async function playSentence(text, button) {
    if (button) button.disabled = true;
    try {
      const span = await options.sentenceAudio(text);
      if (!span) { toast("This sentence wasn't found in the book's audio.", "info"); return; }
      if (!player) {
        player = new Audio();
        player.addEventListener("timeupdate", () => { if (player.currentTime >= playerEnd) player.pause(); });
      }
      if (!player.src.endsWith(span.url)) player.src = span.url;
      playerEnd = span.end;
      player.currentTime = span.start;
      await player.play();
    } catch (err) {
      toast(err.message || "Couldn't play the audio.", "error");
    } finally {
      if (button) button.disabled = false;
    }
  }

  function stopSentence() {
    if (player) player.pause();
  }

  // Recordings of a word (online sources), fetched once per word.
  const wordAudioCache = new Map();
  function wordAudio(entry, language) {
    const key = `${language}|${entry.expression}|${entry.reading}`;
    if (!wordAudioCache.has(key)) {
      const query = new URLSearchParams({ language, expression: entry.expression, reading: entry.reading || "" });
      wordAudioCache.set(key, api(`/api/dict/audio?${query}`).then((d) => d.sources).catch((err) => { wordAudioCache.delete(key); throw err; }));
    }
    return wordAudioCache.get(key);
  }

  // Plays the word's recordings in turn, one per click.
  async function playWord(entry, language, button) {
    button.disabled = true;
    try {
      const sources = await wordAudio(entry, language);
      if (!sources.length) { toast("No recording found for this word.", "info"); return; }
      const index = (Number(button.dataset.next) || 0) % sources.length;
      button.dataset.next = String(index + 1);
      button.title = `${sources[index].name}${sources.length > 1 ? ` (${index + 1}/${sources.length}, click for the next one)` : ""}`;
      if (!player) {
        player = new Audio();
        player.addEventListener("timeupdate", () => { if (player.currentTime >= playerEnd) player.pause(); });
      }
      playerEnd = Infinity;
      player.src = sources[index].url;
      await player.play();
    } catch (err) {
      toast(err.message || "Couldn't play the recording.", "error");
    } finally {
      button.disabled = false;
    }
  }

  // ------------------------------------------------------------ popup

  function ensurePopup() {
    if (popup) return popup;
    popup = el("div", { class: "mc-popup", id: "mc-popup", role: "dialog", "aria-label": "Dictionary", hidden: true });
    popup.addEventListener("click", (e) => {
      const query = e.target.closest("a[data-query]");
      if (query) {
        e.preventDefault();
        lookupText(query.dataset.query, current && current.anchorRect);
      }
    });
    document.body.append(popup);
    return popup;
  }

  function hidePopup() {
    lookupToken++;
    stopSentence();
    if (popup) popup.hidden = true;
    clearHighlight();
    current = null;
  }

  function placePopup(anchor) {
    const pad = 10;
    popup.style.left = "0px";
    popup.style.top = "0px";
    popup.hidden = false;
    const w = popup.offsetWidth, h = popup.offsetHeight;
    const vw = window.innerWidth, vh = window.innerHeight;
    let left, top;
    if (options.isVertical && options.isVertical()) {
      // beside the vertical line, on the left if possible (the reading direction)
      left = anchor.left - w - pad >= 0 ? anchor.left - w - pad : anchor.right + pad;
      top = Math.min(Math.max(pad, anchor.top), vh - h - pad);
    } else {
      left = Math.min(Math.max(pad, anchor.left), vw - w - pad);
      top = anchor.bottom + pad + h <= vh ? anchor.bottom + pad : Math.max(pad, anchor.top - h - pad);
    }
    popup.style.left = `${Math.max(pad, left)}px`;
    popup.style.top = `${Math.max(pad, top)}px`;
  }

  function statusControl(entry, language) {
    const group = el("div", { class: "mc-status", role: "radiogroup", "aria-label": "Word status" });
    const render = () => {
      for (const b of group.children) b.setAttribute("aria-checked", String(b.dataset.value === entry.status.status));
    };
    for (const [value, label] of STATUSES) {
      group.append(el("button", {
        type: "button", role: "radio", "data-value": value, class: `mc-status-${value}`, text: label,
        onclick: async () => {
          try {
            await api("/api/words/status", { language, expression: entry.form, reading: entry.reading, status: value });
            entry.status.status = value;
            render();
            updateColour(entry.form, value);
            if (options.onStatusChange) options.onStatusChange(entry.form, value);
          } catch (err) { toast(err.message, "error"); }
        },
      }));
    }
    render();
    return group;
  }

  // The book's own tag (zh-Hant, zh-Hans…) picks better glyphs than the bare language key.
  function displayLang(language) {
    const tag = options.getLanguage() || "";
    return tag.toLowerCase().startsWith(language) ? tag : language;
  }

  function headword(entry, language) {
    const word = el("span", { class: "mc-word", lang: displayLang(language) });
    if (language === "ja" && entry.reading && entry.reading !== entry.expression) {
      word.append(el("ruby", {}, entry.expression, el("rt", { text: entry.reading })));
    } else {
      word.append(entry.expression);
    }
    const parts = [word];
    if (language !== "ja" && entry.reading && entry.reading !== entry.expression) parts.push(el("span", { class: "mc-reading", text: entry.display_reading || entry.reading }));
    return el("div", { class: "mc-head" }, ...parts);
  }

  function renderEntries(data, language) {
    const box = ensurePopup();
    box.replaceChildren();
    const close = el("button", { type: "button", class: "mc-close", "aria-label": "Close", text: "×", onclick: hidePopup });
    if (!data.dictionaries) {
      box.append(close, el("p", { class: "mc-empty" },
        "No dictionary for this language yet. ",
        el("a", { href: "/settings/#dictionaries", target: "_blank", text: "Import one in Settings" }), "."));
      return;
    }
    if (!data.entries.length) {
      box.append(close, el("p", { class: "mc-empty", text: "No results." }));
      return;
    }
    box.append(close);
    const sentence = current && current.sentence && current.sentence.text;
    if (sentence && options.sentenceAudio && options.hasAudio && options.hasAudio()) {
      const play = el("button", { type: "button", class: "mc-play", title: "Play the sentence", text: "▶ Sentence" });
      play.addEventListener("click", () => playSentence(sentence, play));
      box.append(play);
    }
    for (const entry of data.entries) {
      const meta = el("div", { class: "mc-meta" });
      if (entry.inflections.length) {
        meta.append(el("span", { class: "mc-infl", title: entry.inflections.map((i) => `${i.name}: ${i.description || ""}`).join("\n") },
          `« ${entry.inflections.map((i) => i.name).join(" « ")}`));
      }
      for (const f of entry.frequencies.slice(0, 3)) meta.append(el("span", { class: "mc-chip", title: f.dictionary, text: `${f.dictionary.split(/[\s[(]/)[0]} ${f.display}` }));
      if (entry.frequencies.length > 3) {
        const rest = entry.frequencies.slice(3);
        meta.append(el("span", { class: "mc-chip", title: rest.map((f) => `${f.dictionary}: ${f.display}`).join("\n"), text: `+${rest.length}` }));
      }
      for (const p of entry.pronunciations || []) meta.append(pronunciation(p, entry, language));

      const notes = [];
      if (entry.form !== entry.expression) notes.push(el("p", { class: "mc-note" }, "Saved as ", el("strong", { lang: displayLang(language), text: entry.form }), " (the script you learn)."));
      if (entry.status.linked) {
        const s = entry.status.linked;
        notes.push(el("p", { class: "mc-note mc-linked" },
          `You ${s.status === "known" ? "know" : "are learning"} this word in ${s.script === "traditional" ? "Traditional" : "Simplified"}: `,
          el("strong", { lang: displayLang(language), text: s.expression })));
      }

      const defs = el("div", { class: "mc-defs" });
      for (const [dictionary, senses] of groupByDictionary(entry.definitions)) {
        const list = el(senses.length > 1 ? "ol" : "div", { class: "mc-senses" });
        for (const d of senses) {
          const tags = [...new Set([...d.tags, ...d.term_tags])].filter((t) => !/^\d+$/.test(t)).map((t) => el("span", {
            class: "mc-tag", text: t, title: (d.tag_info[t] && d.tag_info[t].notes) || undefined,
          }));
          list.append(el(senses.length > 1 ? "li" : "div", { class: "mc-sense" },
            tags.length ? el("div", { class: "mc-tags" }, ...tags) : null,
            renderGlossary(d.glossary, d.dict_id)));
        }
        defs.append(el("section", { class: "mc-def" }, el("div", { class: "mc-dict", text: dictionary }), list));
      }

      const chars = characterSection(entry, language);
      const add = el("button", { type: "button", class: "mc-add", text: "+ Card", onclick: () => openCreator(entry, language) });
      const listen = el("button", { type: "button", class: "mc-listen", title: "Play the word (online recordings)", "aria-label": "Play the word", text: "🔊" });
      listen.addEventListener("click", () => playWord(entry, language, listen));
      box.append(el("article", { class: "mc-entry" },
        el("div", { class: "mc-entry-top" }, headword(entry, language), listen, add),
        meta.childNodes.length ? meta : null,
        ...notes,
        statusControl(entry, language),
        defs,
        chars));
    }
  }

  // The word's characters, from the character (kanji / hanzi) dictionaries: folded, opened on demand.
  function characterSection(entry, language) {
    if (!entry.characters || !entry.characters.length) return null;
    const lang = displayLang(language);
    const box = el("details", { class: "mc-chars" }, el("summary", { text: `Characters (${entry.characters.map((c) => c.character).join("")})` }));
    for (const { character, entries } of entry.characters) {
      const body = el("div", { class: "mc-char-body" });
      for (const k of entries) {
        const readings = [k.onyomi.join("、"), k.kunyomi.join("、")].filter(Boolean).join(" · ");
        const stats = [k.stats.strokes && `${k.stats.strokes} strokes`, k.stats.grade && `grade ${k.stats.grade}`,
          k.stats.jlpt && `JLPT N${k.stats.jlpt}`, k.stats.freq && `#${k.stats.freq}`, ...k.frequencies].filter(Boolean);
        body.append(el("div", { class: "mc-char-entry" },
          readings ? el("div", { class: "mc-char-readings", lang, text: readings }) : null,
          el("div", { class: "mc-char-meanings", text: k.meanings.join("; ") }),
          stats.length ? el("div", { class: "mc-char-stats", text: stats.join(" · ") }) : null));
      }
      box.append(el("div", { class: "mc-char" }, el("span", { class: "mc-char-glyph", lang, text: character }), body));
    }
    return box;
  }

  // Morae of a kana reading: small kana belong to the previous one (きょう = きょ + う).
  function morae(kana) {
    const out = [];
    for (const ch of kana) {
      if (/[ゃゅょぁぃぅぇぉゎャュョァィゥェォヮ]/.test(ch) && out.length) out[out.length - 1] += ch;
      else out.push(ch);
    }
    return out;
  }

  // Pitch accent with the downstep position (0: heiban, 1: atamadaka...): high morae are overlined, ꜜ marks the drop.
  function pitchGraph(reading, position) {
    if (typeof position !== "number") return el("span", { class: "mc-pitch", text: `${reading} ${position}` });
    const box = el("span", { class: "mc-pitch", title: `Pitch accent [${position}]`, lang: "ja" });
    morae(reading).forEach((mora, i) => {
      const n = i + 1;
      const high = position === 0 ? n > 1 : position === 1 ? n === 1 : n > 1 && n <= position;
      box.append(el("span", { class: high ? "mc-high" : "mc-low", text: mora }));
      if (n === position) box.append(el("span", { class: "mc-drop", text: "ꜜ" }));
    });
    box.append(el("span", { class: "mc-pitch-num", text: `[${position}]` }));
    return box;
  }

  function pronunciation(p, entry, language) {
    const reading = p.reading || (entry.reading !== entry.expression ? entry.reading : entry.expression);
    const wrap = el("span", { class: "mc-pron", title: p.dictionary });
    if (p.pitches) for (const position of p.pitches) wrap.append(pitchGraph(reading, position));
    if (p.ipa) for (const ipa of p.ipa) wrap.append(el("span", { class: "mc-ipa", text: ipa }));
    return wrap;
  }

  function groupByDictionary(definitions) {
    const groups = new Map();
    for (const d of definitions) {
      if (!groups.has(d.dictionary)) groups.set(d.dictionary, []);
      groups.get(d.dictionary).push(d);
    }
    return groups;
  }

  async function lookupScan(scan, anchorRect) {
    const token = ++lookupToken;
    const query = scan.text.slice(scan.start, scan.start + SCAN_CHARS);
    let data;
    try {
      data = await api("/api/dict/lookup", { language: scan.language, text: query });
    } catch (err) {
      toast(err.message, "error");
      return;
    }
    if (token !== lookupToken) return;
    const length = data.entries.length ? data.entries[0].length : 1;
    const range = highlight(scan, length);
    const rect = range ? range.getBoundingClientRect() : anchorRect;
    current = {
      language: data.language, entries: data.entries, anchorRect: rect,
      sentence: sentenceAround(scan.text, scan.start, length),
      node: scan.chars[scan.start].node,
    };
    renderEntries(data, data.language);
    placePopup(rect);
    popup.scrollTop = 0;
  }

  // Lookup of a word clicked inside a definition (cross reference).
  async function lookupText(text, anchorRect) {
    const language = current ? current.language : options.getLanguage();
    const sentence = current ? current.sentence : { text: "", before: "", word: text, after: "" };
    const token = ++lookupToken;
    const data = await api("/api/dict/lookup", { language, text }).catch((err) => { toast(err.message, "error"); return null; });
    if (!data || token !== lookupToken) return;
    current = { language: data.language, entries: data.entries, anchorRect, sentence, node: current ? current.node : null };
    renderEntries(data, data.language);
    placePopup(anchorRect);
  }

  // ------------------------------------------------------------ card creator

  let creator = null;

  function definitionHtml(entry, selected) {
    const box = document.createElement("div");
    for (const [dictionary, senses] of groupByDictionary(entry.definitions)) {
      if (!selected.has(dictionary)) continue;
      const list = document.createElement(senses.length > 1 ? "ol" : "div");
      for (const d of senses) {
        const item = document.createElement(senses.length > 1 ? "li" : "div");
        item.append(renderGlossary(d.glossary, d.dict_id));
        list.append(item);
      }
      box.append(list);
    }
    for (const img of box.querySelectorAll("img")) img.remove();
    for (const node of box.querySelectorAll("[data-query]")) { node.removeAttribute("href"); node.removeAttribute("data-query"); }
    for (const node of box.querySelectorAll("[class]")) node.removeAttribute("class");
    return box.innerHTML;
  }

  function escapeHtml(text) {
    const d = document.createElement("div");
    d.textContent = text;
    return d.innerHTML;
  }

  function readFile(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve({ data: reader.result, name: file.name });
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });
  }

  function mediaSlot(kind, label, accept) {
    const state = { value: null };
    const preview = el("div", { class: "mc-media-preview" });
    const input = el("input", { type: "file", accept, hidden: true });
    const url = el("input", { type: "url", placeholder: "or paste a link (https://…)", class: "mc-media-url" });
    const render = () => {
      preview.replaceChildren();
      if (!state.value) return;
      const src = state.value.data || state.value.url;
      preview.append(kind === "image" ? el("img", { src, alt: "" }) : el("audio", { src, controls: true }),
        el("button", { type: "button", class: "mc-media-remove", text: "Remove", onclick: () => { state.value = null; url.value = ""; render(); } }));
    };
    const set = async (file) => {
      if (!file) return;
      if (file.size > 30 * 1024 * 1024) return toast("Files are limited to 30 MB.", "error");
      state.value = await readFile(file);
      render();
    };
    input.addEventListener("change", () => { set(input.files[0]); input.value = ""; });
    const setValue = (value) => { state.value = value; render(); };
    url.addEventListener("change", () => {
      const value = url.value.trim();
      state.value = /^https?:\/\//.test(value) ? { url: value } : null;
      render();
    });
    const zone = el("div", { class: "mc-media", "data-kind": kind },
      el("div", { class: "mc-media-row" },
        el("span", { class: "mc-label", text: label }),
        el("button", { type: "button", class: "mc-btn", text: "Choose a file…", onclick: () => input.click() }),
        input),
      url, preview);
    zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("dragover"); });
    zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      zone.classList.remove("dragover");
      const file = e.dataTransfer.files[0];
      if (file) set(file);
      else {
        const link = e.dataTransfer.getData("text/uri-list") || e.dataTransfer.getData("text/plain");
        if (/^https?:\/\//.test(link)) { url.value = link.trim(); url.dispatchEvent(new Event("change")); }
      }
    });
    return { zone, state, set, setValue, preview };
  }

  // A voice reading the card's sentence (Edge-TTS), for sentences without audio. The voice set in the
  // settings is picked first; ready resolves to it ("" when sentences aren't read automatically).
  function ttsRow(language, getText, slot) {
    const select = el("select", { class: "mc-tts-voice", "aria-label": "Voice", disabled: true });
    const button = el("button", { type: "button", class: "mc-btn", text: "Generate", disabled: true });
    const row = el("div", { class: "mc-media-row mc-tts" }, el("span", { class: "mc-label", text: "Read by" }), select, button);
    const ready = api(`/api/tts/voices?language=${encodeURIComponent(language)}`).then(({ voices, default: fallback, chosen }) => {
      if (!voices.length) { row.hidden = true; return ""; }
      for (const v of voices) select.append(el("option", { value: v.id, text: v.label }));
      select.value = chosen || fallback;
      select.disabled = button.disabled = false;
      return chosen;
    }).catch(() => { row.hidden = true; return ""; });
    const generate = async () => {
      const text = getText().trim();
      if (!text) return toast("There's no sentence to read.", "info");
      button.disabled = true;
      button.textContent = "Generating…";
      try {
        const audio = await api("/api/tts", { language, text, voice: select.value });
        if (row.isConnected) slot.setValue(audio);
      } catch (err) {
        toast(err.message, "error");
      } finally {
        button.disabled = false;
        button.textContent = "Generate";
      }
    };
    button.addEventListener("click", generate);
    return { row, ready, generate };
  }

  async function openCreator(entry, language) {
    const ctx = current;
    hidePopup();
    if (creator) creator.dialog.remove();
    const sentence = ctx ? ctx.sentence : { text: "", before: "", word: entry.source, after: "" };
    const selected = new Set(entry.definitions.length ? [entry.definitions[0].dictionary] : []);

    const word = el("input", { type: "text", value: entry.form, lang: displayLang(language) });
    const reading = el("input", { type: "text", value: entry.reading !== entry.expression ? entry.display_reading || entry.reading : "", lang: displayLang(language) });
    const definition = el("div", { class: "mc-editable", contenteditable: "true", role: "textbox", "aria-multiline": "true" });
    definition.innerHTML = definitionHtml(entry, selected);
    const sentenceBox = el("div", { class: "mc-editable", contenteditable: "true", role: "textbox", lang: displayLang(language) });
    sentenceBox.innerHTML = sentence.text
      ? `${escapeHtml(sentence.before)}<b>${escapeHtml(sentence.word)}</b>${escapeHtml(sentence.after)}` : "";
    const translation = el("textarea", { rows: "2", placeholder: "Optional" });
    const notes = el("textarea", { rows: "2", placeholder: "Optional" });
    const source = el("input", { type: "text", value: options.getSource ? options.getSource() : "" });
    const tags = el("input", { type: "text", placeholder: "space separated" });
    const image = mediaSlot("image", "Image", "image/*");
    const audio = mediaSlot("audio", "Word audio", "audio/*");
    const sentenceAudio = mediaSlot("sentence_audio", "Sentence audio", "audio/*,video/*");
    const tts = ttsRow(language, () => sentenceBox.textContent, sentenceAudio);
    sentenceAudio.zone.insertBefore(tts.row, sentenceAudio.preview);

    const dictChoice = el("div", { class: "mc-dict-choice" });
    for (const name of [...new Set(entry.definitions.map((d) => d.dictionary))]) {
      const box = el("input", { type: "checkbox", checked: selected.has(name) });
      box.addEventListener("change", () => {
        if (box.checked) selected.add(name); else selected.delete(name);
        definition.innerHTML = definitionHtml(entry, selected);
      });
      dictChoice.append(el("label", { class: "mc-check" }, box, name));
    }

    const target = el("p", { class: "mc-target" });
    api("/api/anki/config").then(({ config }) => {
      const setup = config.notes[language];
      target.replaceChildren(setup && setup.deck && setup.model
        ? `Anki: ${setup.deck} › ${setup.model}`
        : el("span", {}, "No Anki note type set for this language yet: ",
          el("a", { href: "/settings/#anki", target: "_blank", text: "set it up" }), ". The card will wait until then."));
    }).catch(() => {});

    const field = (label, control, hint) => el("label", { class: "mc-field" }, el("span", { class: "mc-label" }, label, hint ? el("small", { text: hint }) : null), control);
    const status = el("p", { class: "mc-creator-status", role: "status" });
    const send = el("button", { type: "button", class: "mc-btn mc-primary", text: "Add to Anki" });
    const later = el("button", { type: "button", class: "mc-btn", text: "Save for later" });
    const cancel = el("button", { type: "button", class: "mc-btn", text: "Cancel" });

    const dialog = el("dialog", { class: "mc-creator", "aria-label": "Card creator" },
      el("div", { class: "mc-creator-head" }, el("h2", { text: "New card" }), target),
      el("div", { class: "mc-creator-body" },
        el("div", { class: "mc-col" },
          el("div", { class: "mc-row2" }, field("Word", word), field("Reading", reading)),
          field("Definition", definition, "editable"),
          dictChoice.childNodes.length > 1 ? dictChoice : null,
          field("Sentence", sentenceBox, "editable"),
          field("Sentence translation", translation),
          field("Notes", notes),
          el("div", { class: "mc-row2" }, field("Source", source), field("Tags", tags))),
        el("div", { class: "mc-col" },
          image.zone,
          el("p", { class: "mc-hint", text: "Tip: paste an image (Ctrl+V) or drop a file anywhere in this window." }),
          audio.zone,
          sentenceAudio.zone)),
      el("div", { class: "mc-creator-foot" }, status, cancel, later, send));
    document.body.append(dialog);
    creator = { dialog };

    dialog.addEventListener("paste", (e) => {
      const file = [...(e.clipboardData && e.clipboardData.files) || []].find((f) => f.type.startsWith("image/"));
      if (file && !e.target.closest(".mc-editable, input, textarea")) {
        e.preventDefault();
        image.set(file);
      } else if (file && e.target.closest(".mc-editable")) {
        // images pasted in the text fields go to the image slot instead
        e.preventDefault();
        image.set(file);
      }
    });
    dialog.addEventListener("dragover", (e) => e.preventDefault());
    dialog.addEventListener("drop", (e) => {
      if (e.target.closest(".mc-media")) return;
      e.preventDefault();
      const file = e.dataTransfer.files[0];
      if (!file) return;
      if (file.type.startsWith("image/")) image.set(file);
      else if (file.type.startsWith("audio/") || file.type.startsWith("video/")) (audio.state.value ? sentenceAudio : audio).set(file);
    });
    dialog.addEventListener("close", () => { dialog.remove(); if (creator && creator.dialog === dialog) creator = null; });
    cancel.addEventListener("click", () => dialog.close());

    const submit = async (sendNow) => {
      send.disabled = later.disabled = true;
      status.textContent = sendNow ? "Sending to Anki…" : "Saving…";
      const media = {};
      if (image.state.value) media.image = image.state.value;
      if (audio.state.value) media.audio = audio.state.value;
      if (sentenceAudio.state.value) media.sentence_audio = sentenceAudio.state.value;
      try {
        const { card } = await api("/api/cards", {
          language, send: sendNow, tags: tags.value, key_reading: entry.reading !== entry.expression ? entry.reading : "",
          fields: {
            word: word.value.trim(), reading: reading.value.trim(), definition: definition.innerHTML,
            sentence: sentenceBox.innerHTML, sentence_translation: translation.value, notes: notes.value, source: source.value,
          },
          media,
        });
        dialog.close();
        updateColour(card.expression, "learning");
        if (options.onStatusChange) options.onStatusChange(card.expression, "learning");
        if (card.status === "sent") toast("Added to Anki ✓", "success");
        else if (card.status === "failed") toast(`Anki refused the card: ${card.error}`, "error");
        else if (card.error && !/reachable/.test(card.error)) toast(`Saved, not sent yet: ${card.error}`, "info");
        else toast(sendNow ? "Anki isn't reachable: the card will be sent at the next sync." : "Saved: the card will be sent at the next sync.", "info");
      } catch (err) {
        status.textContent = err.message;
        send.disabled = later.disabled = false;
      }
    };
    send.addEventListener("click", () => submit(true));
    later.addEventListener("click", () => submit(false));
    dialog.showModal();
    word.focus();

    if (options.getImage && ctx && ctx.node) {
      const shot = options.getImage(ctx.node);
      if (shot) image.setValue(shot);
    }

    // A recording of the word, when an online source has one; the others can be picked instead.
    wordAudio(entry, language).then((sources) => {
      if (!sources.length || !dialog.isConnected) return;
      if (!audio.state.value) audio.setValue({ url: sources[0].url });
      if (sources.length < 2) return;
      const pick = el("select", { class: "mc-audio-source", "aria-label": "Recording" });
      sources.forEach((source, i) => pick.append(el("option", { value: String(i), text: `${i + 1}. ${source.name}` })));
      pick.addEventListener("change", () => {
        audio.setValue({ url: sources[Number(pick.value)].url });
        audio.preview.querySelector("audio")?.play().catch(() => {});
      });
      audio.zone.insertBefore(el("div", { class: "mc-media-row mc-tts" }, el("span", { class: "mc-label", text: "Recording" }), pick), audio.preview);
    }).catch(() => {});

    // A translation of the sentence, made offline in the language of the settings.
    if (sentence.text) {
      translation.placeholder = "Translating…";
      api("/api/translate", { language, text: sentenceBox.textContent }).then(({ translation: text }) => {
        if (text && !translation.value) translation.value = text;
        translation.placeholder = "Optional";
      }).catch((err) => { translation.placeholder = `Optional (no translation: ${err.message})`; });
    }

    // The sentence's audio, cut from the book's audio when there is one, else read by the settings' voice.
    const bookClip = sentence.text && options.sentenceClip && options.hasAudio && options.hasAudio()
      ? (() => {
        const wait = el("p", { class: "mc-hint", text: "Cutting the sentence's audio…" });
        sentenceAudio.preview.append(wait);
        return options.sentenceClip(sentence.text).then((clipped) => {
          wait.remove();
          if (clipped && !sentenceAudio.state.value) sentenceAudio.setValue(clipped);
          else if (!clipped) sentenceAudio.preview.append(el("p", { class: "mc-hint", text: "This sentence wasn't found in the book's audio." }));
          return clipped;
        }).catch((err) => { wait.textContent = err.message; return null; });
      })()
      : Promise.resolve(null);
    Promise.all([bookClip, tts.ready]).then(([clipped, voice]) => {
      if (!clipped && voice && sentence.text && !sentenceAudio.state.value && dialog.isConnected) tts.generate();
    });
  }

  // ------------------------------------------------------------ keyboard

  // While the popup is open: ↑ ↓ (or K J) pick a result, Enter or C makes a card, A plays the word,
  // P plays the sentence, 1-4 set the status, Esc closes.
  function selectedEntry() {
    return popup.querySelector(".mc-entry.mc-selected") || popup.querySelector(".mc-entry");
  }

  function moveSelection(step) {
    const entries = [...popup.querySelectorAll(".mc-entry")];
    if (!entries.length) return;
    const current = entries.indexOf(selectedEntry());
    const next = entries[Math.max(0, Math.min(entries.length - 1, current + step))];
    for (const e of entries) e.classList.toggle("mc-selected", e === next);
    next.scrollIntoView({ block: "nearest" });
  }

  const clickIn = (selector) => () => { const target = selectedEntry() && selectedEntry().querySelector(selector); if (target) target.click(); };
  const popupKeys = {
    Escape: hidePopup,
    ArrowDown: () => moveSelection(1), j: () => moveSelection(1),
    ArrowUp: () => moveSelection(-1), k: () => moveSelection(-1),
    Enter: clickIn(".mc-add"), c: clickIn(".mc-add"),
    a: clickIn(".mc-listen"),
    p: () => { const play = popup.querySelector(".mc-play"); if (play) play.click(); },
    1: clickIn(".mc-status-new"), 2: clickIn(".mc-status-learning"), 3: clickIn(".mc-status-known"), 4: clickIn(".mc-status-ignored"),
  };

  // ------------------------------------------------------------ wiring

  function attach(container, opts) {
    options = opts;
    ensurePopup();
    let down = null;
    container.addEventListener("pointerdown", (e) => { down = { x: e.clientX, y: e.clientY }; });
    container.addEventListener("click", (e) => {
      if (options.getMode() !== "click" || e.button !== 0) return;
      if (e.target.closest("a")) return;
      if (down && Math.hypot(e.clientX - down.x, e.clientY - down.y) > 4) return;  // a drag selects text
      const selection = window.getSelection();
      if (selection && String(selection).length > 0) return;
      const scan = scanAt(e.clientX, e.clientY, container);
      if (!scan) { hidePopup(); return; }
      e.stopPropagation();
      lookupScan(scan, { left: e.clientX, right: e.clientX, top: e.clientY, bottom: e.clientY });
    });
    container.addEventListener("mousemove", (e) => {
      if (options.getMode() !== "shift" || !e.shiftKey) return;
      clearTimeout(hoverTimer);
      const { clientX: x, clientY: y } = e;
      hoverTimer = setTimeout(() => {
        const scan = scanAt(x, y, container);
        if (scan) lookupScan(scan, { left: x, right: x, top: y, bottom: y });
      }, 60);
    });
    document.addEventListener("mousedown", (e) => {
      if (popup && !popup.hidden && !popup.contains(e.target) && !container.contains(e.target)) hidePopup();
    });
    document.addEventListener("keydown", (e) => {
      if (!popup || popup.hidden || e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.target.closest && e.target.closest("input, select, textarea, [contenteditable], dialog")) return;
      const action = popupKeys[e.key];
      if (!action) return;
      e.stopImmediatePropagation();
      e.preventDefault();
      action();
    }, true);
  }

  window.MiningCatMining = {
    attach, hide: hidePopup, isOpen: () => Boolean(popup && !popup.hidden), renderGlossary, api,
    colourWords, clearColours, updateColour,
  };
})();
