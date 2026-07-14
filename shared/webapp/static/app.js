/* device — library web app. Vanilla JS, no build step. */
"use strict";

const $ = (sel) => document.querySelector(sel);
const state = { tracks: [], playlists: {}, selected: null, query: "" };

/* ————— helpers ————— */

function fmtDur(s) {
  s = Math.max(0, Math.round(s));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function fmtBytes(b) {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (b >= 1024 && i < units.length - 1) { b /= 1024; i++; }
  return `${b.toFixed(b >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}

function toast(msg, ok = false) {
  const el = document.createElement("div");
  el.className = "toast" + (ok ? " ok" : "");
  el.textContent = msg;
  $("#toasts").appendChild(el);
  setTimeout(() => el.remove(), 3200);
}

/* Optional shared PIN (config.WEBAPP_PIN on the device): remembered for
   the browser session, prompted for on the first 401. */
function pinHeaders() {
  const pin = sessionStorage.getItem("devicePin");
  return pin ? { "X-Device-Pin": pin } : {};
}

async function api(path, options = {}, retried = false) {
  options.headers = { ...(options.headers || {}), ...pinHeaders() };
  const res = await fetch(path, options);
  let body = {};
  try { body = await res.json(); } catch { /* non-JSON error page */ }
  if (res.status === 401 && !retried) {
    const pin = prompt("This device asks for its PIN:");
    if (pin) {
      sessionStorage.setItem("devicePin", pin);
      return api(path, options, true);
    }
  }
  if (!res.ok) throw new Error(body.error || `${res.status} ${res.statusText}`);
  return body;
}

/* ————— tabs ————— */

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    tab.classList.add("active");
    $(`#view-${tab.dataset.view}`).classList.add("active");
  });
});

/* ————— header status ————— */

async function refreshStatus() {
  try {
    const s = await api("/api/status");
    $("#device-name").textContent = s.name || "device";
    $("#stat-tracks").textContent = `${s.tracks} tracks`;
    $("#stat-disk").textContent = `${fmtBytes(s.disk_free)} free`;
    const bat = $("#stat-battery");
    bat.textContent = s.battery == null ? "battery --" : `battery ${s.battery}%`;
    bat.classList.toggle("good", s.battery != null && s.battery > 20);
  } catch { /* header is best-effort */ }
}

/* ————— library ————— */

async function refreshLibrary() {
  const body = await api("/api/library");
  state.tracks = body.tracks;
  renderLibrary();
  refreshStatus();
}

function renderLibrary() {
  const q = state.query.toLowerCase();
  const tracks = state.tracks.filter((t) =>
    !q || `${t.title} ${t.artist} ${t.album}`.toLowerCase().includes(q));
  $("#library-count").textContent =
    q ? `${tracks.length} match${tracks.length === 1 ? "" : "es"}` : "";

  const byArtist = new Map();
  for (const t of tracks) {
    if (!byArtist.has(t.artist)) byArtist.set(t.artist, new Map());
    const albums = byArtist.get(t.artist);
    if (!albums.has(t.album)) albums.set(t.album, []);
    albums.get(t.album).push(t);
  }

  const root = $("#library");
  root.replaceChildren();
  if (!tracks.length) {
    const p = document.createElement("p");
    p.className = "muted empty-hint";
    p.textContent = q ? "Nothing matches." :
      "Library is empty — drag songs into the Upload tab.";
    root.appendChild(p);
    return;
  }
  for (const [artist, albums] of byArtist) {
    const group = document.createElement("div");
    group.className = "artist-group";
    const head = document.createElement("div");
    head.className = "artist-head";
    head.textContent = artist;
    group.appendChild(head);
    for (const [album, list] of albums) {
      const block = document.createElement("div");
      block.className = "album-block";
      const ah = document.createElement("div");
      ah.className = "album-head";
      const total = list.reduce((acc, t) => acc + t.duration, 0);
      ah.innerHTML = `<span class="name"></span>
                      <span class="count">${list.length} · ${fmtDur(total)}</span>`;
      ah.querySelector(".name").textContent = album;
      block.appendChild(ah);
      for (const t of list) block.appendChild(trackRow(t));
      group.appendChild(block);
    }
    root.appendChild(group);
  }
}

function trackRow(t) {
  const row = document.createElement("div");
  row.className = "track-row";
  row.innerHTML = `
    <span class="track-no">${t.track_no || ""}</span>
    <span class="track-title"></span>
    <span class="track-dur">${fmtDur(t.duration)}</span>
    <span class="row-actions">
      <button class="icon-btn" title="Edit tags">✎</button>
      <button class="icon-btn" title="Add to playlist">＋</button>
      <button class="icon-btn danger" title="Delete">✕</button>
    </span>`;
  row.querySelector(".track-title").textContent = t.title;
  const [editBtn, addBtn, delBtn] = row.querySelectorAll("button");
  editBtn.addEventListener("click", () => openEdit(t));
  addBtn.addEventListener("click", () => openPick(t));
  delBtn.addEventListener("click", () => deleteTrack(t));
  return row;
}

async function deleteTrack(t) {
  if (!confirm(`Delete "${t.title}"?\n\nIt moves to the device's trash and is` +
               ` purged after a week.`)) return;
  try {
    await api(`/api/tracks/${encodeURIComponent(t.id)}`, { method: "DELETE" });
    toast(`Removed: ${t.title}`, true);
    await Promise.all([refreshLibrary(), refreshPlaylists()]);
  } catch (e) { toast(e.message); }
}

$("#search").addEventListener("input", (e) => {
  state.query = e.target.value;
  renderLibrary();
});

/* ————— edit modal ————— */

const editModal = $("#edit-modal");
let editing = null;

function openEdit(t) {
  editing = t;
  const f = $("#edit-form");
  f.title.value = t.title;
  f.artist.value = t.artist;
  f.album.value = t.album;
  f.track_no.value = t.track_no || "";
  $("#edit-file").textContent = t.id;
  editModal.showModal();
}

$("#edit-cancel").addEventListener("click", () => editModal.close());
$("#edit-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  try {
    await api(`/api/tracks/${encodeURIComponent(editing.id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: f.title.value, artist: f.artist.value,
        album: f.album.value, track_no: f.track_no.value || 0,
      }),
    });
    editModal.close();
    toast("Track updated", true);
    await Promise.all([refreshLibrary(), refreshPlaylists()]);
  } catch (err) { toast(err.message); }
});

/* ————— upload ————— */

const dropzone = $("#dropzone");
["dragenter", "dragover"].forEach((ev) =>
  dropzone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropzone.classList.add("drag");
  }));
["dragleave", "drop"].forEach((ev) =>
  dropzone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropzone.classList.remove("drag");
  }));
dropzone.addEventListener("drop", (e) => enqueue([...e.dataTransfer.files]));
$("#file-input").addEventListener("change", (e) => {
  enqueue([...e.target.files]);
  e.target.value = "";
});

function enqueue(files) {
  for (const file of files) uploadOne(file);
}

function uploadOne(file, replace = false) {
  const li = document.createElement("li");
  li.innerHTML = `
    <div class="up-head"><span class="up-name"></span>
    <span class="up-state">0%</span></div>
    <div class="progress"><div></div></div>`;
  li.querySelector(".up-name").textContent = file.name;
  $("#upload-queue").prepend(li);
  const stateEl = li.querySelector(".up-state");
  const bar = li.querySelector(".progress > div");
  const track = li.querySelector(".progress");

  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/upload" + (replace ? "?replace=1" : ""));
  const pin = sessionStorage.getItem("devicePin");
  if (pin) xhr.setRequestHeader("X-Device-Pin", pin);
  xhr.upload.addEventListener("progress", (e) => {
    if (e.lengthComputable) {
      const pct = Math.round((e.loaded / e.total) * 100);
      bar.style.width = `${pct}%`;
      stateEl.textContent = `${pct}%`;
    }
  });
  xhr.addEventListener("load", async () => {
    let body = {};
    try { body = JSON.parse(xhr.responseText); } catch { /* ignore */ }
    if (xhr.status === 201) {
      stateEl.textContent = "done";
      stateEl.className = "up-state ok";
      track.classList.add("done");
      bar.style.width = "100%";
      await refreshLibrary();
    } else if (xhr.status === 409) {
      stateEl.textContent = "exists";
      stateEl.className = "up-state err";
      if (confirm(`${body.error}\n\nReplace it?`)) {
        li.remove();
        uploadOne(file, true);
      }
    } else {
      stateEl.textContent = body.error || `failed (${xhr.status})`;
      stateEl.className = "up-state err";
    }
  });
  xhr.addEventListener("error", () => {
    stateEl.textContent = "connection failed";
    stateEl.className = "up-state err";
  });
  const form = new FormData();
  form.append("file", file);
  xhr.send(form);
}

/* ————— playlists ————— */

async function refreshPlaylists() {
  const body = await api("/api/playlists");
  state.playlists = body.playlists;
  if (state.selected && !(state.selected in state.playlists)) state.selected = null;
  renderPlaylists();
}

function renderPlaylists() {
  const list = $("#playlist-list");
  list.replaceChildren();
  const names = Object.keys(state.playlists).sort((a, b) => a.localeCompare(b));
  for (const name of names) {
    const li = document.createElement("li");
    if (name === state.selected) li.classList.add("selected");
    li.innerHTML = `<span class="name"></span><span class="count"></span>`;
    li.querySelector(".name").textContent = name;
    li.querySelector(".count").textContent = state.playlists[name].length;
    li.addEventListener("click", () => {
      state.selected = name;
      renderPlaylists();
    });
    list.appendChild(li);
  }
  renderPlaylistDetail();
}

function renderPlaylistDetail() {
  const box = $("#playlist-detail");
  box.replaceChildren();
  if (!state.selected) {
    const p = document.createElement("p");
    p.className = "muted empty-hint";
    p.textContent = "Select a playlist — drag rows to set the play order on the device.";
    box.appendChild(p);
    return;
  }
  const name = state.selected;
  const ids = state.playlists[name];
  const byId = new Map(state.tracks.map((t) => [t.id, t]));

  const head = document.createElement("div");
  head.className = "pd-head";
  head.innerHTML = `<h3></h3>
    <span class="pd-actions">
      <button class="btn" id="pl-rename">Rename</button>
      <button class="btn danger" id="pl-delete">Delete</button>
    </span>`;
  head.querySelector("h3").textContent = name;
  box.appendChild(head);

  head.querySelector("#pl-rename").addEventListener("click", async () => {
    const next = prompt("New name:", name);
    if (!next || next === name) return;
    try {
      await api(`/api/playlists/${encodeURIComponent(name)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rename: next }),
      });
      state.selected = next;
      await refreshPlaylists();
    } catch (e) { toast(e.message); }
  });
  head.querySelector("#pl-delete").addEventListener("click", async () => {
    if (!confirm(`Delete playlist "${name}"? (Songs stay in the library.)`)) return;
    try {
      await api(`/api/playlists/${encodeURIComponent(name)}`, { method: "DELETE" });
      state.selected = null;
      await refreshPlaylists();
    } catch (e) { toast(e.message); }
  });

  if (!ids.length) {
    const p = document.createElement("p");
    p.className = "muted empty-hint";
    p.textContent = "Empty — use ＋ on a library track to add it here.";
    box.appendChild(p);
    return;
  }

  ids.forEach((tid, i) => {
    const t = byId.get(tid);
    const row = document.createElement("div");
    row.className = "p-row";
    row.draggable = true;
    row.dataset.index = i;
    row.innerHTML = `<span class="grip">⠿</span>
      <span class="track-no">${i + 1}</span>
      <span class="track-title"></span>
      <span class="track-dur">${t ? fmtDur(t.duration) : ""}</span>
      <span class="row-actions">
        <button class="icon-btn danger" title="Remove from playlist">✕</button>
      </span>`;
    row.querySelector(".track-title").textContent = t ? t.title : tid;
    row.querySelector("button").addEventListener("click", () =>
      setPlaylist(name, ids.filter((_, j) => j !== i)));
    row.addEventListener("dragstart", () => row.classList.add("dragging"));
    row.addEventListener("dragend", () => row.classList.remove("dragging"));
    box.appendChild(row);
  });

  box.addEventListener("dragover", (e) => {
    e.preventDefault();
    const dragging = box.querySelector(".dragging");
    if (!dragging) return;
    const rows = [...box.querySelectorAll(".p-row:not(.dragging)")];
    const after = rows.find((r) =>
      e.clientY < r.getBoundingClientRect().top + r.offsetHeight / 2);
    if (after) box.insertBefore(dragging, after);
    else box.appendChild(dragging);
  });
  box.addEventListener("drop", (e) => {
    e.preventDefault();
    const order = [...box.querySelectorAll(".p-row")]
      .map((r) => ids[Number(r.dataset.index)]);
    setPlaylist(name, order);
  });
}

async function setPlaylist(name, ids) {
  try {
    await api(`/api/playlists/${encodeURIComponent(name)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tracks: ids }),
    });
    await refreshPlaylists();
  } catch (e) { toast(e.message); }
}

$("#create-playlist").addEventListener("click", createPlaylist);
$("#new-playlist").addEventListener("keydown", (e) => {
  if (e.key === "Enter") createPlaylist();
});

async function createPlaylist() {
  const input = $("#new-playlist");
  const name = input.value.trim();
  if (!name) return;
  try {
    await api("/api/playlists", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    input.value = "";
    state.selected = name;
    await refreshPlaylists();
  } catch (e) { toast(e.message); }
}

/* ————— add-to-playlist modal ————— */

const pickModal = $("#pick-modal");

function openPick(t) {
  const names = Object.keys(state.playlists).sort((a, b) => a.localeCompare(b));
  const list = $("#pick-list");
  list.replaceChildren();
  $("#pick-track").textContent = t.title;
  if (!names.length) {
    const li = document.createElement("li");
    li.textContent = "No playlists yet — create one in the Playlists tab.";
    li.style.cursor = "default";
    list.appendChild(li);
  }
  for (const name of names) {
    const li = document.createElement("li");
    const has = state.playlists[name].includes(t.id);
    li.textContent = has ? `${name} (already added)` : name;
    if (!has) li.addEventListener("click", async () => {
      pickModal.close();
      await setPlaylist(name, [...state.playlists[name], t.id]);
      toast(`Added to ${name}`, true);
    });
    list.appendChild(li);
  }
  pickModal.showModal();
}

$("#pick-cancel").addEventListener("click", () => pickModal.close());

/* ————— boot ————— */

(async function boot() {
  try {
    await Promise.all([refreshLibrary(), refreshPlaylists()]);
  } catch (e) {
    toast(`Cannot reach the device: ${e.message}`);
  }
  setInterval(refreshStatus, 15000);
})();
