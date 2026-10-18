// MiningCat Settings page: dictionaries, languages & words, Anki, cards.
"use strict";

const $ = (id) => document.getElementById(id);

// Everything here is about the language studied (chosen on the home page, see application/study_language.py).
const STUDY = document.body.dataset.study;

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

// Resolves to whether the button of value true was clicked (ui.js).
function dialog(title, message, buttons) {
  return MiningCatUI.dialog(title, message, buttons).then((value) => value === "true");
}
const showError = (err) => dialog(err.title || "Error", err.message || String(err));
const confirmBox = (title, message, label) => dialog(title, message, [{ label: "Cancel", value: false }, { label, value: true, primary: true }]);

// A Bootstrap icon, for the buttons without a label.
const icon = (name) => el("i", { class: `bi bi-${name}`, "aria-hidden": "true" });
const EMPTY = "text-body-secondary small m-0";

const langName = (id) => (S.languages.find((l) => l.id === id) || { name: id }).name;

function options(select, values, value) {
  select.replaceChildren(...values.map((v) => (Array.isArray(v) ? new Option(v[1], v[0]) : new Option(v, v))));
  if (value !== undefined) select.value = value;
}

// ---------------------------------------------------------------- tabs

function showTab() {
  const name = (location.hash || "#dictionaries").slice(1);
  for (const a of document.querySelectorAll("[data-tab]")) {
    a.setAttribute("aria-selected", String(a.dataset.tab === name));
    a.classList.toggle("active", a.dataset.tab === name);
  }
  for (const p of document.querySelectorAll(".tab-panel")) p.hidden = p.id !== `tab-${name}`;
  if (name === "cards") loadCards();
  if (name === "languages") loadWords();
  if (name === "anki") refreshAnki();
  if (name === "translation") renderTranslation();
  if (name === "voice") { renderLocalVoice(); renderElevenLabs(); }
  if (name === "ereader") loadEreader();
}

// ---------------------------------------------------------------- dictionaries

// A dictionary that only has word frequencies: listed with the frequency lists, not with the dictionaries.
const frequencyOnly = (d, frequencyIds) => frequencyIds.has(d.id) && !d.term_count && !d.kanji_count;

async function loadDictionaries() {
  const [{ dictionaries }, { lists }] = await Promise.all([api("/api/dict"), api(`/api/frequency/lists?language=${STUDY}`)]);
  const frequencyIds = new Set(lists.map((l) => l.id));
  const box = $("dict-list");
  const list = dictionaries.filter((d) => d.language === STUDY && !frequencyOnly(d, frequencyIds));
  if (!list.length) {
    box.replaceChildren(el("p", { class: EMPTY, text: "No dictionary yet." }));
    return;
  }
  box.replaceChildren(el("div", { class: "list-group" },
    ...list.map((d, i) => {
      const enabled = el("input", { type: "checkbox", class: "form-check-input m-0", checked: Boolean(d.enabled), "aria-label": `Use ${d.title}` });
      enabled.addEventListener("change", async () => {
        try { await api(`/api/dict/${d.id}`, { enabled: enabled.checked }); loadDictionaries(); loadFrequency(); } catch (err) { showError(err); }
      });
      const move = async (delta) => {
        const ids = list.map((x) => x.id);
        const j = i + delta;
        [ids[i], ids[j]] = [ids[j], ids[i]];
        const others = dictionaries.filter((x) => !ids.includes(x.id)).map((x) => x.id);  // other languages, frequency lists
        try { await api("/api/dict/reorder", { ids: [...ids, ...others] }); loadDictionaries(); loadFrequency(); } catch (err) { showError(err); }
      };
      const counts = [d.term_count ? `${d.term_count.toLocaleString()} terms` : null,
        d.kanji_count ? `${d.kanji_count.toLocaleString()} characters` : null,
        d.meta_count ? `${d.meta_count.toLocaleString()} frequency/pitch entries` : null].filter(Boolean).join(" · ");
      return el("div", { class: "list-group-item d-flex flex-wrap align-items-center gap-2" },
        enabled,
        el("div", { class: `flex-grow-1 fw-semibold${d.enabled ? "" : " text-body-secondary text-decoration-line-through"}` },
          d.title, el("small", { class: "d-block fw-normal text-body-secondary", text: [d.revision, counts].filter(Boolean).join(" · ") })),
        el("div", { class: "btn-group btn-group-sm" },
          el("button", { class: "btn btn-outline-secondary", type: "button", title: "Move up", "aria-label": "Move up", disabled: i === 0, onclick: () => move(-1) }, icon("arrow-up")),
          el("button", { class: "btn btn-outline-secondary", type: "button", title: "Move down", "aria-label": "Move down", disabled: i === list.length - 1, onclick: () => move(1) }, icon("arrow-down"))),
        el("button", {
          class: "btn btn-sm btn-outline-danger", type: "button", title: "Delete", "aria-label": `Delete ${d.title}`,
          onclick: async () => {
            if (!(await confirmBox("Delete dictionary", `Delete “${d.title}”? You can import it again later.`, "Delete"))) return;
            try { await api(`/api/dict/${d.id}/delete`, {}); loadDictionaries(); loadFrequency(); } catch (err) { showError(err); }
          },
        }, icon("trash")));
    })));
}

// ---------------------------------------------------------------- frequency lists

async function loadFrequency() {
  const { lists, chosen, frontier, limit_base: base, limit_per_known_word: perWord } = await api(`/api/frequency/lists?language=${STUDY}`);
  const box = $("freq-lists");
  // the ticked lists are combined (see frequency.py)
  box.replaceChildren(...(lists.length ? lists.map((l) => {
    const id = `freq-list-${l.id}`;
    const check = el("input", { type: "checkbox", class: "form-check-input", id, value: String(l.id),
      checked: chosen.includes(l.id), disabled: !l.enabled });
    check.addEventListener("change", async () => {
      const ids = [...box.querySelectorAll("input:checked")].map((c) => Number(c.value));
      try { await api("/api/frequency/list", { language: STUDY, ids }); loadFrequency(); } catch (err) { showError(err); }
    });
    const remove = el("button", {
      class: "btn btn-sm btn-link text-danger p-0", type: "button", title: "Delete", "aria-label": `Delete ${l.title}`,
      onclick: async () => {
        const what = l.has_terms ? `“${l.title}” is a dictionary too: its definitions will be deleted as well.` : `Delete “${l.title}”?`;
        if (!(await confirmBox("Delete frequency list", `${what} You can import it again later.`, "Delete"))) return;
        try { await api(`/api/dict/${l.id}/delete`, {}); loadDictionaries(); loadFrequency(); } catch (err) { showError(err); }
      },
    }, icon("trash"));
    // A disabled list that is a dictionary too is enabled again with the dictionaries; one that isn't, here.
    const enable = !l.enabled && !l.has_terms ? el("button", {
      class: "btn btn-sm btn-link p-0", type: "button", text: "Enable",
      onclick: async () => {
        try { await api(`/api/dict/${l.id}`, { enabled: true }); loadFrequency(); } catch (err) { showError(err); }
      },
    }) : null;
    return el("div", { class: "d-flex align-items-center gap-2" },
      el("div", { class: "form-check m-0" }, check,
        el("label", { class: "form-check-label", for: id }, l.enabled ? l.title : `${l.title} (disabled)`,
          l.meta_count ? el("small", { class: "text-body-secondary ms-2", text: `${l.meta_count.toLocaleString()} entries` }) : "")),
      ...(enable ? [enable] : []), remove);
  }) : [el("p", { class: EMPTY, text: "No frequency list yet." })]));
  const several = frontier && frontier.dictionaries.length > 1;
  $("freq-frontier").textContent = frontier
    ? `You know ${frontier.known.toLocaleString()} of the ${frontier.words.toLocaleString()} words of ${several ? "these lists" : "this list"}: `
      + "sentences are recommended "
      + `for words up to #${frontier.limit.toLocaleString()} (${base.toLocaleString()} + ${perWord} per word you know).`
    : "No frequency list used: every sentence with one new word is recommended, frequent or not.";
}

// `kind` is "dict" or "freq": the card whose button and progress bar show the import.
async function importDictionary(file, kind = "dict") {
  if (!file) return;
  const form = new FormData();
  form.append("file", file, file.name);
  form.append("language", STUDY);
  const progress = $(`${kind}-progress`);
  progress.hidden = false;
  $(`${kind}-progress-bar`).style.width = "0%";
  $(`${kind}-progress-text`).textContent = `Uploading ${file.name}…`;
  $(`${kind}-pick`).disabled = true;
  try {
    const res = await fetch("/api/dict/import", { method: "POST", headers: { "X-MiningCat": "1" }, body: form });
    const data = await res.json();
    if (!res.ok) throw Object.assign(new Error(data.error), { title: data.title });
    $(`${kind}-progress-text`).textContent = `Importing “${data.title}”…`;
    for (;;) {
      await new Promise((r) => setTimeout(r, 600));
      const job = await api(`/api/dict/import/${data.job}`);
      $(`${kind}-progress-bar`).style.width = `${Math.round(job.progress * 100)}%`;
      if (!job.done) { $(`${kind}-progress-text`).textContent = `Importing “${data.title}”: ${job.message}`; continue; }
      if (job.error) throw Object.assign(new Error(job.error), { title: "Import failed" });
      const d = job.dictionary;
      const [count, unit] = d.term_count ? [d.term_count, "terms"] : d.kanji_count ? [d.kanji_count, "characters"] : [d.meta_count, "frequencies"];
      $(`${kind}-progress-text`).textContent = `“${data.title}” imported: ${count.toLocaleString()} ${unit}.`;
      if (kind === "freq" && d.meta_count) {
        // a frequency list imported here is added to the lists used
        const { chosen } = await api(`/api/frequency/lists?language=${STUDY}`);
        if (!chosen.includes(d.id)) await api("/api/frequency/list", { language: STUDY, ids: [...chosen, d.id] });
      }
      break;
    }
    loadDictionaries();
    loadFrequency();
  } catch (err) {
    progress.hidden = true;
    showError(err);
  } finally {
    $(`${kind}-pick`).disabled = false;
  }
}

// ---------------------------------------------------------------- languages & words

async function loadLanguages() {
  const data = await api("/api/mining/languages");
  S.languages = data.languages;
  const study = S.languages.find((l) => l.id === STUDY);
  const radios = (language, choices, current, path, key) => {
    const row = el("div", { role: "radiogroup", "aria-label": language.name }, el("span", { class: "fw-semibold me-3", text: language.name }));
    for (const [value, label] of choices) {
      const radio = el("input", { type: "radio", class: "form-check-input", name: `${key}-${language.id}`, value, checked: current === value });
      radio.addEventListener("change", () => api(path, { language: language.id, [key]: value }).catch(showError));
      row.append(el("label", { class: "form-check form-check-inline" }, radio, el("span", { class: "form-check-label", text: label })));
    }
    return row;
  };
  // The templates only have these boxes for Chinese languages (script), Mandarin and Taigi (readings).
  $("script-settings")?.replaceChildren(radios(study,
    [["traditional", "Traditional 繁體"], ["simplified", "Simplified 简体"], ["both", "Both"]], data.scripts[STUDY], "/api/mining/script", "script"));
  const readingSystems = {
    zh: [["pinyin", "Pinyin (hànyǔ)"], ["zhuyin", "Zhuyin (ㄏㄢˋ ㄩˇ)"]],
    nan: [["tailo", "Tâi-lô (Tâi-uân)"], ["poj", "Pe̍h-ōe-jī (Tâi-oân)"]],
  };
  if (readingSystems[STUDY]) {
    $("reading-settings")?.replaceChildren(radios(study, readingSystems[STUDY], data.readings[STUDY], "/api/mining/reading", "system"));
  }

  const c = data.counts[STUDY];
  $("word-counts").replaceChildren(c
    ? el("div", { class: "d-inline-block border rounded bg-body-tertiary px-3 py-2 small" },
      el("strong", { class: "d-block", text: study.name }),
      `${c.known || 0} known · ${c.learning || 0} learning${c.ignored ? ` · ${c.ignored} ignored` : ""}`)
    : el("p", { class: EMPTY, text: "No words yet: look words up in the reader, mark them or make cards." }));
}

async function loadWords() {
  const params = new URLSearchParams();
  if ($("words-filter").value) params.set("status", $("words-filter").value);
  params.set("language", STUDY);
  params.set("order", $("words-order").value);
  const { words } = await api(`/api/words?${params}`);
  const table = $("words-table");
  table.replaceChildren(
    el("thead", { class: "sticky-top" }, el("tr", {}, ...["Word", "Reading", "Status", "From", "Added", ""].map((t) => el("th", { text: t })))),
    el("tbody", {}, ...words.map((w) => el("tr", {},
      el("td", { class: "fs-5", lang: w.language, text: w.expression }),
      el("td", { text: w.reading }),
      el("td", {}, el("span", { class: `badge rounded-pill ${STATUS_BADGES[w.status] || STATUS_BADGES.new}`, text: w.status })),
      el("td", { text: { manual: "you", card: "card", anki: "Anki" }[w.source] || w.source }),
      el("td", { class: "text-body-secondary", title: new Date(w.added * 1000).toLocaleString(), text: new Date(w.added * 1000).toLocaleDateString() }),
      el("td", { class: "text-end" }, el("button", {
        class: "btn btn-sm btn-link link-secondary", type: "button", title: "Forget this word", "aria-label": `Forget ${w.expression}`,
        onclick: async () => {
          try { await api("/api/words/status", { language: w.language, expression: w.expression, reading: w.reading, status: "new" }); loadWords(); loadLanguages(); }
          catch (err) { showError(err); }
        },
      }, icon("x-lg")))))));
  if (!words.length) table.append(el("tbody", {}, el("tr", {}, el("td", { colspan: "6", class: "text-body-secondary", text: "No words." }))));
}

// ---------------------------------------------------------------- Anki

async function refreshAnki() {
  const { config, card_fields } = await api("/api/anki/config");
  S.config = config;
  S.cardFields = card_fields;
  $("anki-url").value = config.url;
  $("known-interval").value = config.known_interval;
  $("anki-state").textContent = "Checking Anki…";
  $("anki-state").className = "small text-body-secondary m-0";
  S.anki = await api("/api/anki/status");
  const state = $("anki-state");
  if (S.anki.connected) {
    state.textContent = `Connected to Anki (AnkiConnect ${S.anki.version}): ${S.anki.decks.length} decks, ${S.anki.models.length} note types.`;
    state.className = "small text-success m-0";
  } else {
    state.textContent = S.anki.error;
    state.className = "small text-danger m-0";
  }
  renderNoteSetup();
  renderSyncSources();
}

function selectWith(values, value, placeholder) {
  const list = [...values];
  if (value && !list.includes(value)) list.unshift(value);  // keep a saved value even when Anki is closed
  const select = el("select", { class: "form-select" });
  options(select, [["", placeholder], ...list.map((v) => [v, v])], value || "");
  return select;
}

async function renderNoteSetup() {
  const language = STUDY;
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
  $("deck-create").disabled = !S.anki.connected;
  renderNoteTypeOffer();
  await renderMapping(setup.model, setup.fields);
}

// MiningCat's deck of the language studied ("Mandarin (traditional) - MiningCat"), created in Anki.
async function createDeck() {
  $("deck-create").disabled = true;
  try {
    const { deck } = await api("/api/anki/deck", { language: STUDY });
    if (!S.anki.decks.includes(deck)) S.anki.decks = [...S.anki.decks, deck].sort();
    const select = $("note-deck");
    if (![...select.options].some((o) => o.value === deck)) select.add(new Option(deck, deck));
    select.value = deck;
    $("note-saved").textContent = $("note-model").value ? `${deck} is ready in Anki: Save to use it.` : `${deck} is ready in Anki: choose a note type, then Save.`;
  } catch (err) { showError(err); }
  $("deck-create").disabled = !S.anki.connected;
}

// MiningCat's own note type: created in Anki, or updated once there.
const NOTE_TYPE = "MiningCat";

function renderNoteTypeOffer() {
  const installed = S.anki.models.includes(NOTE_TYPE);
  $("note-type-install").disabled = !S.anki.connected;
  $("note-type-install-label").textContent = installed ? `Update the ${NOTE_TYPE} note type` : `Create ${NOTE_TYPE}'s note type in Anki`;
  $("note-type-help").textContent = installed
    ? "Updating it brings its templates up to date (Mandarin readings: in the pinyin or zhuyin chosen under Words). Changes you made to its templates in Anki are replaced, your fields and notes are kept."
    : "No note type of your own? MiningCat's works for every language: the sentence on the front, the word, its definition and audio on the back, and the readings written in brackets (字[zi4], 日本[にほん]) shown above their words.";
}

async function installNoteType() {
  $("note-type-install").disabled = true;
  try {
    const { model, templates } = await api("/api/anki/note-type", { language: STUDY });
    if (!S.anki.models.includes(model)) S.anki.models = [...S.anki.models, model].sort();
    const select = $("note-model");
    if (![...select.options].some((o) => o.value === model)) select.add(new Option(model, model));
    select.value = model;
    await renderMapping(model, templates);
    $("note-saved").textContent = $("note-deck").value ? `${model} is ready in Anki: Save to use it.` : `${model} is ready in Anki: choose a deck, then Save.`;
  } catch (err) { showError(err); }
  renderNoteTypeOffer();
}

async function renderVoices(language) {
  const select = $("note-voice");
  select.replaceChildren();
  try {
    const { voices, chosen } = await api(`/api/tts/voices?language=${encodeURIComponent(language)}`);
    options(select, [["", voices.length ? "None: generate by hand" : "No voice for this language"], ...voices.map((v) => [v.id, v.label])], chosen);
    select.disabled = !voices.length;
  } catch (err) { showError(err); }
}

// OmniVoice, the local voice of every language (see infrastructure/speech/omnivoice_tts.py): its quality, whether
// Edge's voices are used instead when they answer, and another voice for the language studied. Saved right away.
const STEP_LABELS = { 8: "Fast (8 steps)", 16: "Better (16 steps, 2× slower)", 32: "Best (32 steps, 4× slower)" };

async function renderLocalVoice() {
  try {
    const voice = await api(`/api/tts/local-voice?language=${encodeURIComponent(STUDY)}`);
    $("tts-use-edge").checked = voice.use_edge;
    const taigi = Boolean(voice.mms);  // Edge has no Taigi voice: MMS or OmniVoice
    $("edge-option").hidden = taigi;
    $("tts-intro").textContent = taigi
      ? "Sentences are read by Meta's MMS or by OmniVoice, voices running on your computer (saved right away). MMS is generally faster."
      : "Sentences are read by OmniVoice, a voice running on your computer (every language), or by Edge's voices (saved right away).";
    renderTaigiVoice(taigi);
    options($("tts-steps"), voice.steps.map((s) => [String(s), STEP_LABELS[s] || `${s} steps`]), String(voice.chosen_steps));
    $("local-voice-options").hidden = !voice.installed;
    $("local-voice-install").hidden = voice.installed;
    $("mms-voice").hidden = !voice.mms || voice.mms.installed;  // Taigi's own voice
    if ((voice.mms && !voice.mms.installed) || (taigi && !voice.installed)) followInstall();
    const state = $("local-voice-state");
    if (taigi) {
      state.textContent = voice.installed
        ? "OmniVoice is installed. The first sentence takes longer: the voice loads (and is made up, the first time)."
        : `OmniVoice is optional for Taigi, MMS reads it. Large: about 4 GB with its model (or ${voice.install_command}).`;
      state.className = "small text-body-secondary m-0";
    } else if (voice.installed) {
      state.textContent = voice.use_edge
        ? "OmniVoice is installed: it reads the sentences when Edge doesn't answer, and its voices are in the list above."
        : "OmniVoice is installed. The first sentence takes longer: the voice loads (and is made up, the first time for a language).";
      state.className = "small text-body-secondary m-0";
    } else {
      state.textContent = voice.use_edge
        ? `Without OmniVoice, sentences can't be read when Edge doesn't answer. Large: about 4 GB with its model (or ${voice.install_command}).`
        : `Without OmniVoice or edge-tts, sentences can't be read. Large: about 4 GB with its model (or ${voice.install_command}).`;
      state.className = "small text-warning-emphasis m-0";
      followInstall();  // an install started before the page loaded
    }
  } catch (err) { showError(err); }
}

// Taigi's voice: MMS or OmniVoice (when installed), the one reading its sentences.
async function renderTaigiVoice(taigi) {
  const box = $("taigi-voice-choice");
  box.hidden = true;
  if (!taigi) return;
  try {
    const { voices, chosen } = await api(`/api/tts/voices?language=${encodeURIComponent(STUDY)}`);
    options($("taigi-voice"), voices.map((v) => [v.id, v.label]), chosen);
    box.hidden = voices.length < 2;
  } catch (err) { showError(err); }
}

async function saveTaigiVoice() {
  try {
    S.config = (await api("/api/anki/config", { tts_voices: { [STUDY]: $("taigi-voice").value } })).config;
    renderVoices(STUDY);
  } catch (err) { showError(err); }
}

async function saveLocalVoice() {
  try {
    S.config = (await api("/api/anki/config", {
      tts_use_edge: $("tts-use-edge").checked, tts_steps: Number($("tts-steps").value),
    })).config;
    renderLocalVoice();
    renderVoices(STUDY);  // Edge's voices are only listed with edge-tts
  } catch (err) { showError(err); }
}

// ElevenLabs, the online voice of the user's own account (see application/elevenlabs.py): the key (never shown back,
// only its end), then the model, the voice of the language studied and whether it's the main voice.
async function renderElevenLabs() {
  try {
    const el11 = await api(`/api/tts/elevenlabs?language=${encodeURIComponent(STUDY)}`);
    $("el-permissions").textContent = el11.permissions.join(", ");
    $("el-library").href = el11.voice_library;
    $("el-key").value = "";
    $("el-key").placeholder = el11.has_key ? `Saved (${el11.key_hint}): paste another one to replace it`
      : el11.key_error ? "The saved key can't be read anymore: paste it again" : "sk_…";
    $("el-key").title = el11.key_error;
    $("el-voice").value = el11.voice;
    $("el-main").checked = el11.main;
    $("el-options").hidden = !el11.has_key;
    if (el11.has_key) await renderElevenLabsAccount(el11);
  } catch (err) { showError(err); }
}

// The models and the credits left, asked to ElevenLabs with the key: an error there is most often a permission the
// key lacks, shown under the options.
async function renderElevenLabsAccount(el11) {
  const state = $("el-state");
  const voice = el11.voice ? `Voice: ${el11.voice_name || el11.voice}.` : "Add a voice ID to use ElevenLabs.";
  options($("el-model"), [["", "Latest"], ...(el11.model ? [[el11.model, el11.model]] : [])], el11.model);
  try {
    const { models, credits } = await api("/api/tts/elevenlabs/account");
    const label = (m) => `${m.name}${m.languages.length && !m.languages.includes(STUDY) ? " - doesn't list this language" : ""}`;
    const latest = models.find((m) => m.languages.includes(STUDY)) || models[0];
    const listed = [["", latest ? `Latest (now ${latest.name})` : "Latest"], ...models.map((m) => [m.id, label(m)])];
    if (el11.model && !models.some((m) => m.id === el11.model)) listed.splice(1, 0, [el11.model, el11.model]);
    options($("el-model"), listed, el11.model);
    const left = credits.limit != null ? `${(credits.limit - credits.used).toLocaleString()} of ${credits.limit.toLocaleString()} credits left` : "";
    const reset = credits.reset ? `, until ${new Date(credits.reset * 1000).toLocaleDateString()}` : "";
    state.textContent = `${voice} ${left}${reset}.`;
    state.className = "small text-body-secondary m-0";
  } catch (err) {
    state.textContent = `${voice} ${err.message}`;
    state.className = "small text-warning-emphasis m-0";
  }
}

async function saveElevenLabs(values) {
  try {
    await api("/api/tts/elevenlabs", { language: STUDY, ...values });
    S.config = (await api("/api/anki/config")).config;  // the sentence voice follows the main option
    await renderElevenLabs();
    renderVoices(STUDY);
  } catch (err) { showError(err); }
}

async function saveElevenLabsKey() {
  const key = $("el-key").value.trim();
  if (!key) return showError({ title: "ElevenLabs", message: "Paste your API key first." });
  await saveElevenLabs({ api_key: key });
}

// Main voice: every sentence without audio is then read by ElevenLabs when a card is made, and it's the converter's
// first voice. Each one uses credits: asked before.
async function toggleElevenLabsMain() {
  const box = $("el-main");
  if (box.checked) {
    const sure = await confirmBox("Use ElevenLabs as the main voice?",
      "ElevenLabs then reads every sentence without audio of the cards you make (and every word without a recording), " +
      "and it's the first voice of the converter's Generate audio. Each character read uses your " +
      "ElevenLabs credits, and a book reads many characters. When your credits run out, the audio isn't generated " +
      "until you add some.", "Use ElevenLabs");
    if (!sure) { box.checked = false; return; }
  }
  await saveElevenLabs({ main: box.checked });
}

// The install runs as a job of the converter: followed here until it ends, its log shown under the buttons.
async function installOmniVoice() {
  const sure = await confirmBox("Install OmniVoice?",
    "OmniVoice reads the sentences on your computer, in every language. The install is large (about 4 GB with its " +
    "model, a few minutes) and goes into its own folder, .venv-omnivoice.", "Install");
  if (!sure) return;
  try {
    await api("/api/install-engines", { engines: "omnivoice", page: "settings" });
    followInstall();
  } catch (err) { showError(err); }
}

async function installTaigiVoice() {
  const sure = await confirmBox("Install Taigi's voice?",
    "Meta's MMS reads Taigi on your computer. It comes with Taigi's speech engines (Qwen3-ASR, Meta's MMS): a large " +
    "install, a few minutes.", "Install");
  if (!sure) return;
  try {
    await api("/api/install-engines", { engines: "taigi", page: "settings" });
    followInstall();
  } catch (err) { showError(err); }
}

// The log of an install started here, from the converter's events (they start over with each job); an install the
// Converter page offered keeps its log there. Returns a function closing it.
function showInstallLog() {
  const log = $("install-log");
  log.textContent = "";
  let install = false;  // the events are those of an install started here (and not of another job)
  const source = new EventSource("/api/events?last=0");
  source.onmessage = (e) => {
    let ev;
    try { ev = JSON.parse(e.data); } catch { return; }
    if (ev.type === "start") {
      install = ev.kind === "install" && ev.page === "settings";
      log.textContent = "";
      log.hidden = !install;
    }
    if (ev.type !== "log" || !install) return;
    const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 24;
    log.textContent += ev.text;
    if (atBottom) log.scrollTop = log.scrollHeight;
  };
  return () => source.close();
}

let installPoll = null;
async function followInstall() {
  if (installPoll) return;
  const buttons = [$("tts-install"), $("mms-install")];
  const states = [$("tts-install-state"), $("mms-install-state")];
  let seen = false;  // the install was seen running: its end is reported
  let closeLog = null;
  const check = async () => {
    let job;
    try { ({ job } = await api("/api/state")); } catch { return; }
    const installing = job.running && job.kind === "install";
    seen ||= installing;
    if (installing && !closeLog) closeLog = showInstallLog();
    for (const button of buttons) button.disabled = installing;
    for (const state of states) state.textContent = installing ? job.status || "Installing…" : "";
    if (installing) return;
    clearInterval(installPoll);
    installPoll = null;
    // The last lines arrive with the job's end: the log stays open a moment, and stays shown.
    if (closeLog) setTimeout(closeLog, 3000);
    if (!seen) return;
    const voice = await api(`/api/tts/local-voice?language=${encodeURIComponent(STUDY)}`).catch(() => ({}));
    if (voice.installed || (voice.mms && voice.mms.installed)) {
      renderLocalVoice();
      renderVoices(STUDY);
    } else if (job.status !== "Done") {
      for (const state of states) state.textContent = "The install didn't finish: see its log below.";
    }
  };
  installPoll = setInterval(check, 2000);
  await check();
}

async function newLocalVoice() {
  const sure = await confirmBox("Another voice", `OmniVoice will make up another ${langName(STUDY)} voice: the current one is forgotten.`, "Change the voice");
  if (!sure) return;
  try {
    await api("/api/tts/new-voice", { language: STUDY });
    $("local-voice-state").textContent = "The next sentence will be read by a new voice.";
  } catch (err) { showError(err); }
}

// The translation model of the settings (NLLB-200 or Qwen3) and the language sentences are translated to.
async function renderTranslation() {
  try {
    const { languages, chosen } = await api("/api/translate/languages");
    // Translating to the language studied is pointless: it's only listed if it was chosen before.
    const targets = languages.filter((l) => l.id !== STUDY || l.id === chosen);
    options($("translation-language"), [["", "None: no translation"], ...targets.map((l) => [l.id, l.name])], chosen);
    S.translationModel = null;
    renderModels(await api("/api/translate/models"));
  } catch (err) { showError(err); }
}

const megabytes = (bytes) => (bytes >= 1e9 ? `${(bytes / 1e9).toFixed(1)} GB` : `${Math.round(bytes / 1e6)} MB`);
const chosenModel = () => S.translationModels.find((m) => m.id === $("translation-model").value) || S.translationModels[0];

let modelPoll = null;
function renderModels({ model, models, job, cards_with_context }) {
  const wasRunning = S.translationJob === "running";
  const running = job.state === "running";
  S.translationJob = job.state;
  S.translationModels = models;
  // the model chosen in the list stays, saved or not
  S.translationModel ??= model;
  if ($("translation-model").value) S.translationModel = $("translation-model").value;
  options($("translation-model"), models.map((m) => [m.id, `${m.label} (${megabytes(m.size)}${m.installed ? "" : ", not downloaded"})`]), S.translationModel);
  if (S.cardsWithContext === undefined) $("cards-context").checked = S.cardsWithContext = cards_with_context;
  renderCardsContext();

  $("model-list").replaceChildren(el("table", { class: "table table-sm align-middle mb-0" }, el("tbody", {}, ...models.map((m) => el("tr", {},
    el("td", { text: m.label }),
    el("td", { class: "text-body-secondary", text: m.installed ? megabytes(m.size) : "not downloaded" }),
    el("td", { class: "text-end" }, m.installed
      ? el("button", { type: "button", class: "btn btn-sm btn-outline-danger", title: "Remove", "aria-label": `Remove ${m.label}`,
        onclick: async () => {
          try { renderModels(await api(`/api/translate/models/${m.id}/delete`, {})); } catch (err) { showError(err); }
        } }, icon("trash"))
      : el("button", { type: "button", class: "btn btn-sm btn-outline-secondary", disabled: running, onclick: () => installModel(m) },
        icon("download"), ` Download (${megabytes(m.size)})`)))))));

  $("model-progress").hidden = !running && job.state !== "error";
  if (running) {
    const label = (models.find((m) => m.id === job.model) || { label: job.model }).label;
    $("model-progress-bar").style.width = `${job.total ? (100 * job.done) / job.total : 0}%`;
    $("model-progress-text").textContent = `${label}: ${job.step === "packages" ? "installing its packages (see the terminal)…"
      : job.total ? `${megabytes(job.done)} / ${megabytes(job.total)}` : "starting…"}`;
  } else if (job.state === "error") {
    $("model-progress-bar").style.width = "0%";
    $("model-progress-text").textContent = `Download failed: ${job.error}`;
  }
  clearTimeout(modelPoll);
  if (running) modelPoll = setTimeout(async () => { try { renderModels(await api("/api/translate/models")); } catch (err) { showError(err); } }, 700);
  else if (wasRunning && job.state === "done") dialog("Downloaded", "The translation model is downloaded.");
}

// Qwen3 translates the subtitles; the cards' sentences too only when asked (NLLB-200 does, faster).
function renderCardsContext() {
  $("cards-context-field").hidden = !chosenModel().context;
}

// A model is downloaded once, in the background (with the packages of its engine, when they're missing).
async function installModel(m) {
  const about = m.context
    ? "It translates subtitles with the lines before them as context, better but slower. It needs an NVIDIA GPU or an " +
      "Apple Silicon Mac, with 16 GB of memory."
    : "Its license (CC-BY-NC 4.0) only allows non-commercial use.";
  const install = await confirmBox(`Download ${m.label}?`,
    `${m.label} is downloaded once (${megabytes(m.size)}) and translates every language, on your computer. ${about}` +
    `\n\nYou can also run \`make install-translation TRANSLATION=${m.id}\`.`, "Download");
  if (!install) return false;
  try { renderModels(await api(`/api/translate/models/${m.id}/install`, {})); } catch (err) { showError(err); return false; }
  return true;
}

async function saveTranslation() {
  const m = chosenModel();
  const target = $("translation-language").value;
  // a model not downloaded yet: offered first (the choice is saved either way)
  if (target && !m.installed && S.translationJob !== "running") await installModel(m);
  try {
    S.config = (await api("/api/anki/config", {
      translation_model: m.id, translation_language: target, translation_cards_with_context: $("cards-context").checked,
    })).config;
    S.cardsWithContext = $("cards-context").checked;
    // the cards' sentences need an NLLB model
    const nllb = S.translationModels.filter((x) => !x.context);
    if (target && m.context && !$("cards-context").checked && !nllb.some((x) => x.installed)) {
      dialog("Cards", `The cards' sentences are translated with ${nllb[0].label}, which isn't downloaded yet: download it under Models.`);
    }
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
      const data = await api(`/api/anki/fields?model=${encodeURIComponent(model)}&language=${encodeURIComponent(STUDY)}`);
      fields = data.fields;
      guess = data.guess;
    } catch (err) { showError(err); }
  }
  const markers = [["", "(leave empty)"], ...Object.entries(S.cardFields).map(([k, v]) => [`{${k}}`, v])];
  const rows = fields.map((name) => {
    const value = saved && name in saved ? saved[name] : (guess[name] || "");
    const select = el("select", { class: "form-select form-select-sm", "data-field": name, "aria-label": `Content of ${name}` });
    const known = markers.some(([m]) => m === value);
    options(select, known ? markers : [...markers, [value, value]], value);
    return el("tr", {}, el("th", { class: "w-50", scope: "row", text: name }), el("td", {}, select));
  });
  box.replaceChildren(rows.length
    ? el("table", { class: "table table-sm table-borderless align-middle mb-0" }, el("tbody", {}, ...rows))
    : el("p", { class: EMPTY, text: "Open Anki to see the fields of this note type." }));
}

async function saveNoteSetup() {
  const language = STUDY;
  const fields = {};
  for (const select of $("field-mapping").querySelectorAll("select[data-field]")) fields[select.dataset.field] = select.value;
  try {
    const { config } = await api("/api/anki/config", {
      url: $("anki-url").value,
      notes: { [language]: { deck: $("note-deck").value, model: $("note-model").value, fields, tags: $("note-tags").value } },
      ...($("note-voice").disabled ? {} : { tts_voices: { [language]: $("note-voice").value } }),
    });
    S.config = config;
    $("note-saved").textContent = "Saved.";
    setTimeout(() => { $("note-saved").textContent = ""; }, 3000);
  } catch (err) { showError(err); }
}

function renderSyncSources() {
  const box = $("sync-sources");
  const rows = [];
  for (const s of (S.config.sync || {})[STUDY] || []) rows.push(s);
  box.replaceChildren(...rows.map(syncRow));
  if (!rows.length) box.append(el("p", { class: `${EMPTY} sync-empty`, text: "No deck yet: add the decks that hold the words you already study." }));
}

function syncRow(source = {}) {
  const deck = selectWith(S.anki.decks, source.deck, "Deck");
  deck.dataset.role = "deck";
  const labelled = (text, control) => el("label", {}, el("span", { class: "form-label d-block", text }), control);
  const fieldSelects = (fields, field, reading) => {
    const pick = selectWith(fields, field, fields.length || !deck.value ? "Field" : "Open Anki to list fields");
    const pickReading = selectWith(fields, reading, "(none)");
    pick.dataset.role = "field";
    pickReading.dataset.role = "reading";
    return [pick, pickReading];
  };
  const [pick, pickReading] = fieldSelects([], source.field, source.reading_field);
  const fieldLabel = labelled("Word field", pick);
  const readingLabel = labelled("Reading field", pickReading);
  // The field lists follow the deck chosen, the values chosen being kept when the new deck has them too.
  const renderFields = async (field, reading, deckChanged = false) => {
    const fields = deck.value && S.anki.connected ? await deckFields(deck.value) : [];
    const kept = (value) => (!deckChanged || fields.includes(value) ? value : "");
    const [pick, pickReading] = fieldSelects(fields, kept(field), kept(reading));
    fieldLabel.lastChild.replaceWith(pick);
    readingLabel.lastChild.replaceWith(pickReading);
  };
  deck.addEventListener("change", () => {
    const get = (role) => row.querySelector(`[data-role="${role}"]`).value;
    renderFields(get("field"), get("reading"), true);
  });
  const row = el("div", { class: "sync-source d-flex flex-wrap align-items-end gap-2 mb-2" },
    labelled("Deck", deck), fieldLabel, readingLabel,
    el("button", { class: "btn btn-outline-danger", type: "button", title: "Remove", "aria-label": "Remove", onclick: () => row.remove() }, icon("trash")));
  renderFields(source.field, source.reading_field);
  return row;
}

const deckFieldsCache = {};

function deckFields(deck) {
  deckFieldsCache[deck] ??= api(`/api/anki/deck-fields?deck=${encodeURIComponent(deck)}`)
    .then((data) => data.fields)
    .catch((err) => { delete deckFieldsCache[deck]; showError(err); return []; });
  return deckFieldsCache[deck];
}

async function saveSync() {
  // The other languages' decks are kept as they are.
  const sync = { [STUDY]: [] };
  for (const row of $("sync-sources").querySelectorAll(".sync-source")) {
    const get = (role) => row.querySelector(`[data-role="${role}"]`).value.trim();
    if (!get("deck") || !get("field")) continue;
    sync[STUDY].push({ deck: get("deck"), field: get("field"), reading_field: get("reading") });
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
    const r = result.languages[STUDY];
    if (r) {
      parts.push(`${langName(STUDY)}: ${r.notes} notes read, ${r.known} known, ${r.learning} learning${r.kept ? `, ${r.kept} kept as you set them` : ""}`);
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
// The colours of the word and card statuses
const STATUS_BADGES = {
  new: "text-bg-secondary", ignored: "text-bg-secondary", learning: "text-bg-warning", pending: "text-bg-warning",
  known: "text-bg-success", sent: "text-bg-success", failed: "text-bg-danger", exported: "text-bg-info",
};

async function loadCards() {
  const status = $("cards-filter").value;
  const params = new URLSearchParams({ language: STUDY });
  if (status) params.set("status", status);
  const { cards } = await api(`/api/cards?${params}`);
  const table = $("cards-table");
  table.replaceChildren(
    el("thead", { class: "sticky-top" }, el("tr", {}, ...["Word", "Sentence", "Status", ""].map((t) => el("th", { text: t })))),
    el("tbody", {}, ...cards.map((c) => {
      const sentence = el("td");
      sentence.textContent = c.fields.sentence.replace(/<[^>]+>/g, "");
      return el("tr", {},
        el("td", { class: "fs-5", lang: c.language, text: c.expression }),
        sentence,
        el("td", {}, el("span", { class: `badge rounded-pill ${STATUS_BADGES[c.status] || STATUS_BADGES.new}`, text: CARD_STATUS[c.status] || c.status }),
          c.error && c.status !== "sent" ? el("div", { class: "small text-danger", text: c.error }) : null),
        el("td", { class: "text-end text-nowrap" },
          c.status !== "sent" ? el("button", {
            class: "btn btn-sm btn-outline-secondary me-1", type: "button", text: "Send",
            onclick: async () => {
              try { const { card } = await api(`/api/cards/${c.id}/send`, {}); if (card.status !== "sent") showError({ title: "Not sent", message: card.error }); loadCards(); updateBadge(); }
              catch (err) { showError(err); }
            },
          }) : null,
          el("button", {
            class: "btn btn-sm btn-outline-danger", type: "button", title: "Delete", "aria-label": `Delete the card for ${c.expression}`,
            onclick: async () => {
              if (!(await confirmBox("Delete card", `Delete the card for “${c.expression}” from MiningCat? (A card already in Anki stays there.)`, "Delete"))) return;
              try { await api(`/api/cards/${c.id}/delete`, {}); loadCards(); updateBadge(); } catch (err) { showError(err); }
            },
          }, icon("trash"))));
    })));
  if (!cards.length) table.append(el("tbody", {}, el("tr", {}, el("td", { colspan: "4", class: "text-body-secondary", text: "No cards here." }))));
}

async function updateBadge() {
  try {
    const [{ cards: pending }, { cards: failed }] = await Promise.all([api(`/api/cards?status=pending&language=${STUDY}`), api(`/api/cards?status=failed&language=${STUDY}`)]);
    const n = pending.length + failed.length;
    $("pending-badge").hidden = n === 0;
    $("pending-badge").textContent = String(n);
  } catch { /* ignore */ }
}

async function exportCards() {
  try {
    const body = JSON.stringify({ language: STUDY });
    const res = await fetch("/api/cards/export", { method: "POST", headers: { "Content-Type": "application/json", "X-MiningCat": "1" }, body });
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

// ---------------------------------------------------------------- e-reader (KOReader plugin)

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); MiningCatUI.toast("Copied", "success"); } catch (err) { showError(err); }
}

const copyButton = (text) => el("button", { type: "button", class: "btn btn-sm btn-outline-secondary", onclick: () => copyText(text) }, icon("copy"), " Copy");

function renderEreader(c) {
  $("ereader-enabled").checked = c.enabled;
  $("ereader-port").value = c.port;
  $("ereader-firewall").hidden = !c.listening;
  const state = $("ereader-state");
  state.className = `small m-0 ${c.error ? "text-danger" : c.listening ? "text-success" : "text-body-secondary"}`;
  state.textContent = c.error ? c.error
    : c.listening ? `On: the e-reader can send words to port ${c.port}.`
    : "Off: the e-reader can't reach MiningCat.";
  $("ereader-addresses").replaceChildren(...(c.addresses.length
    ? c.addresses.map((address) => el("div", { class: "d-flex flex-wrap align-items-center gap-2" },
      el("code", { class: "fs-5 user-select-all", text: address }), copyButton(address)))
    : [el("p", { class: EMPTY, text: "This computer isn't on a local network." })]));
  $("ereader-token").textContent = c.token;
  $("ereader-token-copy").onclick = () => copyText(c.token);
}

async function loadEreader() {
  try { renderEreader(await api("/api/ereader/config")); } catch (err) { showError(err); }
}

async function saveEreader(values) {
  try { renderEreader(await api("/api/ereader/config", values)); } catch (err) { showError(err); loadEreader(); }
}

async function renewEreaderToken() {
  if (!await confirmBox("New token", "The e-reader can't send words with the old token anymore: you'll enter the new one in KOReader.", "New token")) return;
  try { renderEreader(await api("/api/ereader/token", {})); } catch (err) { showError(err); }
}

// ---------------------------------------------------------------- user preferences: Discord (the colours: theme.js)
function markDiscord(choice) {
  for (const button of document.querySelectorAll("[data-mc-discord-choice]")) {
    const on = button.dataset.mcDiscordChoice === choice;
    button.classList.toggle("active", on);
    button.setAttribute("aria-pressed", String(on));
  }
}

async function loadDiscord() {
  markDiscord((await api("/api/preferences")).discord);
  for (const button of document.querySelectorAll("[data-mc-discord-choice]")) {
    button.addEventListener("click", async () => {
      try { markDiscord((await api("/api/preferences", { discord: button.dataset.mcDiscordChoice })).discord); } catch (err) { showError(err); }
    });
  }
}

// ---------------------------------------------------------------- init

async function init() {
  try {
    loadDiscord().catch(showError);
    await loadLanguages();
    await loadDictionaries();
    $("dict-pick").addEventListener("click", () => $("dict-file").click());
    $("dict-file").addEventListener("change", (e) => { const f = e.target.files[0]; e.target.value = ""; importDictionary(f); });
    await loadFrequency();
    $("freq-pick").addEventListener("click", () => $("freq-file").click());
    $("freq-file").addEventListener("change", (e) => { const f = e.target.files[0]; e.target.value = ""; importDictionary(f, "freq"); });
    $("words-filter").addEventListener("change", loadWords);
    $("words-order").addEventListener("change", loadWords);
    $("anki-test").addEventListener("click", async () => {
      try { await api("/api/anki/config", { url: $("anki-url").value }); } catch (err) { return showError(err); }
      refreshAnki();
    });
    $("note-save").addEventListener("click", saveNoteSetup);
    $("tts-use-edge").addEventListener("change", saveLocalVoice);
    $("tts-steps").addEventListener("change", saveLocalVoice);
    $("taigi-voice").addEventListener("change", saveTaigiVoice);
    $("tts-new-voice").addEventListener("click", newLocalVoice);
    $("tts-install").addEventListener("click", installOmniVoice);
    $("el-key-save").addEventListener("click", saveElevenLabsKey);
    $("el-save").addEventListener("click", () => saveElevenLabs({ model: $("el-model").value, voice: $("el-voice").value.trim() }));
    $("el-main").addEventListener("change", toggleElevenLabsMain);
    $("mms-install").addEventListener("click", installTaigiVoice);
    $("note-type-install").addEventListener("click", installNoteType);
    $("deck-create").addEventListener("click", createDeck);
    $("translation-save").addEventListener("click", saveTranslation);
    $("translation-model").addEventListener("change", renderCardsContext);
    $("sync-add").addEventListener("click", () => {
      $("sync-sources").querySelector(".sync-empty")?.remove();
      $("sync-sources").append(syncRow());
    });
    $("sync-save").addEventListener("click", async () => {
      try { await saveSync(); $("sync-report").textContent = "Saved."; } catch (err) { showError(err); }
    });
    $("sync-now").addEventListener("click", syncNow);
    $("cards-filter").addEventListener("change", loadCards);
    $("cards-send").addEventListener("click", async () => {
      try {
        const r = await api("/api/cards/send-pending", { language: STUDY });
        dialog("Cards", `${r.sent} sent to Anki, ${r.failed} refused, ${r.pending} still waiting.`);
        loadCards(); updateBadge();
      } catch (err) { showError(err); }
    });
    $("cards-export").addEventListener("click", exportCards);
    $("ereader-enabled").addEventListener("change", () => saveEreader({ enabled: $("ereader-enabled").checked }));
    $("ereader-port-save").addEventListener("click", () => saveEreader({ port: $("ereader-port").value }));
    $("ereader-token-new").addEventListener("click", renewEreaderToken);
    window.addEventListener("hashchange", showTab);
    showTab();
    updateBadge();
  } catch (err) {
    showError(err);
  }
}

document.addEventListener("DOMContentLoaded", init);
