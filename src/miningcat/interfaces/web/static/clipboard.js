// MiningCat clipboard page: the user types or pastes a text, then clicks Read to look its words up with the
// dictionary popup, the word colours and the card creator (mining.js). The text is kept in this browser.
// Long texts are cut into chunks (sections of paragraphs): the browser lays out only the ones near the screen,
// and each chunk is coloured when it comes close to it, under its own key.
"use strict";

const $ = (id) => document.getElementById(id);

const CHUNK_CHARS = 5000;
const STORE_TEXT = "miningcat-clipboard-text";
const STORE_TAG = "miningcat-clipboard-tag";
// A sentence and what closes it, to cut a paragraph too long for one chunk
const SENTENCE = /[^。！？!?.\n]*(?:[。！？!?.]+[」』）)】〉》”’"']*\s*|$)/g;

const C = {
  study: null,
  reading: false,
  observer: null,
  saveTimer: null,
};

function load(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}

function store(key, value) {
  try { localStorage.setItem(key, value); } catch { /* full or blocked: the text just isn't kept */ }
}

function language() {
  return $("language").value || C.study.tag;
}

function showCount() {
  const n = $("editor").value.length;
  $("count").textContent = n ? `${n.toLocaleString()} character${n > 1 ? "s" : ""}` : "";
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
      section = Object.assign(document.createElement("section"), { className: "clip-chunk" });
      section.dataset.key = `clip-${sections.length}`;
      sections.push(section);
      size = 0;
    }
    section.append(Object.assign(document.createElement("p"), { textContent: paragraph }));
    size += paragraph.length;
  }
  return sections;
}

function read() {
  const text = $("text");
  text.lang = language();
  text.replaceChildren(...chunks($("editor").value));
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
  $("toggle").textContent = reading ? "Edit" : "Read";
  $("clear").hidden = reading;
  if (reading) read();
  else { edit(); $("editor").focus(); }
  window.scrollTo(0, 0);
}

function init() {
  C.study = JSON.parse(document.body.dataset.study || "null") || { tag: "und", tags: [] };
  const dark = matchMedia("(prefers-color-scheme: dark)");
  const theme = () => document.body.classList.toggle("theme-dark", dark.matches);
  theme();
  dark.addEventListener("change", theme);

  // Chinese: traditional or simplified characters
  const select = $("language");
  for (const { tag, label } of C.study.tags) select.append(new Option(label, tag));
  select.hidden = C.study.tags.length < 2;
  const saved = load(STORE_TAG);
  if (C.study.tags.some((t) => t.tag === saved)) select.value = saved;
  select.addEventListener("change", () => {
    store(STORE_TAG, select.value);
    if (C.reading) { edit(); read(); }
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
