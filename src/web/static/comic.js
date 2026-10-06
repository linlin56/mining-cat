"use strict";

// MiningCat comics & manga: the pages of a comic, with the text read on them by OCR (web/comics.py) drawn over each
// speech bubble, mokuro-style. Clicking a word looks it up (mining.js): the bubble is the card's sentence, the page its
// picture.

const $ = (id) => document.getElementById(id);

// The language studied (see web/profile.py): {id, name, tag, tags: [{tag, label}]}.
const STUDY = JSON.parse(document.body.dataset.study || "null");
const COMIC_ID = location.pathname.match(/^\/reader\/comic\/([0-9a-f]{16})/)[1];
const NO_SPACE = /^(ja|zh|yue|nan)/;
const PICTURE_MAX_WIDTH = 1280;
const SAVE_DELAY_MS = 800;
const PREFETCH_VIEWS = 2;
const TEXT_MODES = ["hover", "boxes", "always"];
const TEXT_LABELS = { hover: "Text shown on hover", boxes: "Text outlined", always: "Text always shown" };

const C = {
  comic: null, prefs: {}, settings: null,
  views: [],          // the pages shown together: [[1], [2, 3], ...]
  view: 0,
  texts: new Map(),   // page number -> Promise of its text blocks
  queue: Promise.resolve(),  // one OCR request at a time: the pages shown come before the ones prefetched
  saveTimer: null, osdTimer: null, wheelUntil: 0,
  token: 0,
};

// ---------------------------------------------------------------- helpers

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

function showDialog(title, message) {
  const dlg = $("dialog");
  $("dialog-title").textContent = title;
  $("dialog-message").textContent = message;
  const ok = document.createElement("button");
  ok.className = "btn btn-primary";
  ok.textContent = "OK";
  $("dialog-actions").replaceChildren(ok);
  return new Promise((resolve) => {
    dlg.addEventListener("close", resolve, { once: true });
    dlg.showModal();
  });
}
const showError = (err) => showDialog(err.title || "Error", err.message || String(err));

// The reader's theme (light, sepia, dark, or the system's).
function applyTheme() {
  let theme = C.theme || "auto";
  if (theme === "auto") theme = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  document.body.classList.remove("theme-light", "theme-sepia", "theme-dark");
  document.body.classList.add(`theme-${theme}`);
}

function osd(text) {
  const box = $("osd");
  box.textContent = text;
  box.classList.add("show");
  clearTimeout(C.osdTimer);
  C.osdTimer = setTimeout(() => box.classList.remove("show"), 1400);
}

const pageCount = () => C.comic.pages.length;
const pageInfo = (n) => C.comic.pages[n - 1];
const pageUrl = (n) => `/reader/api/comics/${COMIC_ID}/pages/${n}`;
const effectiveLanguage = () => C.prefs.language || STUDY.tag;

function rightToLeft() {
  if (C.prefs.direction) return C.prefs.direction === "rtl";
  return NO_SPACE.test(effectiveLanguage());
}

// ---------------------------------------------------------------- spreads

function twoPages() {
  const spread = C.settings.spread;
  if (spread !== "auto") return spread === "double";
  const stage = $("stage");
  return stage.clientWidth > stage.clientHeight * 1.1;
}

// Pages shown together. A wide page (a double page scanned as one) always stands alone, and so does the cover when
// "cover alone" is on, so that facing pages match the printed book.
function buildViews() {
  const views = [];
  const double = twoPages();
  const wide = (n) => pageInfo(n).width > pageInfo(n).height;
  for (let n = 1; n <= pageCount();) {
    const alone = !double || wide(n) || (n === 1 && C.settings.first_single) || n === pageCount() || wide(n + 1);
    views.push(alone ? [n] : [n, n + 1]);
    n += alone ? 1 : 2;
  }
  return views;
}

const viewOf = (page) => Math.max(0, C.views.findIndex((v) => v.includes(page)));

function relayout() {
  const page = C.views.length ? C.views[C.view][0] : (C.progressPage || 1);
  C.views = buildViews();
  C.view = viewOf(page);
  render();
}

// ---------------------------------------------------------------- pages

function render() {
  const token = ++C.token;
  const pages = C.views[C.view];
  const spread = $("spread");
  spread.classList.toggle("rtl", rightToLeft());
  spread.replaceChildren(...pages.map((n) => {
    const box = document.createElement("div");
    box.className = "comic-page";
    box.dataset.page = String(n);
    const img = document.createElement("img");
    img.src = pageUrl(n);
    img.alt = `Page ${n}`;
    img.draggable = false;
    const layer = document.createElement("div");
    layer.className = "ocr-layer";
    box.append(img, layer);
    return box;
  }));
  sizePages();
  syncTextMode();
  updateBar();
  scheduleSave();
  if (window.MiningCatMining) { MiningCatMining.hide(); MiningCatMining.clearColours("comic"); }
  Promise.all(pages.map((n) => showText(n, token))).then(() => {
    if (token === C.token) colourText();
  });
  prefetch();
}

// The pages fill the stage, side by side, at the same height.
function sizePages() {
  const boxes = [...$("spread").children];
  if (!boxes.length) return;
  const stage = $("stage");
  const ratios = boxes.map((b) => { const p = pageInfo(Number(b.dataset.page)); return p.width / p.height; });
  const height = Math.max(50, Math.min(stage.clientHeight - 8, (stage.clientWidth - 8) / ratios.reduce((a, b) => a + b, 0)));
  boxes.forEach((box, i) => {
    box.style.height = `${Math.floor(height)}px`;
    box.style.width = `${Math.floor(height * ratios[i])}px`;
  });
  for (const box of boxes) fitLines(box);
}

function updateBar() {
  const pages = C.views[C.view];
  $("page-count").textContent = `${pages.join("–")} / ${pageCount()}`;
  const slider = $("page-slider");
  slider.max = String(pageCount());
  slider.value = String(pages[0]);
  // the slider runs in the reading direction
  slider.style.direction = rightToLeft() ? "rtl" : "ltr";
}

function go(view) {
  const target = Math.max(0, Math.min(C.views.length - 1, view));
  if (target === C.view) {
    osd(view < 0 ? "First page" : "Last page");
    return;
  }
  C.view = target;
  render();
}

const next = () => go(C.view + 1);
const previous = () => go(C.view - 1);
// The left and right of the screen, whatever the reading direction.
const turnLeft = () => (rightToLeft() ? next() : previous());
const turnRight = () => (rightToLeft() ? previous() : next());

function scheduleSave() {
  clearTimeout(C.saveTimer);
  C.saveTimer = setTimeout(saveProgress, SAVE_DELAY_MS);
}

function saveProgress() {
  clearTimeout(C.saveTimer);
  if (!C.views.length) return;
  const pages = C.views[C.view];
  fetch(`/reader/api/comics/${COMIC_ID}/progress`, {
    method: "POST", keepalive: true,
    headers: { "Content-Type": "application/json", "X-MiningCat": "1" },
    body: JSON.stringify({ page: C.view === C.views.length - 1 ? pages[pages.length - 1] : pages[0] }),
  }).catch(() => {});
}

// ---------------------------------------------------------------- text read on the pages

function fetchText(n, again = false) {
  if (!again && C.texts.has(n)) return C.texts.get(n);
  const run = () => api(`/reader/api/comics/${COMIC_ID}/pages/${n}/text${again ? "?again=1" : ""}`);
  const promise = C.queue.then(run, run);
  C.queue = promise.catch(() => {});
  C.texts.set(n, promise);
  promise.catch(() => C.texts.delete(n));  // tried again next time the page is shown
  return promise;
}

// The text of the next pages is read while this one is looked at, and their pictures loaded.
function prefetch() {
  for (let v = C.view + 1; v <= Math.min(C.views.length - 1, C.view + PREFETCH_VIEWS); v++) {
    for (const n of C.views[v]) {
      fetchText(n).catch(() => {});
      new Image().src = pageUrl(n);
    }
  }
}

function pageBox(n) {
  return $("spread").querySelector(`.comic-page[data-page="${n}"]`);
}

function setStatus(box, text, isError = false, retry = null) {
  let status = box.querySelector(".page-status");
  if (!text) { status?.remove(); return; }
  if (!status) {
    status = document.createElement("div");
    status.dataset.mcIgnore = "";
    box.append(status);
  }
  status.className = `page-status${isError ? " error" : ""}`;
  status.textContent = text;
  if (retry) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn";
    btn.textContent = "Try again";
    btn.style.marginLeft = "8px";
    btn.addEventListener("click", retry);
    status.append(btn);
  }
}

async function showText(n, token, again = false) {
  const box = pageBox(n);
  if (!box) return;
  const known = C.texts.has(n) && !again;
  const timer = known ? null : setTimeout(() => setStatus(box, "Reading the text…"), 250);
  try {
    const data = await fetchText(n, again);
    if (token !== C.token) return;
    setStatus(box, data.blocks.length ? "" : "No text found on this page");
    if (!data.blocks.length) setTimeout(() => setStatus(box, ""), 1800);
    renderBlocks(box, data.blocks);
  } catch (err) {
    if (token !== C.token) return;
    setStatus(box, err.message, true, () => { setStatus(box, ""); showText(n, C.token).then(colourText); });
  } finally {
    clearTimeout(timer);
  }
}

// Each block (speech bubble) is a <div>, so that a lookup takes the whole bubble as its sentence (mining.js), and
// each of its lines a <span> where it was read. In languages written with spaces, a hidden space separates the lines.
function renderBlocks(box, blocks) {
  const layer = box.querySelector(".ocr-layer");
  const spaced = !NO_SPACE.test(effectiveLanguage());
  const pct = (v) => `${(v * 100).toFixed(3)}%`;
  layer.replaceChildren(...blocks.map((block) => {
    const [bx, by, bw, bh] = block.box;
    const div = document.createElement("div");
    div.className = `cb${block.vertical ? " vertical" : ""}`;
    div.lang = effectiveLanguage();
    Object.assign(div.style, { left: pct(bx), top: pct(by), width: pct(bw), height: pct(bh) });
    block.lines.forEach((line, i) => {
      const [lx, ly, lw, lh] = line.box;
      const span = document.createElement("span");
      span.className = "cl";
      span.textContent = line.text;
      span.dataset.box = JSON.stringify([(lx - bx) / bw, (ly - by) / bh, lw / bw, lh / bh]);
      Object.assign(span.style, {
        left: pct((lx - bx) / bw), top: pct((ly - by) / bh), width: pct(lw / bw), height: pct(lh / bh),
      });
      if (spaced && i) {
        const sep = document.createElement("span");
        sep.className = "sep";
        sep.textContent = " ";
        div.append(sep);
      }
      div.append(span);
    });
    return div;
  }));
  fitLines(box);
}

// Each line's font fills the box where it was read: its thickness gives the size, and the characters are spread
// along its length (CJK), or the font made smaller when the line would overflow.
function fitLines(box) {
  const width = box.clientWidth, height = box.clientHeight;
  if (!width || !height) return;
  const lines = [...box.querySelectorAll(".cl")];
  const sizes = lines.map((span) => {
    const block = span.parentElement;
    const vertical = block.classList.contains("vertical");
    const [, , w, h] = JSON.parse(span.dataset.box);
    const bw = parseFloat(block.style.width) / 100 * width, bh = parseFloat(block.style.height) / 100 * height;
    const thickness = vertical ? w * bw : h * bh;
    const length = vertical ? h * bh : w * bw;
    const count = Math.max(1, [...span.textContent].length);
    const cjk = NO_SPACE.test(effectiveLanguage());
    const size = Math.max(6, Math.min(thickness * 0.88, cjk ? length / count : thickness * 0.88));
    span.style.fontSize = `${size}px`;
    span.style.letterSpacing = "0px";
    return { span, vertical, length, count, size, cjk };
  });
  // measured all at once: one layout for the page
  const measured = sizes.map((s) => (s.vertical ? s.span.scrollHeight : s.span.scrollWidth));
  sizes.forEach((s, i) => {
    const natural = measured[i];
    if (natural > s.length + 1) s.span.style.fontSize = `${Math.max(6, s.size * s.length / natural)}px`;
    else if (s.cjk && s.count > 1) s.span.style.letterSpacing = `${Math.max(0, (s.length - natural) / s.count)}px`;
  });
}

function syncTextMode() {
  const mode = C.settings.text;
  $("spread").classList.remove(...TEXT_MODES.map((m) => `mode-${m}`));
  $("spread").classList.add(`mode-${mode}`);
}

function colourText() {
  if (!window.MiningCatMining) return;
  if (C.settings.colors === "off") MiningCatMining.clearColours("comic");
  else MiningCatMining.colourWords($("spread"), effectiveLanguage(), "comic");
}

async function readAgain() {
  const token = C.token;
  for (const n of C.views[C.view]) {
    C.texts.delete(n);
    await showText(n, token, true);
  }
  colourText();
}

// ---------------------------------------------------------------- mining

let lookedUp = null;  // the bubble looked up: it stays shown while its popup is open

function markLookedUp(block) {
  if (lookedUp && lookedUp !== block) lookedUp.classList.remove("active");
  lookedUp = block;
  if (block) block.classList.add("active");
}

function blockOf(node) {
  const el = node && (node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement);
  return el ? el.closest(".cb") : null;
}

// The card's picture: the page the bubble is on, at most PICTURE_MAX_WIDTH wide.
function getImage(node) {
  const box = blockOf(node)?.closest(".comic-page") || $("spread").firstElementChild;
  const img = box && box.querySelector("img");
  if (!img || !img.naturalWidth) return null;
  const scale = Math.min(1, PICTURE_MAX_WIDTH / img.naturalWidth);
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(img.naturalWidth * scale);
  canvas.height = Math.round(img.naturalHeight * scale);
  canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
  const webp = canvas.toDataURL("image/webp", 0.85);
  if (webp.startsWith("data:image/webp")) return { data: webp, name: "page.webp" };
  return { data: canvas.toDataURL("image/jpeg", 0.85), name: "page.jpg" };
}

function getSource(node) {
  const box = blockOf(node)?.closest(".comic-page");
  const n = box ? box.dataset.page : C.views[C.view][0];
  return `${C.comic.title} (p. ${n})`;
}

// ---------------------------------------------------------------- settings

function syncSettingsForm() {
  const s = C.settings;
  for (const b of $("set-spread").children) b.setAttribute("aria-pressed", String(b.dataset.value === s.spread));
  for (const b of $("set-text").children) b.setAttribute("aria-pressed", String(b.dataset.value === s.text));
  $("set-first-single").checked = s.first_single;
  $("set-colors").value = s.colors;
}

function syncComicSettings() {
  $("set-language").replaceChildren(
    new Option(`Automatic (${STUDY.tags[0] ? STUDY.tags[0].label : STUDY.name})`, ""),
    ...STUDY.tags.map((t) => new Option(t.label, t.tag)),
  );
  const lang = C.prefs.language || "";
  if (lang && !STUDY.tags.some((t) => t.tag === lang)) $("set-language").append(new Option(lang, lang));
  $("set-language").value = lang;
  $("language-setting").hidden = STUDY.tags.length <= 1;
  $("set-direction").value = C.prefs.direction || "";
}

async function saveSettings(changes) {
  Object.assign(C.settings, changes);
  syncSettingsForm();
  try { C.settings = await api("/reader/api/comic-settings", changes); } catch (err) { showError(err); }
  syncSettingsForm();
}

async function savePrefs(changes) {
  try { C.prefs = await api(`/reader/api/comics/${COMIC_ID}/prefs`, changes); } catch (err) { showError(err); }
  syncComicSettings();
}

function cycleText() {
  const mode = TEXT_MODES[(TEXT_MODES.indexOf(C.settings.text) + 1) % TEXT_MODES.length];
  saveSettings({ text: mode });
  syncTextMode();
  osd(TEXT_LABELS[mode]);
}

function togglePanel(force) {
  const panel = $("settings-panel");
  panel.hidden = force === undefined ? !panel.hidden : !force;
}

function toggleFullscreen() {
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  else document.documentElement.requestFullscreen().catch(() => {});
}

function wireSettings() {
  $("settings-btn").addEventListener("click", () => togglePanel());
  $("text-btn").addEventListener("click", cycleText);
  $("fullscreen-btn").addEventListener("click", toggleFullscreen);
  for (const btn of document.querySelectorAll("[data-close]")) btn.addEventListener("click", () => togglePanel(false));
  for (const b of $("set-spread").children) {
    b.addEventListener("click", async () => { await saveSettings({ spread: b.dataset.value }); relayout(); });
  }
  for (const b of $("set-text").children) {
    b.addEventListener("click", () => { saveSettings({ text: b.dataset.value }); syncTextMode(); });
  }
  $("set-first-single").addEventListener("change", async (e) => { await saveSettings({ first_single: e.target.checked }); relayout(); });
  $("set-colors").addEventListener("change", async (e) => { await saveSettings({ colors: e.target.value }); colourText(); });
  // another script, or another reading order: the pages are read (or their blocks ordered) again
  $("set-language").addEventListener("change", async (e) => { await savePrefs({ language: e.target.value }); C.texts.clear(); render(); });
  $("set-direction").addEventListener("change", async (e) => { await savePrefs({ direction: e.target.value }); C.texts.clear(); render(); });
  $("read-again").addEventListener("click", readAgain);
}

// ---------------------------------------------------------------- keyboard & wiring

function isEditing(target) {
  return target && target.closest && (target.closest("input, select, textarea, dialog") || target.isContentEditable);
}

function onKey(e) {
  if (e.ctrlKey || e.metaKey || e.altKey || isEditing(e.target)) return;
  if (window.MiningCatMining && MiningCatMining.isOpen()) return;  // the popup's own keys (mining.js)
  const actions = {
    ArrowLeft: turnLeft, ArrowRight: turnRight,
    " ": () => (e.shiftKey ? previous() : next()),
    PageDown: next, PageUp: previous,
    Home: () => go(0), End: () => go(C.views.length - 1),
    t: cycleText, T: cycleText,
    f: toggleFullscreen, F: toggleFullscreen,
    Escape: () => togglePanel(false),
  };
  const action = actions[e.key];
  if (!action) return;
  e.preventDefault();
  action();
}

function wire() {
  $("turn-left").addEventListener("click", turnLeft);
  $("turn-right").addEventListener("click", turnRight);
  $("page-slider").addEventListener("input", (e) => { $("page-count").textContent = `${e.target.value} / ${pageCount()}`; });
  $("page-slider").addEventListener("change", (e) => go(viewOf(Number(e.target.value))));
  // a click on the page outside the text turns it, on the side clicked (not when it closes a popup)
  let popupWasOpen = false;
  $("spread").addEventListener("pointerdown", (e) => {
    popupWasOpen = Boolean(window.MiningCatMining && MiningCatMining.isOpen());
    const block = e.target.closest(".cb");
    if (block) markLookedUp(block);
  });
  $("spread").addEventListener("click", (e) => {
    if (e.target.closest(".cb, .page-status") || popupWasOpen) return;
    const rect = $("spread").getBoundingClientRect();
    if (e.clientX < rect.left + rect.width / 2) turnLeft(); else turnRight();
  });
  document.addEventListener("mousedown", (e) => {
    if (!e.target.closest(".cb, .mc-popup, dialog")) setTimeout(() => {
      if (!window.MiningCatMining || !MiningCatMining.isOpen()) markLookedUp(null);
    }, 0);
  });
  $("stage").addEventListener("wheel", (e) => {
    if (Math.abs(e.deltaY) < 20 || Date.now() < C.wheelUntil) return;
    C.wheelUntil = Date.now() + 350;
    if (e.deltaY > 0) next(); else previous();
  }, { passive: true });
  document.addEventListener("keydown", onKey);
  document.addEventListener("fullscreenchange", () => {
    document.body.classList.toggle("fullscreen", Boolean(document.fullscreenElement));
  });
  // the stage changes size: the window, fullscreen, or the bars hidden
  let wasDouble = null;
  new ResizeObserver(() => {
    if (!C.comic) return;
    const double = twoPages();
    if (C.settings.spread === "auto" && wasDouble !== null && double !== wasDouble) relayout();
    else sizePages();
    wasDouble = double;
  }).observe($("stage"));
  window.addEventListener("pagehide", saveProgress);
}

async function init() {
  try { C.theme = (await api("/reader/api/settings")).theme; } catch { /* the system's theme */ }
  applyTheme();
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme);
  wireSettings();
  wire();
  try {
    const [data, settings] = await Promise.all([api(`/reader/api/comics/${COMIC_ID}`), api("/reader/api/comic-settings")]);
    C.comic = data.comic;
    C.prefs = data.prefs || {};
    C.settings = settings;
    C.progressPage = (data.progress && data.progress.page) || 1;
  } catch (err) {
    await showError(err);
    location.href = "/reader/";
    return;
  }
  document.title = `${C.comic.title} · MiningCat`;
  $("comic-title").textContent = C.comic.title;
  syncSettingsForm();
  syncComicSettings();
  if (window.MiningCatMining) {
    MiningCatMining.attach($("spread"), {
      getLanguage: effectiveLanguage,
      getSource,
      getMode: () => "click",
      isVertical: () => Boolean(lookedUp && lookedUp.classList.contains("vertical")),
      blockSentence: true,
      hasAudio: () => false,
      getImage,
    });
  }
  relayout();
}

document.addEventListener("DOMContentLoaded", init);

// exposed for debugging and tests
window.MiningCatComic = { state: C, buildViews, go };
