"use strict";
/* Phone Snatch Detector dashboard. Plain JavaScript, no build step.
   Layout and components follow the FollowSense AI dashboard. */

/* ================================================================ helpers */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const ICONS = {
  shield: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="M12 8v4"/><path d="M12 16h.01"/>',
  dashboard: '<rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/><rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/>',
  scan: '<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><path d="M9 9h.01"/><path d="M15 9h.01"/>',
  monitorPlay: '<path d="M10 7.75a.75.75 0 0 1 1.142-.638l3.664 2.249a.75.75 0 0 1 0 1.278l-3.664 2.25a.75.75 0 0 1-1.142-.64z"/><path d="M12 17v4"/><path d="M8 21h8"/><rect x="2" y="3" width="20" height="14" rx="2"/>',
  siren: '<path d="M7 18v-6a5 5 0 1 1 10 0v6"/><path d="M5 21a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-1a2 2 0 0 0-2-2H7a2 2 0 0 0-2 2z"/><path d="M21 12h1"/><path d="M18.5 4.5 18 5"/><path d="M2 12h1"/><path d="M12 2v1"/><path d="m4.929 4.929.707.707"/><path d="M12 12v6"/>',
  video: '<path d="m16 13 5.223 3.482a.5.5 0 0 0 .777-.416V7.87a.5.5 0 0 0-.752-.432L16 10.5"/><rect x="2" y="6" width="14" height="12" rx="2"/>',
  settings: '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
  menu: '<line x1="4" x2="20" y1="6" y2="6"/><line x1="4" x2="20" y1="12" y2="12"/><line x1="4" x2="20" y1="18" y2="18"/>',
  x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  film: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M7 3v18"/><path d="M3 7.5h4"/><path d="M3 12h18"/><path d="M3 16.5h4"/><path d="M17 3v18"/><path d="M17 7.5h4"/><path d="M17 16.5h4"/>',
  cctv: '<path d="M16.75 12h3.632a1 1 0 0 1 .894 1.447l-2.034 4.069a1 1 0 0 1-1.708.134l-2.124-2.97"/><path d="M17.106 9.053a1 1 0 0 1 .447 1.341l-3.106 6.211a1 1 0 0 1-1.342.447L3.61 12.3a2.92 2.92 0 0 1-1.3-3.91L3.69 5.6a2.92 2.92 0 0 1 3.92-1.3z"/><path d="M2 19h3.76a2 2 0 0 0 1.8-1.1L9 15"/><path d="M2 21v-4"/><path d="M7 9h.01"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>',
  radio: '<path d="M4.9 19.1C1 15.2 1 8.8 4.9 4.9"/><path d="M7.8 16.2c-2.3-2.3-2.3-6.1 0-8.5"/><circle cx="12" cy="12" r="2"/><path d="M16.2 7.8c2.3 2.3 2.3 6.1 0 8.5"/><path d="M19.1 4.9C23 8.8 23 15.1 19.1 19"/>',
  camera: '<path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"/><circle cx="12" cy="13" r="3"/>',
  play: '<polygon points="6 3 20 12 6 21 6 3"/>',
  stop: '<circle cx="12" cy="12" r="10"/><rect x="9" y="9" width="6" height="6" rx="1"/>',
  trash: '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><line x1="10" x2="10" y1="11" y2="17"/><line x1="14" x2="14" y1="11" y2="17"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  eye: '<path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>',
  refresh: '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
  arrow: '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
  user: '<circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 0 0-16 0"/>',
  alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  phone: '<rect width="14" height="20" x="5" y="2" rx="2" ry="2"/><path d="M12 18h.01"/>',
  reset: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
  save: '<path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7"/><path d="M7 3v4a1 1 0 0 0 1 1h7"/>',
  archive: '<rect width="20" height="5" x="2" y="3" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"/><path d="M10 12h4"/>',
  fileDown: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M12 18v-6"/><path d="m9 15 3 3 3-3"/>',
};
const ic = (n, s = 16, cls = "") =>
  `<svg class="ic ${cls}" width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[n] || ""}</svg>`;
function paintIcons(root = document) {
  $$("[data-ic]", root).forEach((el) => {
    if (el.dataset.painted) return;
    el.insertAdjacentHTML("afterbegin", ic(el.dataset.ic, +el.dataset.s || 16));
    el.dataset.painted = "1";
  });
}

/* ==================================================================== api */
const api = {
  async get(url) {
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) throw new Error(`Request failed (${r.status})`);
    return r.json();
  },
  async post(url, data) {
    const r = await fetch(url, { method: "POST", body: JSON.stringify(data || {}),
      headers: { "X-Requested-With": "dashboard", "Content-Type": "application/json" } });
    let j = {};
    try { j = await r.json(); } catch (e) { /* empty body */ }
    if (!r.ok || j.error) throw new Error(j.error || `Request failed (${r.status})`);
    return j;
  },
};
const VIDEO_EXT = [".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"];
function uploadVideo(file, onProgress) {
  return new Promise((resolve, reject) => {
    if (!VIDEO_EXT.some((x) => file.name.toLowerCase().endsWith(x))) {
      reject(new Error("Please choose a video file (mp4, mov, avi, mkv, webm)."));
      return;
    }
    const x = new XMLHttpRequest();
    x.open("POST", "/api/videos");
    x.setRequestHeader("X-Requested-With", "dashboard");
    x.setRequestHeader("X-Filename", encodeURIComponent(file.name));
    x.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded / e.total); };
    x.onload = () => {
      let j = {};
      try { j = JSON.parse(x.responseText); } catch (e) { /* not json */ }
      if (x.status === 200 && !j.error) resolve(j); else reject(new Error(j.error || "Upload failed"));
    };
    x.onerror = () => reject(new Error("Upload failed - is the dashboard still running?"));
    x.send(file);
  });
}

/* ================================================================= format */
const fmtTime = (sec) => {
  if (sec == null || Number.isNaN(+sec)) return "-";
  const m = Math.floor(sec / 60);
  return `${String(m).padStart(2, "0")}:${(sec % 60).toFixed(1).padStart(4, "0")}`;
};
const fmtPct = (v) => (v == null ? "-" : `${Math.round(v * 100)}%`);
const fmtBytes = (b) => {
  if (!b) return "0 B";
  const u = ["B", "KB", "MB", "GB"], i = Math.min(u.length - 1, Math.floor(Math.log(b) / Math.log(1024)));
  return `${(b / 1024 ** i).toFixed(i ? 1 : 0)} ${u[i]}`;
};
const clockOf = (s) => (s ? String(s).slice(11) : "-");

/* ================================================================== state */
const S = { jobs: [], events: [], connected: true, seen: null, watchJob: null, page: null, eventsSig: "" };
const jobById = (id) => S.jobs.find((j) => j.id === +id);
const jobLabel = (j) => `#${j.id} · ${j.is_live ? "CCTV" : "Video"} · ${j.source_name}`;
const isBusy = (j) => j && (j.status === "running" || j.status === "queued");

/* ============================================================= components */
const has = (e, f) => e.files.includes(f);
const evUrl = (e, f, dl) => `/api/jobs/${e.job_id}/events/${encodeURIComponent(e.folder)}/${f}?v=${e.mtime}${dl ? "&download=1" : ""}`;

function pageHead(title, sub, actions = "") {
  return `<div class="page-head"><div><h1>${esc(title)}</h1>${sub ? `<p>${esc(sub)}</p>` : ""}</div><div class="actions">${actions}</div></div>`;
}
function cardBox(title, body, { actions = "", pad = true, cls = "", id = "" } = {}) {
  return `<section class="card ${cls}" ${id ? `id="${id}"` : ""}>
    ${title || actions ? `<div class="card-head"><h2>${esc(title)}</h2><div class="row">${actions}</div></div>` : ""}
    <div class="${pad ? "card-body" : ""}">${body}</div></section>`;
}
const badge = (status, text) => `<span class="badge st-${esc(status)}">${esc(text ?? status)}</span>`;
const srcBadge = (live) => (live ? `<span class="badge b-live">${ic("radio", 11)}CCTV</span>` : `<span class="badge b-video">${ic("film", 11)}Video</span>`);
const progress = (v, style = "") => `<div class="progress" style="${style}"><div style="width:${Math.round((v || 0) * 100)}%"></div></div>`;
const emptyBox = (icon, title, text = "") =>
  `<div class="empty">${ic(icon, 40)}<div class="empty-title">${esc(title)}</div>${text ? `<div class="empty-text">${text}</div>` : ""}</div>`;
const statCard = (icon, tone, label, value, hint) =>
  `<div class="card stat"><div class="stat-ic t-${tone}">${ic(icon, 22)}</div><div class="truncate">
    <div class="stat-label">${esc(label)}</div><div class="stat-value">${esc(value ?? "-")}</div>
    ${hint ? `<div class="stat-hint">${esc(hint)}</div>` : ""}</div></div>`;

function photo(e, role, kind = "face", size = "s-28") {
  const face = role === "suspect" ? "suspect_face.jpg" : "victim_face.jpg";
  const body = role === "suspect" ? "suspect_body.jpg" : "victim.jpg";
  const file = kind === "face" ? (has(e, face) ? face : has(e, body) ? body : null) : has(e, body) ? body : null;
  const ring = role === "suspect" ? "r-rose" : "r-amber";
  const id = role === "suspect" ? e.suspect_id : e.victim_id;
  if (!file) return `<div class="ph none ${ring} ${size}" title="No photo captured">${ic("user", size === "s-28" ? 48 : 20)}</div>`;
  return `<button type="button" class="ph ${ring} ${size}" data-open="${esc(e.id)}" title="Open">
    <img src="${evUrl(e, file)}" alt="${role} ID ${esc(id)}" class="${kind === "face" ? "cover" : "contain"}" loading="lazy"></button>`;
}
function pair(e, size = "s-28") {
  return `<div class="pair">
    <figure>${photo(e, "suspect", "face", size)}<figcaption class="rose">Suspect · ID ${esc(e.suspect_id)}</figcaption></figure>
    <div class="arrow"><span>snatched from</span>${ic("arrow", 24)}</div>
    <figure>${photo(e, "victim", "face", size)}<figcaption class="amber">Victim · ID ${esc(e.victim_id)}</figcaption></figure>
  </div>`;
}
function confBar(v) {
  const color = v >= 0.8 ? "var(--rose-500)" : v >= 0.65 ? "var(--amber-500)" : "var(--sky-500)";
  return `<div class="conf"><div class="bar"><div style="width:${fmtPct(v)};background:${color}"></div></div><span class="semibold tabular">${fmtPct(v)}</span></div>`;
}
function evidenceLines(e) {
  const v = e.evidence || {}, out = [];
  if (v.flee >= 0.3) out.push(`ID ${e.suspect_id} ran away after the contact`);
  if (v.reaction >= 0.3) out.push(`ID ${e.victim_id} reacted (jumped up, reached out or chased)`);
  if (v.had_phone > 0) out.push(`ID ${e.victim_id} was holding a phone before the contact`);
  if (v.transfer > 0) out.push(`The phone was seen moving to ID ${e.suspect_id}`);
  if (!out.length) out.push("Hand contact followed by a fast exit");
  return out;
}
function evidenceTags(e) {
  const v = e.evidence || {};
  const tag = (on, text) => (on ? `<span class="badge" style="background:var(--violet-50);color:var(--violet-700);text-transform:none">${text}</span>` : "");
  return tag(v.flee >= 0.3, "Ran away") + tag(v.reaction >= 0.3, "Victim reacted") + tag(v.had_phone > 0, "Had phone")
    + tag(v.transfer > 0, "Phone moved") || `<span class="xs faint">contact + fast exit</span>`;
}
const alertAfter = (e) => `${Math.max(0, (+e.alert_time || 0) - (+e.contact_time || 0)).toFixed(1)}s`;
const eventAt = (e) => (e.is_live ? clockOf(e.captured_at) : fmtTime(e.video_time));

/* ================================================================ actions */
function flash(text) {
  const el = document.createElement("div");
  el.className = "flash";
  el.textContent = text;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 2800);
}
async function review(e, status, notes) {
  try {
    await api.post("/api/events/review", { job_id: e.job_id, folder: e.folder, status, notes });
    e.status = status;
    if (notes != null) e.notes = notes;
    S.eventsSig = "";
    S.page?.update?.(true);
    updateBadge();
  } catch (err) { flash(err.message); }
}
const toggleReview = (e, status) => review(e, e.status === status ? "new" : status);

/* ================================================================= modal */
function closeModal() { $("#modal").innerHTML = ""; document.removeEventListener("keydown", escClose); }
function escClose(ev) { if (ev.key === "Escape") closeModal(); }
function openEvent(id) {
  const e = S.events.find((x) => x.id === id);
  if (!e) return;
  const job = jobById(e.job_id);
  const v = e.evidence || {};
  const fullVideo = job && job.has_output;
  const shots = [["suspect_face.jpg", "Suspect"], ["suspect_face_2.jpg", "Suspect 2"], ["suspect_face_3.jpg", "Suspect 3"],
    ["suspect_face_4.jpg", "Suspect 4"], ["victim_face.jpg", "Victim"], ["suspect_body.jpg", "Suspect body"],
    ["victim.jpg", "Victim body"], ["alert_frame.jpg", "Alert frame"]].filter(([f]) => has(e, f));
  const rows = [
    ["Ran away", fmtPct(v.flee), `Peak ${v.peak_speed ?? "-"} body heights/s, moved ${v.flee_dist ?? "-"} body heights from the contact point`],
    ["Victim reaction", fmtPct(v.reaction), `Speed burst ${fmtPct(v.burst)} · stood up ${fmtPct(v.stand)} · reached out ${fmtPct(v.reach)}`],
    ["Victim was holding a phone", fmtPct(v.had_phone), "Share of the 3 s before the contact with a phone at the victim's wrist"],
    ["Phone changed hands", fmtPct(v.transfer), "Phone seen at the suspect's wrist after the contact, or gone from the victim"],
    ["Captured", esc(e.captured_at), e.location ? `Location: ${esc(e.location)}` : "Clock time of the alert"],
  ];
  $("#modal").innerHTML = `
  <div class="modal" id="modalBg"><div class="card modal-card" role="dialog" aria-modal="true">
    <div class="modal-head"><h3>Event #${e.number} · ID ${esc(e.suspect_id)} snatched from ID ${esc(e.victim_id)}</h3>
      <button class="modal-x" data-close aria-label="Close">&times;</button></div>
    <div class="p-5 grid g-modal">
      <div class="grid" style="gap:16px;align-content:start">
        ${fullVideo ? `<video id="mVideo" src="/api/jobs/${e.job_id}/video" controls></video>`
          : has(e, "clip.mp4") ? `<video src="${evUrl(e, "clip.mp4")}" controls></video>`
          : has(e, "alert_frame.jpg") ? `<img class="snap" src="${evUrl(e, "alert_frame.jpg")}" alt="alert frame">` : ""}
        ${fullVideo && has(e, "clip.mp4") ? `<details><summary>Clip of the snatch</summary><video class="mt-2" src="${evUrl(e, "clip.mp4")}" controls preload="none"></video></details>` : ""}
        ${has(e, "alert_frame.jpg") && (fullVideo || has(e, "clip.mp4")) ? `<details><summary>Alert frame (suspect outlined in red)</summary><img class="snap mt-2" src="${evUrl(e, "alert_frame.jpg")}" alt="alert frame"></details>` : ""}
        <div><div class="label">All captured photos</div><div class="strip">
          ${shots.map(([f, cap]) => `<a href="${evUrl(e, f)}" target="_blank" rel="noopener" title="${cap}"><img src="${evUrl(e, f)}" alt="${cap}"></a>`).join("")}</div></div>
        <div class="row wrap">
          <a class="btn btn-ghost sm" href="${evUrl(e, "package.zip")}">${ic("archive")} Photos &amp; clip (.zip)</a>
          ${has(e, "clip.mp4") ? `<a class="btn btn-ghost sm" href="${evUrl(e, "clip.mp4", true)}">${ic("download")} Clip</a>` : ""}
          ${fullVideo ? `<a class="btn btn-ghost sm" href="/api/jobs/${e.job_id}/video?download=1">${ic("fileDown")} Scanned video</a>` : ""}
        </div>
      </div>
      <div>
        <div class="boxed">
          ${pair(e, "s-28")}
          ${has(e, "suspect_body.jpg") || has(e, "victim.jpg") ? `<div class="grid g-2 mt-4" style="gap:12px">
            ${photo(e, "suspect", "person", "s-body")}${photo(e, "victim", "person", "s-body")}</div>` : ""}
          <div class="xs muted mt-2">Clearest pictures captured while the two people were tracked · ${esc(e.source_name)}${e.location ? ` · ${esc(e.location)}` : ""}</div>
        </div>
        <div class="grid mb-4" style="grid-template-columns:repeat(3,minmax(0,1fr));gap:12px">
          <div class="mini"><small>Confidence</small><b>${fmtPct(e.score)}</b></div>
          <div class="mini"><small>Alert after</small><b>${alertAfter(e)}</b></div>
          <div class="mini"><small>Window</small><b>${fmtTime(e.contact_time)}–${fmtTime(e.alert_time)}</b></div>
        </div>
        <div class="label">Snatch evidence</div>
        <table class="mb-4"><tbody>${rows.map(([k, val, hint]) => `<tr><td class="td"><div class="semibold">${k}</div><div class="xs faint">${hint}</div></td><td class="td right semibold tabular">${val}</td></tr>`).join("")}</tbody></table>
        <div class="note-amber mb-4">This is a detected movement pattern, not proof of theft. Verify the footage before taking any action.</div>
        <label class="label" for="mNotes">Operator notes</label>
        <textarea class="input" id="mNotes" placeholder="e.g. victim confirmed, reported to station police">${esc(e.notes || "")}</textarea>
        <div class="row wrap mt-3">
          <button class="btn btn-danger" data-save="confirmed">${ic("check")} Confirm theft</button>
          <button class="btn btn-primary" data-save="reviewed">Mark reviewed</button>
          <button class="btn btn-ghost" data-save="dismissed">${ic("x")} Dismiss</button>
        </div>
        <div class="xs faint mt-3">Status: ${esc(e.status)} · analysis #${e.job_id}${e.reviewed_at ? ` · reviewed ${esc(e.reviewed_at)}` : ""}</div>
      </div>
    </div>
  </div></div>`;
  const bg = $("#modalBg");
  bg.addEventListener("click", (ev) => {
    if (ev.target === bg || ev.target.closest("[data-close]")) return closeModal();
    const save = ev.target.closest("[data-save]");
    if (save) review(e, save.dataset.save, $("#mNotes").value).then(closeModal);
  });
  const vid = $("#mVideo");
  if (vid) vid.addEventListener("loadedmetadata", () => { vid.currentTime = Math.max(0, (+e.contact_time || 0) - 1.5); }, { once: true });
  document.addEventListener("keydown", escClose);
}

/* ================================================================= toasts */
function toast(e) {
  const t = document.createElement("div");
  t.className = "card toast";
  t.innerHTML = `${ic("alert", 20)}<button class="toast-body"><div class="toast-title">Phone snatching detected</div>
    <div class="sm" style="color:var(--slate-600)">ID ${esc(e.suspect_id)} snatched from ID ${esc(e.victim_id)} · ${fmtPct(e.score)} · ${esc(e.source_name)}</div>
    <div class="xs faint mt-1">Analysis #${e.job_id} · click to review</div></button>
    <button class="icon-btn" aria-label="Dismiss">${ic("x", 16)}</button>`;
  t.querySelector(".toast-body").onclick = () => { t.remove(); location.hash = `#/watch?job=${e.job_id}&event=${encodeURIComponent(e.id)}`; };
  t.querySelector(".icon-btn").onclick = () => t.remove();
  $("#toasts").prepend(t);
  setTimeout(() => t.remove(), 15000);
}

/* ================================================================= pages */
const Overview = {
  mount(el) {
    this.el = el;
    this.sig = "";
    el.innerHTML = pageHead("Overview", "Phone snatching at your stations at a glance",
      `<a class="btn btn-primary" href="#/watch">${ic("scan")} Snatch Watch</a>
       <a class="btn btn-ghost" href="#/videos">${ic("video")} Analyse a video</a>
       <a class="btn btn-ghost" href="#/monitor">${ic("monitorPlay")} Live monitoring</a>`) + `<div id="ovBody"></div>`;
    this.update();
  },
  async update() {
    let d;
    try { d = await api.get("/api/overview"); } catch (e) { return; }
    const sig = JSON.stringify(d);
    if (sig === this.sig) return;
    this.sig = sig;
    const alerts = d.recent_events.length ? `<div class="table-wrap"><table>
      <thead><tr><th class="th">Event</th><th class="th">Suspect → victim</th><th class="th">Source</th><th class="th">At</th><th class="th">Confidence</th><th class="th">Status</th></tr></thead>
      <tbody>${d.recent_events.map((e) => `<tr class="hover">
        <td class="td semibold">#${e.number} <span class="faint">job ${e.job_id}</span></td>
        <td class="td"><div class="row">${photo(e, "suspect", "face", "s-9")}<span class="xs nowrap">ID ${esc(e.suspect_id)}</span><span class="faint">→</span>${photo(e, "victim", "face", "s-9")}<span class="xs nowrap">ID ${esc(e.victim_id)}</span></div></td>
        <td class="td"><div class="truncate" style="max-width:220px">${esc(e.source_name)}</div></td>
        <td class="td tabular">${eventAt(e)}</td><td class="td semibold">${fmtPct(e.score)}</td><td class="td">${badge(e.status)}</td></tr>`).join("")}</tbody></table></div>`
      : emptyBox("alert", "No snatch alerts yet", "Upload a video or connect a camera to start.");
    const jobs = d.recent_jobs.length ? `<ul class="feed">${d.recent_jobs.map((j) => `<li onclick="location.hash='#/monitor?job=${j.id}'">
        <div class="grow"><div class="sm semibold truncate">#${j.id} · ${esc(j.source_name)}</div>
        <div class="xs muted">${esc(j.created_at)} · ${j.event_count} snatch${j.event_count === 1 ? "" : "es"}</div></div>${badge(j.status)}</li>`).join("")}</ul>`
      : emptyBox("video", "No analyses yet");
    $("#ovBody", this.el).innerHTML = `
      <div class="grid g-stats">
        ${statCard("siren", "rose", "Snatches detected", d.events, `${d.unreviewed} awaiting review`)}
        ${statCard("scan", "brand", "Suspect faces captured", d.faces, `${d.confirmed} confirmed as theft`)}
        ${statCard("video", "sky", "Analyses completed", d.jobs_completed, `${d.videos} videos · ${d.cameras} cameras`)}
        ${statCard("monitorPlay", "green", "Running now", d.jobs_running, `${d.running_jobs.length - d.jobs_running} waiting in the queue`)}
      </div>
      ${d.running_jobs.length ? cardBox("Processing now", d.running_jobs.map((j) => `<div class="row wrap mb-3" style="gap:16px">
          <div style="min-width:220px"><div class="semibold">#${j.id} · ${esc(j.source_name)}</div>
          <div class="xs muted">${j.status === "queued" ? "waiting in the queue" : `${j.people ?? 0} people in view · ${j.event_count} snatch alerts · ${j.speed ?? 0} fps`}</div></div>
          <div class="grow" style="min-width:160px">${j.is_live ? `<span class="badge b-live">LIVE</span>` : progress(j.progress)}</div>
          <a class="btn btn-ghost" href="#/monitor?job=${j.id}">Watch</a></div>`).join(""), { cls: "mt-6" }) : ""}
      <div class="grid g-3-1 mt-6">
        ${cardBox("Recent snatch alerts", alerts, { pad: false, actions: `<a class="link" href="#/watch?job=all">View all</a>` })}
        ${cardBox("Recent analyses", jobs, { pad: false, actions: `<a class="link" href="#/videos">Videos</a>` })}
      </div>`;
  },
};

const Watch = {
  mount(el, params) {
    this.el = el;
    this.sig = "";
    this.camSig = "";
    if (params.job === "all") S.watchJob = "";
    else if (params.job) S.watchJob = String(params.job);
    el.innerHTML = pageHead("Snatch Watch", "Who snatched whose phone — photos are captured automatically from saved videos and live CCTV") + `
      <div class="grid g-2">
        <section class="card p-5">
          <div class="opt-head"><div class="opt-ic t-brand">${ic("film", 22)}</div><div>
            <div class="opt-step">Option 1</div><h2 class="opt-title">Saved video</h2>
            <p class="opt-hint">Upload recorded footage. It is analysed in the background; results and photos appear below.</p></div></div>
          <div class="drop" id="drop" role="button" tabindex="0">${ic("upload", 28)}
            <div class="drop-title">Drop a video here or click to browse</div><div class="xs muted">MP4, MOV, AVI, MKV</div></div>
          <input type="file" id="file" accept="video/*,.mov,.mkv" hidden>
          <div class="row mt-3" id="upRow" hidden><span class="sm truncate grow" id="upName"></span>${progress(0, "width:128px")}<span class="sm tabular" id="upPct" style="width:40px;text-align:right"></span></div>
          <div class="sm rose mt-3" id="upErr" hidden></div>
          <div class="sm mt-3"><a class="link" href="#/videos">All uploaded videos →</a></div>
        </section>
        <section class="card p-5">
          <div class="opt-head"><div class="opt-ic t-rose">${ic("cctv", 22)}</div><div>
            <div class="opt-step">Option 2</div><h2 class="opt-title">CCTV live</h2>
            <p class="opt-hint">Connect a camera stream. It is analysed in real time and alerts pop up as they happen.</p></div></div>
          <ul class="cams" id="camList" hidden></ul>
          <form id="camForm" autocomplete="off">
            <div class="form-grid">
              <input class="input" id="camName" placeholder="Camera name (e.g. Platform 2 - CAM 03)" maxlength="60" aria-label="Camera name">
              <input class="input" id="camLoc" placeholder="Location (optional)" maxlength="60" aria-label="Location">
            </div>
            <div class="form-row">
              <input class="input" id="camUrl" required placeholder="rtsp://user:pass@192.168.1.20:554/stream1  (or 0 for this PC's camera)" aria-label="Stream address">
              <button class="btn btn-danger" id="camBtn">${ic("radio")} Connect &amp; start</button>
            </div>
          </form>
          <div class="sm rose mt-2" id="camErr" hidden></div>
        </section>
      </div>
      <div class="card filters mt-6 mb-5">
        <div><label class="label" for="wJob">Source</label><select class="input" id="wJob"></select></div>
        <label class="check"><input type="checkbox" id="wNow"> Happening now only</label>
        <label class="check"><input type="checkbox" id="wHide" checked> Hide dismissed</label>
        <div class="count" id="wCount"></div>
      </div>
      <div id="wBody"></div>`;

    const drop = $("#drop", el), file = $("#file", el);
    drop.onclick = () => { if (!this.uploading) file.click(); };
    drop.onkeydown = (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); drop.click(); } };
    drop.ondragover = (ev) => { ev.preventDefault(); drop.classList.add("over"); };
    drop.ondragleave = () => drop.classList.remove("over");
    drop.ondrop = (ev) => { ev.preventDefault(); drop.classList.remove("over"); this.upload(ev.dataTransfer.files[0]); };
    file.onchange = (ev) => { this.upload(ev.target.files[0]); ev.target.value = ""; };
    $("#camForm", el).onsubmit = (ev) => { ev.preventDefault(); this.connect(); };
    $("#camList", el).onclick = (ev) => this.camAction(ev);
    $("#wJob", el).onchange = (ev) => { S.watchJob = ev.target.value; this.sig = ""; this.update(); };
    $("#wNow", el).onchange = $("#wHide", el).onchange = () => { this.sig = ""; this.update(); };
    $("#wBody", el).onclick = (ev) => {
      const b = ev.target.closest("[data-review]");
      if (b) { const e = S.events.find((x) => x.id === b.dataset.id); if (e) toggleReview(e, b.dataset.review); }
    };
    this.update();
  },
  async upload(f) {
    if (!f) return;
    const row = $("#upRow", this.el), err = $("#upErr", this.el);
    err.hidden = true;
    row.hidden = false;
    $("#upName", this.el).textContent = f.name;
    this.uploading = true;
    const set = (p) => { $("#upRow .progress div", this.el).style.width = `${Math.round(p * 100)}%`; $("#upPct", this.el).textContent = `${Math.round(p * 100)}%`; };
    set(0);
    try {
      const video = await uploadVideo(f, set);
      S.watchJob = String(video.latest_job.id);
      location.hash = `#/monitor?job=${video.latest_job.id}`;
    } catch (e) {
      err.textContent = e.message;
      err.hidden = false;
    }
    this.uploading = false;
    row.hidden = true;
  },
  async connect() {
    const err = $("#camErr", this.el), btn = $("#camBtn", this.el);
    err.hidden = true;
    btn.disabled = true;
    try {
      const job = await api.post("/api/cameras", { name: $("#camName", this.el).value.trim(),
        location: $("#camLoc", this.el).value.trim(), source_url: $("#camUrl", this.el).value.trim() });
      S.watchJob = String(job.id);
      location.hash = `#/monitor?job=${job.id}`;
    } catch (e) {
      err.textContent = e.message;
      err.hidden = false;
    }
    btn.disabled = false;
  },
  async camAction(ev) {
    const b = ev.target.closest("[data-cam]");
    if (!b) return;
    const { cam, act, job } = b.dataset;
    try {
      if (act === "start") { const j = await api.post(`/api/cameras/${cam}/start`); location.hash = `#/monitor?job=${j.id}`; return; }
      if (act === "stop") await api.post(`/api/jobs/${job}/stop`);
      if (act === "delete") { if (!confirm("Remove this camera?")) return; await api.post(`/api/cameras/${cam}/delete`); }
      this.camSig = "";
      this.update();
    } catch (e) { flash(e.message); }
  },
  async update() {
    const el = this.el;
    // cameras
    try {
      const cams = await api.get("/api/cameras");
      const sig = JSON.stringify(cams);
      if (sig !== this.camSig) {
        this.camSig = sig;
        const list = $("#camList", el);
        list.hidden = !cams.length;
        list.innerHTML = cams.map((c) => `<li>${ic("camera", 17, "faint")}
          <div class="grow"><div class="sm semibold truncate">${esc(c.name)}${c.location ? `<span class="faint"> · ${esc(c.location)}</span>` : ""}</div>
          <div class="xs muted truncate">${esc(c.source)}</div></div>
          ${c.live_job_id ? `<a href="#/monitor?job=${c.live_job_id}"><span class="badge b-live">${ic("radio", 12)}LIVE</span></a>
            <button class="btn btn-ghost icon" title="Stop" data-cam="${c.id}" data-act="stop" data-job="${c.live_job_id}">${ic("stop", 15)}</button>`
            : `<button class="btn btn-primary sm" data-cam="${c.id}" data-act="start">${ic("play", 14)} Start</button>
            <button class="icon-btn" title="Remove" data-cam="${c.id}" data-act="delete">${ic("trash", 15)}</button>`}</li>`).join("");
      }
    } catch (e) { /* offline: keep the last list */ }

    // source filter: newest analysis by default, so a new scan never shows old results
    const sel = $("#wJob", el);
    if (S.watchJob === null && S.jobs.length) S.watchJob = String(S.jobs[0].id);
    if (S.watchJob && !jobById(S.watchJob)) S.watchJob = S.jobs.length ? String(S.jobs[0].id) : "";
    const opts = `<option value="">All videos and cameras</option>` + S.jobs.map((j) => `<option value="${j.id}">${esc(jobLabel(j))}</option>`).join("");
    if (sel.dataset.opts !== opts) { sel.innerHTML = opts; sel.dataset.opts = opts; }
    sel.value = S.watchJob || "";

    const nowOnly = $("#wNow", el).checked, hide = $("#wHide", el).checked;
    const shown = S.events.filter((e) => (!S.watchJob || e.job_id === +S.watchJob) && (!nowOnly || e.is_active) && (!hide || e.status !== "dismissed"));
    const sig = JSON.stringify([shown, S.watchJob, S.jobs.map((j) => [j.id, j.status, j.has_output])]);
    if (sig === this.sig) return;
    this.sig = sig;
    const active = shown.filter((e) => e.is_active), past = shown.filter((e) => !e.is_active);
    $("#wCount", el).innerHTML = `${shown.length} detection${shown.length === 1 ? "" : "s"} · <b>${active.length} happening now</b>`;
    const job = S.watchJob ? jobById(S.watchJob) : null;
    let body = "";
    if (job && isBusy(job)) {
      body += `<div class="card p-4 mb-5 row wrap" style="gap:16px">${badge(job.status)}<span class="sm semibold truncate">${esc(job.source_name)}</span>
        ${job.is_live ? `<span class="badge b-live">LIVE</span>` : `<div class="grow" style="min-width:140px">${progress(job.progress)}</div><span class="sm tabular">${Math.round(job.progress * 100)}%</span>`}
        <a class="link ml-auto" href="#/monitor?job=${job.id}">Watch live →</a></div>`;
    }
    if (active.length) body += `<section class="mb-8"><h2 class="sec-title"><span class="dot live"></span> Happening now</h2><div class="grid g-cards">${active.map((e) => this.card(e)).join("")}</div></section>`;
    if (past.length) body += `<section><h2 class="sec-title">Detected</h2><div class="grid g-cards">${past.map((e) => this.card(e)).join("")}</div></section>`;
    if (!shown.length) {
      body += `<div class="card">${emptyBox("phone", job && isBusy(job) ? "Analysing… no snatch detected so far" : "No phone snatching detected",
        job && !isBusy(job) ? `Nothing was found in <b>${esc(job.source_name)}</b>. Choose another source above, or upload a video / connect a camera.`
          : "Upload a saved video or connect a CCTV camera above. When someone grabs a phone and runs, both people's photos appear here.")}</div>`;
    }
    $("#wBody", el).innerHTML = body;
  },
  card(e) {
    const job = jobById(e.job_id);
    return `<article class="card det ${e.is_active ? "active" : ""} ${e.status === "dismissed" ? "dismissed" : ""}">
      <div class="det-head">${srcBadge(e.is_live)}<span class="truncate grow" title="${esc(e.source_name)}">${esc(e.source_name)}${e.location ? ` · ${esc(e.location)}` : ""}</span>${badge(e.status)}</div>
      ${pair(e)}
      <div class="metrics">
        <div class="metric"><small>Confidence</small><b class="strong">${fmtPct(e.score)}</b></div>
        <div class="metric"><small>Alert after</small><b>${alertAfter(e)}</b></div>
        <div class="metric"><small>At</small><b>${eventAt(e)}</b></div>
      </div>
      <ul class="notes">${evidenceLines(e).map((n) => `<li>${esc(n)}</li>`).join("")}</ul>
      <div class="det-foot">
        <button class="btn btn-ghost sm" data-open="${esc(e.id)}">${ic("eye", 15)} Inspect</button>
        <button class="btn btn-ghost icon-md ${e.status === "confirmed" ? "on-ok" : ""}" title="Confirm theft" data-review="confirmed" data-id="${esc(e.id)}">${ic("check", 15)}</button>
        <button class="btn btn-ghost icon-md ${e.status === "dismissed" ? "on-no" : ""}" title="Dismiss (false alarm)" data-review="dismissed" data-id="${esc(e.id)}">${ic("x", 15)}</button>
        <a class="link ml-auto" href="#/monitor?job=${e.job_id}&t=${Math.max(0, (+e.contact_time || 0) - 1.5).toFixed(1)}">${e.is_active ? "Watch live →" : job && job.has_output ? "Open video →" : "Open analysis →"}</a>
      </div></article>`;
  },
};

const Monitor = {
  mount(el, params) {
    this.el = el;
    this.key = "";
    this.feedSig = "";
    this.seek = params.t != null ? +params.t : null;
    this.jobId = +params.job || null;
    el.innerHTML = pageHead("Live Monitoring", "Annotated video with tracking IDs, phones, the suspect and the victim",
      `<select class="input" id="mJob" aria-label="Analysis"></select>`) + `
      <div class="grid g-monitor">
        <section class="card" style="overflow:hidden;align-self:start"><div class="screen" id="mScreen"></div><div class="screen-bar" id="mBar" hidden></div></section>
        <div class="grid" style="gap:24px;align-content:start">
          ${cardBox("Live status", `<dl class="dl-grid" id="mStats"></dl>`)}
          ${cardBox("Detections", `<ul class="feed" id="mFeed"></ul><div class="card-foot" id="mFoot"></div>`, { pad: false })}
        </div>
      </div>`;
    $("#mJob", el).onchange = (ev) => {
      this.jobId = +ev.target.value;
      this.seek = null;
      history.replaceState(null, "", `#/monitor?job=${this.jobId}`);
      this.update();
    };
    $("#mBar", el).onclick = async (ev) => {
      const b = ev.target.closest("[data-stop]");
      if (!b) return;
      b.disabled = true;
      try { await api.post(`/api/jobs/${b.dataset.stop}/stop`); flash("Stopping…"); } catch (e) { flash(e.message); }
    };
    $("#mFeed", el).onclick = (ev) => { const li = ev.target.closest("[data-ev]"); if (li) openEvent(li.dataset.ev); };
    this.update();
  },
  update() {
    const el = this.el;
    if ((!this.jobId || !jobById(this.jobId)) && S.jobs.length) {
      const running = S.jobs.find((j) => j.status === "running");
      this.jobId = (running || S.jobs[0]).id;
    }
    const job = jobById(this.jobId);
    const sel = $("#mJob", el);
    const opts = S.jobs.length ? S.jobs.map((j) => `<option value="${j.id}">${esc(`${jobLabel(j)} · ${j.status}`)}</option>`).join("") : `<option value="">No analyses yet</option>`;
    if (sel.dataset.opts !== opts) { sel.innerHTML = opts; sel.dataset.opts = opts; }
    if (job) sel.value = String(job.id);

    // picture: rebuilt only when the job or its mode changes, so a playing video is not interrupted
    const mode = !job ? "none" : job.status === "queued" ? "queued" : job.status === "running" ? "live" : job.has_output ? "video" : "nooutput";
    const key = `${job ? job.id : 0}:${mode}`;
    const screen = $("#mScreen", el);
    if (key !== this.key) {
      this.key = key;
      if (mode === "none") screen.innerHTML = emptyBox("monitorPlay", "Nothing to show", "Upload a video or start a camera stream.");
      else if (mode === "queued") screen.innerHTML = `<div class="msg">Queued — waiting for the analysis in front of it to finish…</div>`;
      else if (mode === "live") screen.innerHTML = job.has_live ? `<img id="mLive" alt="live annotated picture" src="/api/jobs/${job.id}/live?t=${Date.now()}">` : `<div class="msg">Starting — loading the models…</div>`;
      else if (mode === "video") {
        screen.innerHTML = `<video id="mVid" src="/api/jobs/${job.id}/video" controls></video>`;
        const v = $("#mVid", el);
        if (this.seek != null) { const t = this.seek; v.addEventListener("loadedmetadata", () => { v.currentTime = t; }, { once: true }); this.seek = null; }
      } else screen.innerHTML = `<div class="msg">${job.status === "failed" ? `Analysis failed${job.error ? `: ${esc(job.error)}` : ""}` : job.is_live ? "Camera session ended. Clips of each detection are kept with the events." : "No annotated video for this analysis"}</div>`;
    } else if (mode === "live") {
      const img = $("#mLive", el);
      if (img) {
        const next = new Image();   // swap only once loaded: no flicker
        next.onload = () => { img.src = next.src; };
        next.src = `/api/jobs/${job.id}/live?t=${Date.now()}`;
      } else if (job.has_live) this.key = "";
    }

    const bar = $("#mBar", el);
    bar.hidden = !job;
    if (job) {
      const video = !job.is_live && job.video_id;
      bar.innerHTML = `${badge(job.status)}${job.is_live ? `<span class="badge b-live">${ic("radio", 12)} LIVE</span>` : ""}
        <span class="sm truncate" style="color:var(--slate-600);max-width:320px">${esc(job.source_name)}${job.location ? ` · ${esc(job.location)}` : ""}</span>
        ${job.status === "running" && !job.is_live ? `<div class="grow" style="min-width:120px">${progress(job.progress)}</div>` : ""}
        <div class="row ml-auto">
          ${isBusy(job) ? `<button class="btn btn-danger" data-stop="${job.id}">${ic("stop")} Stop</button>` : ""}
          ${job.has_output ? `<a class="btn btn-ghost" href="/api/jobs/${job.id}/video?download=1">${ic("download")} Scanned video</a>` : ""}
          ${video && !isBusy(job) ? `<a class="btn btn-ghost" href="/api/videos/${job.video_id}/file?download=1">${ic("fileDown")} Original</a>` : ""}
        </div>`;
    }

    const stat = (label, value) => `<div><dt>${label}</dt><dd>${value}</dd></div>`;
    $("#mStats", el).innerHTML = job ? [
      stat("Status", badge(job.status)),
      stat("Progress", job.is_live ? "live" : `${Math.round(job.progress * 100)}%`),
      stat("Frames", job.total ? `${job.frame}/${job.total}` : job.frame || "-"),
      stat("Processing", job.speed ? `${job.speed} fps` : "-"),
      stat("People in view", job.status === "running" ? job.people ?? "-" : "-"),
      stat("Snatch alerts", `<span class="${job.event_count ? "rose" : ""}">${job.event_count}</span>`),
    ].join("") : `<div class="sm muted">No analysis selected.</div>`;

    const evs = job ? S.events.filter((e) => e.job_id === job.id) : [];
    const sig = JSON.stringify([job && job.id, evs.map((e) => [e.id, e.status, e.mtime])]);
    if (sig !== this.feedSig) {
      this.feedSig = sig;
      $("#mFeed", el).innerHTML = evs.length ? evs.slice().reverse().map((e) => `<li data-ev="${esc(e.id)}">
          ${photo(e, "suspect", "face", "s-9")}<span class="faint">→</span>${photo(e, "victim", "face", "s-9")}
          <div class="grow"><div><span class="faint tabular">${eventAt(e)}</span> <span class="semibold rose">Snatch</span> · ID ${esc(e.suspect_id)} → ID ${esc(e.victim_id)}</div>
          <div class="xs muted">${evidenceLines(e)[0]}</div></div><span class="semibold tabular">${fmtPct(e.score)}</span></li>`).join("")
        : `<div class="sm muted" style="padding:24px 20px">Detections from this analysis appear here as they happen.</div>`;
      $("#mFoot", el).innerHTML = job ? `<a class="link" href="#/events?job=${job.id}">All events of analysis #${job.id} →</a>` : "";
    }
  },
};

const Events = {
  mount(el, params) {
    this.el = el;
    this.sig = "";
    el.innerHTML = pageHead("Snatch Events", "Every detected phone snatch. Review the footage before acting.",
      `<a class="btn btn-ghost" id="csv" href="/api/events.csv">${ic("download")} Export CSV</a>`) + `
      <div class="card filters mb-5">
        <div><label class="label" for="eJob">Analysis</label><select class="input" id="eJob"></select></div>
        <div><label class="label" for="eStatus">Review status</label><select class="input" id="eStatus" style="min-width:160px">
          ${["", "new", "confirmed", "reviewed", "dismissed"].map((s) => `<option value="${s}">${s || "Any"}</option>`).join("")}</select></div>
        <div style="min-width:200px"><label class="label" for="eMin">Min confidence: <span id="eMinV">0%</span></label>
          <input type="range" id="eMin" min="0" max="1" step="0.05" value="0" style="width:100%"></div>
      </div>
      <div class="card" id="eTable"></div>`;
    this.job = params.job || "";
    ["#eJob", "#eStatus", "#eMin"].forEach((s) => { $(s, el).oninput = () => { this.job = $("#eJob", el).value; this.sig = ""; this.update(); }; });
    $("#eTable", el).onclick = (ev) => {
      const b = ev.target.closest("[data-review]");
      if (b) { const e = S.events.find((x) => x.id === b.dataset.id); if (e) toggleReview(e, b.dataset.review); }
    };
    this.update();
  },
  update() {
    const el = this.el, sel = $("#eJob", el);
    const opts = `<option value="">All analyses</option>` + S.jobs.map((j) => `<option value="${j.id}">${esc(`#${j.id} · ${j.source_name}`)}</option>`).join("");
    if (sel.dataset.opts !== opts) { sel.innerHTML = opts; sel.dataset.opts = opts; }
    sel.value = this.job && jobById(this.job) ? this.job : "";
    const status = $("#eStatus", el).value, min = +$("#eMin", el).value;
    $("#eMinV", el).textContent = fmtPct(min);
    $("#csv", el).href = `/api/events.csv${sel.value ? `?job=${sel.value}` : ""}`;
    const list = S.events.filter((e) => (!sel.value || e.job_id === +sel.value) && (!status || e.status === status) && (e.score || 0) >= min);
    const sig = JSON.stringify(list.map((e) => [e.id, e.status, e.mtime, e.is_active]));
    if (sig === this.sig) return;
    this.sig = sig;
    $("#eTable", el).innerHTML = list.length ? `<div class="table-wrap"><table>
      <thead><tr><th class="th">Event</th><th class="th">Suspect → victim</th><th class="th">Source</th><th class="th">Detected at</th>
        <th class="th">Confidence</th><th class="th">Evidence</th><th class="th">Status</th><th class="th right">Actions</th></tr></thead>
      <tbody>${list.map((e) => `<tr class="hover">
        <td class="td semibold">#${e.number}<div class="xs faint">job ${e.job_id}${e.is_active ? `<span class="rose"> ● active</span>` : ""}</div></td>
        <td class="td"><div class="row">${photo(e, "suspect", "face", "s-11")}<span class="xs semibold rose nowrap">ID ${esc(e.suspect_id)}</span><span class="faint">→</span>
          ${photo(e, "victim", "face", "s-11")}<span class="xs semibold amber nowrap">ID ${esc(e.victim_id)}</span></div></td>
        <td class="td"><div class="row">${srcBadge(e.is_live)}<span class="truncate" style="max-width:160px" title="${esc(e.source_name)}">${esc(e.source_name)}</span></div></td>
        <td class="td tabular nowrap">${eventAt(e)}<div class="xs faint">${esc(e.captured_at)}</div></td>
        <td class="td nowrap">${confBar(e.score || 0)}</td>
        <td class="td"><div class="row wrap" style="gap:4px;min-width:180px">${evidenceTags(e)}</div></td>
        <td class="td">${badge(e.status)}</td>
        <td class="td right nowrap">
          <button class="btn btn-ghost icon" title="Inspect" data-open="${esc(e.id)}">${ic("eye", 15)}</button>
          <button class="btn btn-ghost icon ${e.status === "confirmed" ? "on-ok" : ""}" title="Confirm" data-review="confirmed" data-id="${esc(e.id)}">${ic("check", 15)}</button>
          <button class="btn btn-ghost icon ${e.status === "dismissed" ? "on-no" : ""}" title="Dismiss" data-review="dismissed" data-id="${esc(e.id)}">${ic("x", 15)}</button>
          <a class="btn btn-ghost icon" title="Download photos and clip" href="${evUrl(e, "package.zip")}">${ic("archive", 15)}</a>
        </td></tr>`).join("")}</tbody></table></div>`
      : emptyBox("siren", "No snatch events", "Nothing matches the filters.");
  },
};

const Videos = {
  mount(el) {
    this.el = el;
    this.sig = "";
    this.uploads = [];
    el.innerHTML = pageHead("Video Management", "Upload recorded footage, follow processing, download results and delete videos") + `
      <div class="card drop big mb-6" id="vDrop" role="button" tabindex="0">${ic("upload", 36)}
        <div class="drop-title" style="font-size:16px">Drop video files here or click to browse</div>
        <div class="sm muted">MP4, MOV, AVI, MKV · analysis starts automatically with the current settings</div></div>
      <input type="file" id="vFile" accept="video/*,.mov,.mkv" multiple hidden>
      <div id="vUploads"></div>
      <div class="card alert-box mb-4" id="vErr" hidden></div>
      <div id="vTables"></div>`;
    const drop = $("#vDrop", el), input = $("#vFile", el);
    drop.onclick = () => input.click();
    drop.onkeydown = (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); input.click(); } };
    drop.ondragover = (ev) => { ev.preventDefault(); drop.classList.add("over"); };
    drop.ondragleave = () => drop.classList.remove("over");
    drop.ondrop = (ev) => { ev.preventDefault(); drop.classList.remove("over"); this.handle([...ev.dataTransfer.files]); };
    input.onchange = (ev) => { this.handle([...ev.target.files]); ev.target.value = ""; };
    $("#vTables", el).onclick = (ev) => this.action(ev);
    this.update();
  },
  renderUploads() {
    $("#vUploads", this.el).innerHTML = this.uploads.map((u) => `<div class="card p-4 mb-3 row" style="gap:16px">
      <span class="sm semibold truncate" style="width:256px">${esc(u.name)}</span><div class="grow">${progress(u.p)}</div>
      <span class="sm tabular" style="width:48px;text-align:right">${Math.round(u.p * 100)}%</span></div>`).join("");
  },
  async handle(files) {
    const err = $("#vErr", this.el);
    err.hidden = true;
    for (const f of files) {
      const u = { name: f.name, p: 0 };
      this.uploads.push(u);
      this.renderUploads();
      try { await uploadVideo(f, (p) => { u.p = p; this.renderUploads(); }); } catch (e) { err.textContent = `${f.name}: ${e.message}`; err.hidden = false; }
      this.uploads = this.uploads.filter((x) => x !== u);
      this.renderUploads();
      this.sig = "";
      this.update();
    }
  },
  async action(ev) {
    const b = ev.target.closest("[data-act]");
    if (!b) return;
    const { act, id, name } = b.dataset;
    try {
      if (act === "analyse") { await api.post(`/api/videos/${id}/analyse`); flash("Analysis queued - it replaces the previous result of this video"); }
      if (act === "delvideo") {
        if (!confirm(`Delete "${name}" with its analysis, scanned video and all detections?`)) return;
        await api.post(`/api/videos/${id}/delete`);
        flash("Video deleted");
      }
      if (act === "stop") await api.post(`/api/jobs/${id}/stop`);
      if (act === "deljob") {
        if (!confirm(`Delete camera session #${id} with all its detections?`)) return;
        await api.post(`/api/jobs/${id}/delete`);
        flash("Session deleted");
      }
      this.sig = "";
      await poll();
    } catch (e) { flash(e.message); }
  },
  async update() {
    let videos;
    try { videos = await api.get("/api/videos"); } catch (e) { return; }
    const sessions = S.jobs.filter((j) => j.is_live);
    const sig = JSON.stringify([videos, sessions]);
    if (sig === this.sig) return;
    this.sig = sig;
    const vrows = videos.map((v) => {
      const j = v.latest_job, busy = isBusy(j);
      return `<tr class="hover">
        <td class="td"><div class="semibold row" style="color:var(--slate-800)">${ic("video", 16, "faint")}<span class="truncate" style="max-width:280px">${esc(v.name)}</span></div>
          <div class="xs faint">${fmtBytes(v.size)} · ${Math.round(v.fps)} fps</div></td>
        <td class="td tabular">${fmtTime(v.duration)}</td>
        <td class="td nowrap">${v.width}×${v.height}</td>
        <td class="td xs nowrap">${esc(v.uploaded_at)}</td>
        <td class="td" style="min-width:180px">${!j ? `<span class="faint sm">not analysed</span>` : busy
          ? `<div class="row xs mb-1" style="justify-content:space-between">${badge(j.status)}<span class="tabular">${Math.round(j.progress * 100)}%</span></div>${progress(j.progress)}`
          : `${badge(j.status)}${j.error ? `<div class="xs rose mt-1 truncate" style="max-width:220px" title="${esc(j.error)}">${esc(j.error)}</div>` : ""}`}</td>
        <td class="td xs" style="color:var(--slate-600)">${j && !busy ? `<span class="rose semibold">${j.event_count} snatch${j.event_count === 1 ? "" : "es"}</span>` : "—"}</td>
        <td class="td right nowrap">
          ${j ? `<a class="btn btn-ghost icon" title="Monitor" href="#/monitor?job=${j.id}">${ic("monitorPlay", 15)}</a>` : ""}
          ${j && j.has_output ? `<a class="btn btn-ghost icon" title="Download scanned video" href="/api/jobs/${j.id}/video?download=1">${ic("download", 15)}</a>` : ""}
          <a class="btn btn-ghost icon" title="Download original video" href="/api/videos/${v.id}/file?download=1">${ic("fileDown", 15)}</a>
          <button class="btn btn-ghost icon" title="Analyse again with current settings" ${busy ? "disabled" : ""} data-act="analyse" data-id="${v.id}">${ic("refresh", 15)}</button>
          <button class="btn btn-ghost icon danger-hover" title="Delete video and its results" ${j && j.status === "running" ? "disabled" : ""} data-act="delvideo" data-id="${v.id}" data-name="${esc(v.name)}">${ic("trash", 15)}</button>
        </td></tr>`;
    }).join("");
    const srows = sessions.map((j) => `<tr class="hover">
        <td class="td"><div class="semibold row">${ic("camera", 16, "faint")}${esc(j.source_name)}</div><div class="xs faint">${esc(j.location || "")}</div></td>
        <td class="td xs nowrap">${esc(j.started_at || j.created_at)}</td>
        <td class="td xs nowrap">${esc(j.finished_at || "—")}</td>
        <td class="td">${badge(j.status)}</td>
        <td class="td xs"><span class="rose semibold">${j.event_count} snatch${j.event_count === 1 ? "" : "es"}</span></td>
        <td class="td right nowrap">
          <a class="btn btn-ghost icon" title="Monitor" href="#/monitor?job=${j.id}">${ic("monitorPlay", 15)}</a>
          ${isBusy(j) ? `<button class="btn btn-ghost icon" title="Stop" data-act="stop" data-id="${j.id}">${ic("stop", 15)}</button>` : ""}
          <button class="btn btn-ghost icon danger-hover" title="Delete session and its detections" ${j.status === "running" ? "disabled" : ""} data-act="deljob" data-id="${j.id}">${ic("trash", 15)}</button>
        </td></tr>`).join("");
    $("#vTables", this.el).innerHTML = cardBox("Videos", videos.length ? `<div class="table-wrap"><table>
        <thead><tr><th class="th">Video</th><th class="th">Length</th><th class="th">Resolution</th><th class="th">Uploaded</th><th class="th">Latest analysis</th><th class="th">Results</th><th class="th right">Actions</th></tr></thead>
        <tbody>${vrows}</tbody></table></div>` : emptyBox("video", "No videos uploaded yet"), { pad: false })
      + (sessions.length ? cardBox("CCTV sessions", `<div class="table-wrap"><table>
        <thead><tr><th class="th">Camera</th><th class="th">Started</th><th class="th">Ended</th><th class="th">Status</th><th class="th">Results</th><th class="th right">Actions</th></tr></thead>
        <tbody>${srows}</tbody></table></div>`, { pad: false, cls: "mt-6" }) : "");
  },
};

const Settings = {
  async mount(el) {
    this.el = el;
    el.innerHTML = pageHead("Settings", "Detection settings used for new analyses. Running analyses keep the settings they started with.",
      `<button class="btn btn-ghost" id="sReset">${ic("reset")} Reset defaults</button><button class="btn btn-primary" id="sSave">${ic("save")} Save</button>`)
      + `<div id="sBody">${emptyBox("settings", "Loading…")}</div>`;
    try { this.data = await api.get("/api/settings"); } catch (e) { $("#sBody", el).innerHTML = emptyBox("alert", "Could not load settings"); return; }
    this.values = { ...this.data.values };
    this.render();
    $("#sSave", el).onclick = async () => {
      try { this.data.values = (await api.post("/api/settings", this.values)).values; this.values = { ...this.data.values }; this.render(); flash("Settings saved - used by the next analysis"); }
      catch (e) { flash(e.message); }
    };
    $("#sReset", el).onclick = async () => {
      if (!confirm("Reset every setting to its default?")) return;
      try { this.data.values = (await api.post("/api/settings/reset")).values; this.values = { ...this.data.values }; this.render(); flash("Defaults restored"); }
      catch (e) { flash(e.message); }
    };
  },
  render() {
    const fmt = (v, spec) => (spec.options ? v : Number(v).toFixed(spec.step < 0.1 ? 2 : spec.step < 1 ? 1 : 0));
    $("#sBody", this.el).innerHTML = this.data.schema.map((sec) => cardBox(sec.title, `<div class="fields">${sec.fields.map(([key, label, help, spec]) => {
      const v = this.values[key], changed = String(v) !== String(this.data.defaults[key]);
      const control = spec.options
        ? `<select class="input" data-key="${key}">${spec.options.map((o) => `<option value="${esc(o)}" ${String(o) === String(v) ? "selected" : ""}>${esc(o)}</option>`).join("")}</select>`
        : `<input type="range" data-key="${key}" min="${spec.min}" max="${spec.max}" step="${spec.step}" value="${v}">`;
      return `<div class="field"><div class="field-top"><label class="semibold sm">${esc(label)}</label>
        <b class="${changed ? "changed" : ""}" id="v-${key}">${esc(fmt(v, spec))}</b></div>
        <div class="field-help">${esc(help)}${changed ? ` · default ${esc(this.data.defaults[key])}` : ""}</div>${control}</div>`;
    }).join("")}</div>`, { cls: "mb-6" })).join("");
    $$("[data-key]", this.el).forEach((inp) => {
      inp.oninput = () => {
        const key = inp.dataset.key, spec = this.data.schema.flatMap((s) => s.fields).find((f) => f[0] === key)[3];
        this.values[key] = spec.options ? spec.options.find((o) => String(o) === inp.value) : +inp.value;
        const lab = $(`#v-${key}`, this.el);
        lab.textContent = fmt(this.values[key], spec);
        lab.classList.toggle("changed", String(this.values[key]) !== String(this.data.defaults[key]));
      };
    });
  },
};

/* ================================================================ router */
const PAGES = { overview: Overview, watch: Watch, monitor: Monitor, events: Events, videos: Videos, settings: Settings };
function parseHash() {
  const h = location.hash.replace(/^#/, "") || "/";
  const [p, qs] = h.split("?");
  const name = p.replace(/^\//, "") || "overview";
  return { name: PAGES[name] ? name : "overview", params: Object.fromEntries(new URLSearchParams(qs || "")) };
}
function route() {
  const { name, params } = parseHash();
  closeModal();
  $$("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.route === name));
  setNav(false);
  S.page = PAGES[name];
  const el = $("#page");
  el.innerHTML = "";
  S.page.mount(el, params);
  paintIcons(el);
  window.scrollTo(0, 0);
  // deep link: any page + ?event=<job>/<folder> opens that detection (used by alerts and shared links)
  if (params.event) openEvent(params.event);
}
function setNav(open) { $("#sidebar").classList.toggle("open", open); $("#shade").hidden = !open; }

/* ================================================================ polling */
function setConn(ok) {
  if (ok === S.connected) return;
  S.connected = ok;
  $("#connDot").className = `dot ${ok ? "" : "off"}`;
  $("#connText").textContent = ok ? "Connected" : "Reconnecting…";
}
function updateBadge() {
  const n = S.events.filter((e) => e.status === "new").length;
  $("#newCount").textContent = n;
  $("#newCount").hidden = !n;
}
async function poll() {
  try {
    const [jobs, events] = await Promise.all([api.get("/api/jobs"), api.get("/api/events")]);
    setConn(true);
    S.jobs = jobs;
    if (S.seen) events.filter((e) => !S.seen.has(e.id)).forEach(toast);
    S.seen = new Set(events.map((e) => e.id));
    S.events = events;
    updateBadge();
    S.page?.update?.();
  } catch (e) { setConn(false); }
}

document.addEventListener("click", (ev) => {
  const open = ev.target.closest("[data-open]");
  if (open) { ev.preventDefault(); openEvent(open.dataset.open); }
});
$("#openNav").onclick = () => setNav(true);
$("#closeNav").onclick = () => setNav(false);
$("#shade").onclick = () => setNav(false);
window.addEventListener("hashchange", route);
paintIcons();
poll().then(route);
setInterval(poll, 2000);
