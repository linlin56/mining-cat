// MiningCat e-reader inbox: the words sent from KOReader, each with its sentence. The sentences are read like the
// Clipboard (dictionary popup, word colours, card creator: mining.js); once a card is made from a sentence, it
// leaves the inbox.
"use strict";

const $ = (id) => document.getElementById(id);

const STORE_TAG = "miningcat-inbox-tag";

const I = {
  study: null,
  items: new Map(),  // id → item
};

function load(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}

function store(key, value) {
  try { localStorage.setItem(key, value); } catch { /* blocked: the choice just isn't kept */ }
}

const api = (path, body) => MiningCatMining.api(path, body);
const showError = (err) => MiningCatUI.dialog(err.title || "E-reader", err.message || String(err));

function language() {
  return $("language").value || I.study.tag;
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else node.setAttribute(key, value);
  }
  node.append(...children.filter((c) => c != null));
  return node;
}

function when(seconds) {
  return new Date(seconds * 1000).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function source(item) {
  return [item.book, item.location].filter(Boolean).join(" · ");
}

// The sentence, the word looked up on the e-reader underlined (its first occurrence).
function sentenceNode(item) {
  const p = el("p", { class: "mc-text fs-4 lh-lg mb-2", lang: language() });
  const at = item.sentence.indexOf(item.word);
  if (at < 0) {
    p.textContent = item.sentence;
    return p;
  }
  p.append(item.sentence.slice(0, at), el("span", { class: "mc-inbox-word", text: item.word }),
    item.sentence.slice(at + item.word.length));
  return p;
}

function itemNode(item) {
  const dismiss = el("button", { type: "button", class: "btn btn-sm btn-link link-secondary p-0 ms-auto", title: "Remove it without making a card" },
    el("i", { class: "bi bi-x-lg", "aria-hidden": "true" }), " Dismiss");
  dismiss.addEventListener("click", () => remove(item.id));
  return el("article", { class: "card mb-3", "data-id": String(item.id) },
    el("div", { class: "card-body" },
      sentenceNode(item),
      el("div", { class: "d-flex flex-wrap align-items-baseline gap-2 small text-body-secondary", "data-mc-ignore": "" },
        item.book ? el("span", {}, el("i", { class: "bi bi-book me-1", "aria-hidden": "true" }), source(item)) : null,
        el("span", { text: when(item.sent) }),
        dismiss)));
}

function showCount() {
  const n = I.items.size;
  $("count").textContent = n ? `${n} word${n > 1 ? "s" : ""} waiting` : "";
  $("empty").hidden = n > 0;
}

function render() {
  MiningCatMining.hide();
  const box = $("items");
  box.replaceChildren(...[...I.items.values()].map(itemNode));
  showCount();
  MiningCatMining.colourWords(box, language(), "inbox");
}

// Adds the words sent since, and drops those gone: the sentences already shown stay, so that an open popup or card
// creator keeps its sentence.
async function refresh() {
  let items;
  try {
    ({ items } = await api(`/api/inbox?language=${encodeURIComponent(I.study.id)}`));
  } catch (err) { showError(err); return; }
  const ids = new Set(items.map((item) => item.id));
  for (const id of [...I.items.keys()]) {
    if (ids.has(id)) continue;
    I.items.delete(id);
    const node = $("items").querySelector(`[data-id="${id}"]`);
    if (node) node.remove();
  }
  const added = items.filter((item) => !I.items.has(item.id));
  for (const item of added) {
    I.items.set(item.id, item);
    $("items").append(itemNode(item));
  }
  showCount();
  if (added.length) MiningCatMining.colourWords($("items"), language(), "inbox");
}

async function remove(id) {
  try {
    await api(`/api/inbox/${id}/delete`, {});
  } catch (err) { showError(err); return; }
  I.items.delete(id);
  const node = $("items").querySelector(`[data-id="${id}"]`);
  if (node) node.remove();
  showCount();
}

function itemOf(node) {
  const article = node && (node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement).closest("[data-id]");
  return article ? I.items.get(Number(article.dataset.id)) : null;
}

function init() {
  I.study = JSON.parse(document.body.dataset.study || "null") || { id: "", tag: "und", tags: [] };

  // Chinese: traditional or simplified characters
  const select = $("language");
  for (const { tag, label } of I.study.tags) select.append(new Option(label, tag));
  select.hidden = I.study.tags.length < 2;
  const saved = load(STORE_TAG);
  if (I.study.tags.some((t) => t.tag === saved)) select.value = saved;
  select.addEventListener("change", () => { store(STORE_TAG, select.value); render(); });

  $("refresh").addEventListener("click", refresh);
  MiningCatMining.attach($("items"), {
    getLanguage: language,
    getSource: (node) => { const item = itemOf(node); return item && item.book ? source(item) : "E-reader"; },
    getMode: () => "click",
    isVertical: () => false,
    // The card's sentence is all the text sent: the context chosen on the e-reader.
    blockSentence: true,
    onCard: (card, node) => { const item = itemOf(node); if (item) remove(item.id); },
  });
  refresh();
}

document.addEventListener("DOMContentLoaded", init);
// Back on the page: the words sent meanwhile show up.
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && I.study) refresh();
});
