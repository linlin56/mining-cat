// MiningCat web GUI - the converter page (its API: interfaces/web/blueprints/converter*.py).
"use strict";

const $ = (id) => document.getElementById(id);

const MODE_HELP = {
  "Standard": "Audio files + book: one MP4 per chapter, with subtitles aligned on the book's text.",
  "Generate subtitles": "Audio files only: subtitles are transcribed by Whisper (less accurate than with the book).",
  "Generate audio": "Book only: audio is generated with a text-to-speech voice, with matching subtitles.",
};

const S = {
  opts: null,
  lang: null,                 // language options object from /api/options
  source: "Audiobook / Ebook",
  precision: "Base (default)",
  audio: [],                  // [{path, name}]
  ebook: [],                  // [{path, name}]
  chapters: [],               // [{index, title}]
  selected: new Set(),
  chaptersLoading: false,
  uploads: 0,
  video: {
    mode: "From web", website: "Instagram", url: "",
    file: null, tracks: [], track: null,
    ocr: false, region: null, fps: 4,
  },
  running: false,
  jobKind: null,              // kind of the running job ("audiobook", "video" or "game")
  lastVideoSrt: null,
  replayUntil: 0,             // events up to this id are a replay (page reload): no dialogs
};

// ---------------------------------------------------------------- API

class ApiError extends Error {
  constructor(title, message) { super(message); this.title = title; }
}

async function api(path, body) {
  const init = body === undefined
    ? {}
    : { method: "POST", headers: { "Content-Type": "application/json", "X-MiningCat": "1" }, body: JSON.stringify(body) };
  let res;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError("Server unreachable", "MiningCat isn't answering. Is it still running?");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(data.title || "Error", data.error || `Request failed (${res.status})`);
  return data;
}

// Uploads with a progress readout (audiobooks can weigh hundreds of MB).
function upload(kind, fileList, statusEl) {
  const form = new FormData();
  for (const f of fileList) form.append("files", f, f.name);
  S.uploads += 1;
  refreshBusy();
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/upload/${kind}`);
    xhr.setRequestHeader("X-MiningCat", "1");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && statusEl) statusEl.textContent = `Copying… ${Math.round((e.loaded / e.total) * 100)}%`;
    };
    xhr.onload = () => {
      let data = {};
      try { data = JSON.parse(xhr.responseText); } catch { /* keep {} */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data);
      else reject(new ApiError(data.title || "Upload failed", data.error || `Upload failed (${xhr.status})`));
    };
    xhr.onerror = () => reject(new ApiError("Upload failed", "The file could not be sent to MiningCat."));
    xhr.send(form);
  }).finally(() => {
    S.uploads -= 1;
    if (statusEl) statusEl.textContent = "";
    refreshBusy();
  });
}

// ---------------------------------------------------------------- dialogs

function showDialog(title, message, buttons = [{ label: "OK", value: true, primary: true }]) {
  const dlg = $("dialog");
  $("dialog-title").textContent = title;
  $("dialog-message").textContent = message;
  const actions = $("dialog-actions");
  actions.replaceChildren();
  for (const b of buttons) {
    const btn = document.createElement("button");
    btn.className = b.primary ? "btn btn-primary" : "btn";
    btn.value = String(b.value);
    btn.textContent = b.label;
    actions.append(btn);
  }
  return new Promise((resolve) => {
    dlg.addEventListener("close", () => resolve(dlg.returnValue === "true"), { once: true });
    dlg.returnValue = "false";
    dlg.showModal();
    actions.querySelector(".btn-primary")?.focus();
  });
}

// Like showDialog, but resolves to the value of the button that was clicked ("" if the dialog was dismissed).
function chooseDialog(title, message, buttons) {
  return showDialog(title, message, buttons).then(() => $("dialog").returnValue);
}

const alertBox = (title, message) => showDialog(title, message);
const askYesNo = (title, message) => showDialog(title, message, [
  { label: "No", value: false },
  { label: "Yes", value: true, primary: true },
]);
const showError = (err) => alertBox(err.title || "Error", err.message || String(err));

async function offerOpenFolder(title, message, which) {
  if (await askYesNo(title, `${message}\n\nOpen the output folder?`)) {
    try { await api("/api/open-folder", { which }); } catch (err) { showError(err); }
  }
}

// A converted book can be read in the reader, with each sentence's audio at hand.
async function offerReader() {
  const choice = await chooseDialog("Done",
    "Processing complete!\n\nRead the book in MiningCat's reader, with its audio? Click a word to hear its sentence, and get the sentence's audio on your cards.",
    [{ label: "Close", value: "" }, { label: "Open output folder", value: "folder" }, { label: "Read with audio", value: "reader", primary: true }]);
  try {
    if (choice === "folder") await api("/api/open-folder", { which: "final" });
    if (choice === "reader") {
      const { id } = await api("/api/reader/from-output", { ebook: S.ebook.map((f) => f.path) });
      location.href = `/reader/${id}`;
    }
  } catch (err) { showError(err); }
}

// A converted video can be watched in the player, with its subtitles to mine from.
async function offerPlayer() {
  const choice = await chooseDialog("Done",
    "Video processing complete!\n\nWatch it in MiningCat's player? Click a word in the subtitles to look it up, and make cards with the screenshot and the line's audio.",
    [{ label: "Close", value: "" }, { label: "Open output folder", value: "folder" }, { label: "Watch in the player", value: "player", primary: true }]);
  try {
    if (choice === "folder") await api("/api/open-folder", { which: "final" });
    if (choice === "player") {
      const { id } = await api("/api/player/from-output", { language: $("language").value });
      location.href = `/player/${id}`;
    }
  } catch (err) { showError(err); }
}

// ---------------------------------------------------------------- helpers

function fillSelect(select, values, value) {
  select.replaceChildren(...values.map((v) => new Option(v, v)));
  select.value = values.includes(value) ? value : values[0];
}

// ---------------------------------------------------------------- language / source / mode

function onLanguageChange() {
  S.lang = S.opts.languages.find((l) => l.id === $("language").value);
  const convert = $("convert");
  fillSelect(convert, S.lang.convert, "No conversion");
  convert.disabled = S.lang.convert.length <= 1;
  fillSelect($("voice"), S.lang.voices, S.lang.default_voice);
  if (!S.lang.precision.includes(S.precision)) S.precision = S.lang.precision[0];
  for (const sel of document.querySelectorAll(".precision-select")) fillSelect(sel, S.lang.precision, S.precision);
  updateFreqButtons();
}

function renderSource() {
  for (const btn of $("source").children) btn.setAttribute("aria-checked", String(btn.dataset.value === S.source));
  $("screen-audiobook").hidden = S.source !== "Audiobook / Ebook";
  $("screen-video").hidden = S.source !== "Video";
  $("screen-game").hidden = S.source !== "Video game / Screen share";
  $("game-actions").hidden = S.source !== "Video game / Screen share";
  const csv = S.source === "CSV to cards";
  $("screen-csv").hidden = $("csv-actions").hidden = !csv;
  // cards are made in the language studied: its variant and script conversions don't apply
  $("convert").closest(".field").hidden = csv;
  $("language-field").hidden = csv || S.opts.languages.length <= 1;
}

function renderMode() {
  const mode = $("mode").value;
  $("mode-help").textContent = MODE_HELP[mode] || "";
  // Precision is only used when Whisper runs (not in TTS mode)
  $("precision-field").hidden = mode === "Generate audio";
  $("audio-panel").hidden = mode === "Generate audio";
  $("voice-panel").hidden = mode !== "Generate audio";
  $("ebook-panel").hidden = mode === "Generate subtitles";
  $("freq-panel").hidden = mode === "Generate subtitles";
}

// ---------------------------------------------------------------- audio files

function renderAudio() {
  const list = $("audio-list");
  list.replaceChildren(...S.audio.map((f) => {
    const li = document.createElement("li");
    const name = document.createElement("span");
    name.className = "file-name";
    name.textContent = f.name;
    name.title = f.name;
    const rm = document.createElement("button");
    rm.type = "button";
    rm.className = "remove-btn";
    rm.textContent = "×";
    rm.title = `Remove ${f.name}`;
    rm.setAttribute("aria-label", `Remove ${f.name}`);
    rm.addEventListener("click", () => removeAudio(f));
    li.append(name, rm);
    return li;
  }));
  $("audio-empty").hidden = S.audio.length > 0;
}

async function addAudio(fileList) {
  if (!fileList.length) return;
  try {
    const { files, rejected } = await upload("audio", fileList, $("audio-upload-status"));
    for (const f of files) if (!S.audio.some((a) => a.path === f.path)) S.audio.push(f);
    renderAudio();
    if (rejected.length) alertBox("Unsupported files", `These files were skipped:\n${rejected.join("\n")}`);
  } catch (err) { showError(err); }
}

async function removeAudio(file) {
  S.audio = S.audio.filter((f) => f !== file);
  renderAudio();
  try { await api("/api/discard", { path: file.path }); } catch { /* the list is what matters */ }
}

// ---------------------------------------------------------------- ebook & chapters

function renderEbook() {
  const label = $("ebook-label");
  if (!S.ebook.length) {
    label.textContent = "No file selected";
    label.className = "dim";
  } else {
    label.textContent = S.ebook.length === 1 ? S.ebook[0].name : `${S.ebook.length} TXT files selected`;
    label.className = "selected";
  }
  label.title = S.ebook.map((f) => f.name).join("\n");

  const list = $("chapter-list");
  if (S.chaptersLoading) {
    const li = document.createElement("li");
    li.className = "loading";
    li.textContent = "Loading chapters…";
    list.replaceChildren(li);
  } else {
    list.replaceChildren(...S.chapters.map((ch) => {
      const li = document.createElement("li");
      const lab = document.createElement("label");
      const box = document.createElement("input");
      box.type = "checkbox";
      box.checked = S.selected.has(ch.index);
      box.addEventListener("change", () => {
        box.checked ? S.selected.add(ch.index) : S.selected.delete(ch.index);
        renderChapterCount();
      });
      const num = document.createElement("span");
      num.className = "chapter-num";
      num.textContent = `Ch.${String(ch.index + 1).padStart(3, "0")}`;
      const title = document.createElement("span");
      title.className = "file-name";
      title.textContent = ch.title;
      title.title = ch.title;
      lab.append(box, num, title);
      li.append(lab);
      return li;
    }));
  }
  renderChapterCount();
}

function renderChapterCount() {
  const total = S.chapters.length;
  $("chapter-count").textContent = total ? `${S.selected.size}/${total} chapters` : "";
}

async function loadChapters() {
  if (!S.ebook.length) {
    S.chapters = [];
    S.selected = new Set();
    renderEbook();
    return;
  }
  S.chaptersLoading = true;
  renderEbook();
  try {
    const data = await api("/api/chapters", { files: S.ebook.map((f) => f.path) });
    S.ebook = data.files;
    S.chapters = data.chapters;
    S.selected = new Set(data.chapters.map((c) => c.index));
    if (data.error) alertBox("Could not read the book", data.error);
  } catch (err) {
    S.chapters = [];
    S.selected = new Set();
    showError(err);
  } finally {
    S.chaptersLoading = false;
    renderEbook();
  }
}

// Picking a new book replaces the previous selection (one EPUB, or one or several TXT files).
async function selectEbook(fileList) {
  if (!fileList.length) return;
  try {
    const { files, rejected } = await upload("ebook", fileList, $("ebook-upload-status"));
    if (rejected.length) alertBox("Unsupported files", `These files were skipped:\n${rejected.join("\n")}`);
    if (!files.length) return;
    const previous = S.ebook.filter((old) => !files.some((f) => f.path === old.path));
    S.ebook = files;
    for (const old of previous) api("/api/discard", { path: old.path }).catch(() => {});
    await loadChapters();
  } catch (err) { showError(err); }
}

// ---------------------------------------------------------------- video

function hasVideoSource() {
  return S.video.mode === "Local file" ? S.video.file !== null : S.video.url !== "";
}

function renderVideo() {
  const v = S.video;
  const local = v.mode === "Local file";
  $("video-web").hidden = local;
  $("video-local").hidden = !local;
  $("video-url").placeholder = S.opts.url_hints[v.website] || "";

  const label = $("video-file-label");
  label.textContent = v.file ? v.file.name : "No file selected";
  label.className = v.file ? "selected" : "dim";

  const multi = v.tracks.length > 1;
  $("audio-track-field").hidden = !(local && multi);

  $("ocr-region-btn").disabled = !(v.ocr && hasVideoSource());
  $("ocr-fps-row").hidden = !v.ocr;
  $("ocr-fps-value").textContent = String(v.fps);
  $("ocr-hint").hidden = !(v.ocr && v.region === null);
  const summary = $("ocr-region-summary");
  summary.hidden = !(v.ocr && v.region !== null);
  if (v.region) {
    const pct = (x) => `${Math.round(x * 100)}%`;
    const [x, y, w, h] = v.region;
    summary.textContent = `Subtitle region: ${pct(w)} × ${pct(h)} of the frame, from ${pct(x)} left / ${pct(y)} top.`;
  }
  // Whisper never runs when OCR is on
  $("video-precision-row").hidden = v.ocr;
}

function resetOcrRegion() {
  S.video.region = null;
  renderVideo();
}

async function selectVideo(fileList) {
  if (!fileList.length) return;
  try {
    const { files, rejected } = await upload("video", [fileList[0]], $("video-upload-status"));
    if (rejected.length) alertBox("Unsupported file", `This file was skipped:\n${rejected.join("\n")}`);
    if (!files.length) return;
    const old = S.video.file;
    S.video.file = files[0];
    S.video.tracks = [];
    S.video.track = null;
    if (old && old.path !== files[0].path) api("/api/discard", { path: old.path }).catch(() => {});
    // A region drawn for a previous video's frame shouldn't silently apply to a different one.
    resetOcrRegion();
    const { tracks } = await api("/api/video/tracks", { path: files[0].path });
    S.video.tracks = tracks;
    if (tracks.length > 1) {
      const sel = $("audio-track");
      sel.replaceChildren(...tracks.map((t) => new Option(t.label, String(t.index))));
      S.video.track = tracks[0].index;
      sel.value = String(tracks[0].index);
    }
    renderVideo();
  } catch (err) { showError(err); }
}

// ---------------------------------------------------------------- OCR region picker

// The same picker serves the subtitle region and the video game areas: `open` describes what to load and where to save.
const ocr = { frames: [], index: 0, region: null, drag: null, token: 0, onOk: null };

function drawOcrRect(region) {
  const [x, y, w, h] = region;
  Object.assign($("ocr-rect").style, {
    left: `${x * 100}%`, top: `${y * 100}%`, width: `${w * 100}%`, height: `${h * 100}%`,
  });
}

function showOcrFrame() {
  $("ocr-frame").src = ocr.frames[ocr.index];
  $("ocr-nav-label").textContent = `Frame ${ocr.index + 1}/${ocr.frames.length}`;
}

// `load()` resolves to {frames, region?}. `onOk(region)` is called with the drawn region.
async function openRegionDialog({ title, help, loading, region, load, onOk }) {
  const dlg = $("ocr-dialog");
  const token = ++ocr.token;
  ocr.region = region;
  ocr.onOk = onOk;
  ocr.frames = [];
  ocr.index = 0;
  $("ocr-title").textContent = title;
  $("ocr-help").textContent = help;
  $("ocr-loading").hidden = false;
  $("ocr-loading").textContent = loading;
  $("ocr-stage").hidden = true;
  $("ocr-nav").hidden = true;
  dlg.showModal();
  try {
    const data = await load();
    if (token !== ocr.token || !dlg.open) return;
    ocr.frames = data.frames;
    if (data.region) ocr.region = data.region;
    $("ocr-loading").hidden = true;
    $("ocr-stage").hidden = false;
    $("ocr-nav").hidden = ocr.frames.length <= 1;
    showOcrFrame();
    drawOcrRect(ocr.region);
  } catch (err) {
    if (token !== ocr.token) return;
    dlg.close();
    showError(err);
  }
}

function openOcrDialog() {
  const local = S.video.mode === "Local file";
  openRegionDialog({
    title: "Select subtitle region",
    help: "Drag a rectangle around the subtitles. Browse frames to find one with dialogue on screen.",
    loading: local ? "Loading preview frames…" : "Downloading the video for preview, please wait…",
    region: S.video.region || S.opts.ocr.default_region,
    load: () => api("/api/ocr/preview", local ? { path: S.video.file.path } : { url: S.video.url }),
    onOk: (region) => { S.video.region = region; renderVideo(); },
  });
}

function ocrPoint(e) {
  const r = $("ocr-frame").getBoundingClientRect();
  return {
    x: Math.min(Math.max(e.clientX - r.left, 0), r.width),
    y: Math.min(Math.max(e.clientY - r.top, 0), r.height),
    w: r.width,
    h: r.height,
  };
}

function ocrDragRegion(e) {
  const end = ocrPoint(e);
  const s = ocr.drag;
  const left = Math.min(s.x, end.x), right = Math.max(s.x, end.x);
  const top = Math.min(s.y, end.y), bottom = Math.max(s.y, end.y);
  return { px: [right - left, bottom - top], region: [left / s.w, top / s.h, (right - left) / s.w, (bottom - top) / s.h] };
}

function setupOcrDialog() {
  const stage = $("ocr-stage");
  stage.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    ocr.drag = ocrPoint(e);
    stage.setPointerCapture(e.pointerId);
    e.preventDefault();
  });
  stage.addEventListener("pointermove", (e) => {
    if (!ocr.drag) return;
    drawOcrRect(ocrDragRegion(e).region);
  });
  const endDrag = (e) => {
    if (!ocr.drag) return;
    const { px, region } = ocrDragRegion(e);
    ocr.drag = null;
    // too small to be an intentional selection: keep the previous region
    if (px[0] >= 4 && px[1] >= 4) ocr.region = region;
    drawOcrRect(ocr.region);
  };
  stage.addEventListener("pointerup", endDrag);
  stage.addEventListener("pointercancel", () => { ocr.drag = null; drawOcrRect(ocr.region); });

  $("ocr-prev").addEventListener("click", () => {
    ocr.index = (ocr.index - 1 + ocr.frames.length) % ocr.frames.length;
    showOcrFrame();
  });
  $("ocr-next").addEventListener("click", () => {
    ocr.index = (ocr.index + 1) % ocr.frames.length;
    showOcrFrame();
  });
  $("ocr-bottom").addEventListener("click", () => { ocr.region = S.opts.ocr.default_region; drawOcrRect(ocr.region); });
  $("ocr-full").addEventListener("click", () => { ocr.region = [0, 0, 1, 1]; drawOcrRect(ocr.region); });
  $("ocr-cancel").addEventListener("click", () => { ocr.token++; $("ocr-dialog").close(); });
  $("ocr-ok").addEventListener("click", () => {
    const { onOk, region, frames } = ocr;
    ocr.token++;
    $("ocr-dialog").close();
    if (frames.length && onOk) onOk(region);
  });
  $("ocr-dialog").addEventListener("cancel", () => { ocr.token++; });
}

// ---------------------------------------------------------------- video game / screen share

const GAME_AREAS = {
  screenshot: {
    title: "Select the window's full size (screenshot sent to the page)",
    help: "Drag a rectangle around the part of the window you want to see in the page.",
  },
  text: {
    title: "Select the text area (read by OCR)",
    help: "Drag a rectangle around the game's dialog box, where the text appears. Only this part is read by OCR.",
  },
};

// Server-side state of the capture panel: {supported, backend_label, hotkeys, page_url, running, settings}
const G = { info: null, busy: false, windows: [] };

function setLabel(el, text, selected) {
  el.textContent = text;
  el.className = selected ? "selected" : "dim";
  el.title = text;
}

function renderGame() {
  const info = G.info;
  if (!info) return;
  const s = info.settings;
  $("game-backend").textContent = info.backend_label;
  setLabel($("game-window-label"), s.window_label || "No window selected", s.has_window);
  setLabel($("game-screenshot-label"), s.screenshot_region ? "Selected" : (s.has_window ? "Whole capture" : "Not selected"), !!s.screenshot_region);
  setLabel($("game-text-label"), s.text_region ? "Selected" : "Not selected", !!s.text_region);
  const idle = info.supported && !G.busy;
  $("game-window-btn").disabled = !idle;
  $("game-screenshot-btn").disabled = !(idle && s.has_window);
  $("game-text-btn").disabled = !(idle && s.has_window);
  $("game-continuous").checked = s.continuous;
  const hotkey = $("game-hotkey");
  if (hotkey.options.length !== info.hotkeys.length) fillSelect(hotkey, info.hotkeys, s.hotkey);
  hotkey.value = s.hotkey;
  hotkey.disabled = s.continuous;
  $("game-hotkey-hint").hidden = s.continuous;

  const running = S.running && S.jobKind === "game";
  const start = $("game-start");
  start.textContent = running ? "Stop" : "Start";
  start.disabled = running ? false : (S.running || G.busy || !(info.supported && s.is_ready));
  $("game-page").disabled = !running;
}

async function refreshGame() {
  try {
    G.info = await api("/api/game/state");
    renderGame();
  } catch (err) { showError(err); }
}

// Runs a request with the selection buttons disabled (portal dialogs and captures can take a while).
async function gameRequest(path, body) {
  G.busy = true;
  renderGame();
  try {
    const data = await api(path, body);
    if (data.settings) G.info.settings = data.settings;
    return data;
  } finally {
    G.busy = false;
    renderGame();
  }
}

async function loadWindowList() {
  const { system_picker, windows } = await api("/api/game/windows");
  G.windows = windows;
  $("window-list").replaceChildren(...windows.map((w) => new Option(w.label, String(w.id))));
  return system_picker;
}

async function selectGameWindow() {
  try {
    // Wayland: the OS shows its own dialog, which this request waits for.
    if (await loadWindowList()) return await gameRequest("/api/game/window", {});
  } catch (err) { return showError(err); }
  $("window-dialog").showModal();
}

async function confirmGameWindow() {
  const value = $("window-list").value;
  if (!value) return;
  $("window-dialog").close();
  try { await gameRequest("/api/game/window", { id: Number(value) }); } catch (err) { showError(err); }
}

function selectGameArea(area) {
  openRegionDialog({
    ...GAME_AREAS[area],
    loading: "Capturing the window…",
    region: [0, 0, 1, 1],
    load: async () => {
      const data = await api("/api/game/frame", { area });
      return { frames: [data.frame], region: data.region };
    },
    onOk: async (region) => {
      try { await gameRequest("/api/game/area", { area, region }); } catch (err) { showError(err); }
    },
  });
}

async function setGameTrigger(change) {
  try { await gameRequest("/api/game/trigger", change); } catch (err) { showError(err); renderGame(); }
}

async function toggleGame() {
  if (S.running && S.jobKind === "game") {
    $("game-start").disabled = true;
    setStatus("Stopping…", 100);
    try { await api("/api/game/stop", {}); } catch (err) { showError(err); }
    return;
  }
  // Opened right away: a tab opened after waiting for the server would be blocked as a pop-up.
  const tab = window.open("/game/", "miningcat-game");
  try {
    setRunning(true, "game");
    await api("/api/game/start", { language: S.lang.id, convert: $("convert").value });
  } catch (err) {
    if (tab) tab.close();
    setRunning(false);
    showError(err);
  }
}

function setupGame() {
  $("game-window-btn").addEventListener("click", selectGameWindow);
  $("game-screenshot-btn").addEventListener("click", () => selectGameArea("screenshot"));
  $("game-text-btn").addEventListener("click", () => selectGameArea("text"));
  $("game-hotkey").addEventListener("change", (e) => setGameTrigger({ hotkey: e.target.value }));
  $("game-continuous").addEventListener("change", (e) => setGameTrigger({ continuous: e.target.checked }));
  $("game-start").addEventListener("click", toggleGame);
  $("game-page").addEventListener("click", () => window.open("/game/", "miningcat-game"));
  $("window-refresh").addEventListener("click", () => loadWindowList().catch(showError));
  $("window-cancel").addEventListener("click", () => $("window-dialog").close());
  $("window-ok").addEventListener("click", confirmGameWindow);
  $("window-list").addEventListener("dblclick", confirmGameWindow);
}

// ---------------------------------------------------------------- frequency lists

function updateFreqButtons() {
  const charOk = S.lang && S.lang.char_list;
  $("char-freq").disabled = !charOk;
  $("video-word-freq").disabled = !S.lastVideoSrt;
  $("video-char-freq").disabled = !(S.lastVideoSrt && charOk);
}

async function runFrequency(kind, source, button) {
  button.disabled = true;
  try {
    const body = { kind, source, language: S.lang.id };
    if (source === "book") {
      body.ebook = S.ebook.map((f) => f.path);
      body.chapters = [...S.selected];
    }
    const data = await api("/api/frequency", body);
    await offerOpenFolder("Done", data.message, "frequency");
  } catch (err) {
    showError(err);
  } finally {
    button.disabled = false;
    updateFreqButtons();
  }
}

// ---------------------------------------------------------------- run

function refreshBusy() {
  $("controls").disabled = S.running;
  const blocked = S.running || S.uploads > 0;
  $("start").disabled = blocked;
  $("video-start").disabled = blocked;
  renderGame();
  renderCsvActions();  // csv_cards.js
}

function setRunning(running, kind = null) {
  S.running = running;
  S.jobKind = running ? kind : null;
  refreshBusy();
}

function common() {
  return { language: S.lang.id, convert: $("convert").value, precision: S.precision };
}

async function startAudiobook() {
  const body = {
    ...common(),
    mode: $("mode").value,
    voice: $("voice").value,
    audio: S.audio.map((f) => f.path),
    ebook: S.ebook.map((f) => f.path),
    chapters: [...S.selected],
  };
  try {
    setRunning(true, "audiobook");
    await api("/api/run/audiobook", body);
  } catch (err) {
    setRunning(false);
    showError(err);
  }
}

async function startVideo() {
  const v = S.video;
  if (v.mode !== "Local file" && v.url) {
    try {
      const { error } = await api("/api/video/validate", { url: v.url, website: v.website });
      if (error) return alertBox("URL mismatch", error);
    } catch (err) { return showError(err); }
  }
  const body = {
    ...common(),
    input_mode: v.mode,
    website: v.website,
    url: v.url,
    path: v.file ? v.file.path : null,
    audio_track: v.tracks.length > 1 ? v.track : null,
    ocr: v.ocr,
    ocr_region: v.region,
    ocr_fps: v.fps,
  };
  try {
    setRunning(true, "video");
    await api("/api/run/video", body);
  } catch (err) {
    setRunning(false);
    showError(err);
  }
}

async function clearOutput() {
  const ok = await askYesNo("Clear output", "This will delete all files in the output folder.\n\nAre you sure?");
  if (!ok) return;
  try {
    await api("/api/clear-output", {});
    S.lastVideoSrt = null;
    updateFreqButtons();
  } catch (err) { showError(err); }
}

// ---------------------------------------------------------------- progress & log (Server-Sent Events)

const LOG_MAX_CHARS = 400_000;

function appendLog(text) {
  const log = $("log");
  const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 24;
  log.textContent += text;
  if (log.textContent.length > LOG_MAX_CHARS) log.textContent = log.textContent.slice(-LOG_MAX_CHARS * 0.8);
  if (atBottom) log.scrollTop = log.scrollHeight;
}

function setStatus(text, pct) {
  $("status").textContent = text;
  $("progress-bar").style.width = `${Math.max(0, Math.min(100, pct))}%`;
}

function handleEvent(id, ev) {
  const replay = id <= S.replayUntil;
  switch (ev.type) {
    case "start":
      $("log").textContent = "";
      setRunning(true, ev.kind);
      break;
    case "log":
      appendLog(ev.text);
      break;
    case "status":
      setStatus(ev.text, ev.pct);
      break;
    case "done":
      // On a replay, /api/state already gave the current subtitles (the output may have been cleared since).
      if (ev.kind === "video" && !replay) {
        S.lastVideoSrt = ev.has_srt ? true : null;
        updateFreqButtons();
      }
      if (!replay && ev.kind === "audiobook" && S.ebook.length && $("mode").value !== "Generate subtitles") {
        offerReader();
      } else if (!replay && ev.kind === "video") {
        offerPlayer();
      } else if (!replay && ev.kind !== "game") {
        offerOpenFolder("Done", "Processing complete!", "final");
      }
      break;
    case "finish":
      setRunning(false);
      // The capture subprocess may have saved a new Wayland restore token.
      if (ev.kind === "game") refreshGame();
      break;
  }
}

function connectEvents() {
  const conn = $("connection");
  const source = new EventSource("/api/events?last=0");
  source.onopen = () => { conn.textContent = ""; };
  source.onerror = () => { conn.textContent = "Connection lost, retrying…"; };
  source.onmessage = (e) => {
    let ev;
    try { ev = JSON.parse(e.data); } catch { return; }
    handleEvent(Number(e.lastEventId) || 0, ev);
  };
}

// ---------------------------------------------------------------- drag & drop

function setupDropzones() {
  const handlers = { audio: addAudio, ebook: selectEbook, video: selectVideo, csv: selectCsv };
  for (const zone of document.querySelectorAll(".dropzone")) {
    const handler = handlers[zone.dataset.kind];
    zone.addEventListener("dragover", (e) => {
      if (S.running || !e.dataTransfer.types.includes("Files")) return;
      e.preventDefault();
      zone.classList.add("dragover");
    });
    zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      zone.classList.remove("dragover");
      if (!S.running) handler([...e.dataTransfer.files]);
    });
  }
  // Dropping a file anywhere else must not navigate away from the app.
  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("drop", (e) => e.preventDefault());
}

// ---------------------------------------------------------------- wiring

function filePicker(buttonId, inputId, accept, handler) {
  const input = $(inputId);
  input.accept = accept;
  $(buttonId).addEventListener("click", () => input.click());
  input.addEventListener("change", () => {
    const files = [...input.files];
    input.value = "";
    handler(files);
  });
}

function wire() {
  const o = S.opts;
  $("repo-link").href = o.github_url;

  // header: the variants of the language studied (Mandarin: Taiwan or China), hidden when there's only one
  const langSel = $("language");
  langSel.replaceChildren(...o.languages.map((l) => new Option(l.label, l.id)));
  langSel.value = o.default_language;
  langSel.addEventListener("change", onLanguageChange);
  $("language-field").hidden = o.languages.length <= 1;

  const src = $("source");
  src.replaceChildren(...o.sources.map((s) => {
    const b = document.createElement("button");
    b.type = "button";
    b.role = "radio";
    b.dataset.value = s;
    b.textContent = s;
    b.addEventListener("click", () => { S.source = s; renderSource(); });
    return b;
  }));

  for (const sel of document.querySelectorAll(".precision-select")) {
    sel.addEventListener("change", () => {
      S.precision = sel.value;
      for (const other of document.querySelectorAll(".precision-select")) other.value = S.precision;
    });
  }
  S.precision = o.default_precision;

  // audiobook screen
  fillSelect($("mode"), o.modes, "Standard");
  $("mode").addEventListener("change", renderMode);
  $("audio-exts").textContent = `(${o.audio_extensions.map((e) => e.toUpperCase()).join(", ")})`;
  filePicker("audio-add", "audio-input", o.audio_extensions.map((e) => `.${e}`).join(","), addAudio);
  filePicker("ebook-select", "ebook-input", ".epub,.txt", selectEbook);
  $("chapters-all").addEventListener("click", () => {
    S.selected = new Set(S.chapters.map((c) => c.index));
    renderEbook();
  });
  $("chapters-none").addEventListener("click", () => { S.selected = new Set(); renderEbook(); });
  $("word-freq").addEventListener("click", (e) => runFrequency("word", "book", e.currentTarget));
  $("char-freq").addEventListener("click", (e) => runFrequency("char", "book", e.currentTarget));
  $("start").addEventListener("click", startAudiobook);

  // video screen
  fillSelect($("video-input-mode"), o.input_modes, S.video.mode);
  $("video-input-mode").addEventListener("change", (e) => { S.video.mode = e.target.value; renderVideo(); });
  fillSelect($("video-website"), o.websites, S.video.website);
  $("video-website").addEventListener("change", (e) => { S.video.website = e.target.value; renderVideo(); });
  $("video-url").addEventListener("input", (e) => {
    const url = e.target.value.trim();
    if (url === S.video.url) return;
    S.video.url = url;
    // A region drawn for a previous URL's frame shouldn't silently apply to a different one.
    resetOcrRegion();
  });
  filePicker("video-select", "video-input", o.video_extensions.map((e) => `.${e}`).join(","), selectVideo);
  $("audio-track").addEventListener("change", (e) => { S.video.track = Number(e.target.value); });
  $("use-ocr").addEventListener("change", (e) => { S.video.ocr = e.target.checked; renderVideo(); });
  const fps = $("ocr-fps");
  fps.min = o.ocr.fps_min;
  fps.max = o.ocr.fps_max;
  fps.value = S.video.fps = o.ocr.fps_default;
  fps.addEventListener("input", () => { S.video.fps = Number(fps.value); renderVideo(); });
  $("ocr-region-btn").addEventListener("click", openOcrDialog);
  $("video-word-freq").addEventListener("click", (e) => runFrequency("word", "video", e.currentTarget));
  $("video-char-freq").addEventListener("click", (e) => runFrequency("char", "video", e.currentTarget));
  $("video-start").addEventListener("click", startVideo);

  for (const btn of document.querySelectorAll('[data-action="clear-output"]')) btn.addEventListener("click", clearOutput);

  setupOcrDialog();
  setupGame();
  setupDropzones();
}

async function init() {
  try {
    S.opts = await api("/api/options");
    if (!S.opts.languages.length) {
      // The language studied has no converter (e.g. Taigi): only the reader and the player work with it.
      $("no-converter").hidden = false;
      for (const id of ["controls", "game-actions"]) $(id).hidden = true;
      for (const block of document.querySelectorAll(".progress-block, .log-panel")) block.hidden = true;
      return;
    }
    wire();
    onLanguageChange();
    renderSource();
    renderMode();
    renderVideo();

    const { job, files } = await api("/api/state");
    S.replayUntil = job.last_event_id || 0;
    S.lastVideoSrt = job.last_video_srt;
    setRunning(job.running, job.kind);
    setStatus(job.status || "", job.pct || 0);
    updateFreqButtons();
    S.audio = files.audio;
    S.ebook = files.ebook;
    renderAudio();
    connectEvents();
    await refreshGame();
    await loadChapters();
  } catch (err) {
    showError(err);
  }
}

document.addEventListener("DOMContentLoaded", init);
