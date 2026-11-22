const token = "__NEXUS_TOKEN__";

// ── i18n (ไทย/English) ──────────────────────────────────────────────
const I18N = {
  th: {
    "queue.title": "คิวโหลด", "queue.empty": "ยังไม่มีงาน", "clear.done": "ล้างที่จบ",
    "folder.ph": "โฟลเดอร์เก็บไฟล์", "folder.save": "ตั้งโฟลเดอร์", "folder.open": "เปิดโฟลเดอร์",
    "settings.title": "⚙️ ตั้งค่า", "settings.thumb": "ฝังภาพปก", "settings.meta": "ฝัง metadata",
    "settings.lyrics": "ฝังเนื้อเพลง", "settings.sponsor": "ตัดช่วง sponsor (SponsorBlock)",
    "settings.normalize": "ปรับความดังให้สม่ำเสมอ", "conc.pre": "โหลดพร้อมกัน", "conc.post": "งาน",
    "header.note": "หน้านี้ใช้โหลดอย่างเดียว เครื่องเล่นอยู่ในโปรแกรม", "engine.checking": "กำลังตรวจเครื่องมือ",
    "engine.ready": "เครื่องมือพร้อม", "engine.notready": "เครื่องมือยังไม่พร้อม ระบบจะจัดให้",
    "search.ph": "ค้นหาเพลง", "go": "โหลด",
    "st.waiting": "รอ", "st.downloading": "กำลังโหลด", "st.processing": "กำลังจัดไฟล์",
    "st.completed": "เสร็จ", "st.failed": "ไม่สำเร็จ", "st.cancelled": "ยกเลิก",
    "note.queued": "ใส่คิวแล้ว", "note.duplicate": "ลิงก์นี้อยู่ในคิวแล้ว", "note.searching": "กำลังค้น",
    "note.folder": "ตั้งโฟลเดอร์แล้ว", "note.saved": "บันทึกแล้ว ✓", "note.conn": "เชื่อมเซิร์ฟเวอร์โหลดไม่ได้",
    "note.load": "โหลด"
  },
  en: {
    "queue.title": "Download Queue", "queue.empty": "No jobs yet", "clear.done": "Clear finished",
    "folder.ph": "Save folder path", "folder.save": "Set folder", "folder.open": "Open folder",
    "settings.title": "⚙️ Settings", "settings.thumb": "Embed cover art", "settings.meta": "Embed metadata",
    "settings.lyrics": "Embed lyrics", "settings.sponsor": "Skip sponsor segments (SponsorBlock)",
    "settings.normalize": "Normalize loudness", "conc.pre": "Parallel downloads", "conc.post": "tasks",
    "header.note": "This page only downloads. The player lives in the desktop app.", "engine.checking": "Checking tools",
    "engine.ready": "Tools ready", "engine.notready": "Tools not ready — NexusTube will set them up",
    "search.ph": "Search music", "go": "Get",
    "st.waiting": "Queued", "st.downloading": "Downloading", "st.processing": "Processing",
    "st.completed": "Done", "st.failed": "Failed", "st.cancelled": "Cancelled",
    "note.queued": "Queued", "note.duplicate": "Already in queue", "note.searching": "Searching",
    "note.folder": "Folder saved", "note.saved": "Saved ✓", "note.conn": "Cannot reach the download server",
    "note.load": "Get"
  }
};
let LANG = localStorage.getItem("nexustube_lang") || "th";
function t(key) { return (I18N[LANG] && I18N[LANG][key]) || I18N.th[key] || key; }

function applyLang() {
  document.documentElement.lang = LANG;
  for (const el of document.querySelectorAll("[data-i18n]")) el.textContent = t(el.dataset.i18n);
  for (const el of document.querySelectorAll("[data-i18n-ph]")) el.placeholder = t(el.dataset.i18nPh);
  document.getElementById("lang").value = LANG;
  const engineText = document.getElementById("engine-text");
  if (engineText.classList.contains("on")) engineText.textContent = t("engine.ready");
  paintQueueRows(lastQueueTasks);
}

// Local-first: หน้านี้ถูกเสิร์ฟจากเครื่องผู้ใช้เอง (127.0.0.1) จึงเรียก API แบบ same-origin เท่านั้น
function apiUrl(path) {
  return String(path || "").replace(/^\//, "");
}

function esc(value) {
  return String(value || "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  }[ch]));
}

async function api(op, extra = {}) {
  let res;
  try {
    res = await fetch(apiUrl("api"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Nexus-Token": token
      },
      body: JSON.stringify({ op, ...extra })
    });
  } catch {
    throw new Error(t("note.conn"));
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (!data.error) throw new Error(t("note.conn"));
    throw new Error(data.error);
  }
  return data;
}

function note(text, isError) {
  const el = document.getElementById("note");
  el.textContent = text || "";
  el.className = isError ? "err" : "meta";
}

const statusText = {
  waiting: "st.waiting",
  downloading: "st.downloading",
  processing: "st.processing",
  completed: "st.completed",
  failed: "st.failed",
  cancelled: "st.cancelled"
};

function looksLikeUrl(value) {
  return /^https?:\/\//i.test(value);
}

function clock(seconds) {
  const n = Math.floor(Number(seconds) || 0);
  if (!n) return "";
  const m = Math.floor(n / 60);
  const s = n % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

async function addUrl(url, title) {
  const format = document.getElementById("format").value;
  const result = await api("add", { url, title: title || "", format });
  if (result.error) {
    note(result.error, true);
    return;
  }
  if (result.duplicate) note(t("note.duplicate"));
  else note(t("note.queued"));
  document.getElementById("results").replaceChildren();
  await paintQueue();
}

function paintResults(items) {
  const box = document.getElementById("results");
  box.replaceChildren();
  for (const item of items) {
    if (!looksLikeUrl(item.url)) continue;
    const row = document.createElement("article");
    const img = document.createElement("img");
    img.alt = "";
    if (/^https?:\/\//i.test(item.thumbnail || "")) img.src = item.thumbnail;
    const text = document.createElement("div");
    const length = clock(item.duration);
    const badge = item.source === "apple_music"
      ? '<span class="src-badge src-apple">♪ Apple Music</span> '
      : '<span class="src-badge src-youtube">▶ YouTube</span> ';
    text.innerHTML = `<strong>${esc(item.title)}</strong><div class="meta">${badge}${esc(item.channel)}${length ? " · " + esc(length) : ""}</div>`;
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "โหลด";
    button.onclick = () => addUrl(item.url, item.title).catch((err) => note(err.message, true));
    row.append(img, text, button);
    box.append(row);
  }
}

let lastQueueTasks = [];

function paintQueueRows(tasks) {
  lastQueueTasks = tasks;
  const box = document.getElementById("queue");
  if (!tasks.length) {
    box.textContent = t("queue.empty");
    box.className = "empty";
    return;
  }
  box.className = "";
  box.replaceChildren();
  for (const task of tasks) {
    const row = document.createElement("article");
    const img = document.createElement("img");
    img.alt = "";
    if (/^https?:\/\//i.test(task.thumbnail || "")) img.src = task.thumbnail;
    const text = document.createElement("div");
    const label = t(statusText[task.status] || task.status) || task.status;
    const progress = task.status === "downloading" || task.status === "processing"
      ? ` ${Math.round(Number(task.percent) || 0)}% ${esc(task.speed || "")} ${esc(task.eta || "")}`
      : "";
    const error = task.error ? `<div class="err">${esc(task.error)}</div>` : "";
    text.innerHTML = `<strong>${esc(task.title)}</strong><div class="meta">${esc(label)}${progress}</div>${error}`;
    const actions = document.createElement("div");
    actions.className = "row";
    if (task.status === "waiting" || task.status === "downloading" || task.status === "processing") {
      const cancel = document.createElement("button");
      cancel.type = "button";
      cancel.className = "quiet";
      cancel.textContent = "ยกเลิก";
      cancel.onclick = () => api("cancel", { id: task.id }).then(paintQueue);
      actions.append(cancel);
    }
    if (task.status === "failed" || task.status === "cancelled") {
      const retry = document.createElement("button");
      retry.type = "button";
      retry.className = "quiet";
      retry.textContent = "ลองใหม่";
      retry.onclick = () => api("retry", { id: task.id }).then(paintQueue);
      actions.append(retry);
    }
    if (task.status === "completed" && task.out_file) {
      const open = document.createElement("button");
      open.type = "button";
      open.className = "quiet";
      open.textContent = "เปิดไฟล์";
      open.onclick = () => api("reveal", { path: task.out_file });
      actions.append(open);
    }
    row.append(img, text, actions);
    box.append(row);
  }
}

async function paintQueue() {
  paintQueueRows(await api("queue"));
}

async function paintState() {
  const state = await api("state");
  document.getElementById("folder").value = state.outdir || "";
  const s = state.settings || {};
  document.getElementById("set-thumb").checked = Boolean(s.embed_thumb);
  document.getElementById("set-meta").checked = Boolean(s.embed_meta);
  document.getElementById("set-lyrics").checked = Boolean(s.embed_lyrics);
  document.getElementById("set-sponsor").checked = Boolean(s.sponsorblock);
  document.getElementById("set-normalize").checked = Boolean(s.normalize);
  document.getElementById("set-conc").value = String(Math.min(6, Math.max(1, Number(s.max_concurrent) || 3)));
  if (state.format) document.getElementById("format").value = state.format;
  const ready = state.engines && state.engines.ytdlp_ready && state.engines.ffmpeg_ready;
  document.getElementById("engine-dot").className = ready ? "dot on" : "dot";
  const engineText = document.getElementById("engine-text");
  engineText.textContent = ready ? t("engine.ready") : t("engine.notready");
  engineText.classList.add("on");
}

document.getElementById("grab").onsubmit = async (event) => {
  event.preventDefault();
  const query = document.getElementById("query").value.trim();
  const button = document.getElementById("go");
  button.disabled = true;
  try {
    if (looksLikeUrl(query)) await addUrl(query, "");
    else {
      note(t("note.searching"));
      const items = await api("search", { query });
      paintResults(items);
      note(items.length ? `${items.length} results` : "0 results");
    }
  } catch (err) {
    note(err.message, true);
  } finally {
    button.disabled = false;
  }
};

document.getElementById("save-folder").onclick = async () => {
  try {
    const saved = await api("folder", { path: document.getElementById("folder").value.trim() });
    document.getElementById("folder").value = saved.outdir || "";
    note(t("note.folder"));
  } catch (err) {
    note(err.message, true);
  }
};

document.getElementById("open-folder").onclick = () => api("open").catch((err) => note(err.message, true));
document.getElementById("clear-done").onclick = () => api("clear").then(paintQueue).catch((err) => note(err.message, true));

// ── ตั้งค่า: เปลี่ยนแล้วบันทึกทันที ──────────────────────────────
const SETTINGS_KEYS = {
  "set-thumb": "embed_thumb",
  "set-meta": "embed_meta",
  "set-lyrics": "embed_lyrics",
  "set-sponsor": "sponsorblock",
  "set-normalize": "normalize"
};

async function saveSettings(extra = {}) {
  const settings = { ...extra };
  for (const [elId, key] of Object.entries(SETTINGS_KEYS)) {
    settings[key] = document.getElementById(elId).checked;
  }
  try {
    await api("set_settings", { settings });
    document.getElementById("settings-note").textContent = t("note.saved");
    setTimeout(() => { const el = document.getElementById("settings-note"); if (el) el.textContent = ""; }, 2000);
  } catch (err) {
    document.getElementById("settings-note").textContent = err.message;
  }
}

for (const elId of Object.keys(SETTINGS_KEYS)) {
  document.getElementById(elId).addEventListener("change", () => saveSettings());
}
document.getElementById("set-conc").addEventListener("change", () => saveSettings({ max_concurrent: Number(document.getElementById("set-conc").value) }));

// ── ภาษา ────────────────────────────────────────────────────────────
document.getElementById("lang").addEventListener("change", (ev) => {
  LANG = ev.target.value === "en" ? "en" : "th";
  localStorage.setItem("nexustube_lang", LANG);
  applyLang();
});
applyLang();

paintState().then(paintQueue).catch((err) => note(err.message, true));
setInterval(() => paintQueue().catch(() => {}), 2000);
