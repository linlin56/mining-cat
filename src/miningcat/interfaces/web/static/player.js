"use strict";

const $ = (id) => document.getElementById(id);

// The language studied (see application/study_language.py): {id, name, tag, tags: [{tag, label}]}.
const STUDY = JSON.parse(document.body.dataset.study || "null");
const SUBTITLE_EXT = /\.(srt|vtt|ass|ssa)$/i;
const SAVE_EVERY_MS = 5000;
const SEEK_STEP_S = 5;
const AUTO_PAUSE_EARLY_S = 0.05;  // pause just before the end, while the subtitle is still shown
const SCREENSHOT_MAX_WIDTH = 1280;
const POLL_MS = 1500;

const P = {
  settings: null,
  extensions: [], subtitleExtensions: [],
  video: null, prefs: {}, progress: {}, audioTracks: [],
  cues: [], second: [],
  active: null, activeSecond: null,
  pauseAt: null,
  selection: null,      // {first, last}: subtitle lines selected in the list, for the next card
  looping: false,
  lastSaved: 0,
  listHoldUntil: 0,     // the user scrolled the list: don't scroll it for a moment
  pollTimer: null,
  libraryTimer: null,
  osdTimer: null,
  token: 0,
  fileVersion: 0,
  translationTarget: null,  // {id, name}: the language second subtitles are translated to (the settings'), or null
  translationModel: "",     // the name of the model translating them (the settings')
  translationTimer: null,       // changes when the video is prepared again, so that the browser doesn't reuse the old file
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

// Resolves to whether the button of value true was clicked (ui.js).
function showDialog(title, message, buttons) {
  return MiningCatUI.dialog(title, message, buttons).then((value) => value === "true");
}
const showError = (err) => showDialog(err.title || "Error", err.message || String(err));

function storageGet(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function storageSet(key, value) {
  try { localStorage.setItem(key, value); } catch { /* private window */ }
}

function formatTime(seconds, withHours = false) {
  const s = Math.max(0, Math.floor(seconds || 0));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = String(s % 60).padStart(2, "0");
  return h || withHours ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}

function fileUrl() {
  return `/player/api/videos/${P.video.id}/file?v=${P.fileVersion}`;
}

// ---------------------------------------------------------------- library

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

// A video's thumbnail (16:9), with what's written over it.
function thumbnail(...overlays) {
  const box = node("div", "ratio ratio-16x9 rounded overflow-hidden shadow-sm bg-body-tertiary mb-2");
  const inner = node("div");
  inner.append(...overlays);
  box.append(inner);
  return box;
}

// Over a thumbnail: the video being prepared or downloaded, or its error.
function thumbnailState(text, error) {
  return node("div", `position-absolute top-0 bottom-0 start-0 end-0 d-flex align-items-center justify-content-center p-2 text-center text-white fw-semibold small ${error ? "bg-danger bg-opacity-75" : "bg-black bg-opacity-50"}`, text);
}

function removeButton(label, onClick) {
  const del = node("button", "btn btn-sm btn-dark rounded-circle position-absolute top-0 end-0 m-1 mc-delete");
  del.type = "button";
  del.innerHTML = '<i class="bi bi-x-lg" aria-hidden="true"></i>';
  del.title = "Remove from the library";
  del.setAttribute("aria-label", label);
  del.addEventListener("click", onClick);
  return del;
}

function inColumn(card) {
  const col = node("div", "col");
  col.append(card);
  return col;
}

function videoCard(v) {
  const card = node(v.status === "ready" || v.status === "error" ? "a" : "div", "mc-cover d-block position-relative text-reset text-decoration-none");
  if (card.tagName === "A") card.href = `/player/${v.id}`;
  const overlays = [];
  if (v.thumb) {
    const img = node("img", "w-100 h-100 object-fit-cover");
    img.src = `/player/api/videos/${v.id}/thumb?v=${v.added}`;
    img.alt = "";
    img.loading = "lazy";
    overlays.push(img);
  }
  if (v.duration) overlays.push(node("span", "badge text-bg-dark position-absolute bottom-0 end-0 m-1 font-monospace fw-normal", formatTime(v.duration)));
  if (v.status !== "ready") {
    const state = thumbnailState(v.status === "error" ? "Error"
      : v.step === "encoding" ? `Converting… ${Math.round(v.progress || 0)}%` : "Preparing…", v.status === "error");
    if (v.error) state.title = v.error;
    overlays.push(state);
  }
  const title = node("div", "fw-semibold small text-truncate", v.title);
  title.title = v.title;
  const meta = node("div", "small text-body-secondary", v.tracks ? `${v.tracks} subtitle track${v.tracks > 1 ? "s" : ""}` : "No subtitles");
  const progress = node("div", "progress my-1");
  progress.style.height = "3px";
  progress.setAttribute("aria-hidden", "true");
  const fill = node("div", "progress-bar");
  fill.style.width = `${v.percent || 0}%`;
  progress.append(fill);
  const del = removeButton(`Remove ${v.title}`, async (e) => {
    e.preventDefault();
    e.stopPropagation();
    const ok = await showDialog("Remove video", `Remove “${v.title}” from the library? Your original file isn't touched.`,
      [{ label: "Cancel", value: false }, { label: "Remove", value: true, primary: true }]);
    if (!ok) return;
    try {
      await api(`/player/api/videos/${v.id}/delete`, {});
      showLibrary();
    } catch (err) { showError(err); }
  });
  const comp = node("div", "small text-body-secondary");
  comp.dataset.video = v.id;
  card.append(thumbnail(...overlays), title, meta, progress, comp, del);
  return inColumn(card);
}

// Each video's comprehension, one after the other (subtitles never analysed take a moment). Kept while the library
// refreshes itself during a download, fetched again when the library is opened.
let comprehensionToken = 0;
const comprehensionCache = new Map();
async function loadComprehension(list) {
  const token = ++comprehensionToken;
  for (const v of list) {
    if (token !== comprehensionToken) return;
    const box = document.querySelector(`[data-video="${v.id}"]`);
    if (!box || v.status !== "ready" || !v.tracks) continue;
    if (!comprehensionCache.has(v.id)) {
      box.textContent = "…";
      try { comprehensionCache.set(v.id, (await api(`/player/api/videos/${v.id}/comprehension`)).comprehension); }
      catch { comprehensionCache.set(v.id, null); }
      if (token !== comprehensionToken) return;
    }
    const c = comprehensionCache.get(v.id);
    box.textContent = c && c.total ? `${percentText(c.percent)}${c.recommended ? ` · ${c.recommended} i+1` : ""}` : "";
    if (c && c.total) box.title = `${c.known} known, ${c.learning} learning and ${c.new} new words (${c.unique_new} different new words). `
      + `${c.i1} of ${c.sentences} subtitle lines have only one new word`
      + (c.frequency ? `, ${c.recommended} of them a frequent one (up to #${c.frequency.limit.toLocaleString()}).` : ".");
  }
}

function downloadCard(job) {
  const card = node("div", "mc-cover position-relative");
  const failed = job.status === "error";
  const title = node("div", "fw-semibold small text-break", job.url);
  card.append(thumbnail(thumbnailState(failed ? "Download failed" : "Downloading…", failed)), title);
  if (job.error) {
    const dismiss = removeButton("Dismiss", async () => {
      await api(`/player/api/downloads/${job.id}/dismiss`, {}).catch(() => {});
      showLibrary();
    });
    card.append(node("div", "small text-danger text-break", job.error), dismiss);
  }
  return inColumn(card);
}

async function showLibrary(refresh = false) {
  if (!refresh) comprehensionCache.clear();
  clearTimeout(P.libraryTimer);
  closeVideo();
  $("watch").hidden = true;
  $("library").hidden = false;
  document.title = "MiningCat Player";
  const data = await api("/player/api/videos");
  P.extensions = data.extensions;
  P.subtitleExtensions = data.subtitle_extensions;
  $("lib-formats").textContent = `Videos: ${data.extensions.join(", ")} · Subtitles: ${data.subtitle_extensions.join(", ")}. `
    + "Drop a video with its subtitles, or paste a link (YouTube, Instagram, Bilibili): its captions come with it.";
  $("video-input").accept = [...data.extensions, ...data.subtitle_extensions].map((e) => `.${e}`).join(",");
  $("video-grid").replaceChildren(...data.downloads.map(downloadCard), ...data.videos.map(videoCard));
  $("lib-empty").hidden = data.videos.length + data.downloads.length > 0;
  loadComprehension(data.videos);
  const busy = data.downloads.some((j) => j.status === "downloading") || data.videos.some((v) => v.status === "queued" || v.status === "preparing");
  if (busy) P.libraryTimer = setTimeout(() => { if (!$("library").hidden) showLibrary(true).catch(() => {}); }, POLL_MS);
}

// Raw upload with progress: a movie is sent as the request's body and written to disk as it arrives.
function uploadVideo(file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/player/api/videos?name=${encodeURIComponent(file.name)}`);
    xhr.setRequestHeader("X-MiningCat", "1");
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.upload.addEventListener("progress", (e) => { if (e.lengthComputable) onProgress(e.loaded / e.total); });
    xhr.addEventListener("load", () => {
      let data = {};
      try { data = JSON.parse(xhr.responseText); } catch { /* not JSON */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data.video);
      else reject(Object.assign(new Error(data.error || `Upload failed (${xhr.status})`), { title: data.title || "Upload" }));
    });
    xhr.addEventListener("error", () => reject(new Error("The upload failed.")));
    xhr.send(file);
  });
}

async function uploadSubtitles(videoId, files) {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  const res = await fetch(`/player/api/videos/${videoId}/subtitles`, { method: "POST", body: form, headers: { "X-MiningCat": "1" } });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(data.error || "Upload failed"), { title: data.title || "Subtitles" });
  return data;
}

const stem = (name) => name.replace(/\.[^.]+$/, "");

// Subtitles go with the video whose name starts like theirs (movie.mkv + movie.en.srt), or with the only video dropped.
async function handleFiles(fileList) {
  const files = [...fileList];
  const vids = files.filter((f) => !SUBTITLE_EXT.test(f.name));
  const subs = files.filter((f) => SUBTITLE_EXT.test(f.name));
  const status = $("lib-status");
  const errors = [];
  if (!vids.length && subs.length) {
    status.textContent = "";
    showDialog("Subtitles", "Drop subtitles together with their video, or open the video and add them in its settings (Aa).");
    return;
  }
  for (const file of vids) {
    try {
      const video = await uploadVideo(file, (ratio) => { status.textContent = `Uploading ${file.name}… ${Math.round(ratio * 100)}%`; });
      const own = subs.filter((s) => stem(s.name).startsWith(stem(file.name)) || vids.length === 1);
      if (own.length) {
        status.textContent = `Adding the subtitles of ${file.name}…`;
        const result = await uploadSubtitles(video.id, own);
        errors.push(...result.errors);
      }
    } catch (err) {
      errors.push(`${file.name}: ${err.message}`);
    }
  }
  status.textContent = errors.length ? errors.join("\n") : vids.length ? `Added ${vids.length} video${vids.length > 1 ? "s" : ""}.` : "";
  showLibrary();
}

async function fillUrlLanguages() {
  const select = $("url-language");
  try {
    // The converter's variants of the language studied: only worth a choice when there are several.
    const { languages, default_language: fallback } = await api("/api/options");
    select.replaceChildren(...languages.map((l) => new Option(l.label, l.id)));
    const saved = storageGet("miningcat-player-language");
    select.value = languages.some((l) => l.id === saved) ? saved : fallback || "";
    select.hidden = languages.length <= 1;
  } catch { select.hidden = true; }
}

function wireLibrary() {
  $("add-videos").addEventListener("click", () => $("video-input").click());
  $("video-input").addEventListener("change", (e) => { handleFiles(e.target.files); e.target.value = ""; });
  const drop = $("lib-drop");
  const over = ["border-primary", "bg-primary-subtle"];
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add(...over); });
  drop.addEventListener("dragleave", () => drop.classList.remove(...over));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    drop.classList.remove(...over);
    if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
  });
  $("url-language").addEventListener("change", (e) => storageSet("miningcat-player-language", e.target.value));
  $("url-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api("/player/api/videos/url", { url: $("url-input").value.trim(), language: $("url-language").value || null });
      $("url-input").value = "";
      showLibrary();
    } catch (err) { showError(err); }
  });
  fillUrlLanguages();
}

// ---------------------------------------------------------------- opening a video

function effectiveLanguage() {
  return P.prefs.language || (P.video && P.video.language) || STUDY.tag;
}
const offset = () => Number(P.prefs.offset) || 0;

function screenMessage(text, action) {
  $("screen-msg").hidden = !text;
  $("screen-text").textContent = text || "";
  const btn = $("screen-action");
  btn.hidden = !action;
  if (action) {
    btn.textContent = action.label;
    btn.onclick = action.run;
  }
}

async function openVideo(id) {
  const token = ++P.token;
  clearTimeout(P.libraryTimer);
  $("library").hidden = true;
  $("watch").hidden = false;
  const data = await api(`/player/api/videos/${id}`);
  if (token !== P.token) return;
  P.video = data.video;
  P.prefs = data.prefs || {};
  P.progress = data.progress || {};
  P.audioTracks = data.audio_tracks || [];
  document.title = `${P.video.title} · MiningCat`;
  $("video-title").textContent = P.video.title;
  syncVideoSettings();
  await loadTracks();
  waitUntilReady(token);
  followTranslation(token);
}

function closeVideo() {
  P.token++;
  clearTimeout(P.pollTimer);
  if (P.video) saveProgress(true);
  const video = $("video");
  video.pause();
  video.removeAttribute("src");
  video.load();
  P.video = null;
  P.cues = [];
  P.second = [];
  clearTimeout(P.translationTimer);
  if (window.MiningCatMining) { MiningCatMining.hide(); MiningCatMining.clearColours(); }
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
}

function preparationText(v) {
  if (v.status === "queued") return "Preparing the video…";
  const pct = `${Math.round(v.progress || 0)}%`;
  const left = v.eta ? ` · about ${v.eta >= 90 ? `${Math.round(v.eta / 60)} min` : `${v.eta} s`} left` : "";
  switch (v.step) {
    case "subtitles": return "Reading the subtitles inside the video…";
    case "thumbnail": return "Making the thumbnail…";
    case "remuxing": return `Repackaging the video for your browser (no re-encoding)… ${pct}`;
    case "encoding": return `Your browser can't decode this video: converting it… ${pct}${left}`;
    default: return "Preparing the video…";
  }
}

// A new video is prepared by the server first (thumbnail, subtitles inside it, a copy for the browser if needed).
function waitUntilReady(token) {
  clearTimeout(P.pollTimer);
  const v = P.video;
  if (v.status === "ready") {
    screenMessage("");
    loadSource();
    return;
  }
  if (v.status === "error") {
    screenMessage(`This video couldn't be prepared:\n${v.error || "unknown error"}`, { label: "Try again", run: () => prepareAgain(null) });
    return;
  }
  screenMessage(preparationText(v));
  P.pollTimer = setTimeout(async () => {
    try {
      const data = await api(`/player/api/videos/${v.id}`);
      if (token !== P.token) return;
      const trackCount = P.video.tracks.length;
      P.video = data.video;
      P.audioTracks = data.audio_tracks || [];
      if (P.video.tracks.length !== trackCount) { syncVideoSettings(); await loadTracks(); }
      waitUntilReady(token);
    } catch (err) {
      screenMessage(err.message);
    }
  }, POLL_MS);
}

async function prepareAgain(level) {
  try {
    P.progress = { time: $("video").currentTime || P.progress.time || 0 };
    $("video").removeAttribute("src");
    $("video").load();
    P.video = (await api(`/player/api/videos/${P.video.id}/prepare`, level ? { level } : {})).video;
    P.fileVersion = Date.now();
    waitUntilReady(P.token);
  } catch (err) { showError(err); }
}

function loadSource() {
  const video = $("video");
  if (video.getAttribute("src") === fileUrl()) return;
  video.src = fileUrl();
  video.load();
}

function onLoadedMetadata() {
  const video = $("video");
  const start = Number(P.progress.time) || 0;
  if (start > 5 && (!video.duration || start < video.duration - 5)) video.currentTime = start;
  // HEVC without hardware decoding: some browsers play the sound without the picture
  if (P.video.video_codec && !video.videoWidth) unplayable();
  update();
}

// What the browser says about the video's codec, in an MP4 ("" when it surely can't decode it).
function canDecode(v) {
  const tenBit = /10/.test(v.pix_fmt || "");
  const types = {
    h264: `video/mp4; codecs="${tenBit ? "avc1.6e0028" : "avc1.640028"}"`,
    hevc: `video/mp4; codecs="${tenBit ? "hvc1.2.4.L120.90" : "hvc1.1.6.L120.90"}"`,
    av1: 'video/mp4; codecs="av01.0.08M.08"',
    vp9: 'video/mp4; codecs="vp09.00.40.08"',
  };
  return Boolean(types[v.video_codec] && $("video").canPlayType(types[v.video_codec]));
}

// The browser couldn't play what it got: the same streams in an MP4 first (a second or two: e.g. Safari plays HEVC,
// but not in an MKV), then the video encoded again (minutes) when the browser can't decode it at all.
function unplayable() {
  const v = P.video;
  const level = v.level || "auto";
  const next = level === "auto" && canDecode(v) ? "remux" : level !== "encode" ? "encode" : null;
  if (!next) {
    screenMessage("Your browser can't play this video, even converted. Try another browser (Chrome plays the most formats).");
    return;
  }
  prepareAgain(next);
}

function saveProgress(now = false) {
  const video = $("video");
  if (!P.video || !video.currentTime || (!now && Date.now() - P.lastSaved < SAVE_EVERY_MS)) return;
  P.lastSaved = Date.now();
  fetch(`/player/api/videos/${P.video.id}/progress`, {
    method: "POST", keepalive: true,
    headers: { "Content-Type": "application/json", "X-MiningCat": "1" },
    body: JSON.stringify({ time: video.currentTime }),
  }).catch(() => {});
}

// ---------------------------------------------------------------- subtitles

// `punctuation`: the subtitles studied, in the punctuation of their language when the settings say so (, → ，).
async function fetchCues(trackId, punctuation = false) {
  if (!trackId) return [];
  const query = punctuation && P.settings.fullwidth_punctuation ? `?punctuation=${encodeURIComponent(effectiveLanguage())}` : "";
  try {
    return (await api(`/player/api/videos/${P.video.id}/subtitles/${trackId}${query}`)).cues;
  } catch { return []; }
}

// The displayed tracks: the ones chosen for this video, else the first one.
async function loadTracks() {
  const tracks = P.video.tracks || [];
  const ids = new Set(tracks.map((t) => t.id));
  const primary = ids.has(P.prefs.primary) ? P.prefs.primary : (P.prefs.primary === undefined && tracks[0] ? tracks[0].id : "");
  const secondary = ids.has(P.prefs.secondary) && P.prefs.secondary !== primary ? P.prefs.secondary : "";
  const [cues, second] = await Promise.all([fetchCues(primary, true), fetchCues(secondary)]);
  P.cues = cues;
  P.second = second;
  P.primaryId = primary;
  P.active = P.activeSecond = null;
  P.selection = null;
  $("set-primary").value = primary;
  $("set-secondary").value = secondary;
  $("remove-subs").disabled = !primary;
  renderList();
  update();
}

function renderList() {
  const lang = effectiveLanguage();
  const items = P.cues.map((cue, i) => {
    const li = document.createElement("li");
    li.className = "cue d-flex align-items-baseline gap-2 py-2 ps-3 pe-2 border-bottom";
    li.dataset.i = String(i);
    const select = document.createElement("input");
    select.type = "checkbox";
    select.className = "form-check-input flex-shrink-0 align-self-center m-0 cue-select";
    select.dataset.mcIgnore = "";
    select.title = "Select this line for the card (with the lines next to it, for a sentence split across lines)";
    select.setAttribute("aria-label", "Select this line");
    const time = document.createElement("button");
    time.type = "button";
    time.className = "btn btn-sm btn-link link-secondary text-decoration-none font-monospace px-1 py-0 flex-shrink-0 cue-time";
    time.dataset.mcIgnore = "";
    time.textContent = formatTime(cue.start);
    time.title = "Go to this subtitle";
    const text = document.createElement("p");
    text.className = "cue-text fs-5 m-0 flex-grow-1 text-break";
    text.lang = lang;
    text.textContent = cue.text;
    li.append(select, time, text);
    return li;
  });
  $("cues").replaceChildren(...items);
  renderSelection();
  $("cues-empty").hidden = P.cues.length > 0 || !P.video;
  colourList();
}

// The list's words are read even with the colours off: they give the comprehension and the recommended lines.
function colourList() {
  if (!window.MiningCatMining) return;
  if (!P.cues.length) MiningCatMining.clearColours("list");
  else MiningCatMining.colourWords($("cues"), effectiveLanguage(), "list", { paint: P.settings.colors !== "off" });
}

// ---------------------------------------------------------------- comprehension & recommended lines

const percentText = (p) => (p === null || p === undefined ? "" : `${p >= 99.95 ? 100 : p.toFixed(1)}% known`);

// Each subtitle line is a sentence: it's recommended (i+1) when every word but one new word is known.
// Recomputed whenever the list's words or their statuses change (a card made, a word marked known...).
function showComprehension(key) {
  if (key !== "list") return;
  const a = MiningCatMining.analyse("list", (node) => node.parentElement && node.parentElement.closest("li.cue"));
  P.recommended = [];
  for (const li of $("cues").children) {
    li.classList.remove("i1");
    li.removeAttribute("title");
  }
  for (const unit of a ? a.units : []) {
    if (!unit.recommended) continue;
    unit.element.classList.add("i1");
    unit.element.title = `Recommended: “${unit.targetRange.toString()}” is the only new word`;
    P.recommended.push(Number(unit.element.dataset.i));
  }
  P.recommended.sort((x, y) => x - y);
  $("cue-summary").hidden = !a || !a.total;
  if (a && a.total) {
    $("comp-summary").textContent = `${percentText(a.percent)} · ${P.recommended.length} i+1`;
    const i1 = a.units.filter((u) => u.i1).length;
    $("comp-summary").title = `${a.known} known, ${a.learning} learning and ${a.new} new words in these subtitles. `
      + `${i1} lines have only one new word`
      + (a.frequency ? `, ${P.recommended.length} of them a frequent one (up to #${a.frequency.limit.toLocaleString()} of “${a.frequency.title}”).` : ".");
  }
}

function nextRecommended(cur) {
  const next = (P.recommended || []).find((i) => i > cur);
  if (next === undefined) osd("No recommended line after this one");
  else seekToCue(next);
}

function colourOverlay() {
  if (!window.MiningCatMining) return;
  if (P.settings.colors === "off") MiningCatMining.clearColours("overlay");
  else MiningCatMining.colourWords($("sub-primary"), effectiveLanguage(), "overlay");
}

// Indices of the cues shown at time t (several when they overlap).
function activeAt(cues, t) {
  let lo = 0, hi = cues.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (cues[mid].start <= t) lo = mid + 1; else hi = mid;
  }
  const out = [];
  for (let i = lo - 1; i >= 0 && i >= lo - 8; i--) if (cues[i].end > t) out.unshift(i);
  return out;
}

// Index of the last cue that started at time t, -1 before the first one.
function lastStarted(t) {
  let lo = 0, hi = P.cues.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (P.cues[mid].start <= t + 0.001) lo = mid + 1; else hi = mid;
  }
  return lo - 1;
}

function renderLines(box, cues, indices, lookup) {
  box.replaceChildren(...indices.map((i) => {
    const p = document.createElement("p");
    p.textContent = cues[i].text;
    if (lookup) {
      p.dataset.i = String(i);
      p.lang = effectiveLanguage();
      p.classList.toggle("selected", inSelection(i));
    }
    return p;
  }));
}

function update() {
  if (!P.video) return;
  const video = $("video");
  if (P.pauseAt !== null && video.currentTime >= P.pauseAt) {
    P.pauseAt = null;
    video.pause();
  }
  const t = video.currentTime - offset();
  const idx = activeAt(P.cues, t);
  const key = idx.join(",");
  if (key !== P.active) {
    P.active = key;
    renderLines($("sub-primary"), P.cues, idx, true);
    colourOverlay();
    markCurrent(idx);
    if (idx.length && !video.paused && P.settings.auto_pause) P.pauseAt = cueEnd(idx);
  }
  const second = activeAt(P.second, t);
  const secondKey = second.join(",");
  if (secondKey !== P.activeSecond) {
    P.activeSecond = secondKey;
    renderLines($("sub-secondary"), P.second, second, false);
  }
}

const cueEnd = (indices) => Math.max(...indices.map((i) => P.cues[i].end)) + offset() - AUTO_PAUSE_EARLY_S;

function markCurrent(indices) {
  for (const el of $("cues").querySelectorAll(".cue.current")) el.classList.remove("current");
  const first = indices.length ? $("cues").children[indices[0]] : null;
  for (const i of indices) $("cues").children[i]?.classList.add("current");
  if (first && !document.body.classList.contains("no-list") && Date.now() > P.listHoldUntil) {
    first.scrollIntoView({ block: "center", behavior: "smooth" });
  }
}

function loop() {
  update();
  saveProgress();
  if ($("video").paused) { P.looping = false; return; }
  requestAnimationFrame(loop);
}

function onPlay() {
  // auto-pause also applies to the subtitle already on screen, unless playback starts again at its very end
  if (P.settings.auto_pause && P.active) {
    const end = cueEnd(P.active.split(",").map(Number));
    if ($("video").currentTime < end - 0.1) P.pauseAt = end;
  }
  if (!P.looping) { P.looping = true; requestAnimationFrame(loop); }
}

function seekTo(time) {
  const video = $("video");
  video.currentTime = Math.max(0, Math.min(time, (video.duration || Infinity) - 0.05));
  P.pauseAt = null;
  P.active = null;
  update();
}

function seekToCue(i) {
  if (i < 0 || i >= P.cues.length) return;
  seekTo(P.cues[i].start + offset());
}

// Plays one subtitle and stops at its end (the popup's ▶ Sentence, ↓).
function playCue(i) {
  if (i < 0 || i >= P.cues.length) return;
  seekToCue(i);
  P.pauseAt = P.cues[i].end + offset();
  $("video").play().catch(() => {});
}

// ---------------------------------------------------------------- mining

function cueIndexOf(node) {
  const el = node && (node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement);
  const holder = el && el.closest("[data-i]");
  return holder ? Number(holder.dataset.i) : null;
}

function snapshot(video) {
  const scale = Math.min(1, SCREENSHOT_MAX_WIDTH / video.videoWidth);
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(video.videoWidth * scale);
  canvas.height = Math.round(video.videoHeight * scale);
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  const webp = canvas.toDataURL("image/webp", 0.85);
  if (webp.startsWith("data:image/webp")) return { data: webp, name: "screenshot.webp" };
  return { data: canvas.toDataURL("image/jpeg", 0.85), name: "screenshot.jpg" };
}

// The picture of a line that isn't on screen, taken by the server (a hidden <video> doesn't load reliably in Safari).
async function frameAt(time) {
  return api(`/player/api/videos/${P.video.id}/frame`, { time });
}

// The picture on screen when the looked-up line is the one shown (instant, and exactly what you saw), else the
// middle of the line, from the server. With several lines selected, the clicked line gives the picture.
function getImage(node) {
  const video = $("video");
  if (!P.video || !P.video.video_codec) return null;
  const i = cueIndexOf(node);
  const t = video.currentTime - offset();
  if (video.videoWidth && (i === null || (P.cues[i].start - 0.5 <= t && t <= P.cues[i].end + 0.5))) {
    try { return snapshot(video); } catch { /* e.g. the frame isn't decoded yet: ask the server */ }
  }
  const time = i === null ? video.currentTime : (P.cues[i].start + P.cues[i].end) / 2 + offset();
  return frameAt(time);
}

// ---------------------------------------------------------------- lines selected for a card

// A sentence split across subtitle lines: select its lines in the list (one click per line, the lines in between
// come with them), then look up a word in one of them. The card gets them all, with one piece of audio.
const inSelection = (i) => Boolean(P.selection && i >= P.selection.first && i <= P.selection.last);

function toggleSelect(i) {
  const sel = P.selection;
  if (!sel) P.selection = { first: i, last: i };
  else if (i < sel.first) sel.first = i;
  else if (i > sel.last) sel.last = i;
  else if (sel.first === sel.last) P.selection = null;
  else if (i === sel.first) sel.first += 1;
  else if (i === sel.last) sel.last -= 1;
  else sel.last = i;  // a line in the middle: the selection ends there
  renderSelection();
}

function clearSelection() {
  if (!P.selection) return;
  P.selection = null;
  renderSelection();
}

function renderSelection() {
  const sel = P.selection;
  for (const li of $("cues").children) {
    const on = inSelection(Number(li.dataset.i));
    li.classList.toggle("selected", on);
    li.firstChild.checked = on;
  }
  $("cue-selection").hidden = !sel;
  if (sel) {
    const count = sel.last - sel.first + 1;
    const start = P.cues[sel.first].start, end = rangeEnd(sel);
    $("cue-selection-text").textContent = `${count} line${count > 1 ? "s" : ""} for the next card · `
      + `${formatTime(start)}–${formatTime(end)} (${(end - start).toFixed(1)} s)`;
  }
  P.active = null;  // marks the selected lines over the video too
  update();
}

const rangeEnd = (range) => Math.max(...P.cues.slice(range.first, range.last + 1).map((c) => c.end));

// The lines a lookup in line `node` takes: the selection when the line is in it, else the line alone.
function rangeOf(node) {
  const i = cueIndexOf(node);
  if (i === null || !P.cues[i]) return null;
  return inSelection(i) ? { ...P.selection, clicked: i } : { first: i, last: i, clicked: i };
}

// The selected lines, one per line: two sentences on two lines aren't glued together.
function expandSentence(node, sentence) {
  const r = rangeOf(node);
  if (!r || r.first === r.last) return sentence;
  const before = P.cues.slice(r.first, r.clicked).map((c) => `${c.text}\n`).join("") + sentence.before;
  const after = sentence.after + P.cues.slice(r.clicked + 1, r.last + 1).map((c) => `\n${c.text}`).join("");
  return { text: `${before}${sentence.word}${after}`, before, word: sentence.word, after };
}

// The card's sentence translation: the second subtitles' lines at the time of the line(s), when the settings
// say so. null (no second track, nothing at that time): the sentence is translated offline.
function getTranslation(node) {
  const r = rangeOf(node);
  if (!r || !P.settings.secondary_translation || !P.second.length) return null;
  const start = P.cues[r.first].start, end = rangeEnd(r);
  // the tracks' timings differ a little: a second line counts when it overlaps half of its own span or of the lines'
  const lines = P.second.filter((c) => Math.min(c.end, end) - Math.max(c.start, start) > Math.min(c.end - c.start, end - start) / 2);
  return lines.length ? lines.map((c) => c.text).join("\n") : null;
}

function getSource(node) {
  if (!P.video) return "";
  const r = rangeOf(node);
  const time = r ? P.cues[r.first].start : $("video").currentTime - offset();
  return `${P.video.title} (${formatTime(time, true)})`;
}

async function sentenceClip(text, node) {
  const r = rangeOf(node);
  if (!r) return null;
  const data = await api(`/player/api/videos/${P.video.id}/clip`, { start: P.cues[r.first].start + offset(), end: rangeEnd(r) + offset() });
  return { data: data.data, name: data.name };
}

// For the card creator's waveform: the lines' span in the file, with the settings' margins around it…
function sentenceRange(text, node) {
  const r = rangeOf(node);
  if (!r) return null;
  return { start: P.cues[r.first].start + offset(), end: rangeEnd(r) + offset(),
    before: P.settings.audio_before / 1000, after: P.settings.audio_after / 1000 };
}

// …and any span of the audio, as is: WAV for the waveform, MP3 for the card.
async function audioSpan(start, end, format = "mp3") {
  const data = await api(`/player/api/videos/${P.video.id}/clip`, { start, end, exact: true, format });
  return { data: data.data, name: data.name };
}

function playSentence(text, node) {
  const r = rangeOf(node);
  if (!r) return;
  seekToCue(r.first);
  P.pauseAt = rangeEnd(r) + offset();
  $("video").play().catch(() => {});
}

function pauseForLookup() {
  const video = $("video");
  if (!video.paused) video.pause();
  P.pauseAt = null;
}

// ---------------------------------------------------------------- settings

function syncSettingsForm() {
  const s = P.settings;
  document.documentElement.style.setProperty("--sub-size", `${s.sub_size}px`);
  $("set-sub-size").value = s.sub_size;
  $("out-sub-size").textContent = `${s.sub_size}px`;
  for (const b of $("set-display").children) {
    b.setAttribute("aria-pressed", String(b.dataset.value === s.sub_display));
    b.classList.toggle("active", b.dataset.value === s.sub_display);
  }
  $("subs").classList.toggle("blur", s.sub_display === "blur");
  $("subs").classList.toggle("hidden", s.sub_display === "hidden");
  $("set-auto-pause").checked = s.auto_pause;
  $("set-secondary-translation").checked = s.secondary_translation;
  $("set-fullwidth-punctuation").checked = s.fullwidth_punctuation;
  $("punctuation-setting").hidden = !["zh", "yue", "nan", "ja"].includes(STUDY.id);
  $("set-colors").value = s.colors;
  $("set-audio-before").value = s.audio_before;
  $("set-audio-after").value = s.audio_after;
  document.body.classList.toggle("no-list", !s.list);
}

function syncVideoSettings() {
  const v = P.video;
  // Only the forms of the language studied (Mandarin: traditional or simplified characters).
  const detected = STUDY.tags.find((t) => t.tag === v.language);
  $("set-language").replaceChildren(
    new Option(`Automatic (${detected ? detected.label : v.language || STUDY.name})`, ""),
    ...STUDY.tags.map((t) => new Option(t.label, t.tag)),
  );
  // a tag set elsewhere (zh-TW from the converter) is kept, under its own name
  const lang = P.prefs.language || "";
  if (lang && !STUDY.tags.some((t) => t.tag === lang)) $("set-language").append(new Option(lang, lang));
  $("set-language").value = lang;
  $("language-setting").hidden = STUDY.tags.length <= 1;
  const options = (none) => [new Option(none, ""), ...(v.tracks || []).map((t) => new Option(`${t.label} · ${t.cues} lines`, t.id))];
  $("set-primary").replaceChildren(...options("None"));
  $("set-secondary").replaceChildren(...options("None"));
  const from = $("second-from").value;
  $("second-from").replaceChildren(...options("None").slice(1));
  $("second-from").value = (v.tracks || []).some((t) => t.id === from) ? from : (P.prefs.primary || ((v.tracks || [])[0] || {}).id || "");
  syncSecondGenerate();
  $("out-offset").textContent = `${offset() >= 0 ? "+" : ""}${offset().toFixed(1)} s`;
  $("audio-setting").hidden = P.audioTracks.length < 2;
  $("set-audio").replaceChildren(...P.audioTracks.map((t) => new Option(t.label, String(t.index))));
  $("set-audio").value = String(P.prefs.audio_track || 0);
}

// ---------------------------------------------------------------- second subtitles

// "Generate second subtitles": a track translated, in the background, to the language of the settings.
function syncSecondGenerate(job = null) {
  const target = P.translationTarget;
  const running = Boolean(job && job.state === "running");
  const hasTracks = Boolean(P.video && P.video.tracks && P.video.tracks.length);
  $("second-from").disabled = running || !hasTracks;
  $("second-generate-btn").disabled = running || !hasTracks || !target;
  const status = $("second-generate-status");
  status.classList.toggle("text-danger", Boolean(job && job.state === "error"));
  if (running) {
    status.textContent = job.total ? `Translating to ${job.target} with ${job.model}… ${job.done}/${job.total} lines` : `Preparing ${job.model}…`;
  } else if (job && job.state === "error") {
    status.textContent = `The subtitles couldn't be translated:\n${job.error}`;
  } else if (!target) {
    status.replaceChildren("Choose the language sentences are translated to in ", Object.assign(document.createElement("a"), { href: "/settings/#translation", target: "_blank", textContent: "Settings › Translation" }), " first.");
  } else if (!hasTracks) {
    status.textContent = "Add subtitles to translate first.";
  } else {
    status.replaceChildren(`Second subtitles will be generated in ${target.name} with ${P.translationModel} (`,
      Object.assign(document.createElement("a"), { href: "/settings/#translation", target: "_blank", textContent: "change" }), ").");
  }
}

async function generateSecondSubtitles() {
  const trackId = $("second-from").value;
  if (!P.video || !trackId) return;
  try {
    const { translation } = await api(`/player/api/videos/${P.video.id}/subtitles/${trackId}/translate`, {});
    syncSecondGenerate(translation);
    followTranslation(P.token);
  } catch (err) { showError(err); }
}

// Follows the translation of the video's subtitles (also one started before the page was reloaded); once it's done,
// the new track becomes the second subtitles.
async function followTranslation(token) {
  clearTimeout(P.translationTimer);
  try {
    const data = await api(`/player/api/videos/${P.video.id}/translation`);
    if (token !== P.token) return;
    const job = data.translation;
    if (job.state === "running") {
      syncSecondGenerate(job);
      P.translationTimer = setTimeout(() => followTranslation(token), POLL_MS);
      return;
    }
    if (job.state === "done" && job.track && !P.video.tracks.some((t) => t.id === job.track.id)) {
      P.video.tracks = data.tracks;
      P.prefs = data.prefs;
      syncVideoSettings();
      await loadTracks();
      osd(`Second subtitles: ${job.track.label}`);
    }
    syncSecondGenerate(job.state === "error" ? job : null);
  } catch { /* the video was closed or deleted */ }
}

async function loadTranslationTarget() {
  try {
    const { languages, chosen, model } = await api("/api/translate/languages");
    P.translationTarget = languages.find((l) => l.id === chosen) || null;
    P.translationModel = model;
  } catch { P.translationTarget = null; }
}

async function saveSettings(changes) {
  Object.assign(P.settings, changes);
  syncSettingsForm();
  try { P.settings = await api("/player/api/settings", changes); } catch (err) { showError(err); }
  syncSettingsForm();
}

async function savePrefs(changes) {
  try {
    P.prefs = await api(`/player/api/videos/${P.video.id}/prefs`, changes);
  } catch (err) { showError(err); }
}

function osd(text) {
  const box = $("osd");
  box.textContent = text;
  box.classList.add("show");
  clearTimeout(P.osdTimer);
  P.osdTimer = setTimeout(() => box.classList.remove("show"), 1400);
}

const offsetTimer = { id: null };
function shiftOffset(delta) {
  const value = delta === 0 ? 0 : Math.round((offset() + delta) * 10) / 10;
  P.prefs.offset = value;
  $("out-offset").textContent = `${value >= 0 ? "+" : ""}${value.toFixed(1)} s`;
  osd(`Subtitle timing ${value >= 0 ? "+" : ""}${value.toFixed(1)} s`);
  P.active = P.activeSecond = null;
  update();
  clearTimeout(offsetTimer.id);
  offsetTimer.id = setTimeout(() => savePrefs({ offset: value }), 500);
}

const DISPLAYS = ["shown", "blur", "hidden"];
const DISPLAY_LABELS = { shown: "Subtitles shown", blur: "Subtitles blurred (hover to read)", hidden: "Subtitles hidden" };

function cycleDisplay() {
  const next = DISPLAYS[(DISPLAYS.indexOf(P.settings.sub_display) + 1) % DISPLAYS.length];
  saveSettings({ sub_display: next });
  osd(DISPLAY_LABELS[next]);
}

function toggleAutoPause() {
  saveSettings({ auto_pause: !P.settings.auto_pause });
  P.pauseAt = null;
  osd(P.settings.auto_pause ? "Auto-pause on" : "Auto-pause off");
}

function toggleList() {
  saveSettings({ list: !P.settings.list });
}

// The settings panel (a Bootstrap offcanvas)
function togglePanel(force) {
  const panel = bootstrap.Offcanvas.getOrCreateInstance($("settings-panel"));
  if (force === undefined) panel.toggle();
  else if (force) panel.show();
  else panel.hide();
}

// The whole page goes fullscreen (not the <video>), so that the subtitles and the popup stay visible.
function toggleFullscreen() {
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  else document.documentElement.requestFullscreen().catch(() => {});
}

function changeSpeed(delta) {
  const video = $("video");
  video.playbackRate = Math.max(0.25, Math.min(3, Math.round((video.playbackRate + delta) * 100) / 100));
  osd(`Speed ${video.playbackRate}×`);
}

function wireSettings() {
  $("settings-btn").addEventListener("click", () => togglePanel());
  $("list-btn").addEventListener("click", toggleList);
  $("i1-only").addEventListener("change", (e) => $("cues").classList.toggle("i1-only", e.target.checked));
  if (window.MiningCatMining) MiningCatMining.onAnalysis(showComprehension);
  $("fullscreen-btn").addEventListener("click", toggleFullscreen);
  $("set-sub-size").addEventListener("input", (e) => {
    document.documentElement.style.setProperty("--sub-size", `${e.target.value}px`);
    $("out-sub-size").textContent = `${e.target.value}px`;
  });
  $("set-sub-size").addEventListener("change", (e) => saveSettings({ sub_size: Number(e.target.value) }));
  for (const b of $("set-display").children) b.addEventListener("click", () => saveSettings({ sub_display: b.dataset.value }));
  $("set-auto-pause").addEventListener("change", (e) => { saveSettings({ auto_pause: e.target.checked }); P.pauseAt = null; });
  $("set-colors").addEventListener("change", async (e) => {
    await saveSettings({ colors: e.target.value });
    colourList();
    colourOverlay();
  });
  $("set-language").addEventListener("change", async (e) => {
    await savePrefs({ language: e.target.value });
    if (P.settings.fullwidth_punctuation) return loadTracks();  // the punctuation of the language chosen
    renderList();
    P.active = null;
    update();
  });
  $("set-primary").addEventListener("change", async (e) => {
    await savePrefs({ primary: e.target.value });
    await loadTracks();
  });
  $("set-secondary").addEventListener("change", async (e) => {
    await savePrefs({ secondary: e.target.value });
    await loadTracks();
  });
  $("set-fullwidth-punctuation").addEventListener("change", async (e) => {
    await saveSettings({ fullwidth_punctuation: e.target.checked });
    if (P.video) await loadTracks();
  });
  $("set-secondary-translation").addEventListener("change", (e) => saveSettings({ secondary_translation: e.target.checked }));
  $("second-generate-btn").addEventListener("click", generateSecondSubtitles);
  // the language of the translations may have been changed in the settings meanwhile
  $("settings-panel").addEventListener("show.bs.offcanvas", async () => {
    await loadTranslationTarget();
    if (P.video) followTranslation(P.token);
  });
  for (const [id, key] of [["set-audio-before", "audio_before"], ["set-audio-after", "audio_after"]]) {
    $(id).addEventListener("change", (e) => saveSettings({ [key]: Number(e.target.value) }));
  }
  for (const b of document.querySelectorAll("[data-offset]")) b.addEventListener("click", () => shiftOffset(Number(b.dataset.offset)));
  $("set-audio").addEventListener("change", async (e) => {
    await savePrefs({ audio_track: Number(e.target.value) });
    prepareAgain(null);
  });
  $("add-subs").addEventListener("click", () => $("subs-input").click());
  $("subs-input").addEventListener("change", (e) => { addSubtitles([...e.target.files]); e.target.value = ""; });
  $("remove-subs").addEventListener("click", async () => {
    const id = $("set-primary").value;
    const track = P.video.tracks.find((t) => t.id === id);
    if (!track) return;
    const ok = await showDialog("Remove subtitles", `Remove the subtitles “${track.label}” from this video?`,
      [{ label: "Cancel", value: false }, { label: "Remove", value: true, primary: true }]);
    if (!ok) return;
    try {
      const data = await api(`/player/api/videos/${P.video.id}/subtitles/${id}/delete`, {});
      P.video.tracks = data.tracks;
      P.prefs = data.prefs;
      syncVideoSettings();
      await loadTracks();
    } catch (err) { showError(err); }
  });
}

async function addSubtitles(files) {
  const subs = files.filter((f) => SUBTITLE_EXT.test(f.name));
  if (!subs.length || !P.video) return;
  try {
    const data = await uploadSubtitles(P.video.id, subs);
    P.video.tracks = data.tracks;
    if (data.added.length) {
      P.prefs = await api(`/player/api/videos/${P.video.id}/prefs`, { primary: data.added[0].id });
    }
    syncVideoSettings();
    await loadTracks();
    if (data.errors.length) showDialog("Subtitles", data.errors.join("\n"));
    else osd(`${data.added.length} subtitle track${data.added.length > 1 ? "s" : ""} added`);
  } catch (err) { showError(err); }
}

// ---------------------------------------------------------------- keyboard & wiring

function isEditing(target) {
  return target && target.closest && (target.closest("input, select, textarea, .modal") || target.isContentEditable);
}

function onKey(e) {
  if ($("watch").hidden || !P.video || e.ctrlKey || e.metaKey || e.altKey || isEditing(e.target)) return;
  const video = $("video");
  const popupOpen = window.MiningCatMining && MiningCatMining.isOpen();
  if (popupOpen && e.key !== " ") return;  // the popup's own keys (mining.js)
  const t = video.currentTime - offset();
  const cur = lastStarted(t);
  const inside = cur >= 0 && P.cues[cur].end > t;
  const actions = {
    " ": () => {
      if (popupOpen) MiningCatMining.hide();
      if (video.paused) video.play().catch(() => {}); else video.pause();
    },
    ArrowLeft: () => (e.shiftKey ? seekTo(video.currentTime - SEEK_STEP_S) : seekToCue(inside ? cur - 1 : cur)),
    ArrowRight: () => (e.shiftKey ? seekTo(video.currentTime + SEEK_STEP_S) : seekToCue(cur + 1)),
    ArrowDown: () => playCue(Math.max(0, cur)),
    "[": () => shiftOffset(-0.1),
    "]": () => shiftOffset(0.1),
    "-": () => changeSpeed(-0.1),
    "+": () => changeSpeed(0.1),
    "=": () => changeSpeed(0.1),
    s: cycleDisplay, S: cycleDisplay,
    p: toggleAutoPause, P: toggleAutoPause,
    l: toggleList, L: toggleList,
    n: () => nextRecommended(cur), N: () => nextRecommended(cur),
    f: toggleFullscreen, F: toggleFullscreen,
    Escape: clearSelection,
  };
  const action = actions[e.key];
  if (!action) return;
  e.preventDefault();
  e.stopPropagation();  // the <video>'s own keys, when it has the focus, would play and pause it a second time
  action();
}

function wireWatch() {
  const video = $("video");
  video.addEventListener("loadedmetadata", onLoadedMetadata);
  video.addEventListener("play", onPlay);
  video.addEventListener("pause", () => saveProgress(true));
  video.addEventListener("seeked", () => { P.active = null; update(); });
  video.addEventListener("timeupdate", update);
  video.addEventListener("error", () => {
    if (P.video && P.video.status === "ready" && video.getAttribute("src")) unplayable();
  });
  // a double click would put the <video> alone in fullscreen, without the subtitles
  video.addEventListener("dblclick", (e) => { e.preventDefault(); toggleFullscreen(); });
  document.addEventListener("fullscreenchange", () => {
    if (document.fullscreenElement === video) {
      document.exitFullscreen().catch(() => {});
      osd("Press F (or the fullscreen button) for fullscreen with the subtitles");
    }
    document.body.classList.toggle("fullscreen", document.fullscreenElement === document.documentElement);
  });
  // the clicked subtitle mustn't move on while it's looked up
  $("sub-primary").addEventListener("pointerdown", (e) => { if (e.button === 0) pauseForLookup(); });
  $("cues").addEventListener("click", (e) => {
    const time = e.target.closest(".cue-time");
    if (time) seekToCue(Number(time.closest(".cue").dataset.i));
    const select = e.target.closest(".cue-select");
    if (select) toggleSelect(Number(select.closest(".cue").dataset.i));
  });
  for (const type of ["wheel", "touchmove"]) {
    $("cue-panel").addEventListener(type, () => { P.listHoldUntil = Date.now() + 4000; }, { passive: true });
  }
  $("cue-selection-clear").addEventListener("click", clearSelection);
  $("back").addEventListener("click", (e) => {
    e.preventDefault();
    history.pushState({}, "", "/player/");
    route();
  });
  document.addEventListener("keydown", onKey, true);  // before the focused <video> gets the key
  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("drop", (e) => {
    e.preventDefault();
    if (!$("watch").hidden && e.dataTransfer.files.length) addSubtitles([...e.dataTransfer.files]);
  });
  window.addEventListener("pagehide", () => saveProgress(true));
}

// ---------------------------------------------------------------- routing

async function route() {
  const match = location.pathname.match(/^\/player\/([0-9a-f]{16})\/?$/);
  try {
    if (match) await openVideo(match[1]);
    else await showLibrary();
  } catch (err) {
    await showError(err);
    if (match) { history.replaceState({}, "", "/player/"); showLibrary(); }
  }
}

async function init() {
  P.settings = await api("/player/api/settings");
  await loadTranslationTarget();
  syncSettingsForm();
  wireLibrary();
  wireSettings();
  wireWatch();
  if (window.MiningCatMining) {
    MiningCatMining.attach($("watch-body"), {
      getLanguage: effectiveLanguage,
      getSource,
      getMode: () => "click",
      isVertical: () => false,
      blockSentence: true,
      hasAudio: () => Boolean(P.video && P.video.audio && P.video.audio.length),
      playSentence,
      expandSentence,
      getTranslation,
      onCard: clearSelection,
      sentenceClip,
      sentenceRange,
      audioSpan,
      getImage,
      onLookup: pauseForLookup,
    });
  }
  window.addEventListener("popstate", route);
  route();
}

document.addEventListener("DOMContentLoaded", init);

// exposed for debugging and tests
window.MiningCatPlayer = { state: P, activeAt, seekTo, playCue };
