// MiningCat web GUI - browser side of src/web/app.py.
// Mirrors the behaviour of the Tkinter GUI (gui.py + gui_components/*).
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

const ocr = { frames: [], index: 0, region: null, drag: null, token: 0 };

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

async function openOcrDialog() {
  const dlg = $("ocr-dialog");
  const token = ++ocr.token;
  const local = S.video.mode === "Local file";
  ocr.region = S.video.region || S.opts.ocr.default_region;
  ocr.frames = [];
  ocr.index = 0;
  $("ocr-loading").hidden = false;
  $("ocr-loading").textContent = local ? "Loading preview frames…" : "Downloading the video for preview, please wait…";
  $("ocr-stage").hidden = true;
  $("ocr-nav").hidden = true;
  dlg.showModal();
  try {
    const body = local ? { path: S.video.file.path } : { url: S.video.url };
    const data = await api("/api/ocr/preview", body);
    if (token !== ocr.token || !dlg.open) return;
    ocr.frames = data.frames;
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
    if (ocr.frames.length) S.video.region = ocr.region;
    ocr.token++;
    $("ocr-dialog").close();
    renderVideo();
  });
  $("ocr-dialog").addEventListener("cancel", () => { ocr.token++; });
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
}

function setRunning(running) {
  S.running = running;
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
    setRunning(true);
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
    setRunning(true);
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
      setRunning(true);
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
      if (!replay) {
        const msg = ev.kind === "video" ? "Video processing complete!" : "Processing complete!";
        offerOpenFolder("Done", msg, "final");
      }
      break;
    case "finish":
      setRunning(false);
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
  const handlers = { audio: addAudio, ebook: selectEbook, video: selectVideo };
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

  // header
  const langSel = $("language");
  langSel.replaceChildren(...o.languages.map((l) => new Option(l.label, l.id)));
  langSel.value = o.default_language;
  langSel.addEventListener("change", onLanguageChange);

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
  setupDropzones();
}

async function init() {
  try {
    S.opts = await api("/api/options");
    wire();
    onLanguageChange();
    renderSource();
    renderMode();
    renderVideo();

    const { job, files } = await api("/api/state");
    S.replayUntil = job.last_event_id || 0;
    S.lastVideoSrt = job.last_video_srt;
    setRunning(job.running);
    setStatus(job.status || "", job.pct || 0);
    updateFreqButtons();
    S.audio = files.audio;
    S.ebook = files.ebook;
    renderAudio();
    connectEvents();
    await loadChapters();
  } catch (err) {
    showError(err);
  }
}

document.addEventListener("DOMContentLoaded", init);
