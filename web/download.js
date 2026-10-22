const token = "__NEXUS_TOKEN__";
const API_ROOT = location.hostname.endsWith("github.io") ? "https://keyboards-frequency-pointed-ties.trycloudflare.com" : "";

function apiUrl(path) {
  const clean = String(path || "").replace(/^\//, "");
  return API_ROOT ? API_ROOT + "/" + clean : clean;
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
    throw new Error("เชื่อมเซิร์ฟเวอร์โหลดไม่ได้");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (!data.error) throw new Error("เชื่อมเซิร์ฟเวอร์โหลดไม่ได้");
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
  waiting: "รอ",
  downloading: "กำลังโหลด",
  processing: "กำลังจัดไฟล์",
  completed: "เสร็จ",
  failed: "ไม่สำเร็จ",
  cancelled: "ยกเลิก"
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
  if (result.duplicate) note("ลิงก์นี้อยู่ในคิวแล้ว");
  else note("ใส่คิวแล้ว");
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
    text.innerHTML = `<strong>${esc(item.title)}</strong><div class="meta">${esc(item.channel)}${length ? " · " + esc(length) : ""}</div>`;
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "โหลด";
    button.onclick = () => addUrl(item.url, item.title).catch((err) => note(err.message, true));
    row.append(img, text, button);
    box.append(row);
  }
}

function paintQueueRows(tasks) {
  const box = document.getElementById("queue");
  if (!tasks.length) {
    box.textContent = "ยังไม่มีงาน";
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
    const label = statusText[task.status] || task.status;
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
    if (task.out_file === true || (API_ROOT && task.status === "completed")) {
      const link = document.createElement("a");
      link.href = apiUrl("file") + "?id=" + encodeURIComponent(task.id);
      link.textContent = "ดาวน์โหลด";
      link.className = "quiet";
      actions.append(link);
    } else if (task.out_file) {
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
  const folder = document.querySelector(".folder");
  if (state.public && folder) folder.hidden = true;
  document.getElementById("folder").value = state.outdir || "";
  if (state.format) document.getElementById("format").value = state.format;
  const ready = state.engines && state.engines.ytdlp_ready && state.engines.ffmpeg_ready;
  document.getElementById("engine-dot").className = ready ? "dot on" : "dot";
  document.getElementById("engine-text").textContent = ready ? "เครื่องมือพร้อม" : "เครื่องมือยังไม่พร้อม ระบบจะจัดให้";
}

document.getElementById("grab").onsubmit = async (event) => {
  event.preventDefault();
  const query = document.getElementById("query").value.trim();
  const button = document.getElementById("go");
  button.disabled = true;
  try {
    if (looksLikeUrl(query)) await addUrl(query, "");
    else {
      note("กำลังค้น");
      const items = await api("search", { query });
      paintResults(items);
      note(items.length ? `เจอ ${items.length} รายการ` : "ไม่เจอรายการ");
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
    note("ตั้งโฟลเดอร์แล้ว");
  } catch (err) {
    note(err.message, true);
  }
};

document.getElementById("open-folder").onclick = () => api("open").catch((err) => note(err.message, true));
document.getElementById("clear-done").onclick = () => api("clear").then(paintQueue).catch((err) => note(err.message, true));

paintState().then(paintQueue).catch((err) => note(err.message, true));
setInterval(() => paintQueue().catch(() => {}), 2000);
