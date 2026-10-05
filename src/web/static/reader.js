// MiningCat Reader - library + paginated reader (horizontal or vertical text).
//
// Pagination uses CSS multi-column layout, like ttu / epub.js: the chapter is laid out in columns
// exactly one page wide (horizontal) or one page tall (vertical-rl, where columns stack downwards),
// and turning a page translates the content by one column.
//
// The reading position is a character offset inside the chapter (text nodes, ruby annotations
// excluded), so it survives font, size, margin or writing-mode changes and window resizes.
"use strict";

const $ = (id) => document.getElementById(id);

const LANGUAGES = [
  ["ja", "Japanese"], ["zh-Hant", "Chinese (Traditional)"], ["zh-Hans", "Chinese (Simplified)"],
  ["yue", "Cantonese"], ["ko", "Korean"], ["en", "English"], ["fr", "French"], ["de", "German"],
  ["es", "Spanish"], ["it", "Italian"], ["pt", "Portuguese"], ["pl", "Polish"], ["vi", "Vietnamese"],
  ["ru", "Russian"],
];
const GAP = 48;          // px between columns (never visible: it falls outside the viewport)
const SAVE_DELAY = 700;  // ms

const R = {
  settings: null,
  book: null, prefs: {}, progress: {},
  chapter: 0, page: 0, pages: 1,
  offset: 0,                // character offset of the first character of the current page
  chapterCache: new Map(),
  index: null,              // text index of the rendered chapter
  vertical: false,
  step: 0,                  // px per page
  charsBefore: [],          // cumulative chapter sizes
  saveTimer: null,
  token: 0,
  audio: null,              // {tracks, names} when the book has the audio of a MiningCat conversion
};

// ---------------------------------------------------------------- API

async function api(path, body) {
  const init = body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-MiningCat": "1" },
    body: JSON.stringify(body),
  };
  const res = await fetch(path, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(data.error || `Request failed (${res.status})`), { title: data.title || "Error" });
  return data;
}

function showDialog(title, message, buttons = [{ label: "OK", value: true, primary: true }]) {
  const dlg = $("dialog");
  $("dialog-title").textContent = title;
  $("dialog-message").textContent = message;
  const actions = $("dialog-actions");
  actions.replaceChildren(...buttons.map((b) => {
    const btn = document.createElement("button");
    btn.className = b.primary ? "btn btn-primary" : "btn";
    btn.value = String(b.value);
    btn.textContent = b.label;
    return btn;
  }));
  return new Promise((resolve) => {
    dlg.addEventListener("close", () => resolve(dlg.returnValue === "true"), { once: true });
    dlg.returnValue = "false";
    dlg.showModal();
  });
}
const showError = (err) => showDialog(err.title || "Error", err.message || String(err));

// ---------------------------------------------------------------- settings & theme

function applyTheme() {
  let theme = R.settings.theme;
  if (theme === "auto") theme = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  document.body.className = `theme-${theme}`;
}

let settingsTimer = null;
function saveSettings() {
  clearTimeout(settingsTimer);
  settingsTimer = setTimeout(() => api("/reader/api/settings", R.settings).catch(() => {}), 400);
}

// ---------------------------------------------------------------- library

function placeholderColor(text) {
  let h = 0;
  for (const ch of text) h = (h * 31 + ch.codePointAt(0)) % 360;
  return `hsl(${h} 45% 42%)`;
}

async function showLibrary() {
  R.book = null;
  if (window.MiningCatMining) MiningCatMining.clearColours();
  document.title = "MiningCat Reader";
  $("reading").hidden = true;
  $("library").hidden = false;
  const { books, extensions } = await api("/reader/api/books");
  $("lib-formats").textContent = `Supported formats: ${extensions.map((e) => e.toUpperCase()).join(", ")}. Books are stored in the project's library/ folder.`;
  $("book-input").accept = extensions.map((e) => `.${e}`).join(",");
  const grid = $("book-grid");
  grid.replaceChildren(...books.map((b) => {
    const a = document.createElement("a");
    a.className = "book";
    a.href = `/reader/${b.id}`;
    a.addEventListener("click", (e) => {
      if (e.target.closest(".book-delete")) return;
      e.preventDefault();
      history.pushState({}, "", a.href);
      route();
    });
    const cover = document.createElement("div");
    cover.className = "book-cover";
    if (b.cover) {
      const img = document.createElement("img");
      img.src = b.cover;
      img.alt = "";
      img.loading = "lazy";
      cover.append(img);
    } else {
      const ph = document.createElement("div");
      ph.className = "placeholder";
      ph.lang = b.language;
      ph.style.background = placeholderColor(b.title);
      ph.textContent = b.title;
      cover.append(ph);
    }
    const title = document.createElement("div");
    title.className = "book-title";
    title.lang = b.language;
    title.textContent = b.title;
    title.title = b.title;
    const meta = document.createElement("div");
    meta.className = "book-meta";
    const left = document.createElement("span");
    left.textContent = [b.author, b.format.toUpperCase()].filter(Boolean).join(" · ");
    const right = document.createElement("span");
    right.textContent = b.percent ? `${Math.floor(b.percent)}%` : "New";
    meta.append(left, right);
    const bar = document.createElement("div");
    bar.className = "book-progress";
    const fill = document.createElement("div");
    fill.style.width = `${b.percent || 0}%`;
    bar.append(fill);
    const del = document.createElement("button");
    del.type = "button";
    del.className = "book-delete";
    del.textContent = "×";
    del.title = "Remove from library";
    del.setAttribute("aria-label", `Remove ${b.title} from the library`);
    del.addEventListener("click", async (e) => {
      e.preventDefault();
      const ok = await showDialog("Remove book", `Remove “${b.title}” and its reading progress from the library?`,
        [{ label: "Cancel", value: false }, { label: "Remove", value: true, primary: true }]);
      if (!ok) return;
      try { await api(`/reader/api/books/${b.id}/delete`, {}); showLibrary(); } catch (err) { showError(err); }
    });
    a.append(cover, title, meta, bar, del);
    return a;
  }));
  $("lib-empty").hidden = books.length > 0;
}

async function addBooks(fileList) {
  if (!fileList.length) return;
  const form = new FormData();
  for (const f of fileList) form.append("files", f, f.name);
  const status = $("lib-status");
  status.textContent = `Importing ${fileList.length} file${fileList.length > 1 ? "s" : ""}…`;
  try {
    const res = await fetch("/reader/api/books", { method: "POST", headers: { "X-MiningCat": "1" }, body: form });
    const data = await res.json();
    if (data.errors && data.errors.length) showDialog("Some files could not be imported", data.errors.join("\n"));
  } catch (err) {
    showError(err);
  } finally {
    status.textContent = "";
    showLibrary();
  }
}

// ---------------------------------------------------------------- opening a book

async function openBook(bookId) {
  $("library").hidden = true;
  $("reading").hidden = false;
  $("loading").hidden = false;
  const token = ++R.token;
  const data = await api(`/reader/api/books/${bookId}`);
  if (token !== R.token) return;
  R.book = data.book;
  R.audio = null;
  renderAudio();
  api(`/reader/api/books/${bookId}/audio`).then((d) => { if (R.book && R.book.id === bookId) { R.audio = d.audio; renderAudio(); } }).catch(() => {});
  R.prefs = data.prefs || {};
  R.progress = data.progress || {};
  R.chapterCache = new Map();
  R.chapter = -1;
  R.index = null;
  $("content").replaceChildren();
  R.charsBefore = [];
  let sum = 0;
  for (const ch of R.book.chapters) { R.charsBefore.push(sum); sum += ch.chars; }
  document.title = `${R.book.title} · MiningCat Reader`;
  $("book-title").textContent = R.book.title;
  $("book-title").lang = R.book.language;
  buildToc();
  syncSettingsForm();
  const chapter = Math.min(R.progress.chapter || 0, R.book.chapters.length - 1);
  await goTo(chapter, { offset: R.progress.offset || 0 });
}

function effectiveWriting() {
  const w = R.prefs.writing && R.prefs.writing !== "auto" ? R.prefs.writing : R.book.writing;
  return w === "vertical" ? "vertical" : "horizontal";
}
function effectiveLanguage() {
  return R.prefs.language || R.book.language || "und";
}

// ---------------------------------------------------------------- chapter rendering

async function chapterHtml(i) {
  if (!R.chapterCache.has(i)) {
    R.chapterCache.set(i, api(`/reader/api/books/${R.book.id}/chapters/${i}`).then((d) => d.html));
  }
  return R.chapterCache.get(i);
}

// CJK books: paragraphs get a first-line indent unless they already start with a space or an
// opening bracket, and short numbers are set upright in vertical text (縦中横, e.g. 第12章).
function decorate(content) {
  const lang = effectiveLanguage();
  if (!/^(ja|zh|yue|ko)/.test(lang)) return;
  for (const p of content.querySelectorAll("p")) {
    const first = (p.textContent || "").replace(/^[\n\r\t ]+/, "")[0] || "";
    if (first && !/[\s「『（(【〈《“‘—―…]/.test(first)) p.classList.add("indent");
  }
  if (content.querySelector(".tcy")) return;
  const NUMBER = /(^|[^0-9A-Za-z.,])([0-9]{1,2})(?![0-9A-Za-z.,])/g;
  const walker = document.createTreeWalker(content, NodeFilter.SHOW_TEXT);
  const targets = [];
  while (walker.nextNode()) {
    const node = walker.currentNode;
    NUMBER.lastIndex = 0;
    if (NUMBER.test(node.data) && !node.parentElement.closest("rt, rp")) targets.push(node);
  }
  for (const node of targets) {
    const frag = document.createDocumentFragment();
    let last = 0;
    for (const m of node.data.matchAll(NUMBER)) {
      const start = m.index + m[1].length;
      frag.append(node.data.slice(last, start));
      const span = document.createElement("span");
      span.className = "tcy";
      span.textContent = m[2];
      frag.append(span);
      last = start + m[2].length;
    }
    frag.append(node.data.slice(last));
    node.replaceWith(frag);
  }
}

async function waitForMedia(content) {
  const imgs = [...content.querySelectorAll("img")];
  for (const img of imgs) img.loading = "eager";
  const timeout = new Promise((r) => setTimeout(r, 2500));
  await Promise.race([
    Promise.all(imgs.map((img) => (img.complete ? null : img.decode().catch(() => null)))),
    timeout,
  ]);
  if (document.fonts && document.fonts.ready) await Promise.race([document.fonts.ready, timeout]);
}

async function renderChapter(i) {
  const content = $("content");
  const html = await chapterHtml(i);
  content.innerHTML = html;
  content.lang = effectiveLanguage();
  decorate(content);
  R.index = null;
  layout();
  colourWords();
  await waitForMedia(content);
  layout();
  // prefetch the neighbours
  if (i + 1 < R.book.chapters.length) chapterHtml(i + 1).catch(() => {});
  if (i > 0) chapterHtml(i - 1).catch(() => {});
}

// Colours the chapter's words by status (new, learning), unless turned off in the settings.
function colourWords() {
  if (!window.MiningCatMining) return;
  if (R.settings.colors === "off" || !R.book) MiningCatMining.clearColours();
  else MiningCatMining.colourWords($("content"), effectiveLanguage());
}

// Sizes the column layout to the viewport and counts the pages of the current chapter.
function layout() {
  const s = R.settings;
  const root = document.documentElement.style;
  root.setProperty("--font-size", `${s.font_size}px`);
  root.setProperty("--line-height", String(s.line_height));
  root.setProperty("--margin", `${s.margin}px`);
  root.setProperty("--gap", `${GAP}px`);

  const viewport = $("viewport");
  const w = Math.floor(viewport.clientWidth);
  const h = Math.floor(viewport.clientHeight);
  root.setProperty("--page-w", `${w}px`);
  root.setProperty("--page-h", `${h}px`);

  const content = $("content");
  R.vertical = effectiveWriting() === "vertical";
  content.className = `content ${R.vertical ? "vertical" : "horizontal"} ${s.font}${s.furigana ? "" : " no-rt"}`;
  content.style.transform = "none";
  R.step = R.vertical ? h + GAP : w + GAP;
  const extent = R.vertical ? content.scrollHeight : content.scrollWidth;
  R.pages = Math.max(1, Math.round((extent + GAP) / R.step));
  R.index = null;
}

// `anchor`: the character the reader is at, when it's known and on this page. Keeping it (instead of
// the first character of the page) means repeated layout changes don't drift backwards.
function showPage(page, anchor) {
  if (window.MiningCatMining) MiningCatMining.hide();
  R.page = Math.max(0, Math.min(page, R.pages - 1));
  const shift = R.page * R.step;
  $("content").style.transform = R.vertical ? `translateY(${-shift}px)` : `translateX(${-shift}px)`;
  R.offset = typeof anchor === "number" && pageOfOffset(anchor) === R.page ? anchor : offsetForPage(R.page);
  updateStatus();
  scheduleSave();
}

// ---------------------------------------------------------------- reading position

// Text nodes of the chapter in reading order, with their cumulative character offsets.
function textIndex() {
  if (R.index) return R.index;
  const content = $("content");
  const nodes = [], starts = [];
  let total = 0;
  const walker = document.createTreeWalker(content, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (!node.data.trim()) return NodeFilter.FILTER_REJECT;
      if (node.parentElement && node.parentElement.closest("rt, rp")) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  while (walker.nextNode()) {
    nodes.push(walker.currentNode);
    starts.push(total);
    total += walker.currentNode.data.length;
  }
  R.index = { nodes, starts, total };
  return R.index;
}

function locate(offset) {
  const { nodes, starts } = textIndex();
  let lo = 0, hi = nodes.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (starts[mid] <= offset) lo = mid; else hi = mid - 1;
  }
  return { node: nodes[lo], at: offset - starts[lo] };
}

const range = document.createRange();

// Page on which the character at `offset` is laid out.
function pageOfOffset(offset) {
  const { nodes, total } = textIndex();
  if (!nodes.length) return 0;
  const { node, at } = locate(Math.max(0, Math.min(offset, total - 1)));
  range.setStart(node, Math.min(at, node.data.length - 1));
  range.setEnd(node, Math.min(at + 1, node.data.length));
  let rect = range.getClientRects()[0] || range.getBoundingClientRect();
  if (!rect || (rect.width === 0 && rect.height === 0)) rect = node.parentElement.getBoundingClientRect();
  return pageOfRect(rect);
}

function pageOfRect(rect) {
  const origin = $("content").getBoundingClientRect();
  const pos = R.vertical ? (rect.top + rect.bottom) / 2 - origin.top : (rect.left + rect.right) / 2 - origin.left;
  return Math.max(0, Math.min(R.pages - 1, Math.floor(pos / R.step)));
}

// First character shown on `page` (binary search: pages grow with the offset).
function offsetForPage(page) {
  const { total } = textIndex();
  if (!total || page <= 0) return 0;
  let lo = 0, hi = total - 1;
  if (pageOfOffset(hi) < page) return hi;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (pageOfOffset(mid) >= page) hi = mid; else lo = mid + 1;
  }
  return lo;
}

function percent() {
  const total = R.book.total_chars || 1;
  return Math.min(100, ((R.charsBefore[R.chapter] || 0) + R.offset) / total * 100);
}

function updateStatus() {
  const ch = R.book.chapters[R.chapter];
  $("chapter-title").textContent = ch ? ch.title : "";
  $("chapter-title").lang = effectiveLanguage();
  $("page-info").textContent = `${R.page + 1} / ${R.pages}`;
  const pct = percent();
  $("percent-info").textContent = `${pct.toFixed(1)}%`;
  $("progress-fill").style.width = `${pct}%`;
  for (const a of document.querySelectorAll("#toc a")) a.classList.toggle("current", Number(a.dataset.chapter) === R.chapter);
}

function progressBody() {
  return { chapter: R.chapter, offset: R.offset, percent: percent() };
}

function scheduleSave() {
  clearTimeout(R.saveTimer);
  const bookId = R.book.id;
  const body = progressBody();
  R.saveTimer = setTimeout(() => api(`/reader/api/books/${bookId}/progress`, body).catch(() => {}), SAVE_DELAY);
}

function saveNow() {
  if (!R.book) return;
  clearTimeout(R.saveTimer);
  fetch(`/reader/api/books/${R.book.id}/progress`, {
    method: "POST",
    keepalive: true,
    headers: { "Content-Type": "application/json", "X-MiningCat": "1" },
    body: JSON.stringify(progressBody()),
  }).catch(() => {});
}

// ---------------------------------------------------------------- navigation

// target: {page} | {offset} | {anchor} | {end: true}
async function goTo(chapter, target = {}) {
  const token = ++R.token;
  $("loading").hidden = false;
  try {
    if (chapter !== R.chapter || !$("content").childNodes.length || target.reload) {
      R.chapter = chapter;
      await renderChapter(chapter);
    }
    if (token !== R.token) return;
    let page = 0;
    if (target.end) page = R.pages - 1;
    else if (typeof target.page === "number") page = target.page;
    else if (typeof target.offset === "number") {
      page = pageOfOffset(target.offset);
      showPage(page, target.offset);
      return;
    }
    else if (target.anchor) {
      const el = $("content").querySelector(`#${CSS.escape(target.anchor)}`);
      if (el) {
        page = pageOfRect(el.getBoundingClientRect());
        el.classList.add("flash");
        setTimeout(() => el.classList.remove("flash"), 1700);
      }
    }
    showPage(page);
  } catch (err) {
    showError(err);
  } finally {
    if (token === R.token) $("loading").hidden = true;
  }
}

function next() {
  if (!R.book) return;
  if (R.page < R.pages - 1) showPage(R.page + 1);
  else if (R.chapter < R.book.chapters.length - 1) goTo(R.chapter + 1, { page: 0 });
}

function prev() {
  if (!R.book) return;
  if (R.page > 0) showPage(R.page - 1);
  else if (R.chapter > 0) goTo(R.chapter - 1, { end: true });
}

// In vertical (right-to-left) books the next page is on the left.
const leftAction = () => (R.vertical ? next() : prev());
const rightAction = () => (R.vertical ? prev() : next());

// Keeps the current character on screen after anything that changes the layout.
function relayout() {
  if (!R.book || $("reading").hidden) return;
  const offset = R.offset;
  $("content").lang = effectiveLanguage();
  layout();
  showPage(pageOfOffset(offset), offset);
}

// ---------------------------------------------------------------- contents & settings panels

function buildToc() {
  const list = $("toc");
  const entries = R.book.toc.length
    ? R.book.toc
    : R.book.chapters.map((c, i) => ({ title: c.title, chapter: i, anchor: "", depth: 0 }));
  list.replaceChildren(...entries.map((t) => {
    const li = document.createElement("li");
    const a = document.createElement("a");
    a.href = "#";
    a.textContent = t.title;
    a.lang = R.book.language;
    a.dataset.chapter = t.chapter;
    a.style.paddingInlineStart = `${8 + 16 * (t.depth || 0)}px`;
    a.addEventListener("click", (e) => {
      e.preventDefault();
      togglePanel("toc-panel", false);
      goTo(t.chapter, t.anchor ? { anchor: t.anchor } : { page: 0 });
    });
    li.append(a);
    return li;
  }));
}

function togglePanel(id, force) {
  const panel = $(id);
  const open = force !== undefined ? force : panel.hidden;
  for (const p of document.querySelectorAll(".panel")) p.hidden = true;
  panel.hidden = !open;
}

function syncSettingsForm() {
  const s = R.settings;
  $("set-font-size").value = s.font_size;
  $("out-font-size").textContent = `${s.font_size}px`;
  $("set-line-height").value = s.line_height;
  $("out-line-height").textContent = Number(s.line_height).toFixed(1);
  $("set-margin").value = s.margin;
  $("out-margin").textContent = `${s.margin}px`;
  $("set-furigana").checked = s.furigana;
  $("set-lookup").value = s.lookup || "click";
  $("set-colors").value = s.colors || "status";
  for (const b of $("set-font").children) b.setAttribute("aria-pressed", String(b.dataset.value === s.font));
  for (const b of $("set-theme").children) b.setAttribute("aria-pressed", String(b.dataset.value === s.theme));
  if (R.book) {
    $("set-writing").value = R.prefs.writing || "auto";
    const lang = $("set-language");
    const detected = LANGUAGES.find(([code]) => code === R.book.language);
    lang.replaceChildren(
      new Option(`Automatic (${detected ? detected[1] : R.book.language})`, ""),
      ...LANGUAGES.map(([code, label]) => new Option(label, code)),
    );
    lang.value = R.prefs.language || "";
  }
}

async function savePrefs(changes) {
  Object.assign(R.prefs, changes);
  try { R.prefs = await api(`/reader/api/books/${R.book.id}/prefs`, changes); } catch (err) { showError(err); }
}

function wireSettings() {
  const numeric = [["set-font-size", "font_size"], ["set-line-height", "line_height"], ["set-margin", "margin"]];
  for (const [id, key] of numeric) {
    $(id).addEventListener("input", (e) => {
      R.settings[key] = Number(e.target.value);
      syncSettingsForm();
      relayout();
      saveSettings();
    });
  }
  $("set-furigana").addEventListener("change", (e) => { R.settings.furigana = e.target.checked; relayout(); saveSettings(); });
  $("set-lookup").addEventListener("change", (e) => { R.settings.lookup = e.target.value; saveSettings(); });
  $("audio-link").addEventListener("click", linkAudio);
  $("audio-remove").addEventListener("click", removeAudio);
  $("set-colors").addEventListener("change", (e) => { R.settings.colors = e.target.value; colourWords(); saveSettings(); });
  for (const [id, key] of [["set-font", "font"], ["set-theme", "theme"]]) {
    for (const b of $(id).children) {
      b.addEventListener("click", () => {
        R.settings[key] = b.dataset.value;
        syncSettingsForm();
        applyTheme();
        relayout();
        saveSettings();
      });
    }
  }
  $("set-writing").addEventListener("change", async (e) => { await savePrefs({ writing: e.target.value }); relayout(); });
  $("set-language").addEventListener("change", async (e) => {
    await savePrefs({ language: e.target.value });
    decorate($("content"));
    relayout();
    colourWords();
  });
}

// ---------------------------------------------------------------- audio

function renderAudio() {
  const has = Boolean(R.audio);
  $("audio-status").textContent = has
    ? `${R.audio.tracks} audio file${R.audio.tracks > 1 ? "s" : ""} linked: click a word, then ▶ Sentence to hear it.`
    : "No audio. If you converted this book with MiningCat, link the conversion's audio.";
  $("audio-link").textContent = has ? "Link the last conversion again" : "Link the last conversion's audio";
  $("audio-remove").hidden = !has;
}

async function linkAudio() {
  try {
    R.audio = (await api(`/reader/api/books/${R.book.id}/audio/link`, {})).audio;
    renderAudio();
  } catch (err) { showError(err); }
}

async function removeAudio() {
  const ok = await showDialog("Remove audio", "Remove the audio linked to this book? (The conversion's files in output/ are kept.)",
    [{ label: "Cancel", value: false }, { label: "Remove", value: true, primary: true }]);
  if (!ok) return;
  try {
    await api(`/reader/api/books/${R.book.id}/audio/delete`, {});
    R.audio = null;
    renderAudio();
  } catch (err) { showError(err); }
}

async function sentenceAudio(sentence, kind) {
  if (!R.book || !R.audio) return null;
  const data = await api(`/reader/api/books/${R.book.id}/audio/${kind}`, { sentence, chapter: R.chapter });
  return data.found ? data : null;
}

// ---------------------------------------------------------------- input

function isEditing(target) {
  return target && (target.closest("input, select, textarea") || target.isContentEditable);
}

function wireReading() {
  $("zone-left").addEventListener("click", leftAction);
  $("zone-right").addEventListener("click", rightAction);
  $("toc-btn").addEventListener("click", () => togglePanel("toc-panel"));
  $("settings-btn").addEventListener("click", () => togglePanel("settings-panel"));
  for (const btn of document.querySelectorAll("[data-close]")) btn.addEventListener("click", () => togglePanel(btn.closest(".panel").id, false));
  $("back").addEventListener("click", (e) => {
    e.preventDefault();
    saveNow();
    history.pushState({}, "", "/reader/");
    route();
  });

  // Internal links (notes, cross references) jump inside the book.
  $("content").addEventListener("click", (e) => {
    const a = e.target.closest("a[data-chapter]");
    if (!a) return;
    e.preventDefault();
    goTo(Number(a.dataset.chapter), a.dataset.anchor ? { anchor: a.dataset.anchor } : { page: 0 });
  });

  document.addEventListener("keydown", (e) => {
    if ($("reading").hidden || isEditing(e.target) || e.ctrlKey || e.metaKey || e.altKey || $("dialog").open) return;
    if (document.querySelector(".mc-creator[open]")) return;
    const keys = {
      ArrowLeft: leftAction, ArrowRight: rightAction,
      ArrowDown: next, ArrowUp: prev, PageDown: next, PageUp: prev, " ": e.shiftKey ? prev : next,
      Home: () => goTo(R.chapter, { page: 0 }), End: () => goTo(R.chapter, { end: true }),
      t: () => togglePanel("toc-panel"), s: () => togglePanel("settings-panel"),
      Escape: () => {
        if ([...document.querySelectorAll(".panel")].some((p) => !p.hidden)) togglePanel("toc-panel", false);
        else $("back").click();
      },
    };
    const action = keys[e.key];
    if (!action) return;
    e.preventDefault();
    action();
  });

  // One page per wheel gesture.
  let wheelLock = 0;
  $("stage").addEventListener("wheel", (e) => {
    if (e.target.closest(".panel")) return;
    e.preventDefault();
    const now = Date.now();
    const delta = Math.abs(e.deltaY) > Math.abs(e.deltaX) ? e.deltaY : e.deltaX;
    if (now < wheelLock || Math.abs(delta) < 4) return;
    wheelLock = now + 280;
    if (delta > 0) next(); else prev();
  }, { passive: false });

  // Swipes on touch screens.
  let touch = null;
  $("stage").addEventListener("pointerdown", (e) => {
    if (e.pointerType === "touch") touch = { x: e.clientX, y: e.clientY, t: Date.now() };
  });
  $("stage").addEventListener("pointerup", (e) => {
    if (!touch || e.pointerType !== "touch") return;
    const dx = e.clientX - touch.x, dy = e.clientY - touch.y;
    const quick = Date.now() - touch.t < 600;
    touch = null;
    if (!quick || Math.abs(dx) < 45 || Math.abs(dx) < Math.abs(dy)) return;
    if (window.getSelection && String(window.getSelection())) return;
    if (dx < 0) rightAction(); else leftAction();
  });

  let resizeTimer = null;
  new ResizeObserver(() => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(relayout, 120);
  }).observe($("viewport"));

  window.addEventListener("pagehide", saveNow);
  document.addEventListener("visibilitychange", () => { if (document.hidden) saveNow(); });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { applyTheme(); });
}

function wireLibrary() {
  const input = $("book-input");
  $("add-books").addEventListener("click", () => input.click());
  input.addEventListener("change", () => {
    const files = [...input.files];
    input.value = "";
    addBooks(files);
  });
  const drop = $("lib-drop");
  drop.addEventListener("dragover", (e) => {
    if (!e.dataTransfer.types.includes("Files")) return;
    e.preventDefault();
    drop.classList.add("dragover");
  });
  drop.addEventListener("dragleave", () => drop.classList.remove("dragover"));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    drop.classList.remove("dragover");
    addBooks([...e.dataTransfer.files]);
  });
  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("drop", (e) => e.preventDefault());
}

// ---------------------------------------------------------------- routing

async function route() {
  const match = location.pathname.match(/^\/reader\/([0-9a-f]{16})\/?$/);
  try {
    if (match) await openBook(match[1]);
    else await showLibrary();
  } catch (err) {
    await showError(err);
    if (match) { history.replaceState({}, "", "/reader/"); showLibrary(); }
  }
}

async function init() {
  R.settings = await api("/reader/api/settings");
  applyTheme();
  syncSettingsForm();
  wireLibrary();
  wireReading();
  wireSettings();
  if (window.MiningCatMining) {
    MiningCatMining.attach($("content"), {
      getLanguage: effectiveLanguage,
      getSource: () => (R.book ? R.book.title : ""),
      getMode: () => R.settings.lookup || "click",
      isVertical: () => R.vertical,
      hasAudio: () => Boolean(R.audio),
      sentenceAudio: (text) => sentenceAudio(text, "find"),
      sentenceClip: (text) => sentenceAudio(text, "clip").then((d) => (d ? { data: d.data, name: d.name } : null)),
    });
  }
  window.addEventListener("popstate", () => { saveNow(); route(); });
  route();
}

document.addEventListener("DOMContentLoaded", init);

// exposed for debugging and tests
window.MiningCatReader = { state: R, goTo, next, prev, pageOfOffset, offsetForPage };
