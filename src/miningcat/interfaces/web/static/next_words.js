// MiningCat Next words page: the most frequent words of the frequency lists not studied yet (api/frequency/next).
"use strict";

const $ = (id) => document.getElementById(id);
const STUDY = document.body.dataset.study;
let loads = 0;  // the number of the last load: an older one that answers later is ignored

async function api(path, body) {
  const init = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json", "X-MiningCat": "1" }, body: JSON.stringify(body),
  };
  const res = await fetch(path, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(data.error || `Request failed (${res.status})`), { title: data.title || "Error" });
  return data;
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) if (c !== null && c !== undefined && c !== false) node.append(c);
  return node;
}

const icon = (name) => el("i", { class: `bi bi-${name}`, "aria-hidden": "true" });
const showError = (err) => MiningCatUI.dialog(err.title || "Error", err.message || String(err));
const message = (text) => el("tr", {}, el("td", { colspan: "6", class: "text-body-secondary text-center py-4", text }));

async function setStatus(word, status, buttons) {
  for (const b of buttons) b.disabled = true;
  try {
    await api("/api/words/status", { language: STUDY, expression: word.expression, reading: "", status });
    await load();
  } catch (err) {
    for (const b of buttons) b.disabled = false;
    showError(err);
  }
}

function row(word, i) {
  const buttons = [];
  const button = (status, label, name) => {
    const b = el("button", {
      type: "button", class: "btn btn-sm btn-link link-secondary p-0", title: label, "aria-label": `${label}: ${word.expression}`,
      onclick: () => setStatus(word, status, buttons),
    }, icon(name));
    buttons.push(b);
    return b;
  };
  return el("tr", {},
    el("td", { class: "text-end text-body-secondary", text: String(i + 1) }),
    el("td", { class: "text-end font-monospace small", text: `#${word.rank.toLocaleString()}` }),
    el("td", { class: "fs-5", lang: STUDY, text: word.expression }),
    el("td", { class: "text-nowrap", text: word.reading || "—" }),
    el("td", { class: "small", text: word.meaning || "—" }),
    el("td", { class: "text-end text-nowrap" },
      el("div", { class: "d-inline-flex gap-3" },
        button("known", "Mark known", "check2-circle"), button("ignored", "Ignore", "eye-slash"))));
}

async function load() {
  const body = $("next-words");
  const current = ++loads;
  let data;
  try {
    data = await api(`/api/frequency/next?language=${encodeURIComponent(STUDY)}`);
  } catch (err) {
    if (current !== loads) return;
    body.replaceChildren(message("Couldn't load the words."));
    showError(err);
    return;
  }
  if (current !== loads) return;
  const { frontier, words } = data;
  if (!frontier) {
    $("next-summary").textContent = "";
    body.replaceChildren(message("No frequency list used: import or tick one in Settings › Dictionaries."));
    return;
  }
  const several = frontier.dictionaries.length > 1;
  $("next-summary").textContent = `${several ? "Lists" : "List"}: ${frontier.title} · you know ${frontier.known.toLocaleString()} `
    + `of its ${frontier.words.toLocaleString()} words.`;
  body.replaceChildren(...(words.length ? words.map(row) : [message("You have every word of these lists.")]));
}

if (STUDY) load();
else $("next-words").replaceChildren(message("Choose the language you study on the home page first."));
