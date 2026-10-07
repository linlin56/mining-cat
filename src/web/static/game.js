// MiningCat video game page: the captures of `main.py game serve` (started from the converter's
// "Video game / Screen share" source), with the dictionary popup, word colours and the card creator.
// The capture server pushes each capture through its websocket; its screenshot becomes the card's image.
"use strict";

const $ = (id) => document.getElementById(id);

const G = {
  pageUrl: null,     // the capture server, e.g. http://127.0.0.1:6677/
  language: null,    // BCP-47 tag of the game's language
  socket: null,
  count: 0,
  images: new WeakMap(),  // capture element -> screenshot data URL
  colourTimer: null,
};

function setStatus(text, live = false) {
  $("status").textContent = text;
  $("status").classList.toggle("live", live);
}

function resetFeed() {
  for (const el of document.querySelectorAll(".capture")) el.remove();
  G.count = 0;
  $("count").textContent = "";
  $("empty").hidden = false;
  $("empty").innerHTML = "Waiting for a capture.<br>Press the capture key in the game, or click <b>Capture</b> above.<br>"
    + "Click a word to look it up, then <b>+ Card</b>: the screenshot goes on the card.";
}

// Colours every line again once captures stop arriving (cheap: segmentations are cached by the server).
function scheduleColours() {
  clearTimeout(G.colourTimer);
  G.colourTimer = setTimeout(() => MiningCatMining.colourWords($("feed"), G.language), 300);
}

// Captures whose every word is known but one new word (i+1) are marked: the best ones to make a card with.
function markRecommended(key) {
  if (key !== "main") return;
  const a = MiningCatMining.analyse("main", (node) => node.parentElement && node.parentElement.closest(".capture"));
  for (const article of $("feed").querySelectorAll(".capture")) {
    article.classList.remove("i1");
    article.removeAttribute("title");
  }
  for (const unit of a ? a.units : []) {
    if (!unit.recommended) continue;
    unit.element.classList.add("i1");
    unit.element.title = `Recommended: “${unit.targetRange.toString()}” is the only new word`;
  }
}

function addCapture(data) {
  $("empty").hidden = true;
  const article = document.createElement("article");
  article.className = "capture";
  const meta = document.createElement("div");
  meta.className = "capture-meta";
  // shown by CSS: not text, so that it's neither coloured nor looked up
  meta.dataset.meta = `${data.ts} · ${data.ms} ms`;
  const img = document.createElement("img");
  img.className = "capture-shot";
  img.src = data.image;
  img.alt = "";
  const line = document.createElement("p");
  line.className = "capture-line";
  line.lang = G.language;
  line.textContent = data.text;
  article.append(meta, img, line);
  G.images.set(article, data.image);
  const stick = window.innerHeight + window.scrollY >= document.body.offsetHeight - 80;
  $("feed").append(article);
  G.count += 1;
  $("count").textContent = `${G.count} capture${G.count > 1 ? "s" : ""}`;
  if (stick) article.scrollIntoView({ behavior: "smooth", block: "end" });
  scheduleColours();
}

function connect() {
  const socket = new WebSocket(`${G.pageUrl.replace(/^http/, "ws")}ws`);
  G.socket = socket;
  socket.onopen = () => setStatus("listening", true);
  socket.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.type === "clear") resetFeed();
    else if (data.type === "capture") addCapture(data);
  };
  socket.onclose = () => {
    setStatus("capture stopped - waiting for it to start again");
    setTimeout(waitForCapture, 2000);
  };
}

// The capture server only answers while the capture runs: wait for it, and learn its language.
async function waitForCapture() {
  try {
    const state = await MiningCatMining.api("/api/game/state");
    G.pageUrl = state.page_url;
    if (state.running && state.language_tag) {
      G.language = state.language_tag;
      setStatus("connecting…");
      connect();
      return;
    }
    setStatus("the capture isn't running: start it from MiningCat (Video game / Screen share)");
  } catch {
    setStatus("MiningCat isn't answering");
  }
  setTimeout(waitForCapture, 2000);
}

// The capture server has no CORS headers: these requests are fire-and-forget ("no-cors").
function post(path) {
  if (G.pageUrl) fetch(G.pageUrl + path, { method: "POST", mode: "no-cors" }).catch(() => {});
}

function init() {
  const dark = matchMedia("(prefers-color-scheme: dark)");
  const theme = () => document.body.classList.toggle("theme-dark", dark.matches);
  theme();
  dark.addEventListener("change", theme);
  resetFeed();
  $("capture").addEventListener("click", () => post("capture"));
  $("clear").addEventListener("click", () => post("clear"));
  MiningCatMining.onAnalysis(markRecommended);
  MiningCatMining.attach($("feed"), {
    getLanguage: () => G.language || "und",
    getSource: () => "Video game",
    getMode: () => "click",
    isVertical: () => false,
    getImage: (node) => {
      const article = node.parentElement && node.parentElement.closest(".capture");
      const data = article && G.images.get(article);
      return data ? { data, name: "screenshot.webp" } : null;
    },
  });
  waitForCapture();
}

document.addEventListener("DOMContentLoaded", init);
