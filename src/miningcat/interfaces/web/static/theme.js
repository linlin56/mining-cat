// The user's colour preferences (Settings › User preferences, kept by the server in user/user-config.json): the
// server writes them on <html> (base.html), and this script, loaded in <head>, applies them before the page is drawn,
// so that it never flashes in the wrong colours:
// - the colour mode (Bootstrap's data-bs-theme): light, dark, or the system's. A page can choose its own (the
//   reader's light, sepia or dark);
// - the highlight colours of the text (data-mc-highlights, see theme.css): default, or a palette for colour blindness;
// - the colour of the heatmap of reviews (data-mc-heatmap): orange by default.
// Buttons and radios set them with data-mc-theme-toggle, data-mc-theme-choice, data-mc-highlights-choice and
// data-mc-heatmap-choice.
"use strict";

window.MiningCatTheme = (() => {
  const root = document.documentElement;
  const dark = matchMedia("(prefers-color-scheme: dark)");
  // the other tabs of MiningCat follow the choices made in this one
  const tabs = window.BroadcastChannel ? new BroadcastChannel("miningcat-preferences") : null;
  const prefs = { theme: root.dataset.mcTheme || "system", highlights: root.dataset.mcHighlights || "default",
    heatmap: root.dataset.mcHeatmap || "orange" };
  let chosen = "auto";   // the page's own theme

  // The day / night of the whole site: the user's choice, else the system's.
  const site = () => (prefs.theme === "system" ? (dark.matches ? "dark" : "light") : prefs.theme);

  // A choice of the settings: a radio is checked, a button pressed.
  function mark(control, on) {
    if (control.matches("input")) { control.checked = on; return; }
    control.classList.toggle("active", on);
    control.setAttribute("aria-pressed", String(on));
  }

  function apply() {
    const theme = chosen === "auto" ? site() : chosen;
    root.dataset.bsTheme = theme;
    root.dataset.mcTheme = prefs.theme;
    root.dataset.mcHighlights = prefs.highlights;
    root.dataset.mcHeatmap = prefs.heatmap;
    for (const button of document.querySelectorAll("[data-mc-theme-toggle]")) {
      const night = theme === "dark";
      button.querySelector("i").className = `bi bi-${night ? "sun" : "moon-stars"}`;
      button.title = night ? "Day mode" : "Night mode";
      button.setAttribute("aria-label", button.title);
    }
    for (const control of document.querySelectorAll("[data-mc-theme-choice]")) mark(control, control.dataset.mcThemeChoice === prefs.theme);
    for (const control of document.querySelectorAll("[data-mc-highlights-choice]")) mark(control, control.dataset.mcHighlightsChoice === prefs.highlights);
    for (const control of document.querySelectorAll("[data-mc-heatmap-choice]")) mark(control, control.dataset.mcHeatmapChoice === prefs.heatmap);
  }

  // changes: {theme?, highlights?, heatmap?}, applied at once and saved by the server
  function save(changes) {
    Object.assign(prefs, changes);
    if ("theme" in changes) chosen = "auto";
    apply();
    fetch("/api/preferences", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-MiningCat": "1" },
      body: JSON.stringify(changes),
    }).then((res) => (res.ok ? res.json() : null)).then((saved) => {
      if (!saved) return;
      Object.assign(prefs, saved);
      apply();
      if (tabs) tabs.postMessage(saved);
    }).catch(() => { /* applied to this page only: MiningCat isn't answering */ });
  }

  // The preferences again from the server: a page shown from the browser's history may be older than them.
  function reload() {
    fetch("/api/preferences").then((res) => (res.ok ? res.json() : null)).then((saved) => {
      if (saved) { Object.assign(prefs, saved); apply(); }
    }).catch(() => {});
  }

  dark.addEventListener("change", apply);
  if (tabs) tabs.addEventListener("message", (e) => { Object.assign(prefs, e.data); apply(); });
  window.addEventListener("pageshow", (e) => { if (e.persisted) reload(); });
  document.addEventListener("DOMContentLoaded", apply);
  document.addEventListener("click", (e) => {
    if (e.target.closest("[data-mc-theme-toggle]")) save({ theme: site() === "dark" ? "light" : "dark" });
    const theme = e.target.closest("[data-mc-theme-choice]");
    if (theme) save({ theme: theme.dataset.mcThemeChoice });
    const highlights = e.target.closest("[data-mc-highlights-choice]");
    if (highlights) save({ highlights: highlights.dataset.mcHighlightsChoice });
    const heatmap = e.target.closest("[data-mc-heatmap-choice]");
    if (heatmap) save({ heatmap: heatmap.dataset.mcHeatmapChoice });
  });
  apply();

  // theme: "light", "dark", "sepia", or "auto" (the site's)
  return { set(theme) { chosen = theme || "auto"; apply(); } };
})();
