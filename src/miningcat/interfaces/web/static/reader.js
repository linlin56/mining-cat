// MiningCat Reader - library + paginated reader (horizontal or vertical text).
//
// Pagination uses CSS multi-column layout, like ttu / epub.js: the chapter is laid out in columns
// exactly one page wide (horizontal) or one page tall (vertical-rl, where columns stack downwards),
// and turning a page translates the content by one column.
//
// The reading position is a character offset inside the chapter (text nodes, ruby annotations
// excluded), so it survives font, size, margin or writing-mode changes and window resizes.
"use strict";

const $ = (id) => document.getElementById(id);

// The language studied (see application/study_language.py): {id, name, tag, tags: [{tag, label}]}.
const STUDY = JSON.parse(document.body.dataset.study || "null");
const GAP = 48;          // px between columns (never visible: it falls outside the viewport)
const SAVE_DELAY = 700;  // ms

const R = {
  settings: null,
  book: null, prefs: {}, progress: {},
  chapter: 0, page: 0, pages: 1,
  offset: 0,                // character offset of the first character of the current page
  chapterCache: new Map(),
  index: null,              // text index of the rendered chapter
  vertical: false,
  step: 0,                  // px per page
  charsBefore: [],          // cumulative chapter sizes
  saveTimer: null,
  token: 0,
  audio: null,              // {tracks, names} when the book has the audio of a MiningCat conversion
  folder: null,             // the folder of the library shown (null: the library itself)
  folders: {},              // the folders of the library, {id: {name}}
  imageExtensions: [],      // the pictures imported as comics of one page
  places: {},               // the folder of each book and comic sorted, {"book:<id>": folder id}
  items: {},                // the books and comics of the library, {"book:<id>": book}
  dragging: null,           // what is dragged in the library: {key, image}
};

// ---------------------------------------------------------------- API

async function api(path, body) {
  const init = body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-MiningCat": "1" },
    body: JSON.stringify(body),
  };
  const res = await fetch(path, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(data.error || `Request failed (${res.status})`), { title: data.title || "Error" });
  return data;
}

// Resolves to whether the button of value true was clicked (ui.js).
function showDialog(title, message, buttons) {
  return MiningCatUI.dialog(title, message, buttons).then((value) => value === "true");
}
const showError = (err) => showDialog(err.title || "Error", err.message || String(err));

// ---------------------------------------------------------------- settings & theme

// The reader's own theme while a book is read; the library follows the site's day / night (theme.js).
function applyTheme() {
  MiningCatTheme.set(R.book ? R.settings.theme : "auto");
}

let settingsTimer = null;
function saveSettings() {
  clearTimeout(settingsTimer);
  settingsTimer = setTimeout(() => api("/reader/api/settings", R.settings).catch(() => {}), 400);
}

// ---------------------------------------------------------------- library

function placeholderColor(text) {
  let h = 0;
  for (const ch of text) h = (h * 31 + ch.codePointAt(0)) % 360;
  return `hsl(${h} 45% 42%)`;
}

async function showLibrary() {
  R.book = null;
  applyTheme();
  if (window.MiningCatMining) MiningCatMining.clearColours();
  $("reading").hidden = true;
  $("library").hidden = false;
  const [{ books, extensions }, comics, folders] = await Promise.all(
    [api("/reader/api/books"), api("/reader/api/comics"), api("/reader/api/folders")]);
  R.folders = folders.folders;
  R.places = folders.items;
  R.folder = new URLSearchParams(location.search).get("folder");
  if (R.folder && !R.folders[R.folder]) {
    R.folder = null;
    history.replaceState({}, "", "/reader/");
  }
  // pictures are imported as comics of one page
  R.comicExtensions = [...comics.extensions, ...comics.images];
  R.imageExtensions = comics.images;
  const upper = (list) => list.map((e) => e.toUpperCase()).join(", ");
  $("lib-formats").textContent = `Supported formats: ${upper(extensions)}; `
    + `comics and manga: ${upper(comics.extensions)}; images: ${upper(comics.images)} (their text is read by OCR). `
    + "Books are stored in the project's library/ folder.";
  $("book-input").accept = [...extensions, ...R.comicExtensions].map((e) => `.${e}`).join(",");
  // books and comics together, the last opened first; the folders first, by name
  const items = [...books.map((b) => ({ ...b, kind: "book" })), ...comics.comics.map((c) => ({ ...c, kind: "comic" }))]
    .sort((a, b) => (b.opened || 0) - (a.opened || 0) || (b.added || 0) - (a.added || 0));
  R.items = Object.fromEntries(items.map((item) => [itemKey(item), item]));
  const here = items.filter((item) => (R.places[itemKey(item)] || null) === R.folder);
  // what each folder holds: its books and comics, and its folders
  const counts = {};
  for (const item of items) { const f = R.places[itemKey(item)]; if (f) counts[f] = (counts[f] || 0) + 1; }
  for (const f of Object.values(R.folders)) if (f.parent) counts[f.parent] = (counts[f.parent] || 0) + 1;
  const folderCards = subfolders(R.folder).map(([id, f]) => folderCard(id, f, counts[id] || 0));
  $("book-grid").replaceChildren(...folderCards, ...here.map((item) => (item.kind === "comic" ? comicCard(item) : bookCard(item))));
  document.title = R.folder ? `${R.folders[R.folder].name} · MiningCat Reader` : "MiningCat Reader";
  $("folder-bar").hidden = !R.folder;
  if (R.folder) renderPath();
  $("lib-empty").hidden = Boolean(R.folder) || items.length > 0 || folderCards.length > 0;
  $("folder-empty").hidden = !R.folder || here.length > 0 || folderCards.length > 0;
  loadComprehension(here.filter((item) => item.kind === "book"));
}

// ---------------------------------------------------------------- folders

// "book:<id>", "comic:<id>" or "folder:<id>"
const itemKey = (item) => `${item.kind}:${item.id}`;
const DRAG_TYPE = "application/x-miningcat-item";

function libraryUrl(folder) {
  return folder ? `/reader/?folder=${folder}` : "/reader/";
}

function goToLibrary(folder) {
  history.pushState({}, "", libraryUrl(folder));
  route();
}

// The folders of a folder (null: of the library), by name.
function subfolders(parent) {
  return Object.entries(R.folders)
    .filter(([, f]) => (f.parent || null) === parent)
    .sort(([, a], [, b]) => a.name.localeCompare(b.name, undefined, { numeric: true }));
}

// All the folders, each followed by its own: [{id, name, depth}].
function folderTree(parent = null, depth = 0) {
  return subfolders(parent).flatMap(([id, f]) => [{ id, name: f.name, depth }, ...folderTree(id, depth + 1)]);
}

// Whether the folder `folder` is `ancestor` or one of its folders, at any depth (null: the library, in none).
function isInside(folder, ancestor) {
  for (let id = folder, steps = 0; id && steps < 1000; id = R.folders[id]?.parent, steps++) {
    if (id === ancestor) return true;
  }
  return false;
}

// Where a book, a comic or a folder is (null: in the library).
function placeOf(key) {
  return key.startsWith("folder:") ? R.folders[key.slice(7)]?.parent || null : R.places[key] || null;
}

// Library › Folder › Folder: the folders above can be opened, and take the books dropped on them.
function renderPath() {
  const path = [];
  for (let id = R.folder; id && !path.includes(id); id = R.folders[id]?.parent) path.unshift(id);
  const crumb = (id, name, current) => {
    const li = node("li", `breadcrumb-item text-truncate${current ? " active fw-semibold text-body" : ""}`);
    if (current) {
      li.setAttribute("aria-current", "page");
      li.innerHTML = '<i class="bi bi-folder2-open text-primary-emphasis me-1" aria-hidden="true"></i>';
      li.append(name);
      return li;
    }
    const a = node("a", "mc-folder-target rounded px-1", name);
    a.href = libraryUrl(id);
    a.dataset.folder = id || "";
    a.title = "Drop a book here to move it there";
    a.addEventListener("click", (e) => { e.preventDefault(); goToLibrary(id); });
    li.append(a);
    return li;
  };
  $("folder-path").replaceChildren(crumb(null, "Library", false), ...path.map((id, i) => crumb(id, R.folders[id].name, i === path.length - 1)));
}

// Puts books, comics and folders ("book:<id>"…) in a folder, or back in the library (folder null).
async function moveItems(keys, folder) {
  const items = keys.map((key) => { const [kind, id] = key.split(":"); return { kind, id }; });
  try { await api("/reader/api/folders/move", { items, folder }); } catch (err) { showError(err); }
  showLibrary();
}

// Where a book or a folder goes, without dragging it (touch screens, keyboard): the library or a folder, as a tree.
function chooseFolder(key, title) {
  const modal = $("move-modal");
  const moving = key.startsWith("folder:") ? key.slice(7) : null;
  const current = placeOf(key);
  const entry = (id, name, depth, icon) => {
    const button = node("button", "list-group-item list-group-item-action d-flex align-items-center gap-2");
    button.type = "button";
    button.style.paddingLeft = `${1 + depth * 1.25}rem`;
    button.innerHTML = `<i class="bi ${icon} text-primary-emphasis" aria-hidden="true"></i>`;
    button.append(node("span", "text-truncate flex-grow-1", name));
    if (id === current) button.append(node("span", "small text-body-secondary", "here"));
    // a folder never goes into itself, nor into one of its folders
    button.disabled = id === current || Boolean(moving && isInside(id, moving));
    button.addEventListener("click", () => { MiningCatUI.hideModal(modal); moveItems([key], id); });
    return button;
  };
  $("move-what").textContent = `Where should “${title}” go?`;
  $("move-list").replaceChildren(entry(null, "Library", 0, "bi-book"),
    ...folderTree().map((f) => entry(f.id, f.name, f.depth + 1, "bi-folder2")));
  MiningCatUI.showModal(modal);
}

// Whether what is dragged can be dropped on `target`: a book into another folder, a folder into another folder (never
// into itself or its own folders), a picture onto another picture or an album.
function accepts(target, drag) {
  if (!target || !drag) return false;
  if (target.dataset.folder !== undefined) {
    const folder = target.dataset.folder || null;
    if (folder === placeOf(drag.key)) return false;
    return !drag.key.startsWith("folder:") || !isInside(folder, drag.key.slice(7));
  }
  return drag.image && target.dataset.merge !== drag.key;
}

// A picture dropped onto a picture (or an album) becomes its next page.
async function addToAlbum(imageKey, albumKey) {
  const image = R.items[imageKey], album = R.items[albumKey];
  const ok = await showDialog("Make an album",
    `Add “${image.title}” to “${album.title}”, as its page ${album.pages + 1}? It leaves the library: it's a page of “${album.title}” now.`,
    [{ label: "Cancel", value: false }, { label: "Add", value: true, primary: true }]);
  if (!ok) return;
  try { await api(`/reader/api/comics/${album.id}/append`, { image: image.id }); } catch (err) { showError(err); }
  showLibrary();
}

// The name of a new folder, or of a folder renamed: resolves to it, or null when cancelled.
function askFolderName(title, value, action) {
  return new Promise((resolve) => {
    const modal = $("folder-modal");
    let name = null;
    $("folder-modal-title").textContent = title;
    $("folder-save").textContent = action;
    $("folder-input").value = value;
    $("folder-form").onsubmit = (e) => {
      e.preventDefault();
      name = $("folder-input").value.trim();
      if (name) MiningCatUI.hideModal(modal);
    };
    modal.addEventListener("shown.bs.modal", () => $("folder-input").select(), { once: true });
    modal.addEventListener("hidden.bs.modal", () => resolve(name), { once: true });
    MiningCatUI.showModal(modal);
  });
}

// A new folder, in the folder shown.
async function newFolder() {
  const name = await askFolderName("New folder", "", "Create");
  if (!name) return;
  try { await api("/reader/api/folders", { name, parent: R.folder }); } catch (err) { showError(err); }
  showLibrary();
}

async function renameFolder() {
  const id = R.folder;
  const name = await askFolderName("Rename folder", R.folders[id].name, "Rename");
  if (!name) return;
  try { await api(`/reader/api/folders/${id}`, { name }); } catch (err) { showError(err); }
  showLibrary();
}

async function deleteFolder() {
  const id = R.folder;
  const parent = R.folders[id].parent || null;
  const where = parent ? `goes up into “${R.folders[parent].name}”` : "goes back to the library";
  const ok = await showDialog("Delete folder", `Delete the folder “${R.folders[id].name}”? What it holds (books and folders) ${where}.`,
    [{ label: "Cancel", value: false }, { label: "Delete", value: true, primary: true }]);
  if (!ok) return;
  try { await api(`/reader/api/folders/${id}/delete`, {}); } catch (err) { showError(err); }
  goToLibrary(parent);
}

// Makes a card of the library draggable: into a folder, or (a picture) onto another picture.
function draggable(a, key, image = false) {
  a.draggable = true;
  a.addEventListener("dragstart", (e) => {
    e.dataTransfer.setData(DRAG_TYPE, key);
    e.dataTransfer.effectAllowed = "move";
    R.dragging = { key, image };
    a.classList.add("mc-dragging");
  });
  a.addEventListener("dragend", () => { a.classList.remove("mc-dragging"); R.dragging = null; });
}

// The round button on a cover that moves it, without dragging it.
function moveButton(key, title) {
  const move = node("button", "btn btn-sm btn-dark rounded-circle position-absolute top-0 start-0 m-1 mc-delete");
  move.type = "button";
  move.innerHTML = '<i class="bi bi-folder-symlink" aria-hidden="true"></i>';
  move.title = "Move to a folder";
  move.setAttribute("aria-label", `Move ${title} to a folder`);
  move.addEventListener("click", (e) => { e.preventDefault(); chooseFolder(key, title); });
  return move;
}

// A folder: opened on click, books and folders dropped on it go in; dragged itself into another folder.
function folderCard(id, folder, count) {
  const a = node("a", "mc-cover mc-folder-target d-block position-relative rounded text-reset text-decoration-none");
  a.href = libraryUrl(id);
  a.dataset.folder = id;
  draggable(a, `folder:${id}`);
  const box = node("div", "ratio rounded overflow-hidden shadow-sm bg-body-tertiary mb-2");
  box.style.setProperty("--bs-aspect-ratio", "150%");
  const icon = node("div", "d-flex align-items-center justify-content-center text-primary-emphasis mc-folder-cover");
  icon.innerHTML = '<i class="bi bi-folder2" aria-hidden="true"></i>';
  box.append(icon);
  const name = node("div", "fw-semibold small text-truncate", folder.name);
  name.title = folder.name;
  a.append(box, name, node("div", "small text-body-secondary", count === 1 ? "1 item" : `${count} items`), moveButton(`folder:${id}`, folder.name));
  a.addEventListener("click", (e) => {
    if (e.target.closest(".mc-delete")) return;
    e.preventDefault();
    goToLibrary(id);
  });
  const col = node("div", "col");
  col.append(a);
  return col;
}

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

// A book or a comic in the library (a column of the grid): its cover, title, reading progress and remove button.
// cover: the image's URL, else the title is written on a colour. book: the book's id, for its comprehension.
// item: {kind, id, title}, dragged into the folders.
function libraryCard({ href, cover, title, language, about, percent, book, remove, item }) {
  const a = node("a", "mc-cover d-block position-relative text-reset text-decoration-none");
  a.href = href;
  draggable(a, itemKey(item), Boolean(item.image));
  // a picture dropped on a picture or an album becomes its next page
  if (item.image || item.album) {
    a.classList.add("mc-merge-target");
    a.dataset.merge = itemKey(item);
  }
  const box = node("div", "ratio rounded overflow-hidden shadow-sm bg-body-tertiary mb-2");
  box.style.setProperty("--bs-aspect-ratio", "150%");
  if (cover) {
    const img = node("img", "object-fit-cover");
    img.src = cover;
    img.alt = "";
    img.draggable = false;  // the whole card is dragged, not its picture
    img.loading = "lazy";
    box.append(img);
  } else {
    const ph = node("div", "d-flex align-items-center justify-content-center p-3 text-center text-white fw-bold text-break", title);
    ph.lang = language;
    ph.style.background = placeholderColor(title);
    box.append(ph);
  }
  const name = node("div", "fw-semibold small text-truncate", title);
  name.lang = language;
  name.title = title;
  const meta = node("div", "d-flex justify-content-between gap-2 small text-body-secondary");
  meta.append(node("span", "text-truncate", about), node("span", "", percent ? `${Math.floor(percent)}%` : "New"));
  const bar = node("div", "progress my-1");
  bar.style.height = "3px";
  bar.setAttribute("aria-hidden", "true");
  const fill = node("div", "progress-bar");
  fill.style.width = `${percent || 0}%`;
  bar.append(fill);
  const del = node("button", "btn btn-sm btn-dark rounded-circle position-absolute top-0 end-0 m-1 mc-delete");
  del.type = "button";
  del.innerHTML = '<i class="bi bi-x-lg" aria-hidden="true"></i>';
  del.title = "Remove from library";
  del.setAttribute("aria-label", `Remove ${title} from the library`);
  del.addEventListener("click", (e) => { e.preventDefault(); remove(); });
  a.append(box, name, meta, bar, del);
  if (R.folder || Object.keys(R.folders).length) a.append(moveButton(itemKey(item), title));
  if (book) {
    const comp = node("div", "small text-body-secondary");
    comp.dataset.book = book;
    a.append(comp);
  }
  const col = node("div", "col");
  col.append(a);
  return col;
}

function bookCard(b) {
  const col = libraryCard({
    href: `/reader/${b.id}`, cover: b.cover, title: b.title, language: b.language, percent: b.percent, book: b.id, item: b,
    about: [b.author, b.format.toUpperCase()].filter(Boolean).join(" · "),
    remove: async () => {
      const ok = await showDialog("Remove book", `Remove “${b.title}” and its reading progress from the library?`,
        [{ label: "Cancel", value: false }, { label: "Remove", value: true, primary: true }]);
      if (!ok) return;
      try { await api(`/reader/api/books/${b.id}/delete`, {}); showLibrary(); } catch (err) { showError(err); }
    },
  });
  const a = col.firstChild;
  a.addEventListener("click", (e) => {
    if (e.target.closest(".mc-delete")) return;
    e.preventDefault();
    history.pushState({}, "", a.href);
    route();
  });
  return col;
}

// A comic or manga (or an image, a comic of one page): opened in its own page (static/comic.js).
function comicCard(c) {
  return libraryCard({
    href: `/reader/comic/${c.id}`, cover: `/reader/api/comics/${c.id}/thumb?v=${c.added}`, title: c.title,
    language: c.language, percent: c.percent, about: c.image ? "Image" : `${c.pages} pages · ${c.album ? "Album" : "Comic"}`, item: c,
    remove: async () => {
      const ok = await showDialog(c.image ? "Remove image" : "Remove comic", c.image
        ? `Remove “${c.title}” and the text read on it from the library?`
        : `Remove “${c.title}”, the text read on its pages and its reading progress from the library?`,
        [{ label: "Cancel", value: false }, { label: "Remove", value: true, primary: true }]);
      if (!ok) return;
      try { await api(`/reader/api/comics/${c.id}/delete`, {}); showLibrary(); } catch (err) { showError(err); }
    },
  });
}

// Each book's comprehension, one book after the other (a book never analysed takes a moment).
let comprehensionToken = 0;
async function loadComprehension(books) {
  const token = ++comprehensionToken;
  for (const b of books) {
    if (token !== comprehensionToken) return;
    const box = document.querySelector(`[data-book="${b.id}"]`);
    if (!box) continue;
    box.textContent = "…";
    try {
      const { comprehension: c } = await api(`/reader/api/books/${b.id}/comprehension`);
      box.textContent = c && c.total ? `${percentText(c.percent)}${c.recommended ? ` · ${c.recommended} i+1` : ""}` : "";
      if (c && c.total) box.title = `${c.known} known, ${c.learning} learning and ${c.new} new running words (${c.unique_new} different new words). `
        + `${c.i1} of ${c.sentences} sentences have only one new word`
        + (c.frequency ? `, ${c.recommended} of them a frequent one (up to #${c.frequency.limit.toLocaleString()}).` : ".");
    } catch { box.textContent = ""; }
  }
}

// Comics (and images) are sent one by one, as the request's body: an archive can be hundreds of MB.
async function addComic(file, status) {
  status.textContent = `Importing ${file.name}…`;
  const res = await fetch(`/reader/api/comics?name=${encodeURIComponent(file.name)}`, {
    method: "POST", headers: { "X-MiningCat": "1", "Content-Type": "application/octet-stream" }, body: file,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(`${file.name}: ${data.error || `import failed (${res.status})`}`);
  return data.comic;
}

// The files imported go into `folder` (null: the library).
async function addBooks(fileList, folder = R.folder) {
  if (!fileList.length) return;
  const status = $("lib-status");
  const isComic = (f) => (R.comicExtensions || []).includes(f.name.split(".").pop().toLowerCase());
  const added = [], known = [];
  const comicErrors = [];
  for (const file of fileList.filter(isComic)) {
    try {
      const comic = await addComic(file, status);
      if (comic.new) added.push(`comic:${comic.id}`); else known.push(comic.title);
    } catch (err) { comicErrors.push(err.message); }
  }
  if (comicErrors.length) showDialog("Some files could not be imported", comicErrors.join("\n"));
  fileList = fileList.filter((f) => !isComic(f));
  if (fileList.length) {
    const form = new FormData();
    for (const f of fileList) form.append("files", f, f.name);
    status.textContent = `Importing ${fileList.length} file${fileList.length > 1 ? "s" : ""}…`;
    try {
      const res = await fetch("/reader/api/books", { method: "POST", headers: { "X-MiningCat": "1" }, body: form });
      const data = await res.json();
      for (const b of data.added || []) { if (b.new) added.push(`book:${b.id}`); else known.push(b.title); }
      if (data.errors && data.errors.length) showDialog("Some files could not be imported", data.errors.join("\n"));
      if (data.elsewhere && data.elsewhere.length) {
        showDialog("Books of another language", `These books were imported into the library of another language: choose it on the home page to read them.\n\n${data.elsewhere.join("\n")}`);
      }
    } catch (err) {
      showError(err);
    }
  }
  status.textContent = "";
  // a book imported again stays where it is (in its folder)
  if (folder && known.length) MiningCatUI.toast(`Already in your library: ${known.join(", ")}`);
  if (folder && added.length) await moveItems(added, folder);
  else showLibrary();
}

// A picture pasted (a screenshot, an image copied in the browser) gets a name of its own: browsers call them all
// "image.png".
function pastedFile(file, index) {
  if (!file.type.startsWith("image/") || !/^(image\.\w+)?$/i.test(file.name)) return file;
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const stamp = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}.${pad(d.getMinutes())}.${pad(d.getSeconds())}`;
  const ext = file.type === "image/jpeg" ? "jpg" : file.type.slice(6).replace(/\+.*/, "");
  return new File([file], `Pasted image ${stamp}${index ? ` (${index + 1})` : ""}.${ext}`, { type: file.type });
}

// ---------------------------------------------------------------- opening a book

async function openBook(bookId) {
  $("library").hidden = true;
  $("reading").hidden = false;
  $("loading").hidden = false;
  const token = ++R.token;
  const [data, folders] = await Promise.all([api(`/reader/api/books/${bookId}`), api("/reader/api/folders").catch(() => null)]);
  if (token !== R.token) return;
  if (folders) R.places = folders.items;
  R.book = data.book;
  applyTheme();
  R.audio = null;
  renderAudio();
  api(`/reader/api/books/${bookId}/audio`).then((d) => { if (R.book && R.book.id === bookId) { R.audio = d.audio; renderAudio(); } }).catch(() => {});
  R.prefs = data.prefs || {};
  R.progress = data.progress || {};
  R.chapterCache = new Map();
  R.chapter = -1;
  R.index = null;
  $("content").replaceChildren();
  R.charsBefore = [];
  let sum = 0;
  for (const ch of R.book.chapters) { R.charsBefore.push(sum); sum += ch.chars; }
  document.title = `${R.book.title} · MiningCat Reader`;
  $("book-title").textContent = R.book.title;
  $("book-title").lang = R.book.language;
  buildToc();
  syncSettingsForm();
  const chapter = Math.min(R.progress.chapter || 0, R.book.chapters.length - 1);
  await goTo(chapter, { offset: R.progress.offset || 0 });
}

function effectiveWriting() {
  const w = R.prefs.writing && R.prefs.writing !== "auto" ? R.prefs.writing : R.book.writing;
  return w === "vertical" ? "vertical" : "horizontal";
}
function effectiveLanguage() {
  const own = R.prefs.language || R.book.language;
  return own && own !== "und" ? own : STUDY.tag;
}

// ---------------------------------------------------------------- chapter rendering

async function chapterHtml(i) {
  if (!R.chapterCache.has(i)) {
    R.chapterCache.set(i, api(`/reader/api/books/${R.book.id}/chapters/${i}`).then((d) => d.html));
  }
  return R.chapterCache.get(i);
}

// CJK books: paragraphs get a first-line indent unless they already start with a space or an
// opening bracket, and short numbers are set upright in vertical text (縦中横, e.g. 第12章).
function decorate(content) {
  const lang = effectiveLanguage();
  if (!/^(ja|zh|yue|ko)/.test(lang)) return;
  for (const p of content.querySelectorAll("p")) {
    const first = (p.textContent || "").replace(/^[\n\r\t ]+/, "")[0] || "";
    if (first && !/[\s「『（(【〈《“‘—―…]/.test(first)) p.classList.add("indent");
  }
  if (content.querySelector(".tcy")) return;
  const NUMBER = /(^|[^0-9A-Za-z.,])([0-9]{1,2})(?![0-9A-Za-z.,])/g;
  const walker = document.createTreeWalker(content, NodeFilter.SHOW_TEXT);
  const targets = [];
  while (walker.nextNode()) {
    const node = walker.currentNode;
    NUMBER.lastIndex = 0;
    if (NUMBER.test(node.data) && !node.parentElement.closest("rt, rp")) targets.push(node);
  }
  for (const node of targets) {
    const frag = document.createDocumentFragment();
    let last = 0;
    for (const m of node.data.matchAll(NUMBER)) {
      const start = m.index + m[1].length;
      frag.append(node.data.slice(last, start));
      const span = document.createElement("span");
      span.className = "tcy";
      span.textContent = m[2];
      frag.append(span);
      last = start + m[2].length;
    }
    frag.append(node.data.slice(last));
    node.replaceWith(frag);
  }
}

async function waitForMedia(content) {
  const imgs = [...content.querySelectorAll("img")];
  for (const img of imgs) img.loading = "eager";
  const timeout = new Promise((r) => setTimeout(r, 2500));
  await Promise.race([
    Promise.all(imgs.map((img) => (img.complete ? null : img.decode().catch(() => null)))),
    timeout,
  ]);
  if (document.fonts && document.fonts.ready) await Promise.race([document.fonts.ready, timeout]);
}

async function renderChapter(i) {
  const content = $("content");
  const html = await chapterHtml(i);
  content.innerHTML = html;
  content.lang = effectiveLanguage();
  decorate(content);
  R.index = null;
  layout();
  colourWords();
  await waitForMedia(content);
  layout();
  // prefetch the neighbours
  if (i + 1 < R.book.chapters.length) chapterHtml(i + 1).catch(() => {});
  if (i > 0) chapterHtml(i - 1).catch(() => {});
}

// Colours the chapter's words by status (new, learning), unless turned off in the settings. Their statuses are
// read anyway: they give the chapter's comprehension and its recommended sentences.
function colourWords() {
  if (!window.MiningCatMining) return;
  if (!R.book) MiningCatMining.clearColours();
  else MiningCatMining.colourWords($("content"), effectiveLanguage(), "main", { paint: R.settings.colors !== "off" });
}

// ---------------------------------------------------------------- comprehension & recommended sentences

const percentText = (p) => (p === null || p === undefined ? "" : `${p >= 99.95 ? 100 : p.toFixed(1)}% known`);

// Recomputed whenever the chapter's words or their statuses change (a card made, a word marked known...).
function showComprehension(key) {
  if (key !== "main") return;
  const a = MiningCatMining.analyse("main");
  const recommended = a ? a.units.filter((u) => u.recommended) : [];
  R.recommended = recommended;
  $("comp-info").textContent = a && a.total ? `${percentText(a.percent)}${recommended.length ? ` · ${recommended.length} i+1` : ""}` : "";
  paintRecommended();
  const rarer = a ? a.units.filter((u) => u.i1 && !u.recommended).length : 0;
  $("i1-summary").textContent = !a || !a.total
    ? "No dictionary words in this chapter (import a dictionary in Settings)."
    : `${percentText(a.percent)} · ${a.learning} learning · ${a.new} new words in this chapter · ${recommended.length} recommended sentence${recommended.length === 1 ? "" : "s"}.`
      + (a.frequency ? ` Only words up to #${a.frequency.limit.toLocaleString()} of “${a.frequency.title}” (you know ${a.frequency.known.toLocaleString()} of its words)`
        + `${rarer ? `: ${rarer} other sentence${rarer === 1 ? " teaches a rarer word" : "s teach rarer words"}` : ""}.`
        : " Import a frequency list in Settings to only get the frequent words.");
  $("i1-list").replaceChildren(...recommended.map((u) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "list-group-item list-group-item-action px-2";
    button.lang = effectiveLanguage();
    const before = document.createRange();
    before.setStart(u.range.startContainer, u.range.startOffset);
    before.setEnd(u.targetRange.startContainer, u.targetRange.startOffset);
    const after = document.createRange();
    after.setStart(u.targetRange.endContainer, u.targetRange.endOffset);
    after.setEnd(u.range.endContainer, u.range.endOffset);
    const word = document.createElement("strong");
    word.className = "text-primary-emphasis";
    word.textContent = u.targetRange.toString();
    button.append(before.toString().trimStart(), word, after.toString().trimEnd());
    button.addEventListener("click", () => {
      togglePanel("i1-panel", false);
      showPage(pageOfRect(u.range.getBoundingClientRect()));
      flashRange(u.range);
    });
    return button;
  }));
}

function paintRecommended() {
  if (!window.CSS || !CSS.highlights || !window.Highlight) return;
  const ranges = R.settings.i1 !== false && R.recommended ? R.recommended.map((u) => u.range) : [];
  CSS.highlights.set("mc-i1", new Highlight(...ranges));
}

function flashRange(range) {
  if (!window.CSS || !CSS.highlights || !window.Highlight) return;
  CSS.highlights.set("mc-i1-focus", new Highlight(range));
  clearTimeout(R.flashTimer);
  R.flashTimer = setTimeout(() => CSS.highlights.delete("mc-i1-focus"), 1800);
}

// Sizes the column layout to the viewport and counts the pages of the current chapter.
function layout() {
  const s = R.settings;
  const root = document.documentElement.style;
  root.setProperty("--font-size", `${s.font_size}px`);
  root.setProperty("--line-height", String(s.line_height));
  root.setProperty("--margin", `${s.margin}px`);
  root.setProperty("--gap", `${GAP}px`);

  const viewport = $("viewport");
  const w = Math.floor(viewport.clientWidth);
  const h = Math.floor(viewport.clientHeight);
  root.setProperty("--page-w", `${w}px`);
  root.setProperty("--page-h", `${h}px`);

  const content = $("content");
  R.vertical = effectiveWriting() === "vertical";
  content.className = `content ${R.vertical ? "vertical" : "horizontal"} ${s.font}${s.furigana ? "" : " no-rt"}`;
  content.style.transform = "none";
  R.step = R.vertical ? h + GAP : w + GAP;
  const extent = R.vertical ? content.scrollHeight : content.scrollWidth;
  R.pages = Math.max(1, Math.round((extent + GAP) / R.step));
  R.index = null;
}

// `anchor`: the character the reader is at, when it's known and on this page. Keeping it (instead of
// the first character of the page) means repeated layout changes don't drift backwards.
function showPage(page, anchor) {
  if (window.MiningCatMining) MiningCatMining.hide();
  R.page = Math.max(0, Math.min(page, R.pages - 1));
  const shift = R.page * R.step;
  $("content").style.transform = R.vertical ? `translateY(${-shift}px)` : `translateX(${-shift}px)`;
  R.offset = typeof anchor === "number" && pageOfOffset(anchor) === R.page ? anchor : offsetForPage(R.page);
  updateStatus();
  scheduleSave();
}

// ---------------------------------------------------------------- reading position

// Text nodes of the chapter in reading order, with their cumulative character offsets.
function textIndex() {
  if (R.index) return R.index;
  const content = $("content");
  const nodes = [], starts = [];
  let total = 0;
  const walker = document.createTreeWalker(content, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (!node.data.trim()) return NodeFilter.FILTER_REJECT;
      if (node.parentElement && node.parentElement.closest("rt, rp")) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  while (walker.nextNode()) {
    nodes.push(walker.currentNode);
    starts.push(total);
    total += walker.currentNode.data.length;
  }
  R.index = { nodes, starts, total };
  return R.index;
}

function locate(offset) {
  const { nodes, starts } = textIndex();
  let lo = 0, hi = nodes.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (starts[mid] <= offset) lo = mid; else hi = mid - 1;
  }
  return { node: nodes[lo], at: offset - starts[lo] };
}

const range = document.createRange();

// Page on which the character at `offset` is laid out.
function pageOfOffset(offset) {
  const { nodes, total } = textIndex();
  if (!nodes.length) return 0;
  const { node, at } = locate(Math.max(0, Math.min(offset, total - 1)));
  range.setStart(node, Math.min(at, node.data.length - 1));
  range.setEnd(node, Math.min(at + 1, node.data.length));
  let rect = range.getClientRects()[0] || range.getBoundingClientRect();
  if (!rect || (rect.width === 0 && rect.height === 0)) rect = node.parentElement.getBoundingClientRect();
  return pageOfRect(rect);
}

function pageOfRect(rect) {
  const origin = $("content").getBoundingClientRect();
  const pos = R.vertical ? (rect.top + rect.bottom) / 2 - origin.top : (rect.left + rect.right) / 2 - origin.left;
  return Math.max(0, Math.min(R.pages - 1, Math.floor(pos / R.step)));
}

// First character shown on `page` (binary search: pages grow with the offset).
function offsetForPage(page) {
  const { total } = textIndex();
  if (!total || page <= 0) return 0;
  let lo = 0, hi = total - 1;
  if (pageOfOffset(hi) < page) return hi;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (pageOfOffset(mid) >= page) hi = mid; else lo = mid + 1;
  }
  return lo;
}

function percent() {
  const total = R.book.total_chars || 1;
  return Math.min(100, ((R.charsBefore[R.chapter] || 0) + R.offset) / total * 100);
}

function updateStatus() {
  const ch = R.book.chapters[R.chapter];
  $("chapter-title").textContent = ch ? ch.title : "";
  $("chapter-title").lang = effectiveLanguage();
  $("page-info").textContent = `${R.page + 1} / ${R.pages}`;
  const pct = percent();
  $("percent-info").textContent = `${pct.toFixed(1)}%`;
  $("progress-fill").style.width = `${pct}%`;
  for (const a of document.querySelectorAll("#toc a")) {
    const current = Number(a.dataset.chapter) === R.chapter;
    a.classList.toggle("active", current);
    if (current) a.setAttribute("aria-current", "true"); else a.removeAttribute("aria-current");
  }
}

function progressBody() {
  return { chapter: R.chapter, offset: R.offset, percent: percent() };
}

function scheduleSave() {
  clearTimeout(R.saveTimer);
  const bookId = R.book.id;
  const body = progressBody();
  R.saveTimer = setTimeout(() => api(`/reader/api/books/${bookId}/progress`, body).catch(() => {}), SAVE_DELAY);
}

function saveNow() {
  if (!R.book) return;
  clearTimeout(R.saveTimer);
  fetch(`/reader/api/books/${R.book.id}/progress`, {
    method: "POST",
    keepalive: true,
    headers: { "Content-Type": "application/json", "X-MiningCat": "1" },
    body: JSON.stringify(progressBody()),
  }).catch(() => {});
}

// ---------------------------------------------------------------- navigation

// target: {page} | {offset} | {anchor} | {end: true}
async function goTo(chapter, target = {}) {
  const token = ++R.token;
  $("loading").hidden = false;
  try {
    if (chapter !== R.chapter || !$("content").childNodes.length || target.reload) {
      R.chapter = chapter;
      await renderChapter(chapter);
    }
    if (token !== R.token) return;
    let page = 0;
    if (target.end) page = R.pages - 1;
    else if (typeof target.page === "number") page = target.page;
    else if (typeof target.offset === "number") {
      page = pageOfOffset(target.offset);
      showPage(page, target.offset);
      return;
    }
    else if (target.anchor) {
      const el = $("content").querySelector(`#${CSS.escape(target.anchor)}`);
      if (el) {
        page = pageOfRect(el.getBoundingClientRect());
        el.classList.add("flash");
        setTimeout(() => el.classList.remove("flash"), 1700);
      }
    }
    showPage(page);
  } catch (err) {
    showError(err);
  } finally {
    if (token === R.token) $("loading").hidden = true;
  }
}

function next() {
  if (!R.book) return;
  if (R.page < R.pages - 1) showPage(R.page + 1);
  else if (R.chapter < R.book.chapters.length - 1) goTo(R.chapter + 1, { page: 0 });
}

function prev() {
  if (!R.book) return;
  if (R.page > 0) showPage(R.page - 1);
  else if (R.chapter > 0) goTo(R.chapter - 1, { end: true });
}

// In vertical (right-to-left) books the next page is on the left.
const leftAction = () => (R.vertical ? next() : prev());
const rightAction = () => (R.vertical ? prev() : next());

// Keeps the current character on screen after anything that changes the layout.
function relayout() {
  if (!R.book || $("reading").hidden) return;
  const offset = R.offset;
  $("content").lang = effectiveLanguage();
  layout();
  showPage(pageOfOffset(offset), offset);
}

// ---------------------------------------------------------------- contents & settings panels

function buildToc() {
  const list = $("toc");
  const entries = R.book.toc.length
    ? R.book.toc
    : R.book.chapters.map((c, i) => ({ title: c.title, chapter: i, anchor: "", depth: 0 }));
  list.replaceChildren(...entries.map((t) => {
    const a = document.createElement("a");
    a.className = "nav-link py-1";
    a.href = "#";
    a.textContent = t.title;
    a.lang = R.book.language;
    a.dataset.chapter = t.chapter;
    a.style.paddingInlineStart = `${16 + 16 * (t.depth || 0)}px`;
    a.addEventListener("click", (e) => {
      e.preventDefault();
      togglePanel("toc-panel", false);
      goTo(t.chapter, t.anchor ? { anchor: t.anchor } : { page: 0 });
    });
    return a;
  }));
}

// The side panels (Bootstrap offcanvases): one at a time.
function togglePanel(id, force) {
  const open = force !== undefined ? force : !$(id).classList.contains("show");
  for (const panel of document.querySelectorAll(".offcanvas.show")) {
    if (panel.id !== id) bootstrap.Offcanvas.getOrCreateInstance(panel).hide();
  }
  const panel = bootstrap.Offcanvas.getOrCreateInstance($(id));
  if (open) panel.show(); else panel.hide();
}

const panelOpen = () => Boolean(document.querySelector(".offcanvas.show"));

function syncSettingsForm() {
  const s = R.settings;
  $("set-font-size").value = s.font_size;
  $("out-font-size").textContent = `${s.font_size}px`;
  $("set-line-height").value = s.line_height;
  $("out-line-height").textContent = Number(s.line_height).toFixed(1);
  $("set-margin").value = s.margin;
  $("out-margin").textContent = `${s.margin}px`;
  $("set-furigana").checked = s.furigana;
  $("set-lookup").value = s.lookup || "click";
  $("set-colors").value = s.colors || "status";
  $("set-i1").checked = s.i1 !== false;
  for (const [id, value] of [["set-font", s.font], ["set-theme", s.theme]]) {
    for (const b of $(id).children) {
      b.setAttribute("aria-pressed", String(b.dataset.value === value));
      b.classList.toggle("active", b.dataset.value === value);
    }
  }
  if (R.book) {
    $("set-writing").value = R.prefs.writing || "auto";
    // Only the forms of the language studied (Mandarin: traditional or simplified characters).
    const lang = $("set-language");
    const detected = STUDY.tags.find((t) => t.tag === R.book.language);
    lang.replaceChildren(
      new Option(`Automatic (${detected ? detected.label : R.book.language})`, ""),
      ...STUDY.tags.map((t) => new Option(t.label, t.tag)),
    );
    if (R.prefs.language && !STUDY.tags.some((t) => t.tag === R.prefs.language)) lang.append(new Option(R.prefs.language, R.prefs.language));
    lang.value = R.prefs.language || "";
    $("language-setting").hidden = STUDY.tags.length <= 1;
  }
}

async function savePrefs(changes) {
  Object.assign(R.prefs, changes);
  try { R.prefs = await api(`/reader/api/books/${R.book.id}/prefs`, changes); } catch (err) { showError(err); }
}

function wireSettings() {
  const numeric = [["set-font-size", "font_size"], ["set-line-height", "line_height"], ["set-margin", "margin"]];
  for (const [id, key] of numeric) {
    $(id).addEventListener("input", (e) => {
      R.settings[key] = Number(e.target.value);
      syncSettingsForm();
      relayout();
      saveSettings();
    });
  }
  $("set-furigana").addEventListener("change", (e) => { R.settings.furigana = e.target.checked; relayout(); saveSettings(); });
  $("set-lookup").addEventListener("change", (e) => { R.settings.lookup = e.target.value; saveSettings(); });
  $("audio-link").addEventListener("click", linkAudio);
  $("audio-remove").addEventListener("click", removeAudio);
  $("set-colors").addEventListener("change", (e) => { R.settings.colors = e.target.value; colourWords(); saveSettings(); });
  $("set-i1").addEventListener("change", (e) => { R.settings.i1 = e.target.checked; paintRecommended(); saveSettings(); });
  for (const [id, key] of [["set-font", "font"], ["set-theme", "theme"]]) {
    for (const b of $(id).children) {
      b.addEventListener("click", () => {
        R.settings[key] = b.dataset.value;
        syncSettingsForm();
        applyTheme();
        relayout();
        saveSettings();
      });
    }
  }
  $("set-writing").addEventListener("change", async (e) => { await savePrefs({ writing: e.target.value }); relayout(); });
  $("set-language").addEventListener("change", async (e) => {
    await savePrefs({ language: e.target.value });
    decorate($("content"));
    relayout();
    colourWords();
  });
}

// ---------------------------------------------------------------- audio

function renderAudio() {
  const has = Boolean(R.audio);
  $("audio-status").textContent = has
    ? `${R.audio.tracks} audio file${R.audio.tracks > 1 ? "s" : ""} linked: click a word, then ▶ Sentence to hear it.`
    : "No audio. If you converted this book with MiningCat, link the conversion's audio.";
  $("audio-link").querySelector("span").textContent = has ? "Link the last conversion again" : "Link the last conversion's audio";
  $("audio-remove").hidden = !has;
}

async function linkAudio() {
  try {
    R.audio = (await api(`/reader/api/books/${R.book.id}/audio/link`, {})).audio;
    renderAudio();
  } catch (err) { showError(err); }
}

async function removeAudio() {
  const ok = await showDialog("Remove audio", "Remove the audio linked to this book? (The conversion's files in output/ are kept.)",
    [{ label: "Cancel", value: false }, { label: "Remove", value: true, primary: true }]);
  if (!ok) return;
  try {
    await api(`/reader/api/books/${R.book.id}/audio/delete`, {});
    R.audio = null;
    renderAudio();
  } catch (err) { showError(err); }
}

async function sentenceAudio(sentence, kind) {
  if (!R.book || !R.audio) return null;
  const data = await api(`/reader/api/books/${R.book.id}/audio/${kind}`, { sentence, chapter: R.chapter });
  return data.found ? data : null;
}

// ---------------------------------------------------------------- input

function isEditing(target) {
  return target && (target.closest("input, select, textarea") || target.isContentEditable);
}

function wireReading() {
  $("zone-left").addEventListener("click", leftAction);
  $("zone-right").addEventListener("click", rightAction);
  $("toc-btn").addEventListener("click", () => togglePanel("toc-panel"));
  $("i1-btn").addEventListener("click", () => togglePanel("i1-panel"));
  if (window.MiningCatMining) MiningCatMining.onAnalysis(showComprehension);
  $("settings-btn").addEventListener("click", () => togglePanel("settings-panel"));
  $("back").addEventListener("click", (e) => {
    e.preventDefault();
    saveNow();
    goToLibrary((R.book && R.places[`book:${R.book.id}`]) || null);  // back to the folder the book is in
  });

  // Internal links (notes, cross references) jump inside the book.
  $("content").addEventListener("click", (e) => {
    const a = e.target.closest("a[data-chapter]");
    if (!a) return;
    e.preventDefault();
    goTo(Number(a.dataset.chapter), a.dataset.anchor ? { anchor: a.dataset.anchor } : { page: 0 });
  });

  document.addEventListener("keydown", (e) => {
    if ($("reading").hidden || isEditing(e.target) || e.ctrlKey || e.metaKey || e.altKey || MiningCatUI.isModalOpen()) return;
    const keys = {
      ArrowLeft: leftAction, ArrowRight: rightAction,
      ArrowDown: next, ArrowUp: prev, PageDown: next, PageUp: prev, " ": e.shiftKey ? prev : next,
      Home: () => goTo(R.chapter, { page: 0 }), End: () => goTo(R.chapter, { end: true }),
      t: () => togglePanel("toc-panel"), s: () => togglePanel("settings-panel"), r: () => togglePanel("i1-panel"),
      Escape: () => {
        if (panelOpen()) togglePanel("toc-panel", false);
        else $("back").click();
      },
    };
    const action = keys[e.key];
    if (!action) return;
    e.preventDefault();
    action();
  });

  // One page per wheel gesture.
  let wheelLock = 0;
  $("stage").addEventListener("wheel", (e) => {
    if (e.target.closest(".offcanvas")) return;
    e.preventDefault();
    const now = Date.now();
    const delta = Math.abs(e.deltaY) > Math.abs(e.deltaX) ? e.deltaY : e.deltaX;
    if (now < wheelLock || Math.abs(delta) < 4) return;
    wheelLock = now + 280;
    if (delta > 0) next(); else prev();
  }, { passive: false });

  // Swipes on touch screens.
  let touch = null;
  $("stage").addEventListener("pointerdown", (e) => {
    if (e.pointerType === "touch") touch = { x: e.clientX, y: e.clientY, t: Date.now() };
  });
  $("stage").addEventListener("pointerup", (e) => {
    if (!touch || e.pointerType !== "touch") return;
    const dx = e.clientX - touch.x, dy = e.clientY - touch.y;
    const quick = Date.now() - touch.t < 600;
    touch = null;
    if (!quick || Math.abs(dx) < 45 || Math.abs(dx) < Math.abs(dy)) return;
    if (window.getSelection && String(window.getSelection())) return;
    if (dx < 0) rightAction(); else leftAction();
  });

  let resizeTimer = null;
  new ResizeObserver(() => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(relayout, 120);
  }).observe($("viewport"));

  window.addEventListener("pagehide", saveNow);
  document.addEventListener("visibilitychange", () => { if (document.hidden) saveNow(); });
}

function wireLibrary() {
  const input = $("book-input");
  $("add-books").addEventListener("click", () => input.click());
  input.addEventListener("change", () => {
    const files = [...input.files];
    input.value = "";
    addBooks(files);
  });
  const drop = $("lib-drop");
  const over = ["border-primary", "bg-primary-subtle"];
  // files from outside the page only: a cover dragged in the library carries its picture as a file (Chrome), which
  // would be imported again
  const outsideFiles = (e) => e.dataTransfer.types.includes("Files") && !R.dragging && !e.dataTransfer.types.includes(DRAG_TYPE);
  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("drop", (e) => e.preventDefault());

  // A book or a folder dragged onto a folder goes in it (onto "Library", out of its folders); a picture dragged onto a
  // picture makes an album.
  const targetOf = (e) => e.target.closest?.(".mc-folder-target, .mc-merge-target");
  const clearTargets = (except) => {
    for (const t of document.querySelectorAll(".mc-drop-over")) if (t !== except) t.classList.remove("mc-drop-over");
  };
  // Files from outside go into the folder they're dropped on (a folder of the path too), else into the folder shown.
  const folderOf = (e) => e.target.closest?.(".mc-folder-target");
  document.addEventListener("dragover", (e) => {
    if (outsideFiles(e)) {
      const target = folderOf(e);
      clearTargets(target);
      target?.classList.add("mc-drop-over");
      drop.classList.toggle(over[0], !target && drop.contains(e.target));
      drop.classList.toggle(over[1], !target && drop.contains(e.target));
      return;
    }
    const target = accepts(targetOf(e), R.dragging) ? targetOf(e) : null;
    clearTargets(target);
    if (!target) return;
    e.dataTransfer.dropEffect = "move";
    target.classList.add("mc-drop-over");
  });
  document.addEventListener("dragleave", (e) => { if (!e.relatedTarget) { clearTargets(null); drop.classList.remove(...over); } });
  document.addEventListener("dragend", () => clearTargets(null));
  document.addEventListener("drop", (e) => {
    clearTargets(null);
    drop.classList.remove(...over);
    if (outsideFiles(e)) {
      const target = folderOf(e);
      if (target) addBooks([...e.dataTransfer.files], target.dataset.folder || null);
      else if (drop.contains(e.target)) addBooks([...e.dataTransfer.files]);
      return;
    }
    const target = targetOf(e), drag = R.dragging;
    R.dragging = null;
    if (!accepts(target, drag)) return;
    if (target.dataset.folder !== undefined) moveItems([drag.key], target.dataset.folder || null);
    else addToAlbum(drag.key, target.dataset.merge);
  });

  $("new-folder").addEventListener("click", newFolder);
  $("folder-rename").addEventListener("click", renameFolder);
  $("folder-delete").addEventListener("click", deleteFolder);

  // Ctrl+V (⌘V): the images (or files) of the clipboard are imported, no need to save them first.
  document.addEventListener("paste", (e) => {
    if ($("library").hidden || isEditing(e.target) || MiningCatUI.isModalOpen()) return;
    const files = [...(e.clipboardData?.files || [])].map(pastedFile);
    if (!files.length) return;
    e.preventDefault();
    const imported = (f) => !f.type.startsWith("image/") || R.imageExtensions.includes(f.name.split(".").pop().toLowerCase());
    const refused = files.filter((f) => !imported(f));
    if (refused.length) {
      showDialog("Some pictures could not be imported", `${refused.map((f) => f.type).join(", ")}: not a supported image format `
        + `(supported: ${R.imageExtensions.join(", ")}).`);
    }
    addBooks(files.filter(imported));
  });
}

// ---------------------------------------------------------------- routing

async function route() {
  const match = location.pathname.match(/^\/reader\/([0-9a-f]{16})\/?$/);
  try {
    if (match) await openBook(match[1]);
    else await showLibrary();
  } catch (err) {
    await showError(err);
    if (match) { history.replaceState({}, "", "/reader/"); showLibrary(); }
  }
}

async function init() {
  R.settings = await api("/reader/api/settings");
  applyTheme();
  syncSettingsForm();
  wireLibrary();
  wireReading();
  wireSettings();
  if (window.MiningCatMining) {
    MiningCatMining.attach($("content"), {
      getLanguage: effectiveLanguage,
      getSource: () => (R.book ? R.book.title : ""),
      getMode: () => R.settings.lookup || "click",
      isVertical: () => R.vertical,
      hasAudio: () => Boolean(R.audio),
      sentenceAudio: (text) => sentenceAudio(text, "find"),
      sentenceClip: (text) => sentenceAudio(text, "clip").then((d) => (d ? { data: d.data, name: d.name } : null)),
    });
  }
  window.addEventListener("popstate", () => { saveNow(); route(); });
  route();
}

document.addEventListener("DOMContentLoaded", init);

// exposed for debugging and tests
window.MiningCatReader = { state: R, goTo, next, prev, pageOfOffset, offsetForPage };
