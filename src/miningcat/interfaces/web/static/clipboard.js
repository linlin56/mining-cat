// MiningCat clipboard page: the user types or pastes a text, then clicks Read to look its words up with the
// dictionary popup, the word colours and the card creator (mining.js). 
// The text is kept in this browser, one per study language
// Long texts are cut into chunks (sections of paragraphs): the browser lays out only the ones near the screen,
// and each chunk is coloured when it comes close to it, under its own key.
"use strict";

const $ = (id) => document.getElementById(id);

const CHUNK_CHARS = 5000;
// Followed by the study language's id. The unsuffixed keys are those of before, shared by all the languages.
const STORE_TEXT = "miningcat-clipboard-text";
const STORE_CONVERT = "miningcat-clipboard-convert";
// A sentence and what closes it, to cut a paragraph too long for one chunk
const SENTENCE = /[^。！？!?.\n]*(?:[。！？!?.]+[」』）)】〉》”’"']*\s*|$)/g;

const C = {
  study: null,
  reading: false,
  // The language tag of the text read: Chinese's, from the characters it's shown in
  tag: null,
  // Each Read: an older conversion that comes back late is dropped
  readId: 0,
  // The last text converted, its conversion and its choice: read again unchanged, it isn't sent again
  converted: null,
  observer: null,
  saveTimer: null,
};

function load(key) {
  try { return localStorage.getItem(`${key}-${C.study.id}`); } catch { return null; }
}

function store(key, value) {
  try { localStorage.setItem(`${key}-${C.study.id}`, value); } catch { /* full or blocked: the text just isn't kept */ }
}

// The text of before, shared by all the languages, goes to the first language whose clipboard is opened.
function adoptSharedText() {
  try {
    const shared = localStorage.getItem(STORE_TEXT);
    if (shared === null) return;
    if (load(STORE_TEXT) === null) store(STORE_TEXT, shared);
    localStorage.removeItem(STORE_TEXT);
  } catch { /* blocked: nothing kept anyway */ }
}

// A POST to the server's API: its JSON answer, or an error with its message (any answer not in JSON: its status).
async function post(url, body) {
  let res;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-MiningCat": "1" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error("MiningCat isn't answering. Is it still running?");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `${res.status} ${res.statusText}`);
  return data;
}

function language() {
  return C.tag || C.study.tag;
}

// Mandarin and Cantonese (not Taigi, which has its "Write in"): read as typed, or in traditional or simplified characters
function chinese() {
  return Boolean(C.study.two_scripts);
}

// The tag of a text in a script: zh-Hant or zh-Hans for Mandarin (Cantonese has only one), the study's default when
// the script can't tell (characters of both only, or none).
function tagOf(script) {
  const suffix = { traditional: "-Hant", simplified: "-Hans" }[script];
  return (suffix && C.study.tags.find((t) => t.tag.endsWith(suffix))?.tag) || C.study.tag;
}

// The text as it's read: the editor's, converted to the characters chosen (the editor's text is left as it is), with
// the scripts it's read and typed in (null when unknown).
async function readText() {
  const text = $("editor").value, target = $("chinese-convert").value;
  const asTyped = { text, script: null, source: null };
  if (!chinese()) return asTyped;
  if (C.converted?.from === text && C.converted.target === target) return C.converted;
  try {
    const data = await post("/api/chinese/convert", { text, target, language: C.study.id });
    return C.converted = { ...data, from: text, target };
  } catch (err) {
    // without a conversion asked, the text is read as typed, under the study's tag
    if (target !== "none") throw err;
    return asTyped;
  }
}

function showCount() {
  const n = $("editor").value.length;
  $("count").textContent = n ? `${n.toLocaleString(UI_LOCALE)} character${n > 1 ? "s" : ""}` : "";
}

// Paragraphs of the text, those longer than a chunk cut between sentences.
function paragraphs(text) {
  const out = [];
  for (const line of text.replace(/\r\n?/g, "\n").split("\n")) {
    if (!line.trim()) continue;
    if (line.length <= CHUNK_CHARS) { out.push(line); continue; }
    let part = "";
    for (const sentence of line.match(SENTENCE) || [line]) {
      if (part && part.length + sentence.length > CHUNK_CHARS) { out.push(part); part = ""; }
      part += sentence;
    }
    if (part) out.push(part);
  }
  return out;
}

function chunks(text) {
  const sections = [];
  let section = null, size = 0;
  for (const paragraph of paragraphs(text)) {
    if (!section || size + paragraph.length > CHUNK_CHARS) {
      section = Object.assign(document.createElement("section"), { className: "mc-clip-chunk" });
      section.dataset.key = `clip-${sections.length}`;
      sections.push(section);
      size = 0;
    }
    section.append(Object.assign(document.createElement("p"), { textContent: paragraph }));
    size += paragraph.length;
  }
  return sections;
}

async function read() {
  const id = ++C.readId;
  let shown;
  try {
    shown = await readText();
  } catch (err) {
    if (id !== C.readId) return;
    MiningCatUI.dialog("Characters", `The text couldn't be converted: ${err.message}`);
    shown = { text: $("editor").value, script: null, source: null };
  }
  if (id !== C.readId || !C.reading) return;  // an older Read, come back late: the newer one is shown
  C.tag = tagOf(shown.script);
  if (chinese()) $("editor").lang = tagOf(shown.source);  // its glyphs: the typed text's script
  const text = $("text");
  text.lang = language();
  text.replaceChildren(...chunks(shown.text));
  C.observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      C.observer.unobserve(entry.target);
      MiningCatMining.colourWords(entry.target, language(), entry.target.dataset.key);
    }
  }, { rootMargin: "1500px 0px" });
  for (const section of text.children) C.observer.observe(section);
}

function edit() {
  C.readId++;
  if (C.observer) C.observer.disconnect();
  C.observer = null;
  MiningCatMining.hide();
  MiningCatMining.clearColours();
  $("text").replaceChildren();
}

function setReading(reading) {
  if (reading && !$("editor").value.trim()) { $("editor").focus(); return; }
  C.reading = reading;
  $("editor").hidden = reading;
  $("text").hidden = !reading;
  $("toggle").querySelector("i").className = `bi bi-${reading ? "pencil" : "book"}`;
  $("toggle").querySelector("span").textContent = reading ? "Edit" : "Read";
  $("clear").hidden = reading;
  if (reading) read();
  else { edit(); $("editor").focus(); }
  window.scrollTo(0, 0);
}

function init() {
  C.study = JSON.parse(document.body.dataset.study || "null") || { id: "und", tag: "und", tags: [] };
  adoptSharedText();

  // Chinese: read as typed, or converted to traditional or simplified characters
  const select = $("chinese-convert");
  select.hidden = !chinese();
  const saved = load(STORE_CONVERT);
  if ([...select.options].some((o) => o.value === saved)) select.value = saved;
  $("editor").lang = C.study.tag;  // its fonts (Taigi's romanizations)
  select.addEventListener("change", () => {
    store(STORE_CONVERT, select.value);
    if (C.reading) { edit(); read(); }
  });

  // Taigi: the text in Hanji, Tâi-lô or POJ, whichever (or whichever mix) it's written in
  const convert = $("taigi-convert");
  convert.hidden = C.study.id !== "nan";
  convert.addEventListener("change", async () => {
    const target = convert.value;
    convert.value = "";
    if (!target || !$("editor").value.trim()) return;
    convert.disabled = true;
    try {
      const data = await post("/api/taigi/convert", { text: $("editor").value, target });
      $("editor").value = data.text;
      store(STORE_TEXT, data.text);
      showCount();
      if (C.reading) { edit(); read(); }
    } catch (err) {
      MiningCatUI.dialog("Write in…", `The text couldn't be converted: ${err.message}`);
    } finally {
      convert.disabled = false;
    }
  });

  const editor = $("editor");
  editor.value = load(STORE_TEXT) || "";
  showCount();
  editor.addEventListener("input", () => {
    showCount();
    clearTimeout(C.saveTimer);
    C.saveTimer = setTimeout(() => store(STORE_TEXT, editor.value), 400);
  });
  $("toggle").addEventListener("click", () => setReading(!C.reading));
  $("clear").addEventListener("click", () => {
    editor.value = "";
    store(STORE_TEXT, "");
    showCount();
    editor.focus();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); setReading(!C.reading); }
  });

  MiningCatMining.attach($("text"), {
    getLanguage: language,
    getSource: () => "Clipboard",
    getMode: () => "click",
    isVertical: () => false,
  });
  editor.focus();
}

document.addEventListener("DOMContentLoaded", init);
