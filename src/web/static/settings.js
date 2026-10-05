// MiningCat Settings page: dictionaries, languages & words, Anki, cards.
"use strict";

const $ = (id) => document.getElementById(id);

const S = { languages: [], anki: { decks: [], models: [], connected: false }, config: null, cardFields: {} };

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

function dialog(title, message, buttons = [{ label: "OK", value: true, primary: true }]) {
  const dlg = $("dialog");
  $("dialog-title").textContent = title;
  $("dialog-message").textContent = message;
  $("dialog-actions").replaceChildren(...buttons.map((b) => el("button", { class: b.primary ? "btn btn-primary" : "btn", value: String(b.value), text: b.label })));
  return new Promise((resolve) => {
    dlg.addEventListener("close", () => resolve(dlg.returnValue === "true"), { once: true });
    dlg.returnValue = "false";
    dlg.showModal();
  });
}
const showError = (err) => dialog(err.title || "Error", err.message || String(err));
const confirmBox = (title, message, label) => dialog(title, message, [{ label: "Cancel", value: false }, { label, value: true, primary: true }]);

const langName = (id) => (S.languages.find((l) => l.id === id) || { name: id }).name;

function options(select, values, value) {
  select.replaceChildren(...values.map((v) => (Array.isArray(v) ? new Option(v[1], v[0]) : new Option(v, v))));
  if (value !== undefined) select.value = value;
}

// ---------------------------------------------------------------- tabs

function showTab() {
  const name = (location.hash || "#dictionaries").slice(1);
  for (const a of document.querySelectorAll(".tabs a")) a.setAttribute("aria-selected", String(a.dataset.tab === name));
  for (const p of document.querySelectorAll(".tab-panel")) p.hidden = p.id !== `tab-${name}`;
  if (name === "cards") loadCards();
  if (name === "languages") loadWords();
  if (name === "anki") refreshAnki();
}

// ---------------------------------------------------------------- dictionaries

async function loadDictionaries() {
  const { dictionaries } = await api("/api/dict");
  const box = $("dict-list");
  if (!dictionaries.length) {
    box.replaceChildren(el("p", { class: "empty", text: "No dictionary yet." }));
    return;
  }
  const byLang = {};
  for (const d of dictionaries) (byLang[d.language] = byLang[d.language] || []).push(d);
  box.replaceChildren(...Object.entries(byLang).map(([lang, list]) => el("div", { class: "dict-group" },
    el("h3", { text: langName(lang) }),
    ...list.map((d, i) => {
      const enabled = el("input", { type: "checkbox", checked: Boolean(d.enabled), "aria-label": `Use ${d.title}` });
      enabled.addEventListener("change", async () => {
        try { await api(`/api/dict/${d.id}`, { enabled: enabled.checked }); loadDictionaries(); } catch (err) { showError(err); }
      });
      const move = async (delta) => {
        const ids = list.map((x) => x.id);
        const j = i + delta;
        [ids[i], ids[j]] = [ids[j], ids[i]];
        const others = dictionaries.filter((x) => x.language !== lang).map((x) => x.id);
        try { await api("/api/dict/reorder", { ids: [...ids, ...others] }); loadDictionaries(); } catch (err) { showError(err); }
      };
      const counts = [d.term_count ? `${d.term_count.toLocaleString()} terms` : null,
        d.kanji_count ? `${d.kanji_count.toLocaleString()} characters` : null,
        d.meta_count ? `${d.meta_count.toLocaleString()} frequency/pitch entries` : null].filter(Boolean).join(" · ");
      return el("div", { class: `dict-item${d.enabled ? "" : " disabled"}` },
        el("label", { class: "check" }, enabled),
        el("div", { class: "dict-name" }, d.title, el("small", { text: [d.revision, counts].filter(Boolean).join(" · ") })),
        el("button", { class: "icon-btn", type: "button", title: "Move up", "aria-label": "Move up", text: "↑", disabled: i === 0, onclick: () => move(-1) }),
        el("button", { class: "icon-btn", type: "button", title: "Move down", "aria-label": "Move down", text: "↓", disabled: i === list.length - 1, onclick: () => move(1) }),
        el("button", {
          class: "icon-btn danger", type: "button", title: "Delete", "aria-label": `Delete ${d.title}`, text: "🗑",
          onclick: async () => {
            if (!(await confirmBox("Delete dictionary", `Delete “${d.title}”? You can import it again later.`, "Delete"))) return;
            try { await api(`/api/dict/${d.id}/delete`, {}); loadDictionaries(); } catch (err) { showError(err); }
          },
        }));
    }))));
}

async function importDictionary(file) {
  if (!file) return;
  const form = new FormData();
  form.append("file", file, file.name);
  form.append("language", $("dict-language").value);
  const progress = $("dict-progress");
  progress.hidden = false;
  $("dict-progress-bar").style.width = "0%";
  $("dict-progress-text").textContent = `Uploading ${file.name}…`;
  $("dict-pick").disabled = true;
  try {
    const res = await fetch("/api/dict/import", { method: "POST", headers: { "X-MiningCat": "1" }, body: form });
    const data = await res.json();
    if (!res.ok) throw Object.assign(new Error(data.error), { title: data.title });
    $("dict-progress-text").textContent = `Importing “${data.title}” (${langName(data.language)})…`;
    for (;;) {
      await new Promise((r) => setTimeout(r, 600));
      const job = await api(`/api/dict/import/${data.job}`);
      $("dict-progress-bar").style.width = `${Math.round(job.progress * 100)}%`;
      if (!job.done) { $("dict-progress-text").textContent = `Importing “${data.title}”: ${job.message}`; continue; }
      if (job.error) throw Object.assign(new Error(job.error), { title: "Import failed" });
      $("dict-progress-text").textContent = `“${data.title}” imported: ${(job.dictionary.term_count || job.dictionary.kanji_count).toLocaleString()} ${job.dictionary.term_count ? "terms" : "characters"}.`;
      break;
    }
    loadDictionaries();
  } catch (err) {
    progress.hidden = true;
    showError(err);
  } finally {
    $("dict-pick").disabled = false;
  }
}

// ---------------------------------------------------------------- languages & words

async function loadLanguages() {
  const data = await api("/api/mining/languages");
  S.languages = data.languages;
  options($("dict-language"), [["", "Detect automatically"], ...S.languages.map((l) => [l.id, l.name])], "");
  options($("words-language"), [["", "All languages"], ...S.languages.map((l) => [l.id, l.name])], "");
  options($("note-language"), S.languages.map((l) => [l.id, l.name]), "zh");

  // Only the languages studied (with a dictionary or words) get settings; Mandarin when there's none yet.
  const chinese = S.languages.filter((l) => l.chinese);
  const shown = chinese.some((l) => l.studied) ? chinese.filter((l) => l.studied) : chinese.filter((l) => l.id === "zh");
  const radios = (language, choices, current, path, key) => {
    const row = el("div", { class: "script-row", role: "radiogroup", "aria-label": language.name }, el("span", { text: language.name }));
    for (const [value, label] of choices) {
      const radio = el("input", { type: "radio", name: `${key}-${language.id}`, value, checked: current === value });
      radio.addEventListener("change", () => api(path, { language: language.id, [key]: value }).catch(showError));
      row.append(el("label", { class: "check" }, radio, label));
    }
    return row;
  };
  $("script-settings").replaceChildren(...shown.map((l) => radios(l,
    [["traditional", "Traditional 繁體"], ["simplified", "Simplified 简体"], ["both", "Both"]], data.scripts[l.id], "/api/mining/script", "script")));
  const mandarin = S.languages.find((l) => l.id === "zh");
  $("reading-settings").replaceChildren(radios(mandarin,
    [["pinyin", "Pinyin (hànyǔ)"], ["zhuyin", "Zhuyin (ㄏㄢˋ ㄩˇ)"]], data.readings.zh, "/api/mining/reading", "system"));

  const counts = $("word-counts");
  const entries = Object.entries(data.counts);
  counts.replaceChildren(entries.length
    ? el("div", { class: "counts" }, ...entries.map(([lang, c]) => el("div", { class: "count-card" },
      el("strong", { text: langName(lang) }),
      `${c.known || 0} known · ${c.learning || 0} learning${c.ignored ? ` · ${c.ignored} ignored` : ""}`)))
    : el("p", { class: "empty", text: "No words yet: look words up in the reader, mark them or make cards." }));
}

async function loadWords() {
  const params = new URLSearchParams();
  if ($("words-filter").value) params.set("status", $("words-filter").value);
  if ($("words-language").value) params.set("language", $("words-language").value);
  const { words } = await api(`/api/words?${params}`);
  const table = $("words-table");
  table.replaceChildren(
    el("thead", {}, el("tr", {}, ...["Word", "Reading", "Language", "Status", "From", ""].map((t) => el("th", { text: t })))),
    el("tbody", {}, ...words.map((w) => el("tr", {},
      el("td", { class: "word", lang: w.language, text: w.expression }),
      el("td", { text: w.reading }),
      el("td", { text: langName(w.language) }),
      el("td", {}, el("span", { class: `pill ${w.status}`, text: w.status })),
      el("td", { text: { manual: "you", card: "card", anki: "Anki" }[w.source] || w.source }),
      el("td", {}, el("button", {
        class: "icon-btn", type: "button", title: "Forget this word", "aria-label": `Forget ${w.expression}`, text: "×",
        onclick: async () => {
          try { await api("/api/words/status", { language: w.language, expression: w.expression, reading: w.reading, status: "new" }); loadWords(); loadLanguages(); }
          catch (err) { showError(err); }
        },
      }))))));
  if (!words.length) table.append(el("tbody", {}, el("tr", {}, el("td", { colspan: "6", class: "empty", text: "No words." }))));
}

// ---------------------------------------------------------------- Anki

async function refreshAnki() {
  const { config, card_fields } = await api("/api/anki/config");
  S.config = config;
  S.cardFields = card_fields;
  $("anki-url").value = config.url;
  $("known-interval").value = config.known_interval;
  renderTranslation();
  $("anki-state").textContent = "Checking Anki…";
  $("anki-state").className = "connection-state";
  S.anki = await api("/api/anki/status");
  const state = $("anki-state");
  if (S.anki.connected) {
    state.textContent = `Connected to Anki (AnkiConnect ${S.anki.version}): ${S.anki.decks.length} decks, ${S.anki.models.length} note types.`;
    state.className = "connection-state ok";
  } else {
    state.textContent = S.anki.error;
    state.className = "connection-state bad";
  }
  renderNoteSetup();
  renderSyncSources();
}

function selectWith(values, value, placeholder) {
  const list = [...values];
  if (value && !list.includes(value)) list.unshift(value);  // keep a saved value even when Anki is closed
  const select = el("select");
  options(select, [["", placeholder], ...list.map((v) => [v, v])], value || "");
  return select;
}

async function renderNoteSetup() {
  const language = $("note-language").value;
  const setup = (S.config.notes || {})[language] || { deck: "", model: "", fields: {}, tags: "mining-cat" };
  const deck = selectWith(S.anki.decks, setup.deck, S.anki.connected ? "Choose a deck" : "Open Anki to list decks");
  const model = selectWith(S.anki.models, setup.model, S.anki.connected ? "Choose a note type" : "Open Anki to list note types");
  deck.id = "note-deck";
  model.id = "note-model";
  $("note-deck").replaceWith(deck);
  $("note-model").replaceWith(model);
  $("note-tags").value = setup.tags || "mining-cat";
  renderVoices(language);
  model.addEventListener("change", () => renderMapping(model.value, {}));
  await renderMapping(setup.model, setup.fields);
}

async function renderVoices(language) {
  const select = $("note-voice");
  select.replaceChildren();
  try {
    const { voices, chosen } = await api(`/api/tts/voices?language=${encodeURIComponent(language)}`);
    if ($("note-language").value !== language) return;
    options(select, [["", voices.length ? "None: generate by hand" : "No voice for this language"], ...voices.map((v) => [v.id, v.label])], chosen);
    select.disabled = !voices.length;
  } catch (err) { showError(err); }
}

async function renderTranslation() {
  try {
    const { languages, chosen } = await api("/api/translate/languages");
    options($("translation-language"), [["", "None: no translation"], ...languages.map((l) => [l.id, l.name])], chosen);
    const studied = new Set([...S.languages.filter((l) => l.studied).map((l) => l.id)]);
    const sources = languages.filter((l) => l.id !== chosen);
    const first = sources.find((l) => studied.has(l.id)) || sources[0];
    options($("model-language"), sources.map((l) => [l.id, l.name]), first && first.id);
    $("model-download").disabled = !chosen;
    renderModels(await api("/api/translate/models"));
  } catch (err) { showError(err); }
}

const megabytes = (bytes) => `${Math.round(bytes / 1e6)} MB`;

let modelPoll = null;
function renderModels({ available, installed, job }) {
  const list = $("model-list");
  if (!available) {
    list.replaceChildren(el("p", { class: "empty", text: "Translation needs the argostranslate package (pip install argostranslate)." }));
    $("model-download").disabled = true;
    return;
  }
  list.replaceChildren(installed.length
    ? el("table", { class: "mapping" }, el("tbody", {}, ...installed.map((m) => el("tr", {},
      el("td", { text: m.name }), el("td", { class: "dim", text: megabytes(m.size) }),
      el("td", {}, el("button", { type: "button", class: "icon-btn danger", "aria-label": `Remove ${m.name}`, text: "×",
        onclick: async () => {
          try { renderModels(await api(`/api/translate/models/${m.from}/${m.to}/delete`, {})); } catch (err) { showError(err); }
        } }))))))
    : el("p", { class: "empty", text: "No model yet: they're downloaded the first time a language is translated." }));

  const running = job.state === "running";
  $("model-progress").hidden = !running && job.state !== "error";
  $("model-download").disabled = running || !$("translation-language").value;
  if (running) {
    $("model-progress-bar").value = job.total ? job.done / job.total : 0;
    $("model-progress-bar").max = 1;
    $("model-progress-text").textContent = `${langName(job.language)}${job.step ? ` (model ${job.step})` : ""}: `
      + (job.total ? `${megabytes(job.done)} / ${megabytes(job.total)}` : "starting…");
  } else if (job.state === "error") {
    $("model-progress-bar").value = 0;
    $("model-progress-text").textContent = `Download failed: ${job.error}`;
  }
  clearTimeout(modelPoll);
  if (running) modelPoll = setTimeout(async () => { try { renderModels(await api("/api/translate/models")); } catch (err) { showError(err); } }, 700);
}

async function downloadModels() {
  try { renderModels(await api("/api/translate/models", { language: $("model-language").value })); } catch (err) { showError(err); }
}

async function saveTranslation() {
  try {
    S.config = (await api("/api/anki/config", { translation_language: $("translation-language").value })).config;
    renderTranslation();
    $("translation-saved").textContent = "Saved.";
    setTimeout(() => { $("translation-saved").textContent = ""; }, 3000);
  } catch (err) { showError(err); }
}

async function renderMapping(model, saved) {
  const box = $("field-mapping");
  if (!model) { box.replaceChildren(); return; }
  let fields = Object.keys(saved || {});
  let guess = {};
  if (S.anki.connected) {
    try {
      const data = await api(`/api/anki/fields?model=${encodeURIComponent(model)}`);
      fields = data.fields;
      guess = data.guess;
    } catch (err) { showError(err); }
  }
  const markers = [["", "(leave empty)"], ...Object.entries(S.cardFields).map(([k, v]) => [`{${k}}`, v])];
  const rows = fields.map((name) => {
    const value = saved && name in saved ? saved[name] : (guess[name] || "");
    const select = el("select", { "data-field": name, "aria-label": `Content of ${name}` });
    const known = markers.some(([m]) => m === value);
    options(select, known ? markers : [...markers, [value, value]], value);
    return el("tr", {}, el("td", { text: name }), el("td", {}, select));
  });
  box.replaceChildren(rows.length
    ? el("table", { class: "mapping" }, el("tbody", {}, ...rows))
    : el("p", { class: "empty", text: "Open Anki to see the fields of this note type." }));
}

async function saveNoteSetup() {
  const language = $("note-language").value;
  const fields = {};
  for (const select of $("field-mapping").querySelectorAll("select[data-field]")) fields[select.dataset.field] = select.value;
  try {
    const { config } = await api("/api/anki/config", {
      url: $("anki-url").value,
      notes: { [language]: { deck: $("note-deck").value, model: $("note-model").value, fields, tags: $("note-tags").value } },
      ...($("note-voice").disabled ? {} : { tts_voices: { [language]: $("note-voice").value } }),
    });
    S.config = config;
    $("note-saved").textContent = `Saved for ${langName(language)}.`;
    setTimeout(() => { $("note-saved").textContent = ""; }, 3000);
  } catch (err) { showError(err); }
}

function renderSyncSources() {
  const box = $("sync-sources");
  const rows = [];
  for (const [language, sources] of Object.entries(S.config.sync || {})) for (const s of sources) rows.push({ language, ...s });
  box.replaceChildren(...rows.map(syncRow));
  if (!rows.length) box.append(el("p", { class: "empty", text: "No deck yet: add the decks that hold the words you already study." }));
}

function syncRow(source = {}) {
  const language = el("select", { "data-role": "language" });
  options(language, S.languages.map((l) => [l.id, l.name]), source.language || $("note-language").value);
  const deck = selectWith(S.anki.decks, source.deck, "Deck");
  deck.dataset.role = "deck";
  const field = el("input", { type: "text", value: source.field || "", placeholder: "e.g. Hanzi", "data-role": "field" });
  const reading = el("input", { type: "text", value: source.reading_field || "", placeholder: "optional", "data-role": "reading" });
  const row = el("div", { class: "sync-source" },
    el("label", { class: "field" }, el("span", { class: "field-label", text: "Language" }), language),
    el("label", { class: "field" }, el("span", { class: "field-label", text: "Deck" }), deck),
    el("label", { class: "field" }, el("span", { class: "field-label", text: "Word field" }), field),
    el("label", { class: "field" }, el("span", { class: "field-label", text: "Reading field" }), reading),
    el("button", { class: "icon-btn danger", type: "button", "aria-label": "Remove", text: "×", onclick: () => row.remove() }));
  return row;
}

async function saveSync() {
  const sync = {};
  for (const lang of S.languages) sync[lang.id] = [];
  for (const row of $("sync-sources").querySelectorAll(".sync-source")) {
    const get = (role) => row.querySelector(`[data-role="${role}"]`).value.trim();
    if (!get("deck") || !get("field")) continue;
    sync[get("language")].push({ deck: get("deck"), field: get("field"), reading_field: get("reading") });
  }
  const { config } = await api("/api/anki/config", { url: $("anki-url").value, known_interval: $("known-interval").value, sync });
  S.config = config;
  return config;
}

async function syncNow() {
  const report = $("sync-report");
  try {
    await saveSync();
    report.textContent = "Syncing…";
    const result = await api("/api/anki/sync", {});
    const parts = [`Cards sent: ${result.cards.sent}` + (result.cards.failed ? `, refused: ${result.cards.failed}` : "")];
    for (const [lang, r] of Object.entries(result.languages)) {
      parts.push(`${langName(lang)}: ${r.notes} notes read, ${r.known} known, ${r.learning} learning${r.kept ? `, ${r.kept} kept as you set them` : ""}`);
    }
    report.textContent = parts.join(" · ");
    loadLanguages();
    updateBadge();
  } catch (err) {
    report.textContent = "";
    showError(err);
  }
}

// ---------------------------------------------------------------- cards

const CARD_STATUS = { pending: "waiting", failed: "refused", sent: "in Anki", exported: "exported" };

async function loadCards() {
  const status = $("cards-filter").value;
  const { cards } = await api(`/api/cards${status ? `?status=${status}` : ""}`);
  const table = $("cards-table");
  table.replaceChildren(
    el("thead", {}, el("tr", {}, ...["Word", "Sentence", "Language", "Status", ""].map((t) => el("th", { text: t })))),
    el("tbody", {}, ...cards.map((c) => {
      const sentence = el("td");
      sentence.textContent = c.fields.sentence.replace(/<[^>]+>/g, "");
      return el("tr", {},
        el("td", { class: "word", lang: c.language, text: c.expression }),
        sentence,
        el("td", { text: langName(c.language) }),
        el("td", {}, el("span", { class: `pill ${c.status}`, text: CARD_STATUS[c.status] || c.status }),
          c.error && c.status !== "sent" ? el("div", { class: "error", text: c.error }) : null),
        el("td", {},
          c.status !== "sent" ? el("button", {
            class: "btn", type: "button", text: "Send",
            onclick: async () => {
              try { const { card } = await api(`/api/cards/${c.id}/send`, {}); if (card.status !== "sent") showError({ title: "Not sent", message: card.error }); loadCards(); updateBadge(); }
              catch (err) { showError(err); }
            },
          }) : null,
          el("button", {
            class: "icon-btn danger", type: "button", title: "Delete", "aria-label": `Delete the card for ${c.expression}`, text: "🗑",
            onclick: async () => {
              if (!(await confirmBox("Delete card", `Delete the card for “${c.expression}” from MiningCat? (A card already in Anki stays there.)`, "Delete"))) return;
              try { await api(`/api/cards/${c.id}/delete`, {}); loadCards(); updateBadge(); } catch (err) { showError(err); }
            },
          })));
    })));
  if (!cards.length) table.append(el("tbody", {}, el("tr", {}, el("td", { colspan: "5", class: "empty", text: "No cards here." }))));
}

async function updateBadge() {
  try {
    const [{ cards: pending }, { cards: failed }] = await Promise.all([api("/api/cards?status=pending"), api("/api/cards?status=failed")]);
    const n = pending.length + failed.length;
    $("pending-badge").hidden = n === 0;
    $("pending-badge").textContent = String(n);
  } catch { /* ignore */ }
}

async function exportCards() {
  try {
    const res = await fetch("/api/cards/export", { method: "POST", headers: { "Content-Type": "application/json", "X-MiningCat": "1" }, body: "{}" });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw Object.assign(new Error(data.error || "Export failed"), { title: data.title || "Export" });
    }
    const blob = await res.blob();
    const name = (res.headers.get("Content-Disposition") || "").match(/filename="?([^";]+)"?/);
    const a = el("a", { href: URL.createObjectURL(blob), download: name ? name[1] : "miningcat.apkg" });
    document.body.append(a);
    a.click();
    a.remove();
    loadCards();
    updateBadge();
  } catch (err) { showError(err); }
}

// ---------------------------------------------------------------- init

async function init() {
  try {
    await loadLanguages();
    await loadDictionaries();
    $("dict-pick").addEventListener("click", () => $("dict-file").click());
    $("dict-file").addEventListener("change", (e) => { const f = e.target.files[0]; e.target.value = ""; importDictionary(f); });
    $("words-filter").addEventListener("change", loadWords);
    $("words-language").addEventListener("change", loadWords);
    $("anki-test").addEventListener("click", async () => {
      try { await api("/api/anki/config", { url: $("anki-url").value }); } catch (err) { return showError(err); }
      refreshAnki();
    });
    $("note-language").addEventListener("change", renderNoteSetup);
    $("note-save").addEventListener("click", saveNoteSetup);
    $("translation-save").addEventListener("click", saveTranslation);
    $("model-download").addEventListener("click", downloadModels);
    $("sync-add").addEventListener("click", () => {
      $("sync-sources").querySelector(".empty")?.remove();
      $("sync-sources").append(syncRow());
    });
    $("sync-save").addEventListener("click", async () => {
      try { await saveSync(); $("sync-report").textContent = "Saved."; } catch (err) { showError(err); }
    });
    $("sync-now").addEventListener("click", syncNow);
    $("cards-filter").addEventListener("change", loadCards);
    $("cards-send").addEventListener("click", async () => {
      try {
        const r = await api("/api/cards/send-pending", {});
        dialog("Cards", `${r.sent} sent to Anki, ${r.failed} refused, ${r.pending} still waiting.`);
        loadCards(); updateBadge();
      } catch (err) { showError(err); }
    });
    $("cards-export").addEventListener("click", exportCards);
    window.addEventListener("hashchange", showTab);
    showTab();
    updateBadge();
  } catch (err) {
    showError(err);
  }
}

document.addEventListener("DOMContentLoaded", init);
