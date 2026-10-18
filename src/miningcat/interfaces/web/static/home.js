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
  study = current;
  loadReviews();
  loadInbox();
}

// The words sent from the e-reader, waiting for a card.
async function loadInbox() {
  let counts;
  try { ({ counts } = await api("/api/inbox")); } catch { return; }
  const n = counts[study.id] || 0;
  $("inbox-count").textContent = n;
  $("inbox-count").title = `${n} word${n === 1 ? "" : "s"} waiting`;
  $("inbox-count").hidden = !n;
}

// ---------------------------------------------------------------- Anki reviews

const plural = (n, word) => `${n.toLocaleString()} ${word}${n === 1 ? "" : "s"}`;

// `name`: the language studied, whose decks count.
function reviewsMessage(r, name) {
  switch (r.state) {
    case "not_started": return ["alarm", `You haven't started your ${name} reviews in Anki yet: ${plural(r.due, "card")} due today.`];
    case "in_progress": return ["hourglass-split", `Keep going: ${plural(r.due, "card")} left in your ${name} decks (${r.reviewed.toLocaleString()} reviewed today).`];
    case "done": return ["check-circle", `You're done with your ${name} reviews in Anki for today! ${plural(r.reviewed, "card")} reviewed.`];
    default: return ["cup-hot", `Nothing to review in your ${name} decks today.`];
  }
}

function streakText(r) {
  if (!r.streak) return r.longest ? `No streak right now · longest: ${plural(r.longest, "day")}` : "Review today to start a streak.";
  const longest = r.longest > r.streak ? ` · longest: ${plural(r.longest, "day")}` : "";
  return `🔥 ${r.streak.toLocaleString()}-day streak${longest}`;
}

// Dates as "YYYY-MM-DD", computed in UTC so that no time zone shifts a day.
const isoDay = (t) => new Date(t).toISOString().slice(0, 10);
const DAY_MS = 86_400_000;
const SVG_NS = "http://www.w3.org/2000/svg";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function svg(tag, attrs, ...children) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  node.append(...children);
  return node;
}

// The reviews of each day of a year, a column per week (Monday on top), darker with more reviews. The days after
// today aren't drawn.
function heatmap(days, todayIso, year) {
  const CELL = 11, GAP = 3, STEP = CELL + GAP, TOP = 14;
  const today = Date.parse(`${todayIso}T00:00:00Z`);
  const first = Date.UTC(year, 0, 1), last = Date.UTC(year, 11, 31);
  const start = first - ((new Date(first).getUTCDay() + 6) % 7) * DAY_MS;  // the Monday of the week of January 1st
  const WEEKS = Math.floor((last - start) / DAY_MS / 7) + 1;  // 53 or 54
  // 4 shades, from the quartiles of the year's days with reviews
  const counts = Object.entries(days).filter(([day, n]) => n > 0 && day.startsWith(`${year}-`)).map(([, n]) => n)
    .sort((a, b) => a - b);
  const quartile = (q) => counts[Math.min(counts.length - 1, Math.floor(q * counts.length))] || 0;
  const limits = [quartile(0.25), quartile(0.5), quartile(0.75)];
  const shade = (n) => (n <= 0 ? 0 : 1 + limits.filter((limit) => n > limit).length);
  const FILL = ["var(--bs-secondary-bg)", ".3", ".55", ".8", "1"];
  // --mc-week: the rainbow colour's hue (theme.css), 0 to 52, from red in January to violet in December
  const hue = (week) => Math.round((week * 52) / (WEEKS - 1));
  const style = (level, week) => (level ? `fill: var(--mc-heatmap-cell); fill-opacity: ${FILL[level]}; --mc-week: ${hue(week)}` : `fill: ${FILL[0]}`);

  const root = svg("svg", { viewBox: `0 0 ${WEEKS * STEP - GAP} ${TOP + 7 * STEP - GAP}`, role: "img",
    "aria-label": `Anki reviews per day in ${year}`, class: "d-block w-100 h-auto" });
  let month = null;
  for (let week = 0; week < WEEKS; week++) {
    // the month of the week's first day of the year, written over its first week
    const monday = Math.max(start + week * 7 * DAY_MS, first);
    if (new Date(monday).getUTCMonth() !== month) {
      month = new Date(monday).getUTCMonth();
      if (week < WEEKS - 2) root.append(svg("text", { x: week * STEP, y: 9, style: "fill: var(--bs-secondary-color); font-size: 9px" }, MONTHS[month]));
    }
    for (let day = 0; day < 7; day++) {
      const t = start + (week * 7 + day) * DAY_MS;
      if (t > today || t > last) break;
      if (t < first) continue;
      const iso = isoDay(t);
      const n = days[iso] || 0;
      const date = new Date(t).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
      root.append(svg("rect", { x: week * STEP, y: TOP + day * STEP, width: CELL, height: CELL, rx: 2, class: "mc-heatmap-cell", style: style(shade(n), week) },
        svg("title", {}, `${n ? plural(n, "review") : "No review"} · ${date}`)));
    }
  }
  return root;
}

let study = null;  // the language studied ({id, name...}): only its decks count
let reviewsShown = null;  // the last reviews read ({today, days...}) and the year of the heatmap
let heatmapYear = null;

// The heatmap of a year, with its buttons: the year before when it has reviews, this year, the year after up to this one.
function showYear(year) {
  const r = reviewsShown;
  const thisYear = Number(r.today.slice(0, 4));
  heatmapYear = year;
  $("reviews-history-title").textContent = `Your ${study.name} reviews in ${year}`;
  $("reviews-heatmap").replaceChildren(heatmap(r.days, r.today, year));
  $("reviews-year-prev").disabled = !Object.keys(r.days).some((day) => day < `${year}-01-01`);
  $("reviews-year-current").disabled = year === thisYear;
  $("reviews-year-next").disabled = year >= thisYear;
}

function reviewsNotice(text) {
  const message = $("reviews-message");
  message.className = "small text-body-secondary m-0";
  message.textContent = text;
  $("reviews-streak").textContent = "";
  $("reviews").hidden = false;
  $("reviews-history").hidden = true;
}

async function loadReviews() {
  if (!study) return;
  let r;
  try { r = await api(`/api/anki/reviews?language=${encodeURIComponent(study.id)}`); } catch { return; }
  if (!r.linked) return reviewsNotice(`Link your ${study.name} decks in Settings › Anki to see your reviews and your streak here.`);
  if (!r.connected) return reviewsNotice(`Open Anki (with AnkiConnect) to see your ${study.name} reviews and your streak here.`);
  const [icon, text] = reviewsMessage(r, study.name);
  const message = $("reviews-message");
  message.className = `m-0${r.state === "not_started" ? " fw-semibold" : ""}`;
  const i = Object.assign(document.createElement("i"), { className: `bi bi-${icon} text-primary-emphasis me-2` });
  i.setAttribute("aria-hidden", "true");
  message.replaceChildren(i, text);
  $("reviews-streak").textContent = streakText(r);
  $("reviews").hidden = false;
  $("reviews-history-decks").textContent = r.decks.join(" · ");
  reviewsShown = r;
  showYear(heatmapYear ?? Number(r.today.slice(0, 4)));
  $("reviews-history").hidden = false;
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
  $("reviews-year-prev").addEventListener("click", () => showYear(heatmapYear - 1));
  $("reviews-year-current").addEventListener("click", () => showYear(Number(reviewsShown.today.slice(0, 4))));
  $("reviews-year-next").addEventListener("click", () => showYear(heatmapYear + 1));
  try {
    const { current, languages } = await api("/api/profile");
    if (current) renderHub(current);
    else renderPicker(languages, null);
    $("change-language").addEventListener("click", () => renderPicker(languages, current));
  } catch (err) { showError(err); }
}

document.addEventListener("DOMContentLoaded", init);
// Back from Anki: the reviews made meanwhile show up.
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && !$("hub").hidden) { loadReviews(); loadInbox(); }
});
