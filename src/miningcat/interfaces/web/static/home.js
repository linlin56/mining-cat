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
  loadInbox();
  syncThenLoadGoal(loadReviews());
}

// The word statuses come from Anki: synced first, so that the known words are today's (Anki closed: the last ones).
// Only the statuses: the cards waiting for Anki stay waiting until the user sends them.
// The last plan is shown at once; the new one once the sync is done (Anki answers one request at a time: asked
// together, both would wait for each other).
// The reviews first: the sync's many requests would make them wait.
async function syncThenLoadGoal(reviewsLoaded) {
  const shown = loadGoal(true);
  await Promise.all([reviewsLoaded, shown]);
  $("goal-updating").hidden = $("goal").hidden;
  try { await api("/api/anki/auto-sync", {}); } catch { /* Anki closed or not set up */ }
  await loadGoal();
  $("goal-updating").hidden = true;
  askDeletedWords();
}

// The words whose Anki note was deleted (they lost their status): which ones does the user know?
async function askDeletedWords() {
  let words;
  try { ({ words } = await api(`/api/anki/deleted-words?language=${encodeURIComponent(study.id)}`)); } catch { return; }
  if (!words.length) return;
  $("deleted-all").checked = false;
  $("deleted-list").replaceChildren(...words.map((w) => {
    const item = Object.assign(document.createElement("label"), { className: "list-group-item d-flex align-items-center gap-3" });
    const box = Object.assign(document.createElement("input"), { type: "checkbox", className: "form-check-input m-0 flex-shrink-0", value: w.id });
    const word = Object.assign(document.createElement("span"), { className: "fs-5", lang: study.tag, textContent: w.expression });
    const detail = Object.assign(document.createElement("span"), { className: "small text-body-secondary flex-grow-1",
      textContent: [w.reading, `was ${w.status}`].filter(Boolean).join(" · ") });
    item.append(box, word, detail);
    return item;
  }));
  MiningCatUI.showModal($("deleted-modal"));
}

async function saveDeletedWords() {
  const boxes = [...$("deleted-list").querySelectorAll("input")];
  const shown = boxes.map((box) => box.value), known = boxes.filter((box) => box.checked).map((box) => box.value);
  try {
    await api("/api/anki/deleted-words", { language: study.id, shown, known });
    MiningCatUI.hideModal($("deleted-modal"));
    loadGoal();
  } catch (err) { showError(err); }
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
  $("reviews-loading").hidden = !$("reviews").hidden;  // the first time: nothing shown yet
  let r;
  try { r = await api(`/api/anki/reviews?language=${encodeURIComponent(study.id)}`); } catch { return; } finally { $("reviews-loading").hidden = true; }
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

// ---------------------------------------------------------------- the vocabulary goal (Settings › User preferences)

const dayMs = (iso) => Date.parse(`${iso}T00:00:00Z`);
const longDate = (iso) => new Date(dayMs(iso)).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const fmt = (n) => Math.round(n).toLocaleString();

// A round step for an axis going up to `max`, with about `ticks` lines.
function niceStep(max, ticks = 4) {
  const raw = Math.max(1, max / ticks), power = 10 ** Math.floor(Math.log10(raw));
  return [1, 2, 2.5, 5, 10].map((m) => m * power).find((step) => step >= raw);
}

function tooltip(box) {
  const tip = Object.assign(document.createElement("div"), { className: "mc-chart-tip" });
  tip.hidden = true;
  box.append(tip);
  return (text, xRatio) => {
    tip.hidden = text === null;
    if (text === null) return;
    tip.textContent = text;
    const left = xRatio * box.clientWidth;
    tip.style.left = `${Math.min(Math.max(0, left - tip.offsetWidth / 2), box.clientWidth - tip.offsetWidth)}px`;
  };
}

const LINE = "var(--mc-heatmap)", NEEDED = "var(--bs-secondary-color)", GRID = "var(--bs-border-color)", INK = "var(--bs-secondary-color)";

// The known words of each day, then at the current pace (dashed) and the pace it takes (grey) to the nearest goal.
// The last `lag` days before it are shaded: a card first seen then won't be known in time. The other goals are
// points: filled when reached (on the day), hollow when missed (on their date, above the words known then) or to come.
function goalChart(box, g) {
  const W = 640, H = 220, L = 46, R = 12, T = 10, B = 22;
  const history = g.history.map(([day, n]) => [dayMs(day), n]);
  const today = dayMs(g.today), c = g.current, p = g.plan, by = c ? dayMs(c.by) : null;
  const known = history[history.length - 1][1];
  const start = Math.max(history[0][0], today - 730 * DAY_MS);
  const active = g.goals.filter((goal) => goal.status === "active");
  const end = Math.max(today + 14 * DAY_MS, ...active.map((goal) => dayMs(goal.by)));
  const shown = history.filter(([t]) => t >= start);
  const projected = (t) => known + g.pace * (t - today) / DAY_MS;
  const neededAt = (t) => (c && by > today ? known + (c.words - known) * Math.min(1, (t - today) / (by - today)) : null);
  const projectionEnd = p && p.eta ? Math.min(end, dayMs(p.eta)) : end;
  // where each other goal is drawn
  const markers = g.goals.filter((goal) => !c || goal.id !== c.id).map((goal) => {
    if (goal.status === "reached") {
      const early = Math.round((dayMs(goal.by) - dayMs(goal.reached_on)) / DAY_MS);
      return { goal, t: dayMs(goal.reached_on), text: `Goal reached on ${longDate(goal.reached_on)}: ${plural(goal.words, "word")}${early > 0 ? `, ${plural(early, "day")} early` : ""}` };
    }
    if (goal.status === "missed") {
      return { goal, t: dayMs(goal.by), text: `Goal missed: ${plural(goal.words, "word")} by ${longDate(goal.by)}, ${fmt(goal.missed_known)} known that day` };
    }
    return { goal, t: dayMs(goal.by), text: `Next goal: ${plural(goal.words, "word")} by ${longDate(goal.by)}` };
  }).filter((m) => m.t >= start && m.t <= end);
  const top = Math.max(c ? c.words : 0, known, p && p.pace ? projected(projectionEnd) : 0, ...markers.map((m) => m.goal.words)) * 1.08;
  const step = niceStep(top, 5);
  const yMax = Math.ceil(top / step) * step;
  const x = (t) => L + (W - L - R) * (t - start) / Math.max(DAY_MS, end - start);
  const y = (n) => T + (H - T - B) * (1 - n / yMax);

  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "d-block w-100 h-auto", role: "img",
    "aria-label": `Known words over time, ${fmt(known)} today${c ? `, goal ${fmt(c.words)} by ${longDate(c.by)}` : ""}` });
  for (let n = 0; n <= yMax; n += step) {
    root.append(svg("line", { x1: L, x2: W - R, y1: y(n), y2: y(n), stroke: GRID, "stroke-width": 1 }),
      svg("text", { x: L - 6, y: y(n) + 3, "text-anchor": "end", style: `fill: ${INK}; font-size: 10px` }, fmt(n)));
  }
  for (let i = 0; i <= 4; i++) {
    const t = start + (end - start) * i / 4;
    const label = new Date(t).toLocaleDateString(undefined, { month: "short", year: "2-digit", timeZone: "UTC" });
    root.append(svg("text", { x: x(t), y: H - 6, "text-anchor": i === 0 ? "start" : i === 4 ? "end" : "middle", style: `fill: ${INK}; font-size: 10px` }, label));
  }
  if (c) {
    // too late for new cards
    const late = Math.max(start, by - p.lag * DAY_MS);
    root.append(svg("rect", { x: x(late), y: T, width: Math.max(0, x(by) - x(late)), height: H - T - B, style: "fill: var(--bs-secondary-bg)" }));
    // the goal
    root.append(svg("line", { x1: L, x2: W - R, y1: y(c.words), y2: y(c.words), stroke: INK, "stroke-width": 1, "stroke-dasharray": "2 3" }),
      svg("text", { x: L + 4, y: y(c.words) - 4, style: `fill: ${INK}; font-size: 10px` }, `Goal: ${fmt(c.words)}`));
    root.append(svg("line", { x1: x(today), y1: y(known), x2: x(by), y2: y(c.words), stroke: NEEDED, "stroke-width": 2, "stroke-linecap": "round" }),
      svg("circle", { cx: x(by), cy: y(c.words), r: 4, fill: NEEDED, stroke: "var(--bs-body-bg)", "stroke-width": 2 }));
    if (g.pace > 0) {
      root.append(svg("line", { x1: x(today), y1: y(known), x2: x(projectionEnd), y2: y(projected(projectionEnd)), stroke: LINE, "stroke-width": 2, "stroke-dasharray": "5 4", "stroke-linecap": "round" }));
    }
  }
  root.append(svg("polyline", { points: shown.map(([t, n]) => `${x(t).toFixed(1)},${y(n).toFixed(1)}`).join(" "), fill: "none", stroke: LINE, "stroke-width": 2, "stroke-linejoin": "round" }),
    svg("circle", { cx: x(today), cy: y(known), r: 4, fill: LINE, stroke: "var(--bs-body-bg)", "stroke-width": 2 }));
  // the other goals; a missed one, with a dotted line down to the words known on its date
  const markerNodes = markers.map((m) => {
    const cx = x(m.t), cy = y(m.goal.words), status = m.goal.status;
    const group = svg("g", {});
    if (status === "missed") {
      group.append(svg("line", { x1: cx, x2: cx, y1: cy, y2: y(m.goal.missed_known), stroke: INK, "stroke-width": 1, "stroke-dasharray": "2 3" }));
    }
    group.append(svg("circle", status === "reached"
      ? { cx, cy, r: 6, fill: LINE, stroke: "var(--bs-body-bg)", "stroke-width": 2 }
      : { cx, cy, r: 5, fill: "var(--bs-body-bg)", stroke: status === "missed" ? INK : LINE, "stroke-width": 2 }));
    if (status === "reached") {
      group.append(svg("path", { d: `M${cx - 2.5},${cy} l1.8,1.8 l3.4,-3.6`, fill: "none", stroke: "var(--bs-body-bg)", "stroke-width": 1.6, "stroke-linecap": "round", "stroke-linejoin": "round" }));
    }
    const anchor = cx > W - R - 16 ? "end" : cx < L + 16 ? "start" : "middle";  // kept inside the chart
    group.append(svg("text", { x: cx, y: cy - 10, "text-anchor": anchor, style: `fill: ${INK}; font-size: 10px` }, fmt(m.goal.words)));
    group.append(svg("circle", { cx, cy, r: 11, fill: "transparent" }));  // a bigger target for the pointer
    return [group, m];
  });

  // hover: the day under the pointer
  const cursor = svg("line", { y1: T, y2: H - B, stroke: INK, "stroke-width": 1, visibility: "hidden" });
  const dot = svg("circle", { r: 4, fill: LINE, stroke: "var(--bs-body-bg)", "stroke-width": 2, visibility: "hidden" });
  const hit = svg("rect", { x: L, y: T, width: W - L - R, height: H - T - B, fill: "transparent" });
  root.append(cursor, dot, hit, ...markerNodes.map(([group]) => group));
  box.replaceChildren(root);
  const tip = tooltip(box);
  for (const [group, m] of markerNodes) {
    group.addEventListener("pointerenter", () => tip(m.text, x(m.t) / W));
    group.addEventListener("pointerleave", () => tip(null));
  }
  hit.addEventListener("pointermove", (e) => {
    const rect = root.getBoundingClientRect();
    const t = start + ((e.clientX - rect.left) / rect.width * W - L) / (W - L - R) * (end - start);
    const day = Math.round(t / DAY_MS) * DAY_MS;
    let n, text;
    if (day <= today) {
      const point = shown.reduce((best, pt) => (Math.abs(pt[0] - day) < Math.abs(best[0] - day) ? pt : best), shown[0]);
      [n, text] = [point[1], `${longDate(isoDay(point[0]))} · ${plural(point[1], "known word")}`];
      dot.setAttribute("cx", x(point[0]));
    } else {
      n = c && g.pace > 0 ? Math.min(projected(day), projected(projectionEnd)) : known;
      text = c ? `${longDate(isoDay(day))} · current pace: ${fmt(n)}${by > today && day <= by ? ` · needed: ${fmt(neededAt(day))}` : ""}`
        : `${longDate(isoDay(day))} · no goal in progress`;
      dot.setAttribute("cx", x(day));
    }
    dot.setAttribute("cy", y(n));
    cursor.setAttribute("x1", dot.getAttribute("cx"));
    cursor.setAttribute("x2", dot.getAttribute("cx"));
    cursor.setAttribute("visibility", "visible");
    dot.setAttribute("visibility", "visible");
    tip(text, Number(dot.getAttribute("cx")) / W);
  });
  hit.addEventListener("pointerleave", () => { cursor.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden"); tip(null); });
}

// The words that became known each week (Monday to Sunday) of the last 26, and the pace the goal takes.
function weeksChart(box, g) {
  const W = 640, H = 140, L = 46, R = 12, T = 10, B = 22, WEEKS = 26;
  const values = new Map(g.history.map(([day, n]) => [dayMs(day), n]));
  const today = dayMs(g.today);
  const monday = today - ((new Date(today).getUTCDay() + 6) % 7) * DAY_MS;
  const valueAt = (t) => values.get(t) ?? 0;  // the known words at the end of a day (the history has every day)
  const weeks = [];
  for (let i = WEEKS - 1; i >= 0; i--) {
    const first = monday - i * 7 * DAY_MS, last = Math.min(first + 6 * DAY_MS, today);
    weeks.push([first, Math.max(0, valueAt(last) - valueAt(first - DAY_MS))]);
  }
  const needed = g.plan && g.plan.needed_pace ? g.plan.needed_pace * 7 : 0;
  const top = Math.max(needed, ...weeks.map(([, n]) => n), 1) * 1.1;
  const step = niceStep(top, 3);
  const yMax = Math.ceil(top / step) * step;
  const y = (n) => T + (H - T - B) * (1 - n / yMax);
  const slot = (W - L - R) / WEEKS, bar = Math.max(2, slot - 4);
  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "d-block w-100 h-auto", role: "img", "aria-label": "Words known each week, the last 26 weeks" });
  for (let n = 0; n <= yMax; n += step) {
    root.append(svg("line", { x1: L, x2: W - R, y1: y(n), y2: y(n), stroke: GRID, "stroke-width": 1 }),
      svg("text", { x: L - 6, y: y(n) + 3, "text-anchor": "end", style: `fill: ${INK}; font-size: 10px` }, fmt(n)));
  }
  const tip = tooltip(box);
  weeks.forEach(([first, n], i) => {
    const bx = L + i * slot + (slot - bar) / 2;
    const text = `Week of ${longDate(isoDay(first))} · ${plural(n, "word")}`;
    if (n > 0) {
      const h = H - B - y(n), r = Math.min(4, bar / 2, h);
      root.append(svg("path", { d: `M${bx},${H - B} V${y(n) + r} Q${bx},${y(n)} ${bx + r},${y(n)} H${bx + bar - r} Q${bx + bar},${y(n)} ${bx + bar},${y(n) + r} V${H - B} Z`, fill: LINE }));
    }
    const hit = svg("rect", { x: L + i * slot, y: T, width: slot, height: H - T - B, fill: "transparent" });
    hit.addEventListener("pointerenter", () => tip(text, (L + (i + 0.5) * slot) / W));
    hit.addEventListener("pointerleave", () => tip(null));
    root.append(hit);
    if (i % 4 === 1) {
      root.append(svg("text", { x: L + (i + 0.5) * slot, y: H - 6, "text-anchor": "middle", style: `fill: ${INK}; font-size: 10px` },
        new Date(first).toLocaleDateString(undefined, { day: "numeric", month: "short", timeZone: "UTC" })));
    }
  });
  if (needed) {
    root.append(svg("line", { x1: L, x2: W - R, y1: y(needed), y2: y(needed), stroke: NEEDED, "stroke-width": 2, "stroke-linecap": "round", "pointer-events": "none" }),
      svg("text", { x: W - R, y: y(needed) - 4, "text-anchor": "end", style: `fill: ${INK}; font-size: 10px` }, `needed: ${fmt(needed)} a week`));
  }
  box.prepend(root);
}

function statTile(label, value, detail) {
  const col = Object.assign(document.createElement("div"), { className: "col" });
  const tile = Object.assign(document.createElement("div"), { className: "h-100 border rounded p-3 vstack gap-1" });
  tile.append(Object.assign(document.createElement("span"), { className: "small text-body-secondary", textContent: label }),
    Object.assign(document.createElement("strong"), { className: "fs-4 lh-sm", textContent: value }),
    Object.assign(document.createElement("span"), { className: "small text-body-secondary", textContent: detail }));
  col.append(tile);
  return col;
}

function legendItem(color, dashed, text) {
  const item = Object.assign(document.createElement("span"), { className: "d-inline-flex align-items-center gap-1" });
  item.append(svg("svg", { width: 18, height: 6, "aria-hidden": "true" },
    svg("line", { x1: 1, x2: 17, y1: 3, y2: 3, stroke: color, "stroke-width": 2, "stroke-linecap": "round", ...(dashed ? { "stroke-dasharray": "4 3" } : {}) })), text);
  return item;
}

function legendMarker(style, text) {
  const item = Object.assign(document.createElement("span"), { className: "d-inline-flex align-items-center gap-1" });
  item.append(svg("svg", { width: 12, height: 12, "aria-hidden": "true" },
    svg("circle", { cx: 6, cy: 6, r: 4.5, "stroke-width": 1.8, stroke: "none", ...style })), text);
  return item;
}

function goalStats(g) {
  const p = g.plan, a = g.anki, c = g.current;
  const paceText = `${p.pace.toLocaleString()} words a day over the last 30 days${p.needed_pace !== null ? ` · ${p.needed_pace.toLocaleString()} needed` : ""}`;
  const eta = statTile("At your current pace", p.eta ? longDate(p.eta) : "Not yet", p.eta ? paceText : `No word became known in the last 30 days. ${paceText}`);
  let cards;
  if (p.too_late) cards = statTile("New cards a day", "Too late", `A card takes about ${plural(p.lag, "day")} to be known: new cards won't be by ${longDate(c.by)}.`);
  else {
    const deck = p.deck_new_per_day !== null
      ? `Your decks: ${p.deck_new_per_day} a day${p.raise_limit ? ": raise it in Anki" : ""}.${p.deck_eta ? ` As they are, around ${longDate(p.deck_eta)}.` : ""}`
      : "To show it, " + (a.linked ? "open Anki." : "link your decks in Settings › Anki.");
    cards = statTile("New cards a day", p.new_per_day !== null ? fmt(p.new_per_day) : "–", `To see in Anki until ${longDate(isoDay(dayMs(c.by) - p.lag * DAY_MS))}. ${deck}`);
  }
  const mine = p.mine_per_day === null
    ? statTile("Cards to mine a day", "–", a.linked ? "Open Anki (with AnkiConnect) to count the new cards waiting." : "Link your decks in Settings › Anki to count the new cards waiting.")
    : statTile("Cards to mine a day", fmt(p.mine_per_day),
      `${plural(p.backlog, "new card")} waiting${p.backlog_days !== null ? `: ${plural(p.backlog_days, "day")} at your decks' limit` : ""}.`);
  return [eta, cards, mine];
}

// The news of the goals: one reached or missed in the last two weeks, or none in progress any more.
const RECENT_DAYS = 14;

function goalBanner(g, known) {
  const today = dayMs(g.today), c = g.current;
  const settledOn = (goal) => dayMs(goal.status === "reached" ? goal.reached_on : goal.by);
  const recent = g.goals.filter((goal) => goal.status !== "active" && today - settledOn(goal) <= RECENT_DAYS * DAY_MS)
    .sort((a, b) => settledOn(b) - settledOn(a))[0];
  const next = c ? ` Next: ${plural(c.words, "word")} by ${longDate(c.by)}.` : null;
  const link = (text) => Object.assign(document.createElement("a"), { href: "/settings/#preferences", className: "alert-link", textContent: text });
  if (recent && recent.status === "reached") {
    const early = Math.round((dayMs(recent.by) - dayMs(recent.reached_on)) / DAY_MS);
    return ["alert-success", "trophy",
      [`You reached your goal of ${plural(recent.words, "word")} on ${longDate(recent.reached_on)}${early > 0 ? `, ${plural(early, "day")} early` : ""}! `,
        next || link("Set your next goal")]];
  }
  if (recent) {
    const share = Math.round(100 * recent.missed_known / recent.words);
    const since = known >= recent.words ? "You've got there since." : g.pace > 0
      ? `At your current pace, you'll get there around ${longDate(isoDay(today + Math.ceil((recent.words - known) / g.pace) * DAY_MS))}.` : "";
    return ["alert-secondary", "hourglass-bottom",
      [`Your goal of ${plural(recent.words, "word")} by ${longDate(recent.by)} wasn't reached: you knew ${fmt(recent.missed_known)} that day (${share}%). ${since} `,
        next || link("Set a new goal")]];
  }
  if (!c) return ["alert-secondary", "flag", ["No goal in progress. ", link("Set your next goal")]];
  return null;
}

// cached: the last plan made, shown at once (a new one takes seconds: Anki is read).
async function loadGoal(cached = false) {
  if (!study) return;
  const language = study.id;
  $("goal-loading").hidden = !($("goal").hidden && $("goal-intro").hidden);  // the first time: nothing shown yet
  let g;
  try { g = await api(`/api/goals/plan?language=${encodeURIComponent(language)}${cached ? "&cached=1" : ""}`); } catch { return; } finally { $("goal-loading").hidden = true; }
  if (!study || study.id !== language) return;  // another language chosen meanwhile
  $("goal-intro").hidden = g.goals.length > 0;
  if (!g.goals.length) { $("goal").hidden = true; return; }
  const c = g.current, p = g.plan;
  const known = g.history[g.history.length - 1][1];
  const banner = goalBanner(g, known);
  $("goal-banner").hidden = !banner;
  if (banner) {
    const [kind, icon, content] = banner;
    $("goal-banner").className = `alert ${kind} d-flex align-items-start gap-2 small m-0`;
    const i = Object.assign(document.createElement("i"), { className: `bi bi-${icon}` });
    i.setAttribute("aria-hidden", "true");
    const text = document.createElement("span");
    text.append(...content.filter(Boolean));
    $("goal-banner").replaceChildren(i, text);
  }
  $("goal-current").hidden = !c;
  if (c) {
    const share = Math.min(100, Math.round(100 * known / c.words));
    $("goal-title").textContent = `Your goal: ${plural(c.words, `${study.name} word`)} by ${longDate(c.by)} · ${fmt(known)} known (${share}%)`;
    $("goal-progress").setAttribute("aria-valuenow", share);
    $("goal-progress").firstElementChild.style.width = `${share}%`;
    $("goal-stats").replaceChildren(...goalStats(g));
  } else {
    $("goal-title").textContent = `Your ${study.name} words: ${fmt(known)} known`;
  }
  $("goal").hidden = false;  // drawn once visible: the tooltips need the box's width
  goalChart($("goal-chart"), g);
  $("goal-weeks").replaceChildren();
  weeksChart($("goal-weeks"), g);
  const legend = [legendItem(LINE, false, "Known words")];
  if (c) legend.push(legendItem(LINE, true, "At your current pace"), legendItem(NEEDED, false, "The pace your goal takes"));
  const shownStatuses = new Set(g.goals.filter((goal) => !c || goal.id !== c.id).map((goal) => goal.status));
  if (shownStatuses.has("reached")) legend.push(legendMarker({ fill: LINE }, "Goal reached"));
  if (shownStatuses.has("missed")) legend.push(legendMarker({ fill: "var(--bs-body-bg)", stroke: INK }, "Goal missed"));
  if (shownStatuses.has("active")) legend.push(legendMarker({ fill: "var(--bs-body-bg)", stroke: LINE }, "Next goal"));
  $("goal-legend").replaceChildren(...legend);
  $("goal-note").hidden = !c;
  if (c) {
    $("goal-note").textContent = `A new card takes about ${plural(p.lag, "day")} to be known (shaded before the goal's date), and ${Math.round(p.success * 100)}% of them get there: `
      + (p.measured ? "measured on your Anki cards." : "usual values, until you've reviewed enough cards in Anki.")
      + " Known words are counted from your words and your Anki reviews.";
  }
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
  $("deleted-save").addEventListener("click", saveDeletedWords);
  $("deleted-all").addEventListener("change", (e) => {
    for (const box of $("deleted-list").querySelectorAll("input")) box.checked = e.target.checked;
  });
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
  if (document.visibilityState === "visible" && !$("hub").hidden) { loadReviews(); loadInbox(); loadGoal(); }
});
