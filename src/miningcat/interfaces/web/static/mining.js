// MiningCat dictionary popup and card creator.
//
// MiningCatMining.attach(container, {getLanguage, getSource, getMode}) makes the text of `container`
// searchable: a click (or Shift + hover) on a word looks it up in the imported dictionaries and shows
// a popup with the definitions, the word's status and a "+ Card" button that opens the card creator.
// Optional: hasAudio(), sentenceAudio(text, node) -> {url, start, end} and sentenceClip(text, node) -> {data, name}
// when the text has audio (a book converted by MiningCat): the popup can then play the sentence, and
// the card creator gets the sentence's audio. With sentenceRange(text, node) -> {start, end, before, after} and
// audioSpan(start, end, format) -> {data, name} too (a video), the card creator shows the sentence's waveform
// to choose the span of its audio. playSentence(text, node) plays it instead of the popup's own player
// (e.g. in the video). getImage(node) -> {data, name} (or a promise of it): an image for the card, from
// the text node that was looked up (e.g. the screenshot of a video game capture). blockSentence: the sentence
// is the whole block that was clicked (a subtitle), not the sentence around the word. onLookup(): a word was
// looked up. Elements marked data-mc-ignore aren't looked up (e.g. a translation under a subtitle).
// expandSentence(node, sentence) -> sentence: the sentence of a lookup made longer (e.g. the subtitle lines selected
// around the clicked one), {text, before, word, after}. onCard(card): a card was made.
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

  // A Bootstrap icon, and an icon before a button's text.
  const icon = (name) => el("i", { class: `bi bi-${name}`, "aria-hidden": "true" });
  const withIcon = (name, text) => [icon(name), ` ${text}`];

  // kind: "info", "success" or "error" (ui.js)
  const toast = (message, kind = "info") => MiningCatUI.toast(message, kind);

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
    if (options.blockSentence) {
      const before = text.slice(0, start), word = text.slice(start, start + length), after = text.slice(start + length);
      return { text: text.trim(), before: before.replace(/^\s+/, ""), word, after: after.trimEnd() };
    }
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
    if (caret.node.parentElement.closest("rt, rp, a[data-chapter], [data-mc-ignore]")) return null;
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
  // One set per coloured area (a reader chapter; the subtitle over a video and the subtitle list...), by key:
  // key -> {language, words: [{headword, form, status}], tokens: [{index, start, end, range}], sentences: [[start, end]],
  //         seg, paint}
  const colourSets = new Map();
  const analysisListeners = [];  // fn(key): the words of a set, or their statuses, changed (see analyse())
  const colourTokens = new Map();  // key -> number of the latest request

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
    if (!window.CSS || !CSS.highlights || !window.Highlight) return;
    const groups = Object.fromEntries(COLOUR_HIGHLIGHTS.map((name) => [name, []]));
    for (const colours of colourSets.values()) {
      if (!colours.paint) continue;
      let previous = null;  // {status, end, alt} of the last coloured word
      for (const token of colours.tokens) {
        const status = colours.words[token.index].status;
        if (!COLOURED.includes(status)) { previous = null; continue; }
        const alt = Boolean(previous && previous.status === status && previous.end === token.start && !previous.alt);
        groups[`mc-${status}${alt ? "-alt" : ""}`].push(token.range);
        previous = { status, end: token.end, alt };
      }
    }
    for (const name of COLOUR_HIGHLIGHTS) CSS.highlights.set(name, new Highlight(...groups[name]));
  }

  // Without a key: removes every set.
  function clearColours(key) {
    const keys = key === undefined ? [...new Set([...colourSets.keys(), ...colourTokens.keys()])] : [key];
    for (const k of keys) {
      colourTokens.set(k, (colourTokens.get(k) || 0) + 1);
      colourSets.delete(k);
    }
    paintColours();
    for (const k of keys) notifyAnalysis(k);
  }

  function notifyAnalysis(key) {
    for (const fn of analysisListeners) {
      try { fn(key); } catch (err) { console.error(err); }
    }
  }

  // Colours the words of `root` (e.g. a reader chapter) by status. Words missing from the dictionaries stay as they are.
  // Areas coloured under different keys keep their colours side by side. paint: false only reads the words (for
  // analyse()) when the user turned the colours off.
  async function colourWords(root, language, key = "main", { paint = true } = {}) {
    clearColours(key);
    if (!window.CSS || !CSS.highlights || !window.Highlight) return;
    const token = colourTokens.get(key);
    const seg = segmentText(root);
    if (!seg.text.trim()) return;
    let data;
    try {
      data = await api("/api/words/segment", { language, text: seg.text });
    } catch {
      return;  // e.g. no dictionary language: the text simply stays uncoloured
    }
    if (token !== colourTokens.get(key)) return;
    const tokens = [];
    for (const [start, length, index] of data.tokens) {
      if (index < 0) continue;
      const a = nodeAt(seg, start), b = nodeAt(seg, start + length);
      const range = document.createRange();
      range.setStart(a.node, a.at);
      range.setEnd(b.node, b.at);
      tokens.push({ index, start, end: start + length, range });
    }
    colourSets.set(key, { language: data.language, words: data.words, tokens, sentences: data.sentences || [], seg, paint,
      frequency: data.frequency || null });
    paintColours();
    notifyAnalysis(key);
  }

  // ------------------------------------------------------------ comprehension (same rule as application/mining/comprehension.py)

  // Comprehension of a coloured area, from the statuses of its words (the user's cards): {known, learning, new, total,
  // percent, units: [{start, end, range, element, target, recommended}]}. Units are the sentences of the text, or with
  // `unitOf(textNode) -> element`, the elements holding the words (a subtitle line). A unit is recommended (i+1) when
  // exactly one of its words isn't known and that word is new: `target` is that word ({headword, form, status}),
  // `targetRange` where it first is in the unit. With a frequency list, only the units whose new word ranks within its
  // limit are recommended (`i1` is set for every unit with one new word): `frequency` is {dictionary, known, limit}.
  function analyse(key, unitOf) {
    const colours = colourSets.get(key);
    if (!colours) return null;
    const totals = { known: 0, learning: 0, new: 0 };
    const units = [];
    if (unitOf) {
      const byElement = new Map();
      for (const token of colours.tokens) {
        const element = unitOf(token.range.startContainer);
        if (!element) continue;
        if (!byElement.has(element)) {
          const unit = { element, tokens: [] };
          byElement.set(element, unit);
          units.push(unit);
        }
        byElement.get(element).tokens.push(token);
      }
    } else {
      let k = 0;
      for (const [start, end] of colours.sentences) {
        const unit = { start, end, tokens: [] };
        while (k < colours.tokens.length && colours.tokens[k].start < end) {
          if (colours.tokens[k].start >= start) unit.tokens.push(colours.tokens[k]);
          k++;
        }
        if (!unit.tokens.length) continue;
        const a = nodeAt(colours.seg, start), b = nodeAt(colours.seg, end);
        unit.range = document.createRange();
        unit.range.setStart(a.node, a.at);
        unit.range.setEnd(b.node, b.at);
        units.push(unit);
      }
    }
    for (const token of colours.tokens) {
      const status = colours.words[token.index].status;
      if (status in totals) totals[status]++;
    }
    for (const unit of units) {
      const missing = new Map();
      for (const token of unit.tokens) {
        const word = colours.words[token.index];
        if ((word.status === "new" || word.status === "learning") && !missing.has(word.form)) missing.set(word.form, { word, token });
      }
      const only = missing.size === 1 ? [...missing.values()][0].word : null;
      unit.target = only;
      unit.targetRange = only ? [...missing.values()][0].token.range : null;
      unit.i1 = Boolean(only && only.status === "new");
      const limit = colours.frequency ? colours.frequency.limit : null;
      unit.recommended = unit.i1 && (limit === null || (only.rank !== null && only.rank !== undefined && only.rank <= limit));
      delete unit.tokens;
    }
    const total = totals.known + totals.learning + totals.new;
    return { ...totals, total, percent: total ? (100 * totals.known) / total : null, units, language: colours.language,
      frequency: colours.frequency || null };
  }

  function onAnalysis(fn) { analysisListeners.push(fn); }

  // A status changed in the popup or through a new card: recolour that word everywhere in the text.
  function updateColour(form, status) {
    const changed = [];
    for (const [key, colours] of colourSets) {
      for (const word of colours.words) {
        if (word.form === form && word.status !== status) {
          word.status = status;
          if (!changed.includes(key)) changed.push(key);
        }
      }
    }
    if (changed.length) paintColours();
    for (const key of changed) notifyAnalysis(key);
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

  // A sense's text, its 【word】 references clickable like the cross references of structured content.
  function senseText(text) {
    const out = el("span", { class: "mc-sense-text" });
    for (const part of text.split(/(【[^】]+】)/)) {
      if (/^【[^】]+】$/.test(part)) out.append(el("a", { href: "#", "data-query": part.slice(1, -1), text: part }));
      else if (part) out.append(part);
    }
    return out;
  }

  // Examples one per line, short ones without a translation (兩岸詞典's 美好│完好) together on one line.
  function examplesList(examples) {
    const list = el("ul", { class: "mc-examples" });
    let run = null;
    for (const x of examples) {
      if (!x.translation && x.text.length <= 12) {
        if (run) run.append(" · ");
        else { run = el("li", { class: "mc-inline" }); list.append(run); }
        run.append(el("span", { class: "mc-example", text: x.text }));
        continue;
      }
      run = null;
      list.append(el("li", {}, el("span", { class: "mc-example", text: x.text }),
        x.translation ? el("span", { class: "mc-example-tr", text: x.translation }) : null));
    }
    return list;
  }

  // The definitions of an entry in three blocks, whatever their dictionary: translations (definitions in another
  // language), definitions in the word's language (monolingual dictionaries) and examples. A block is a list of senses
  // {tags, text | sc | items, dictId, subs} and of {reading} (the senses after it are of that pronunciation).
  const BLOCKS = [["translations", "Translations"], ["monolingual", "Definitions"], ["examples", "Examples"]];
  const MONOLINGUAL = { zh: "Chinese definitions", yue: "Cantonese definitions", ja: "Japanese definitions", ko: "Korean definitions" };
  const SCRIPTS = { zh: /[\u3400-\u9fff\uf900-\ufaff]/gu, yue: /[\u3400-\u9fff\uf900-\ufaff]/gu,
    ja: /[\u3040-\u30ff\u3400-\u9fff]/gu, ko: /[\uac00-\ud7af]/gu };

  // Whether a definition is written in the word's language: more of its script than Latin letters.
  function isMonolingual(text, language) {
    const script = SCRIPTS[language];
    if (!script) return false;
    return (text.match(script) || []).length > (text.match(/[A-Za-z\u00c0-\u024f]/g) || []).length;
  }

  function scText(node) {
    if (node === null || node === undefined) return "";
    if (typeof node === "string" || typeof node === "number") return String(node);
    if (Array.isArray(node)) return node.map(scText).join("");
    return typeof node === "object" ? scText(node.content) : "";
  }

  function glossText(item) {
    if (typeof item === "string") return item;
    if (item && item.type === "text") return item.text || "";
    if (item && item.type === "structured-content") return scText(item.content);
    return "";
  }

  // The items of structured content that is only a list (CC-CEDICT's), so they can join the other senses; else null.
  function scListItems(node) {
    if (Array.isArray(node)) {
      const parts = node.filter((n) => !(typeof n === "string" && !n.trim()));
      return parts.length === 1 ? scListItems(parts[0]) : null;
    }
    if (!node || typeof node !== "object") return null;
    if (node.tag === "ul" || node.tag === "ol") {
      const items = Array.isArray(node.content) ? node.content : [node.content];
      return items.every((li) => li && li.tag === "li") ? items.map((li) => li.content) : null;
    }
    return (!node.tag || node.tag === "div") && node.content !== undefined ? scListItems(node.content) : null;
  }

  function senseAllText(sense) {
    return [sense.text || "", ...(sense.subs || []).map(senseAllText)].join(" ");
  }

  function definitionBlocks(entry, language) {
    const blocks = { translations: [], monolingual: [], examples: [] };
    const add = (piece, text) => blocks[isMonolingual(text, language) ? "monolingual" : "translations"].push(piece);
    const stripExamples = (sense) => {
      blocks.examples.push(...sense.examples);
      return { ...sense, examples: [], subs: sense.subs.map(stripExamples) };
    };
    for (const d of entry.definitions) {
      const tags = [...new Set([...d.tags, ...d.term_tags])].filter((t) => !/^\d+$/.test(t))
        .map((t) => ({ name: t, title: (d.tag_info[t] && d.tag_info[t].notes) || undefined }));
      const rest = [];
      for (const item of d.glossary) {
        if (item && item.type === "senses") {
          let reading = null;
          for (const sense of item.senses) {
            if (sense.reading) { reading = sense.reading; continue; }
            const piece = { ...stripExamples(sense), tags: sense.tags.map((t) => ({ name: t })), dictId: d.dict_id };
            const text = senseAllText(sense);
            if (reading) { add({ reading }, text); reading = null; }
            add(piece, text);
          }
          blocks.examples.push(...item.examples);
        } else if (item && item.type === "structured-content" && scListItems(item.content)) {
          for (const node of scListItems(item.content)) add({ sc: node, dictId: d.dict_id, tags, subs: [] }, scText(node));
        } else {
          rest.push(item);
        }
      }
      if (rest.length) add({ items: rest, dictId: d.dict_id, tags, subs: [] }, rest.map(glossText).join(" "));
    }
    return blocks;
  }

  function senseNode(sense) {
    let content = null;
    if (sense.text) content = senseText(sense.text);
    else if (sense.sc !== undefined) content = renderSC(sense.sc, sense.dictId);
    else if (sense.items) content = renderGlossary(sense.items, sense.dictId);
    return el("li", {},
      ...sense.tags.flatMap((t) => [el("span", { class: TAG, text: t.name, title: t.title }), " "]),
      content,
      sense.examples && sense.examples.length ? examplesList(sense.examples) : null,
      sense.subs.length ? el("ol", { class: "mc-subsenses" }, ...sense.subs.map(senseNode)) : null);
  }

  // Numbered senses, each pronunciation's in its own list.
  function senseList(senses) {
    const box = el("div", { class: "mc-sense-block" });
    let list = null;
    for (const sense of senses) {
      if (sense.reading) { box.append(el("div", { class: "mc-sense-reading", text: sense.reading })); list = null; continue; }
      if (!list) { list = el("ol", { class: "mc-numbered" }); box.append(list); }
      list.append(senseNode(sense));
    }
    for (const ol of box.querySelectorAll("ol.mc-numbered")) if (ol.children.length === 1) ol.classList.add("mc-one");
    return box;
  }

  function blockNode(key, items) {
    return key === "examples" ? examplesList(items) : senseList(items);
  }

  // A definition split into senses by the server (glossary.py), shown on its own (outside the blocks of an entry).
  function renderSenses(item) {
    const box = senseList(item.senses.map((s) => s.reading ? s : { ...s, subs: s.subs || [], tags: s.tags.map((t) => ({ name: t })) }));
    if (item.examples.length) box.append(examplesList(item.examples));
    return box;
  }

  function renderGlossary(glossary, dictId) {
    const list = el("ul", { class: glossary.length > 1 ? "mc-gloss" : "mc-gloss mc-single" });
    for (const item of glossary) {
      let content;
      if (typeof item === "string") content = document.createTextNode(item);
      else if (item && item.type === "senses") content = renderSenses(item);
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

  async function playSentence(text, node, button) {
    if (button) button.disabled = true;
    try {
      if (options.playSentence) { await options.playSentence(text, node); return; }
      const span = await options.sentenceAudio(text, node);
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

  // A sentence's translation, made once. `prefetch`: ahead of time, at the lookup (never downloads a model); the card
  // creator asks again when that failed.
  const translationCache = new Map();
  function translateSentence(language, text, prefetch = false) {
    const key = `${language}|${text}`;
    if (!translationCache.has(key)) {
      if (translationCache.size >= 20) translationCache.delete(translationCache.keys().next().value);
      const result = api("/api/translate", { language, text, prefetch }).then((d) => d.translation);
      result.catch(() => translationCache.delete(key));
      translationCache.set(key, result);
    }
    return translationCache.get(key);
  }

  // What the card creator would wait for, asked while the popup is read: the card is complete when it opens.
  function prefetchCard(language, entries, sentence, node) {
    if (entries.length) wordAudio(entries[0], language).catch(() => {});
    const text = `${sentence.before}${sentence.word}${sentence.after}`;
    if (sentence.text && text.trim()) translateSentence(language, text, true).catch(() => {});
    prefetchWave(sentence, node);
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
    popup = el("div", { class: "mc-popup bg-body border rounded-3 shadow-lg p-3", id: "mc-popup", role: "dialog", "aria-label": "Dictionary", hidden: true });
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

  const STATUS_COLOURS = { new: "secondary", learning: "warning", known: "success", ignored: "secondary" };

  function statusControl(entry, language) {
    const group = el("div", { class: "btn-group btn-group-sm d-flex my-2", role: "radiogroup", "aria-label": "Word status" });
    const render = () => {
      for (const b of group.children) {
        b.setAttribute("aria-checked", String(b.dataset.value === entry.status.status));
        b.classList.toggle("active", b.dataset.value === entry.status.status);
      }
    };
    for (const [value, text] of STATUSES) {
      group.append(el("button", {
        type: "button", role: "radio", "data-value": value, class: `btn btn-outline-${STATUS_COLOURS[value]} mc-status-${value}`, text,
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
    const word = el("span", { class: "mc-word fs-3 fw-semibold lh-sm", lang: displayLang(language) });
    if (language === "ja" && entry.reading && entry.reading !== entry.expression) {
      word.append(el("ruby", {}, entry.expression, el("rt", { text: entry.reading })));
    } else {
      word.append(entry.expression);
    }
    const parts = [word];
    if (language !== "ja" && entry.reading && entry.reading !== entry.expression) parts.push(el("span", { class: "fs-6 text-body-secondary", text: entry.display_reading || entry.reading }));
    return el("div", { class: "d-flex flex-wrap align-items-baseline column-gap-2" }, ...parts);
  }

  // "#1,234" for a word's rank in the frequency list, highlighted when it's frequent enough to be recommended now.
  function frequencyText(entry) {
    const list = entry.frequency_list;
    if (!list) return null;
    if (!entry.frequency_rank) return { text: "Not in your frequency list", frequent: false, title: `Not in “${list.dictionary.title}”: a rare word` };
    const frequent = entry.frequency_rank <= list.limit;
    return {
      text: `#${entry.frequency_rank.toLocaleString()}`, frequent,
      title: `Rank in “${list.dictionary.title}” (1 = most frequent). You know ${list.known.toLocaleString()} of its words: `
        + `sentences are recommended for words up to #${list.limit.toLocaleString()}`
        + (frequent ? ", like this one." : ", this one is further down the list."),
    };
  }

  const CHIP = "badge rounded-pill fw-normal";
  const TAG = "badge bg-body-tertiary text-body-secondary border fw-normal";

  function frequencyChip(entry) {
    const f = frequencyText(entry);
    if (!f) return null;
    return f.frequent
      ? el("span", { class: `${CHIP} bg-success-subtle text-success-emphasis fw-semibold`, title: f.title }, ...withIcon("star-fill", f.text))
      : el("span", { class: `${CHIP} bg-body-secondary text-body`, title: f.title, text: f.text });
  }

  function renderEntries(data, language) {
    const box = ensurePopup();
    box.replaceChildren();
    const close = el("button", { type: "button", class: "btn-close float-end position-sticky top-0 ms-2", "aria-label": "Close", onclick: hidePopup });
    if (!data.dictionaries) {
      box.append(close, el("p", { class: "text-body-secondary my-1" },
        "No dictionary for this language yet. ",
        el("a", { href: "/settings/#dictionaries", target: "_blank", text: "Import one in Settings" }), "."));
      return;
    }
    if (!data.entries.length) {
      box.append(close, el("p", { class: "text-body-secondary my-1", text: "No results." }));
      return;
    }
    box.append(close);
    const sentence = current && current.sentence && current.sentence.text;
    if (sentence && (options.sentenceAudio || options.playSentence) && options.hasAudio && options.hasAudio()) {
      const play = el("button", { type: "button", class: "btn btn-sm btn-outline-primary mb-2 mc-play", title: "Play the sentence" }, ...withIcon("play-fill", "Sentence"));
      const node = current.node;
      play.addEventListener("click", () => playSentence(sentence, node, play));
      box.append(play);
    }
    for (const [i, entry] of data.entries.entries()) {
      const meta = el("div", { class: "d-flex flex-wrap align-items-center gap-1 my-1 small" });
      if (entry.inflections.length) {
        meta.append(el("span", { class: "text-body-secondary", title: entry.inflections.map((i) => `${i.name}: ${i.description || ""}`).join("\n") },
          `« ${entry.inflections.map((i) => i.name).join(" « ")}`));
      }
      // The rank in the language's frequency list first (see frequency.py), then the other frequency dictionaries.
      entry.frequency_list = data.frequency || null;
      const chip = frequencyChip(entry);
      if (chip) meta.append(chip);
      const others = entry.frequencies.filter((f) => !data.frequency || f.dictionary !== data.frequency.dictionary.title);
      for (const f of others.slice(0, 3)) meta.append(el("span", { class: `${CHIP} bg-body-secondary text-body`, title: f.dictionary, text: `${f.dictionary.split(/[\s[(]/)[0]} ${f.display}` }));
      if (others.length > 3) {
        const rest = others.slice(3);
        meta.append(el("span", { class: `${CHIP} bg-body-secondary text-body`, title: rest.map((f) => `${f.dictionary}: ${f.display}`).join("\n"), text: `+${rest.length}` }));
      }
      for (const p of entry.pronunciations || []) meta.append(pronunciation(p, entry, language));

      const notes = [];
      if (entry.form !== entry.expression) notes.push(el("p", { class: "small text-body-secondary my-1" }, "Saved as ", el("strong", { lang: displayLang(language), text: entry.form }), " (the script you learn)."));
      if (entry.status.linked) {
        const s = entry.status.linked;
        notes.push(el("p", { class: "small bg-body-tertiary rounded px-2 py-1 my-1" },
          `You ${s.status === "known" ? "know" : "are learning"} this word in ${s.script === "traditional" ? "Traditional" : "Simplified"}: `,
          el("strong", { lang: displayLang(language), text: s.expression })));
      }

      const defs = el("div", { class: "vstack gap-2 mt-1" });
      const blocks = definitionBlocks(entry, language);
      for (const [key] of BLOCKS) if (blocks[key].length) defs.append(el("section", { class: "border-start border-2 ps-2" }, blockNode(key, blocks[key])));

      const chars = characterSection(entry, language);
      const add = el("button", { type: "button", class: "btn btn-sm btn-primary flex-shrink-0 mc-add", onclick: () => openCreator(entry, language) }, ...withIcon("plus-lg", "Card"));
      const listen = el("button", { type: "button", class: "btn btn-sm btn-link link-body-emphasis ms-auto mc-listen", title: "Play the word (online recordings)", "aria-label": "Play the word" }, icon("volume-up"));
      listen.addEventListener("click", () => playWord(entry, language, listen));
      box.append(el("article", { class: `mc-entry${i ? " border-top pt-3 mt-3" : ""}` },
        el("div", { class: "d-flex align-items-start gap-2" }, headword(entry, language), listen, add),
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
    const box = el("details", { class: "mt-2 small" }, el("summary", { class: "text-body-secondary", text: `Characters (${entry.characters.map((c) => c.character).join("")})` }));
    for (const { character, entries } of entry.characters) {
      const body = el("div", { class: "flex-grow-1" });
      for (const [i, k] of entries.entries()) {
        const readings = [k.onyomi.join("、"), k.kunyomi.join("、")].filter(Boolean).join(" · ");
        const stats = [k.stats.strokes && `${k.stats.strokes} strokes`, k.stats.grade && `grade ${k.stats.grade}`,
          k.stats.jlpt && `JLPT N${k.stats.jlpt}`, k.stats.freq && `#${k.stats.freq}`, ...k.frequencies].filter(Boolean);
        body.append(el("div", { class: i ? "border-top pt-1 mt-1" : null },
          readings ? el("div", { class: "fw-semibold", lang, text: readings }) : null,
          el("div", { text: k.meanings.join("; ") }),
          stats.length ? el("div", { class: "opacity-75", text: stats.join(" · ") }) : null));
      }
      box.append(el("div", { class: "d-flex align-items-start gap-2 mt-2" }, el("span", { class: "fs-2 lh-1", lang, text: character }), body));
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
    if (typeof position !== "number") return el("span", { class: "text-nowrap", text: `${reading} ${position}` });
    const box = el("span", { class: "text-nowrap", title: `Pitch accent [${position}]`, lang: "ja" });
    morae(reading).forEach((mora, i) => {
      const n = i + 1;
      const high = position === 0 ? n > 1 : position === 1 ? n === 1 : n > 1 && n <= position;
      box.append(el("span", { class: high ? "mc-high" : "mc-low", text: mora }));
      if (n === position) box.append(el("span", { class: "text-primary-emphasis", text: "ꜜ" }));
    });
    box.append(el("span", { class: "opacity-75 ms-1", text: `[${position}]` }));
    return box;
  }

  function pronunciation(p, entry, language) {
    const reading = p.reading || (entry.reading !== entry.expression ? entry.reading : entry.expression);
    const wrap = el("span", { class: "d-inline-flex align-items-baseline gap-2", title: p.dictionary });
    if (p.pitches) for (const position of p.pitches) wrap.append(pitchGraph(reading, position));
    if (p.ipa) for (const ipa of p.ipa) wrap.append(el("span", { class: "opacity-75", text: ipa }));
    return wrap;
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
    if (options.expandSentence) current.sentence = options.expandSentence(current.node, current.sentence);
    renderEntries(data, data.language);
    placePopup(rect);
    popup.scrollTop = 0;
    if (options.onLookup) options.onLookup();
    prefetchCard(data.language, data.entries, current.sentence, current.node);
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

  function definitionHtml(blocks, selected) {
    const box = document.createElement("div");
    for (const [key] of BLOCKS) if (selected.has(key) && blocks[key].length) box.append(blockNode(key, blocks[key]));
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

  // A field's label in the card creator, and a drop zone while files are dragged over it.
  const LABEL = "small fw-semibold text-body-secondary";
  const DRAG_OVER = ["border-primary", "bg-primary-subtle"];

  function mediaSlot(kind, label, accept) {
    const state = { value: null };
    const preview = el("div", { class: "mc-media-preview d-flex flex-column gap-2 align-items-start" });
    const input = el("input", { type: "file", accept, hidden: true });
    const url = el("input", { type: "url", placeholder: "or paste a link (https://…)", class: "form-control form-control-sm", "aria-label": `${label}: link` });
    const render = () => {
      preview.replaceChildren();
      if (!state.value) return;
      const src = state.value.data || state.value.url;
      preview.append(state.value.wave ? el("span", { class: "form-text m-0", text: "The span chosen on the waveform." })
        : kind === "image" ? el("img", { src, alt: "", class: "img-fluid rounded" }) : el("audio", { src, controls: true, class: "w-100" }),
        el("button", { type: "button", class: "btn btn-sm btn-link link-danger p-0", onclick: () => { state.value = null; url.value = ""; render(); } }, ...withIcon("x-lg", "Remove")));
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
    const zone = el("div", { class: "mc-media border border-2 rounded p-2 d-flex flex-column gap-2", "data-kind": kind },
      el("div", { class: "d-flex align-items-center justify-content-between gap-2" },
        el("span", { class: LABEL, text: label }),
        el("button", { type: "button", class: "btn btn-sm btn-outline-secondary", onclick: () => input.click() }, ...withIcon("folder2-open", "Choose a file…")),
        input),
      url, preview);
    zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add(...DRAG_OVER); });
    zone.addEventListener("dragleave", () => zone.classList.remove(...DRAG_OVER));
    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      zone.classList.remove(...DRAG_OVER);
      const file = e.dataTransfer.files[0];
      if (file) set(file);
      else {
        const link = e.dataTransfer.getData("text/uri-list") || e.dataTransfer.getData("text/plain");
        if (/^https?:\/\//.test(link)) { url.value = link.trim(); url.dispatchEvent(new Event("change")); }
      }
    });
    return { zone, state, set, setValue, preview };
  }

  // A voice reading the card's sentence (Edge-TTS), for sentences without audio (and words without a recording).
  // The voice set in the settings is picked first; ready resolves to it ("" when sentences aren't read automatically).
  function ttsRow(language, getText, slot) {
    const select = el("select", { class: "form-select form-select-sm", "aria-label": "Voice", disabled: true });
    const button = el("button", { type: "button", class: "btn btn-sm btn-outline-secondary text-nowrap", text: "Generate", disabled: true });
    const row = el("div", { class: "d-flex align-items-center gap-2" }, el("span", { class: `${LABEL} text-nowrap`, text: "Read by" }), select, button);
    let available = false;
    const ready = api(`/api/tts/voices?language=${encodeURIComponent(language)}`).then(({ voices, default: fallback, chosen }) => {
      if (!voices.length) { row.hidden = true; return ""; }
      available = true;
      for (const v of voices) select.append(el("option", { value: v.id, text: v.label }));
      select.value = chosen || fallback;
      select.disabled = button.disabled = false;
      return chosen;
    }).catch(() => { row.hidden = true; return ""; });
    const generate = async () => {
      const text = getText().trim();
      if (!text) return toast("There's nothing to read.", "info");
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
    return { row, ready, generate, available: () => available };
  }

  // The span of the sentence's audio, chosen on its waveform (a video): the lines with the settings' margins to begin
  // with, and some context around them. Drag an edge (or a new span), or move a focused edge with ← →; the moved edge
  // is played. A click plays from there. range: {start, end, before, after} (s). The card's audio is cut from the
  // chosen span only when the card is made (the slot holds {wave: true} until then).
  const WAVE_CONTEXT_S = 2.5;
  const WAVE_MAX_S = 170;
  const WAVE_MIN_SPAN_S = 0.1;
  const WAVE_EDGE_PLAY_S = 1.2;
  const WAVE_GRAB_PX = 10;

  function waveSpans(range) {
    const initial = { start: Math.max(0, range.start - range.before), end: range.end + range.after };
    return { initial, win: { start: Math.max(0, initial.start - WAVE_CONTEXT_S), end: initial.end + WAVE_CONTEXT_S } };
  }

  // The audio of a span, fetched once: from the lookup on, so that it's ready when the card creator opens.
  // {blob} plays it, {buffer} (decoded) draws it.
  const waveCache = new Map();
  function waveAudio(start, end) {
    const key = `${start.toFixed(3)}-${end.toFixed(3)}`;
    if (!waveCache.has(key)) {
      if (waveCache.size >= 6) waveCache.delete(waveCache.keys().next().value);
      const decoded = options.audioSpan(start, end, "wav")
        .then((wav) => fetch(wav.data)).then((res) => res.blob())
        .then(async (blob) => ({ blob, buffer: await new OfflineAudioContext(1, 1, 16000).decodeAudioData(await blob.arrayBuffer()) }));
      decoded.catch(() => waveCache.delete(key));
      waveCache.set(key, decoded);
    }
    return waveCache.get(key);
  }

  function hasWave() {
    return Boolean(options.sentenceRange && options.audioSpan && options.hasAudio && options.hasAudio() && window.OfflineAudioContext);
  }

  function prefetchWave(sentence, node) {
    if (!sentence.text || !node || !hasWave()) return;
    const range = options.sentenceRange(sentence.text, node);
    if (!range) return;
    const { win } = waveSpans(range);
    waveAudio(win.start, win.end).catch(() => {});
  }

  function waveEditor(range, slot) {
    const { initial, win } = waveSpans(range);
    const sel = { ...initial };
    let buffer = null, layers = null, colors = null, playing = null, keyTimer = null, frame = 0;
    // Played by an <audio>, as the video is: Safari's Web Audio takes seconds to start.
    let media = null;

    const canvas = el("canvas", { class: "mc-wave-canvas", "aria-hidden": "true" });
    const handle = (label) => el("div", { class: "mc-wave-handle", role: "slider", tabindex: "0", "aria-label": label });
    const startHandle = handle("Start of the sentence's audio");
    const endHandle = handle("End of the sentence's audio");
    const box = el("div", { class: "mc-wave-box loading", title: "Drag the edges, or drag a new span. A click plays from there." },
      canvas, startHandle, endHandle);
    const message = el("p", { class: "form-text m-0", text: "Loading the waveform…" });
    const play = el("button", { type: "button", class: "btn btn-sm btn-outline-secondary", disabled: true }, ...withIcon("play-fill", "Play"));
    const info = el("span", { class: "small text-body-secondary flex-grow-1 font-monospace" });
    const reset = el("button", { type: "button", class: "btn btn-sm btn-outline-secondary", text: "Reset", disabled: true, title: "The subtitles' span with the settings' margins" });
    const wider = el("button", { type: "button", class: "btn btn-sm btn-outline-secondary", text: "More context", disabled: true, title: `${WAVE_CONTEXT_S} s more on each side` });
    const root = el("div", { class: "d-flex flex-column gap-2" }, box, message, el("div", { class: "d-flex flex-wrap align-items-center gap-2" }, play, info, reset, wider));

    const duration = () => (buffer ? buffer.duration : win.end - win.start);
    const share = (t) => (t - win.start) / duration();
    const timeAt = (clientX, rect) => win.start + Math.min(1, Math.max(0, (clientX - rect.left) / rect.width)) * duration();
    const clock = (t) => `${Math.floor(t / 60)}:${(t % 60).toFixed(2).padStart(5, "0")}`;

    // The waveform drawn once in each colour (on resize); a frame only copies them, the chosen span from the bright one.
    function paintLayers() {
      const { width, height } = canvas;
      layers = null;
      if (!buffer || !width) return;
      const css = getComputedStyle(box);
      colors = {
        accent: css.getPropertyValue("--bs-primary").trim() || "#ff8c42",
        dim: css.getPropertyValue("--bs-secondary-color").trim() || "#888",
        fg: css.getPropertyValue("--bs-body-color").trim() || "#000",
      };
      const data = buffer.getChannelData(0);
      const peaks = new Float32Array(width);
      let top = 0;
      for (let x = 0; x < width; x++) {
        const from = Math.floor((x * data.length) / width), to = Math.floor(((x + 1) * data.length) / width);
        let peak = 0;
        for (let i = from; i < to; i++) { const v = data[i] < 0 ? -data[i] : data[i]; if (v > peak) peak = v; }
        peaks[x] = peak;
        if (peak > top) top = peak;
      }
      const scale = top > 0 ? (height / 2 - 2) / top : 0;  // quiet audio fills the height too
      layers = {};
      for (const name of ["dim", "accent"]) {
        const layer = document.createElement("canvas");
        layer.width = width;
        layer.height = height;
        const g = layer.getContext("2d");
        g.fillStyle = colors[name];
        g.beginPath();
        for (let x = 0; x < width; x++) {
          const h = Math.max(0.5, peaks[x] * scale);
          g.rect(x, height / 2 - h, 1, h * 2);
        }
        g.fill();
        layers[name] = layer;
      }
    }

    function draw(head = null) {
      const g = canvas.getContext("2d");
      const { width, height } = canvas;
      g.clearRect(0, 0, width, height);
      if (layers) {
        const x0 = share(sel.start) * width, x1 = share(sel.end) * width;
        g.globalAlpha = 0.14;
        g.fillStyle = colors.accent;
        g.fillRect(x0, 0, x1 - x0, height);
        g.globalAlpha = 1;
        g.drawImage(layers.dim, 0, 0);
        g.save();
        g.beginPath();
        g.rect(x0, 0, x1 - x0, height);
        g.clip();
        g.drawImage(layers.accent, 0, 0);
        g.restore();
        // the subtitles' own span
        g.strokeStyle = colors.dim;
        g.lineWidth = devicePixelRatio;
        g.setLineDash([3 * devicePixelRatio, 3 * devicePixelRatio]);
        g.beginPath();
        for (const t of [range.start, range.end]) {
          const x = Math.round(share(t) * width) + 0.5;
          g.moveTo(x, 0);
          g.lineTo(x, height);
        }
        g.stroke();
        g.setLineDash([]);
        if (head !== null) {
          g.strokeStyle = colors.fg;
          g.beginPath();
          g.moveTo(share(head) * width, 0);
          g.lineTo(share(head) * width, height);
          g.stroke();
        }
      }
      startHandle.style.left = `${share(sel.start) * 100}%`;
      endHandle.style.left = `${share(sel.end) * 100}%`;
      for (const [h, t] of [[startHandle, sel.start], [endHandle, sel.end]]) {
        h.setAttribute("aria-valuenow", t.toFixed(2));
        h.setAttribute("aria-valuetext", clock(t));
      }
      info.textContent = `${clock(sel.start)} – ${clock(sel.end)} · ${(sel.end - sel.start).toFixed(1)} s`;
    }

    // At most one frame per screen refresh while dragging.
    function redraw() {
      if (frame || playing) return;  // while playing, the playhead's loop draws
      frame = requestAnimationFrame(() => { frame = 0; draw(); });
    }

    function resize() {
      const rect = box.getBoundingClientRect();
      if (!rect.width) return;
      canvas.width = Math.round(rect.width * devicePixelRatio);
      canvas.height = Math.round(rect.height * devicePixelRatio);
      paintLayers();
      draw();
    }
    new ResizeObserver(resize).observe(box);

    function stop() {
      if (!playing) return;
      cancelAnimationFrame(playing.frame);
      playing = null;
      media.pause();
      play.replaceChildren(...withIcon("play-fill", "Play"));
      draw();
    }

    // The <audio> starts at the window's start; it's stopped at `to` by the playhead's loop.
    function playSpan(from, to) {
      stop();
      if (!media || to - from <= 0.02) return;
      const zero = win.start;
      const run = { frame: 0 };
      playing = run;
      play.replaceChildren(...withIcon("stop-fill", "Stop"));
      media.currentTime = from - zero;
      media.play().catch(() => { if (playing === run) stop(); });
      const tick = () => {
        if (playing !== run) return;
        if (!root.isConnected) return stop();
        const head = zero + media.currentTime;
        if (head >= to || media.ended) return stop();
        draw(Math.max(from, head));
        run.frame = requestAnimationFrame(tick);
      };
      tick();
    }

    function release() {
      stop();
      if (media) URL.revokeObjectURL(media.src);
      media = null;
    }

    let closed = false;
    function dispose() {
      closed = true;
      release();
    }

    // The span was changed: the card takes it (again, if a file or a voice had replaced it), and its moved edge is played.
    function changed(edge) {
      if (!slot.state.value || !slot.state.value.wave) slot.setValue({ wave: true });
      if (edge === "start") playSpan(sel.start, Math.min(sel.end, sel.start + WAVE_EDGE_PLAY_S));
      else if (edge === "end") playSpan(Math.max(sel.start, sel.end - WAVE_EDGE_PLAY_S), sel.end);
      else playSpan(sel.start, sel.end);
    }

    function setEdge(edge, t) {
      if (edge === "start") sel.start = Math.max(win.start, Math.min(t, sel.end - WAVE_MIN_SPAN_S));
      else sel.end = Math.min(win.start + duration(), Math.max(t, sel.start + WAVE_MIN_SPAN_S));
    }

    function edgeNear(clientX, rect) {
      const dStart = Math.abs(share(sel.start) * rect.width - (clientX - rect.left));
      const dEnd = Math.abs(share(sel.end) * rect.width - (clientX - rect.left));
      if (Math.min(dStart, dEnd) > WAVE_GRAB_PX) return null;
      return dStart < dEnd ? "start" : "end";
    }

    // Pointer: near an edge drags it, elsewhere drags a new span; a click without moving plays from there.
    box.addEventListener("pointermove", (e) => {
      if (buffer && !e.buttons) box.style.cursor = edgeNear(e.clientX, box.getBoundingClientRect()) ? "ew-resize" : "";
    });
    box.addEventListener("pointerdown", (e) => {
      if (!buffer || e.button !== 0) return;
      e.preventDefault();
      const rect = box.getBoundingClientRect();
      const anchor = timeAt(e.clientX, rect);
      const edge = e.target === startHandle ? "start" : e.target === endHandle ? "end" : edgeNear(e.clientX, rect);
      if (edge) {
        stop();
        (edge === "start" ? startHandle : endHandle).focus();  // then ← → fine-tune it
      }
      let moved = false;
      box.setPointerCapture(e.pointerId);
      const move = (ev) => {
        if (!edge && !moved && Math.abs(ev.clientX - e.clientX) < 3) return;
        moved = true;
        const t = timeAt(ev.clientX, rect);
        if (edge) setEdge(edge, t);
        else {
          stop();
          sel.start = Math.min(anchor, t);
          sel.end = Math.min(win.start + duration(), Math.max(anchor, t, sel.start + WAVE_MIN_SPAN_S));
        }
        redraw();
      };
      const up = () => {
        box.removeEventListener("pointermove", move);
        box.removeEventListener("pointerup", up);
        box.removeEventListener("pointercancel", up);
        if (moved) changed(edge);
        else playSpan(anchor, anchor < sel.end ? sel.end : win.start + duration());
      };
      box.addEventListener("pointermove", move);
      box.addEventListener("pointerup", up);
      box.addEventListener("pointercancel", up);
    });

    // Keyboard on an edge: ← → move it by 50 ms (Shift: 250 ms), Space or Enter plays the span.
    for (const [h, edge] of [[startHandle, "start"], [endHandle, "end"]]) {
      h.addEventListener("keydown", (e) => {
        if (!buffer) return;
        const step = e.shiftKey ? 0.25 : 0.05;
        if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
          stop();
          setEdge(edge, sel[edge] + (e.key === "ArrowLeft" ? -step : step));
          redraw();
          clearTimeout(keyTimer);
          keyTimer = setTimeout(() => changed(edge), 350);
        } else if (e.key === " " || e.key === "Enter") {
          if (playing) stop(); else playSpan(sel.start, sel.end);
        } else return;
        e.preventDefault();
        e.stopPropagation();
      });
    }

    play.addEventListener("click", () => (playing ? stop() : playSpan(sel.start, sel.end)));
    reset.addEventListener("click", () => { Object.assign(sel, initial); draw(); changed(null); });

    // The waveform: the picture already there stays until the wider one is decoded.
    async function load() {
      wider.disabled = true;
      try {
        const decoded = await waveAudio(win.start, win.end);
        if (closed) return false;
        release();
        buffer = decoded.buffer;
        media = new Audio(URL.createObjectURL(decoded.blob));
        media.preload = "auto";
        media.load();
        sel.start = Math.max(win.start, sel.start);
        sel.end = Math.min(win.start + duration(), Math.max(sel.end, sel.start + WAVE_MIN_SPAN_S));
        message.hidden = true;
        box.classList.remove("loading");
        for (const h of [startHandle, endHandle]) {
          h.setAttribute("aria-valuemin", win.start.toFixed(2));
          h.setAttribute("aria-valuemax", (win.start + duration()).toFixed(2));
        }
        play.disabled = reset.disabled = false;
        paintLayers();
        draw();
      } catch (err) {
        if (buffer) return toast(err.message, "error");
        message.textContent = `No waveform: ${err.message}`;
        box.hidden = true;
        return false;
      } finally {
        // no more context at the start of the video, or past its end
        const atEdges = buffer && win.start === 0 && buffer.duration < win.end - win.start - 0.05;
        wider.disabled = !buffer || atEdges || win.end - win.start + 2 * WAVE_CONTEXT_S > WAVE_MAX_S;
      }
      return true;
    }

    wider.addEventListener("click", () => {
      win.start = Math.max(0, win.start - WAVE_CONTEXT_S);
      win.end += WAVE_CONTEXT_S;
      load();
    });

    draw();
    // loaded: whether the waveform could be shown; cut(): the card's audio, cut from the chosen span
    return { root, stop, dispose, loaded: load(), cut: () => options.audioSpan(sel.start, sel.end) };
  }

  // The reading of every word of the card's sentence (Mandarin), chosen from the dictionaries by the context.
  // A click on a word the dictionaries read several ways picks its next reading. field() is the sentence with
  // the reading of every word in brackets (你[ni3]<b>好[hao3]</b>), "" while the sentence was edited and its readings aren't back yet.
  function sentenceReadings(language, sentenceBox, getReading) {
    const box = el("div", { class: "form-control mc-readings", lang: displayLang(language), "data-empty": "Reading the sentence…" });
    const picked = new Map();  // "start:text" -> reading picked by the user
    let data = null, timer = 0, request = 0, stale = true;
    const key = (t) => `${t.start}:${t.text}`;
    const pinyinOf = (t) => picked.get(key(t)) || t.pinyin;

    const render = () => {
      box.replaceChildren();
      if (!data || !data.tokens.length) return;
      let pos = 0;
      for (const t of data.tokens) {
        if (t.start > pos) box.append(data.text.slice(pos, t.start));
        const pinyin = pinyinOf(t);
        const choice = t.choices.find((c) => c.pinyin === pinyin);
        let node = el("ruby", {}, t.text, el("rt", { text: choice ? choice.display : pinyin }));
        if (t.choices.length > 1) {
          node = el("button", { type: "button", class: picked.has(key(t)) ? "mc-changed" : null,
            title: `${t.choices.map((c) => c.display).join(" · ")}: click for the next reading` }, node);
          node.addEventListener("click", () => {
            const i = t.choices.findIndex((c) => c.pinyin === pinyin);
            const next = t.choices[(i + 1) % t.choices.length].pinyin;
            if (next === t.pinyin) picked.delete(key(t)); else picked.set(key(t), next);
            render();
          });
        }
        box.append(t.target ? el("b", {}, node) : node);
        pos = t.end;
      }
      if (pos < data.text.length) box.append(data.text.slice(pos));
    };

    const refresh = async () => {
      const id = ++request;
      try {
        const result = await api("/api/sentence/readings", { language, sentence: sentenceBox.innerHTML, reading: getReading() });
        if (id !== request) return;
        data = result;
        stale = false;
        box.dataset.empty = "No sentence";
      } catch (err) {
        if (id !== request) return;
        data = null;
        box.dataset.empty = err.message;
      }
      render();
    };
    const schedule = () => { stale = true; clearTimeout(timer); timer = setTimeout(refresh, 400); };

    const field = () => {
      if (stale || !data || !data.tokens.length) return "";
      let out = "", pos = 0;
      for (const t of data.tokens) {
        out += escapeHtml(data.text.slice(pos, t.start));
        const pinyin = pinyinOf(t);
        const word = escapeHtml(t.text) + (pinyin ? `[${pinyin}]` : "");
        out += t.target ? `<b>${word}</b>` : word;
        pos = t.end;
      }
      return (out + escapeHtml(data.text.slice(pos))).replace(/\n/g, "<br>");
    };

    sentenceBox.addEventListener("input", schedule);
    refresh();
    return { box, field, schedule };
  }

  async function openCreator(entry, language) {
    const ctx = current;
    hidePopup();
    if (creator) creator.modal.hide();
    const sentence = ctx ? ctx.sentence : { text: "", before: "", word: entry.source, after: "" };
    const blocks = definitionBlocks(entry, language);
    const present = BLOCKS.filter(([key]) => blocks[key].length);
    const selected = new Set(present.length ? [present[0][0]] : []);

    const word = el("input", { type: "text", class: "form-control", value: entry.form, lang: displayLang(language) });
    const reading = el("input", { type: "text", class: "form-control", value: entry.reading !== entry.expression ? entry.display_reading || entry.reading : "", lang: displayLang(language) });
    const definition = el("div", { class: "form-control mc-editable", contenteditable: "true", role: "textbox", "aria-multiline": "true" });
    definition.innerHTML = definitionHtml(blocks, selected);
    const sentenceBox = el("div", { class: "form-control mc-editable", contenteditable: "true", role: "textbox", lang: displayLang(language) });
    sentenceBox.innerHTML = sentence.text
      ? `${escapeHtml(sentence.before)}<b>${escapeHtml(sentence.word)}</b>${escapeHtml(sentence.after)}` : "";
    const readings = language === "zh" ? sentenceReadings(language, sentenceBox, () => reading.value.trim() || entry.reading) : null;
    if (readings) reading.addEventListener("input", readings.schedule);
    const translation = el("textarea", { class: "form-control", rows: "2", placeholder: "Optional" });
    const notes = el("textarea", { class: "form-control", rows: "2", placeholder: "Optional" });
    const freq = frequencyText(entry);
    const frequencyInput = el("input", { type: "text", class: "form-control", value: entry.frequency_rank ? String(entry.frequency_rank) : "",
      placeholder: entry.frequency_list ? "Not in the list" : "No frequency list", title: freq ? freq.title : "" });
    const source = el("input", { type: "text", class: "form-control", value: options.getSource ? options.getSource(ctx && ctx.node) : "" });
    const tags = el("input", { type: "text", class: "form-control", placeholder: "space separated" });
    const image = mediaSlot("image", "Image", "image/*");
    const audio = mediaSlot("audio", "Word audio", "audio/*");
    const wordTts = ttsRow(language, () => word.value, audio);
    wordTts.row.hidden = true;  // shown when no recording is found
    audio.zone.insertBefore(wordTts.row, audio.preview);
    const sentenceAudio = mediaSlot("sentence_audio", "Sentence audio", "audio/*,video/*");
    const range = sentence.text && ctx && ctx.node && hasWave() ? options.sentenceRange(sentence.text, ctx.node) : null;
    const wave = range ? waveEditor(range, sentenceAudio) : null;
    if (wave) {
      sentenceAudio.zone.insertBefore(wave.root, sentenceAudio.preview);
      sentenceAudio.setValue({ wave: true });
    }
    const tts = ttsRow(language, () => sentenceBox.textContent, sentenceAudio);
    sentenceAudio.zone.insertBefore(tts.row, sentenceAudio.preview);

    const dictChoice = el("div", { class: "small" });
    for (const [key, label] of present) {
      const box = el("input", { type: "checkbox", class: "form-check-input", checked: selected.has(key) });
      box.addEventListener("change", () => {
        if (box.checked) selected.add(key); else selected.delete(key);
        definition.innerHTML = definitionHtml(blocks, selected);
      });
      dictChoice.append(el("label", { class: "form-check form-check-inline" }, box,
        el("span", { class: "form-check-label", text: key === "monolingual" ? MONOLINGUAL[language] || label : label })));
    }

    const target = el("p", { class: "small text-body-secondary m-0" });
    api("/api/anki/config").then(({ config }) => {
      const setup = config.notes[language];
      target.replaceChildren(setup && setup.deck && setup.model
        ? `Anki: ${setup.deck} › ${setup.model}`
        : el("span", {}, "No Anki note type set for this language yet: ",
          el("a", { href: "/settings/#anki", target: "_blank", text: "set it up" }), ". The card will wait until then."));
    }).catch(() => {});

    const caption = (text, hint) => el("span", { class: `${LABEL} d-flex align-items-baseline gap-2 mb-1` }, text,
      hint ? el("small", { class: "fw-normal", text: hint }) : null);
    const field = (text, control, hint) => el("label", { class: "d-block" }, caption(text, hint), control);
    const status = el("p", { class: "small text-body-secondary me-auto my-0", role: "status" });
    const send = el("button", { type: "button", class: "btn btn-primary" }, ...withIcon("send", "Add to Anki"));
    const later = el("button", { type: "button", class: "btn btn-outline-secondary", text: "Save for later" });
    const cancel = el("button", { type: "button", class: "btn btn-outline-secondary", "data-bs-dismiss": "modal", text: "Cancel" });

    const dialog = el("div", { class: "modal", tabindex: "-1", "aria-labelledby": "mc-creator-title" },
      el("div", { class: "modal-dialog modal-xl modal-dialog-scrollable modal-fullscreen-lg-down" },
        el("div", { class: "modal-content" },
          el("div", { class: "modal-header" },
            el("div", {}, el("h2", { class: "modal-title fs-5", id: "mc-creator-title", text: "New card" }), target),
            el("button", { type: "button", class: "btn-close", "data-bs-dismiss": "modal", "aria-label": "Close" })),
          el("div", { class: "modal-body" },
            el("div", { class: "row g-4" },
              el("div", { class: "col-lg-7 vstack gap-3" },
                el("div", { class: "row g-2" },
                  el("div", { class: "col-sm" }, field("Word", word)),
                  el("div", { class: "col-sm" }, field("Reading", reading)),
                  el("div", { class: "col-sm-3" }, field("Frequency", frequencyInput, freq && freq.frequent ? "★ frequent" : "rank"))),
                el("div", {}, field("Definition", definition, "editable"), dictChoice.childNodes.length > 1 ? dictChoice : null),
                field("Sentence", sentenceBox, "editable"),
                readings ? el("div", {}, caption("Readings", "click a dotted word to change its reading"), readings.box) : null,
                field("Sentence translation", translation),
                field("Notes", notes),
                el("div", { class: "row g-2" },
                  el("div", { class: "col-sm" }, field("Source", source)),
                  el("div", { class: "col-sm" }, field("Tags", tags)))),
              el("div", { class: "col-lg-5 vstack gap-3" },
                el("div", {}, image.zone,
                  el("p", { class: "form-text mb-0", text: "Tip: paste an image (Ctrl+V) or drop a file anywhere in this window." })),
                audio.zone,
                sentenceAudio.zone))),
          el("div", { class: "modal-footer" }, status, cancel, later, send))));
    document.body.append(dialog);
    // a click beside it doesn't lose the card
    const modal = new bootstrap.Modal(dialog, { backdrop: "static" });
    creator = { dialog, modal };

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
    dialog.addEventListener("hidden.bs.modal", () => {
      if (wave) wave.dispose();
      modal.dispose();
      dialog.remove();
      if (creator && creator.dialog === dialog) creator = null;
    });

    const submit = async (sendNow) => {
      send.disabled = later.disabled = true;
      status.textContent = sendNow ? "Sending to Anki…" : "Saving…";
      const media = {};
      if (image.state.value) media.image = image.state.value;
      if (audio.state.value) media.audio = audio.state.value;
      if (sentenceAudio.state.value) media.sentence_audio = sentenceAudio.state.value;
      if (wave && media.sentence_audio && media.sentence_audio.wave) {
        wave.stop();
        try {
          media.sentence_audio = await wave.cut();
        } catch (err) {
          status.textContent = err.message;
          send.disabled = later.disabled = false;
          return;
        }
      }
      try {
        const { card } = await api("/api/cards", {
          language, send: sendNow, tags: tags.value, key_reading: entry.reading !== entry.expression ? entry.reading : "",
          fields: {
            word: word.value.trim(), reading: reading.value.trim(), definition: definition.innerHTML,
            sentence: sentenceBox.innerHTML, sentence_translation: translation.value, notes: notes.value, source: source.value,
            frequency: frequencyInput.value.trim(), sentence_readings: readings ? readings.field() : "",
          },
          media,
        });
        modal.hide();
        updateColour(card.expression, "learning");
        if (options.onStatusChange) options.onStatusChange(card.expression, "learning");
        if (options.onCard) options.onCard(card);
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
    modal.show();
    word.focus();

    if (options.getImage && ctx && ctx.node) {
      Promise.resolve(options.getImage(ctx.node)).then((shot) => {
        if (shot && !image.state.value && dialog.isConnected) image.setValue(shot);
      }).catch(() => {});
    }

    // A recording of the word, when an online source has one; the others can be picked instead. Without one (or
    // offline), the word is read by the settings' voice, as a sentence without audio.
    const readWord = () => wordTts.ready.then((voice) => {
      if (!dialog.isConnected || !wordTts.available()) return;
      wordTts.row.hidden = false;
      if (voice && word.value.trim() && !audio.state.value) wordTts.generate();
    });
    wordAudio(entry, language).catch(() => []).then((sources) => {
      if (!dialog.isConnected) return;
      if (!sources.length) return readWord();
      if (!audio.state.value) audio.setValue({ url: sources[0].url });
      if (sources.length < 2) return;
      const pick = el("select", { class: "form-select form-select-sm", "aria-label": "Recording" });
      sources.forEach((source, i) => pick.append(el("option", { value: String(i), text: `${i + 1}. ${source.name}` })));
      pick.addEventListener("change", () => {
        audio.setValue({ url: sources[Number(pick.value)].url });
        audio.preview.querySelector("audio")?.play().catch(() => {});
      });
      audio.zone.insertBefore(el("div", { class: "d-flex align-items-center gap-2" }, el("span", { class: LABEL, text: "Recording" }), pick), audio.preview);
    }).catch(() => {});

    // A translation of the sentence, made offline in the language of the settings.
    if (sentence.text) {
      translation.placeholder = "Translating…";
      const text = sentenceBox.textContent;
      translateSentence(language, text, true).catch(() => translateSentence(language, text)).then((text) => {
        if (text && !translation.value) translation.value = text;
        translation.placeholder = "Optional";
      }).catch((err) => { translation.placeholder = `Optional (no translation: ${err.message})`; });
    }

    // The sentence's audio, cut from the book's audio when there is one, else read by the settings' voice.
    // (a video: the span chosen on the waveform, when it can be shown)
    const bookClip = wave ? wave.loaded.then((shown) => {
      if (shown) return true;
      if (sentenceAudio.state.value && sentenceAudio.state.value.wave) sentenceAudio.setValue(null);
      return null;
    }) : sentence.text && options.sentenceClip && options.hasAudio && options.hasAudio()
      ? (() => {
        const wait = el("p", { class: "form-text m-0", text: "Cutting the sentence's audio…" });
        sentenceAudio.preview.append(wait);
        return options.sentenceClip(sentence.text, ctx && ctx.node).then((clipped) => {
          wait.remove();
          if (clipped && !sentenceAudio.state.value) sentenceAudio.setValue(clipped);
          else if (!clipped) sentenceAudio.preview.append(el("p", { class: "form-text m-0", text: "This sentence wasn't found in the audio." }));
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
      if (e.target.closest && e.target.closest("input, select, textarea, [contenteditable], .modal")) return;
      const action = popupKeys[e.key];
      if (!action) return;
      e.stopImmediatePropagation();
      e.preventDefault();
      action();
    }, true);
  }

  // What the card creator fills a card with, for cards made without it (a CSV import): the definition blocks a
  // language can have ([key, label]), the HTML of an entry's chosen blocks, the word's recordings, the sentence's translation.
  const cardParts = {
    definitionKinds: (language) => BLOCKS.map(([key, label]) => [key, key === "monolingual" ? MONOLINGUAL[language] || label : label]),
    definitionHtml: (entry, language, keys) => definitionHtml(definitionBlocks(entry, language), new Set(keys)),
    wordAudio, translateSentence,
  };

  window.MiningCatMining = {
    attach, hide: hidePopup, isOpen: () => Boolean(popup && !popup.hidden), renderGlossary, api,
    colourWords, clearColours, updateColour, analyse, onAnalysis, cardParts,
  };
})();
