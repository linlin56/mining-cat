// MiningCat dictionary popup and card creator.
//
// MiningCatMining.attach(container, {getLanguage, getSource, getMode}) makes the text of `container`
// searchable: a click (or Shift + hover) on a word looks it up in the imported dictionaries and shows
// a popup with the definitions, the word's status and a "+ Card" button that opens the card creator.
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
    CSS.highlights.set("mc-lookup", new Highlight(range));
    return range;
  }

  function clearHighlight() {
    if (window.CSS && CSS.highlights) CSS.highlights.delete("mc-lookup");
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
    if (language !== "ja" && entry.reading && entry.reading !== entry.expression) parts.push(el("span", { class: "mc-reading", text: entry.reading }));
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
    for (const entry of data.entries) {
      const meta = el("div", { class: "mc-meta" });
      if (entry.inflections.length) {
        meta.append(el("span", { class: "mc-infl", title: entry.inflections.map((i) => `${i.name}: ${i.description || ""}`).join("\n") },
          `« ${entry.inflections.map((i) => i.name).join(" « ")}`));
      }
      for (const f of entry.frequencies.slice(0, 3)) meta.append(el("span", { class: "mc-chip", title: f.dictionary, text: `${f.dictionary.split(/[\s[(]/)[0]} ${f.display}` }));

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

      const add = el("button", { type: "button", class: "mc-add", text: "+ Card", onclick: () => openCreator(entry, language) });
      box.append(el("article", { class: "mc-entry" },
        el("div", { class: "mc-entry-top" }, headword(entry, language), add),
        meta.childNodes.length ? meta : null,
        ...notes,
        statusControl(entry, language),
        defs));
    }
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
    current = { language: data.language, entries: data.entries, anchorRect, sentence };
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
    return { zone, state, set };
  }

  async function openCreator(entry, language) {
    const ctx = current;
    hidePopup();
    if (creator) creator.dialog.remove();
    const sentence = ctx ? ctx.sentence : { text: "", before: "", word: entry.source, after: "" };
    const selected = new Set(entry.definitions.length ? [entry.definitions[0].dictionary] : []);

    const word = el("input", { type: "text", value: entry.form, lang: displayLang(language) });
    const reading = el("input", { type: "text", value: entry.reading !== entry.expression ? entry.reading : "", lang: displayLang(language) });
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
          language, send: sendNow, tags: tags.value,
          fields: {
            word: word.value.trim(), reading: reading.value.trim(), definition: definition.innerHTML,
            sentence: sentenceBox.innerHTML, sentence_translation: translation.value, notes: notes.value, source: source.value,
          },
          media,
        });
        dialog.close();
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
  }

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
      if (e.key === "Escape" && popup && !popup.hidden) {
        e.stopImmediatePropagation();
        e.preventDefault();
        hidePopup();
      }
    }, true);
  }

  window.MiningCatMining = { attach, hide: hidePopup, isOpen: () => Boolean(popup && !popup.hidden), renderGlossary, api };
})();
