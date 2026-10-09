// MiningCat converter, "CSV to cards": a card for each row of a CSV file (a word and its sentence, at least), filled
// like the card creator fills one (mining.js): definitions from the user's dictionaries, the word's recording, the
// sentences read by a voice and translated. Runs in the browser, with the converter's progress bar and log (app.js).
"use strict";

const CSV = {
  file: "",            // name of the CSV file
  header: [],
  rows: [],            // [[cell]]
  running: false,
  stop: false,
};

// Columns guessed from the header (the first match wins).
const CSV_GUESSES = {
  word: /^(word|words|hanzi|kanji|expression|vocab\w*|term|mot|front|target)$/i,
  sentence: /(sentence|phrase|example|exemple|context)/i,
  reading: /(pinyin|zhuyin|bopomofo|reading|kana|furigana|jyutping|pronunciation|prononciation|lecture)/i,
  translation: /(translation|traduction|meaning)/i,
  notes: /^(notes?|comments?|remarks?)$/i,
  tag: /^(level|niveau|tags?|lesson|le[cç]on|chapter|chapitre|hsk|tocfl|band)$/i,
};
const CSV_CONCURRENCY = 3;

function csvLanguage() {
  const study = JSON.parse(document.body.dataset.study || "null");
  return study ? study.id : "";
}

// ---------------------------------------------------------------- parsing

// RFC 4180: quoted cells may hold the delimiter, line breaks and doubled quotes. The delimiter is the one of
// , ; and tab found most often in the first line.
function parseCsv(text) {
  text = text.replace(/^﻿/, "");
  const firstLine = text.slice(0, text.search(/\r?\n|$/)).replace(/"[^"]*"/g, "");
  const delimiter = [",", ";", "\t"].reduce((best, d) => (firstLine.split(d).length > firstLine.split(best).length ? d : best), ",");
  const rows = [];
  let row = [], cell = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') { cell += '"'; i++; }
      else if (ch === '"') quoted = false;
      else cell += ch;
    } else if (ch === '"' && cell === "") {
      quoted = true;
    } else if (ch === delimiter) {
      row.push(cell); cell = "";
    } else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(cell); cell = "";
      rows.push(row); row = [];
    } else {
      cell += ch;
    }
  }
  if (cell !== "" || row.length) { row.push(cell); rows.push(row); }
  return rows.filter((r) => r.some((c) => c.trim()));
}

// ---------------------------------------------------------------- screen

function csvColumnSelect(id, optional) {
  const select = $(id);
  const options = CSV.header.map((name, i) => new Option(name || `Column ${i + 1}`, String(i)));
  select.replaceChildren(...(optional ? [new Option("—", "")] : []), ...options);
  return select;
}

function csvColumn(id) {
  const value = $(id).value;
  return value === "" ? -1 : Number(value);
}

function guessColumn(kind, taken) {
  return CSV.header.findIndex((name, i) => !taken.has(i) && CSV_GUESSES[kind].test(name));
}

function renderCsvPreview() {
  const table = $("csv-preview");
  const columns = [["Word", "csv-col-word"], ["Pronunciation", "csv-col-reading"], ["Sentence", "csv-col-sentence"],
    ["Translation", "csv-col-translation"], ["Notes", "csv-col-notes"], ["Tag", "csv-col-tag"]]
    .map(([label, id]) => [label, csvColumn(id)]).filter(([, i]) => i >= 0);
  const head = document.createElement("tr");
  for (const [label] of columns) head.append(Object.assign(document.createElement("th"), { textContent: label }));
  const body = CSV.rows.slice(0, 3).map((row) => {
    const tr = document.createElement("tr");
    for (const [, i] of columns) tr.append(Object.assign(document.createElement("td"), { textContent: row[i] || "" }));
    return tr;
  });
  table.replaceChildren(head, ...body);
  table.lang = (JSON.parse(document.body.dataset.study || "null") || {}).tag || "";
}

async function selectCsv(fileList) {
  const file = fileList[0];
  if (!file) return;
  let rows;
  try {
    rows = parseCsv(await file.text());
  } catch (err) {
    showError(new ApiError("CSV", `This file couldn't be read: ${err.message}`));
    return;
  }
  if (rows.length < 2) {
    showError(new ApiError("CSV", "The file needs a first row naming the columns, then one row per card."));
    return;
  }
  CSV.file = file.name;
  CSV.header = rows[0].map((c) => c.trim());
  CSV.rows = rows.slice(1);
  $("csv-label").textContent = `${file.name} — ${CSV.rows.length.toLocaleString()} row${CSV.rows.length > 1 ? "s" : ""}`;
  setSelected($("csv-label"), true);
  $("csv-source").value = file.name.replace(/\.(csv|tsv|txt)$/i, "");

  const taken = new Set();
  for (const [kind, id, optional] of [["word", "csv-col-word", false], ["sentence", "csv-col-sentence", false],
    ["reading", "csv-col-reading", true], ["translation", "csv-col-translation", true], ["notes", "csv-col-notes", true],
    ["tag", "csv-col-tag", true]]) {
    const select = csvColumnSelect(id, optional);
    const guess = guessColumn(kind, taken);
    if (guess >= 0) { select.value = String(guess); taken.add(guess); }
    else if (!optional) select.value = String(CSV.header.findIndex((_, i) => !taken.has(i)));
  }
  for (const id of ["csv-columns-panel", "csv-content-panel", "csv-tags-panel"]) $(id).hidden = false;
  renderCsvPreview();
  renderCsvActions();
}

function renderCsvActions() {
  const ready = CSV.rows.length > 0 && !S.running && S.uploads === 0;
  $("csv-start").disabled = $("csv-later").disabled = !ready;
  $("csv-stop").hidden = !CSV.running;
  $("csv-stop").disabled = CSV.stop;
}

async function setupCsv() {
  const language = csvLanguage();
  filePicker("csv-select", "csv-input", ".csv,.tsv,.txt,text/csv", selectCsv);
  for (const id of ["csv-col-word", "csv-col-sentence", "csv-col-reading", "csv-col-translation", "csv-col-notes", "csv-col-tag"]) {
    $(id).addEventListener("change", renderCsvPreview);
  }
  $("csv-start").addEventListener("click", () => runCsv(true));
  $("csv-later").addEventListener("click", () => runCsv(false));
  $("csv-stop").addEventListener("click", () => { CSV.stop = true; renderCsvActions(); setStatus("Stopping after the cards being made…", 0); });
  if (!language) return;

  const kinds = MiningCatMining.cardParts.definitionKinds(language);
  $("csv-definitions").replaceChildren(...kinds.map(([key, label], i) => {
    const item = Object.assign(document.createElement("label"), { className: "form-check form-check-inline" });
    item.append(Object.assign(document.createElement("input"), { className: "form-check-input", type: "checkbox", value: key, checked: i === 0 }),
      Object.assign(document.createElement("span"), { className: "form-check-label", textContent: label }));
    return item;
  }));
  $("csv-readings-help").hidden = language !== "zh";

  try {
    const { voices, default: fallback, chosen } = await api(`/api/tts/voices?language=${encodeURIComponent(language)}`);
    $("csv-voice").replaceChildren(...voices.map((v) => new Option(v.label, v.id)));
    $("csv-voice").value = chosen || fallback;
    if (!voices.length) {
      $("csv-voice-field").hidden = true;
      $("csv-word-audio").value = "online";
      $("csv-word-audio").querySelector('option[value="voice"]').remove();
      $("csv-sentence-audio").value = "";
      $("csv-sentence-audio").disabled = true;
    }
  } catch { /* no voices: the selects keep their defaults and generation errors are logged */ }

  try {
    const { config } = await api("/api/anki/config");
    const setup = config.notes[language];
    $("csv-target").textContent = setup && setup.deck && setup.model
      ? `Anki: ${setup.deck} › ${setup.model}`
      : "No Anki note type set for this language yet (Settings › Anki): the cards will wait until then.";
  } catch { /* shown when Anki is set up */ }
}

// ---------------------------------------------------------------- making the cards

function escapeCsvHtml(text) {
  const d = document.createElement("div");
  d.textContent = text;
  return d.innerHTML;
}

// The sentence with the word in bold, like the card creator's (its first occurrence).
function sentenceHtml(sentence, word) {
  const at = word ? sentence.indexOf(word) : -1;
  if (at < 0) return escapeCsvHtml(sentence);
  return `${escapeCsvHtml(sentence.slice(0, at))}<b>${escapeCsvHtml(word)}</b>${escapeCsvHtml(sentence.slice(at + word.length))}`;
}

// The dictionary entry of the word: written like it, of the CSV's pronunciation when there is one.
async function csvEntry(language, word, reading) {
  const data = await api("/api/dict/lookup", { language, text: word, reading });
  const same = data.entries.filter((e) => e.expression === word || e.form === word);
  same.sort((a, b) => (b.reading_match || 0) - (a.reading_match || 0));
  return same[0] || null;
}

async function voiceAudio(language, text, voice, name) {
  const audio = await api("/api/tts", { language, text, voice });
  return { data: audio.data, name };
}

async function makeCsvCard(row, settings) {
  const { language, columns } = settings;
  const cell = (key) => (columns[key] >= 0 ? (row[columns[key]] || "").trim() : "");
  const word = cell("word"), sentence = cell("sentence"), csvReading = cell("reading");
  const parts = MiningCatMining.cardParts;
  const entry = await csvEntry(language, word, csvReading).catch(() => null);
  const notes = [];

  const definition = entry && settings.definitions.length ? parts.definitionHtml(entry, language, settings.definitions) : "";
  if (!entry) notes.push("not in your dictionaries");
  const reading = csvReading || (entry && entry.reading !== entry.expression ? entry.display_reading || entry.reading : "");

  let translation = cell("translation");
  if (!translation && settings.translate && sentence) {
    translation = await parts.translateSentence(language, sentence).catch((err) => { notes.push(`no translation: ${err.message}`); return ""; }) || "";
  }

  const media = {};
  if (settings.wordAudio === "online") {
    const sources = await parts.wordAudio({ expression: word, reading: entry ? entry.reading : csvReading }, language).catch(() => []);
    if (sources.length) media.audio = { url: sources[0].url };
  }
  if (!media.audio && settings.wordAudio && settings.voice) {
    media.audio = await voiceAudio(language, word, settings.voice, "word.mp3").catch((err) => { notes.push(`no word audio: ${err.message}`); return undefined; });
  }
  if (settings.sentenceAudio && settings.voice && sentence) {
    media.sentence_audio = await voiceAudio(language, sentence, settings.voice, "sentence.mp3")
      .catch((err) => { notes.push(`no sentence audio: ${err.message}`); return undefined; });
  }
  for (const key of Object.keys(media)) if (!media[key]) delete media[key];

  const tagValue = cell("tag").replace(/\s+/g, "_");
  const { card } = await api("/api/cards", {
    language, send: settings.send, tags: [settings.tags, tagValue].filter(Boolean).join(" "),
    key_reading: entry && entry.reading !== entry.expression ? entry.reading : "",
    fields: {
      word, reading, definition, sentence: sentenceHtml(sentence, word), sentence_translation: translation,
      notes: cell("notes"), source: settings.source, frequency: entry && entry.frequency_rank ? String(entry.frequency_rank) : "",
    },
    media,
  });
  return { card, notes };
}

// The rows to make cards of, and why the others are left out.
async function csvPlan(settings) {
  const limit = parseInt($("csv-limit").value, 10);
  const rows = Number.isFinite(limit) && limit > 0 ? CSV.rows.slice(0, limit) : CSV.rows;
  const word = (row) => (row[settings.columns.word] || "").trim();
  let statuses = {};
  if (settings.skip) {
    const words = [...new Set(rows.map(word).filter(Boolean))];
    for (let i = 0; i < words.length; i += 20000) {
      Object.assign(statuses, (await api("/api/words/statuses", { language: settings.language, expressions: words.slice(i, i + 20000) })).statuses);
    }
  }
  const seen = new Set();
  return rows.map((row, i) => {
    const w = word(row);
    const line = i + 2;  // the header is line 1
    if (!w) return { line, row, skip: "no word" };
    if (!settings.skip) return { line, row };
    const key = `${w}|${(row[settings.columns.reading] || "").trim()}`;
    if (seen.has(key)) return { line, row, skip: "repeated" };
    seen.add(key);
    if (statuses[w]) return { line, row, skip: `already ${statuses[w]}` };
    return { line, row };
  });
}

async function runCsv(send) {
  const language = csvLanguage();
  const columns = {
    word: csvColumn("csv-col-word"), sentence: csvColumn("csv-col-sentence"), reading: csvColumn("csv-col-reading"),
    translation: csvColumn("csv-col-translation"), notes: csvColumn("csv-col-notes"), tag: csvColumn("csv-col-tag"),
  };
  if (columns.word === columns.sentence) {
    showError(new ApiError("CSV", "Choose two different columns for the word and the sentence."));
    return;
  }
  const settings = {
    language, columns, send,
    definitions: [...$("csv-definitions").querySelectorAll("input:checked")].map((b) => b.value),
    wordAudio: $("csv-word-audio").value,
    sentenceAudio: $("csv-sentence-audio").value,
    voice: $("csv-voice").value,
    translate: $("csv-translate").checked,
    source: $("csv-source").value.trim(),
    tags: $("csv-tags").value.trim(),
    skip: $("csv-skip").checked,
  };

  CSV.running = true;
  CSV.stop = false;
  setRunning(true, "csv");
  $("log").textContent = "";
  const counts = { sent: 0, pending: 0, exported: 0, failed: 0, errors: 0, skipped: 0 };
  try {
    setStatus("Reading the CSV…", 0);
    const plan = await csvPlan(settings);
    const todo = plan.filter((p) => !p.skip);
    for (const p of plan.filter((p) => p.skip)) {
      counts.skipped++;
      appendLog(`· line ${p.line} ${(p.row[columns.word] || "").trim()}: skipped (${p.skip})\n`);
    }
    appendLog(`${todo.length} card${todo.length === 1 ? "" : "s"} to make from ${CSV.file}.\n`);

    let next = 0, done = 0, ankiWarned = false;
    const worker = async () => {
      while (next < todo.length && !CSV.stop) {
        const p = todo[next++];
        const word = (p.row[columns.word] || "").trim();
        try {
          const { card, notes } = await makeCsvCard(p.row, settings);
          counts[card.status] = (counts[card.status] || 0) + 1;
          // Anki closed: said once. Another reason to wait (a recording that couldn't be downloaded yet): on its card.
          const unreachable = card.status === "pending" && card.error && /reachable|Settings/.test(card.error);
          const state = { sent: "sent to Anki", failed: `refused by Anki (${card.error})`,
            pending: send && card.error && !unreachable ? `waiting (${card.error})` : "saved" }[card.status] || card.status;
          appendLog(`${card.status === "failed" ? "✗" : "✓"} line ${p.line} ${word}: ${state}${notes.length ? ` — ${notes.join("; ")}` : ""}\n`);
          if (send && unreachable && !ankiWarned) {
            ankiWarned = true;
            appendLog(`  ${card.error} The cards will be sent at the next sync.\n`);
          }
        } catch (err) {
          counts.errors++;
          appendLog(`✗ line ${p.line} ${word}: ${err.message}\n`);
        }
        done++;
        setStatus(`${done} / ${todo.length} cards`, (done / Math.max(1, todo.length)) * 100);
      }
    };
    await Promise.all(Array.from({ length: CSV_CONCURRENCY }, worker));

    const summary = [
      counts.sent && `${counts.sent} sent to Anki`,
      counts.pending && `${counts.pending} waiting for Anki`,
      counts.failed && `${counts.failed} refused by Anki`,
      counts.errors && `${counts.errors} errors`,
      counts.skipped && `${counts.skipped} rows skipped`,
    ].filter(Boolean).join(", ") || "No card made";
    setStatus(`${CSV.stop ? "Stopped" : "Done"}: ${summary}.`, CSV.stop ? (done / Math.max(1, todo.length)) * 100 : 100);
    appendLog(`\n${CSV.stop ? "Stopped" : "Done"}: ${summary}.\n`);
  } catch (err) {
    setStatus("", 0);
    showError(err);
  } finally {
    CSV.running = false;
    CSV.stop = false;
    setRunning(false);
  }
}

document.addEventListener("DOMContentLoaded", setupCsv);
