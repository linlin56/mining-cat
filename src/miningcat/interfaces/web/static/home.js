// MiningCat home page: choose the language you study, then a screen.
"use strict";

const $ = (id) => document.getElementById(id);

async function api(path, body) {
  const init = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json", "X-MiningCat": "1" }, body: JSON.stringify(body),
  };
  const res = await fetch(path, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(data.error || `Request failed (${res.status})`), { title: data.title || "Error" });
  return data;
}

const showError = (err) => MiningCatUI.dialog(err.title || "Error", err.message || String(err));

// The page that sent the user here to choose a language first (see application/study_language.py).
function nextPage() {
  const next = new URLSearchParams(location.search).get("next") || "";
  return /^\/[a-z]+\/[^\s]*$/.test(next) ? next : null;
}

function renderHub(current) {
  $("hub").hidden = false;
  $("picker").hidden = true;
  $("hub-native").textContent = current.native;
  $("hub-native").lang = current.tag;
  $("hub-name").textContent = current.name;
  const converter = $("tile-converter");
  converter.classList.toggle("opacity-50", !current.converter);
  converter.querySelector(".card-text").textContent = current.converter
    ? "Audiobooks, ebooks, videos and games: subtitles, audio, frequency lists."
    : `Not available for ${current.name} yet.`;
}

function renderPicker(languages, current) {
  $("hub").hidden = true;
  $("picker").hidden = false;
  $("languages").replaceChildren(...languages.map((l) => {
    const stats = [l.dictionaries ? `${l.dictionaries} dictionar${l.dictionaries > 1 ? "ies" : "y"}` : null,
      l.words ? `${l.words.toLocaleString()} words` : null].filter(Boolean).join(" · ");
    const button = document.createElement("button");
    button.type = "button";
    button.className = `btn btn-outline-primary w-100 h-100 text-start d-flex flex-column p-3${current && current.id === l.id ? " active" : ""}`;
    const native = Object.assign(document.createElement("span"), { className: "fs-4 lh-sm", lang: l.tag, textContent: l.native });
    const name = Object.assign(document.createElement("strong"), { textContent: l.name });
    const meta = Object.assign(document.createElement("small"), { className: "opacity-75", textContent: stats || " " });
    button.append(native, name, meta);
    button.addEventListener("click", () => choose(l.id));
    const col = Object.assign(document.createElement("div"), { className: "col" });
    col.append(button);
    return col;
  }));
}

async function choose(id) {
  try {
    const { current } = await api("/api/profile", { language: id });
    const next = nextPage();
    if (next) { location.href = next; return; }
    history.replaceState(null, "", "/");
    renderHub(current);
  } catch (err) { showError(err); }
}

async function init() {
  try {
    const { current, languages } = await api("/api/profile");
    if (current) renderHub(current);
    else renderPicker(languages, null);
    $("change-language").addEventListener("click", () => renderPicker(languages, current));
  } catch (err) { showError(err); }
}

document.addEventListener("DOMContentLoaded", init);
