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

function showError(err) {
  $("dialog-title").textContent = err.title || "Error";
  $("dialog-message").textContent = err.message || String(err);
  $("dialog").showModal();
}

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
  converter.classList.toggle("unavailable", !current.converter);
  converter.querySelector("span").textContent = current.converter
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
    button.className = `language${current && current.id === l.id ? " current" : ""}`;
    const native = Object.assign(document.createElement("span"), { className: "language-native", lang: l.tag, textContent: l.native });
    const name = Object.assign(document.createElement("strong"), { textContent: l.name });
    const meta = Object.assign(document.createElement("small"), { className: "dim", textContent: stats || " " });
    button.append(native, name, meta);
    button.addEventListener("click", () => choose(l.id));
    return button;
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
