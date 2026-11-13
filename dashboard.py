"""Control room for the phone snatch detector.

  python dashboard.py            -> http://localhost:8000

From the page you can
  - upload a recorded video and have it analysed,
  - connect a live CCTV camera (RTSP url) or a USB camera (0, 1, ...),
  - watch the live annotated picture,
  - see every captured suspect: faces, capture time, evidence and a clip.

The dashboard starts detect.py as a separate process and talks to it through files in the
output folder (status.json, live.jpg, stop), so a crash in one does not take down the other.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent
VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}
MAX_UPLOAD = 4 * 1024 ** 3   # 4 GB

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Phone Snatch Detector</title>
<style>
  :root { --bg:#0f1318; --card:#191f27; --line:#2a323d; --text:#e8ecf1; --dim:#93a0b0;
          --red:#ff4d4f; --amber:#ffb020; --green:#3ddc84; --blue:#4c9aff; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font:15px/1.5 system-ui, Segoe UI, sans-serif; }
  header { display:flex; flex-wrap:wrap; gap:12px; align-items:center; justify-content:space-between;
           padding:16px 24px; border-bottom:1px solid var(--line); }
  h1 { margin:0; font-size:20px; } h2 { margin:0 0 10px; font-size:15px; }
  .stats { display:flex; flex-wrap:wrap; gap:20px; color:var(--dim); font-size:14px; }
  .stats b { color:var(--text); font-size:18px; margin-right:4px; }
  .wrap { padding:20px 24px; display:grid; gap:16px; }
  .control { display:grid; gap:16px; grid-template-columns:minmax(0, 3fr) minmax(280px, 2fr); }
  @media (max-width:860px) { .control { grid-template-columns:1fr; } }
  .panel { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px; min-width:0; }
  .screen { position:relative; background:#000; border-radius:8px; aspect-ratio:16/9; overflow:hidden;
            display:grid; place-items:center; color:var(--dim); text-align:center; }
  .screen img { width:100%; height:100%; object-fit:contain; display:block; }
  .state { display:flex; flex-wrap:wrap; align-items:center; gap:10px; margin-top:10px; font-size:14px; }
  .dot { width:10px; height:10px; border-radius:50%; background:var(--dim); flex:none; }
  .dot.on { background:var(--green); box-shadow:0 0 8px var(--green); }
  .dot.err { background:var(--red); }
  .grow { flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .bar { height:6px; background:var(--line); border-radius:3px; margin-top:8px; overflow:hidden; }
  .bar i { display:block; height:100%; background:var(--amber); border-radius:3px; }
  #prog i { background:var(--blue); transition:width .4s; }
  label { display:block; color:var(--dim); font-size:13px; margin:10px 0 4px; }
  input[type=text] { width:100%; background:var(--bg); color:var(--text); border:1px solid var(--line);
                     border-radius:6px; padding:8px 10px; font:inherit; }
  input[type=text]:focus { outline:2px solid var(--blue); outline-offset:-1px; }
  button { background:var(--blue); color:#fff; border:0; border-radius:6px; padding:8px 16px;
           font:inherit; font-weight:600; cursor:pointer; }
  button:disabled { opacity:.45; cursor:not-allowed; }
  button.stop { background:var(--red); }
  .drop { border:2px dashed var(--line); border-radius:8px; padding:22px 12px; text-align:center;
          color:var(--dim); cursor:pointer; }
  .drop.over, .drop:hover { border-color:var(--blue); color:var(--text); }
  .sep { border:0; border-top:1px solid var(--line); margin:16px 0; }
  .msg { min-height:20px; margin-top:8px; font-size:13px; color:var(--amber); }
  .dim { color:var(--dim); font-size:13px; }
  main { display:grid; gap:16px; grid-template-columns:repeat(auto-fill, minmax(340px, 1fr)); }
  .card { background:var(--card); border:1px solid var(--line); border-radius:10px; overflow:hidden; }
  .top { display:flex; gap:14px; padding:14px; }
  .face { width:120px; height:120px; object-fit:cover; border-radius:8px; border:2px solid var(--red);
          background:#000; flex:none; cursor:zoom-in; }
  .noface { display:grid; place-items:center; color:var(--dim); font-size:12px; text-align:center; cursor:default; }
  .meta { min-width:0; }
  .tag { display:inline-block; background:var(--red); color:#fff; font-size:11px; font-weight:700;
         letter-spacing:.05em; padding:2px 8px; border-radius:4px; }
  .time { font-size:18px; font-weight:600; margin:6px 0 2px; font-variant-numeric:tabular-nums; }
  .more { display:flex; align-items:center; gap:8px; padding:0 14px 12px; }
  .more img { width:56px; height:56px; object-fit:cover; border-radius:6px; border:1px solid var(--line); cursor:zoom-in; }
  .thumbs { display:flex; gap:8px; padding:0 14px 12px; }
  .thumbs figure { margin:0; flex:1; min-width:0; }
  .thumbs img { width:100%; height:130px; object-fit:contain; background:#000; border-radius:6px; cursor:zoom-in; }
  figcaption { color:var(--dim); font-size:12px; text-align:center; }
  .ev { padding:0 14px 12px; display:flex; flex-wrap:wrap; gap:6px; }
  .chip { border:1px solid var(--line); border-radius:999px; padding:1px 9px; font-size:12px; color:var(--dim); }
  .chip.on { color:var(--text); border-color:var(--amber); }
  video { width:100%; display:block; background:#000; }
  .empty { grid-column:1/-1; text-align:center; color:var(--dim); padding:60px 0; }
  dialog { border:0; padding:0; background:transparent; max-width:95vw; }
  dialog img { max-width:95vw; max-height:90vh; }
  dialog::backdrop { background:rgba(0,0,0,.85); }
</style></head><body>
<header>
  <h1>Phone Snatch Detector</h1>
  <div class="stats"><span><b id="n">0</b>thefts captured</span><span><b id="f">0</b>faces</span>
  <span>last: <b id="last" style="font-size:14px">-</b></span></div>
</header>
<div class="wrap">
  <section class="control">
    <div class="panel">
      <h2>Live view</h2>
      <div class="screen"><img id="live" alt="live annotated picture" hidden>
        <span id="idle">Nothing is running.<br>Upload a video or connect a camera.</span></div>
      <div class="state"><span class="dot" id="dot"></span><span class="grow" id="stateText">idle</span>
        <button class="stop" id="stopBtn" hidden>Stop</button></div>
      <div class="bar" id="prog" hidden><i style="width:0"></i></div>
    </div>
    <div class="panel">
      <h2>Analyse a recorded video</h2>
      <div class="drop" id="drop">Drop a video here or click to choose<br>
        <span class="dim">mp4, avi, mov, mkv, webm</span></div>
      <input type="file" id="file" accept="video/*" hidden>
      <hr class="sep">
      <h2>Connect a CCTV camera</h2>
      <label for="src">RTSP address, or 0 for this PC's camera</label>
      <input type="text" id="src" placeholder="rtsp://user:password@192.168.1.10:554/stream1" autocomplete="off">
      <label for="cam">Camera name (optional)</label>
      <input type="text" id="cam" placeholder="Platform 2 - CAM 03" maxlength="60">
      <div style="margin-top:12px"><button id="startBtn">Start camera</button></div>
      <div class="msg" id="msg"></div>
    </div>
  </section>
  <main id="grid"></main>
</div>
<dialog id="zoom" onclick="this.close()"><img id="zoomimg" alt=""></dialog>
<script>
const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const post = (url, body, headers = {}) =>
  fetch(url, {method:"POST", body, headers:{"X-Requested-With":"dashboard", ...headers}}).then(r => r.json());
let sig = "", busy = false;
function show(src) { $("zoomimg").src = src; $("zoom").showModal(); }
function say(text) { $("msg").textContent = text || ""; }

function card(e) {
  const p = "/files/" + e.id + "/", v = "?v=" + e.mtime, ev = e.evidence || {};
  const chip = (label, on) => `<span class="chip ${on ? "on" : ""}">${label}</span>`;
  const face = e.files.includes("suspect_face.jpg")
    ? `<img class="face" src="${p}suspect_face.jpg${v}" alt="suspect face" onclick="show(this.src)">`
    : `<div class="face noface">face not visible</div>`;
  const more = e.files.filter(f => /^suspect_face_\d+\.jpg$/.test(f));
  const thumb = (f, cap) => e.files.includes(f)
    ? `<figure><img src="${p}${f}${v}" alt="${cap}" onclick="show(this.src)"><figcaption>${cap}</figcaption></figure>` : "";
  return `<article class="card">
    <div class="top">${face}<div class="meta">
      <span class="tag">PHONE SNATCHING</span>
      <div class="time">${esc(e.captured_at || "-")}</div>
      <div class="dim">${esc(e.source || "")}</div>
      <div class="dim">at ${esc(e.video_time)}s · suspect #${esc(e.suspect_id)} · victim #${esc(e.victim_id)}</div>
      <div class="dim">confidence ${Math.round(e.score * 100)}%</div>
      <div class="bar"><i style="width:${Math.round(e.score * 100)}%"></i></div>
    </div></div>
    <div class="ev">${chip("ran away", ev.flee >= 0.3)}${chip("victim reacted", ev.reaction >= 0.3)}
      ${chip("victim had phone", ev.had_phone > 0)}${chip("phone changed hands", ev.transfer > 0)}</div>
    ${more.length ? `<div class="more">${more.map(f => `<img src="${p}${f}${v}" alt="other face" onclick="show(this.src)">`).join("")}<span class="dim">other faces of the suspect</span></div>` : ""}
    <div class="thumbs">${thumb("suspect_body.jpg", "suspect")}${thumb("victim.jpg", "victim")}${thumb("alert_frame.jpg", "alert frame")}</div>
    ${e.files.includes("clip.mp4") ? `<video src="${p}clip.mp4${v}" controls muted preload="metadata"></video>` : ""}
  </article>`;
}

async function loadEvents() {
  try {
    const events = await (await fetch("/api/events")).json();
    const s = JSON.stringify(events);
    if (s === sig) return;            // nothing new: do not interrupt a playing clip
    sig = s;
    $("n").textContent = events.length;
    $("f").textContent = events.filter(e => e.files.includes("suspect_face.jpg")).length;
    $("last").textContent = events.length ? events[0].captured_at || "-" : "-";
    $("grid").innerHTML = events.length ? events.map(card).join("")
      : '<div class="empty">No theft captured yet.</div>';
  } catch (err) { /* server restarting: try again on the next tick */ }
}

async function loadStatus() {
  let st;
  try { st = await (await fetch("/api/status")).json(); } catch (err) { return; }
  busy = st.busy;
  const running = st.busy && st.state !== "error";
  $("dot").className = "dot" + (running ? " on" : st.state === "error" ? " err" : "");
  let text = st.state || "idle";
  if (st.state === "starting") text = `starting ${st.source || ""} (loading models)`;
  if (st.state === "running") text = `${st.live ? "LIVE" : "analysing"} · ${st.source} · ${st.speed} frames/s · ${st.alerts} alert(s)`;
  if (st.state === "finished") text = `finished · ${st.source} · ${st.alerts} alert(s)`;
  if (st.state === "stopped") text = `stopped · ${st.source} · ${st.alerts} alert(s)`;
  if (st.state === "error") text = st.message || "error";
  $("stateText").textContent = text;
  $("stopBtn").hidden = !st.busy;
  $("startBtn").disabled = st.busy;
  $("drop").style.opacity = st.busy ? .45 : 1;
  const showProg = st.state === "running" && !st.live && st.total > 0;
  $("prog").hidden = !showProg;
  if (showProg) $("prog").firstElementChild.style.width = Math.min(100, 100 * st.frame / st.total) + "%";
  if (st.has_live) {
    $("live").hidden = false; $("idle").hidden = true;
    if (running || !$("live").src) $("live").src = "/live.jpg?t=" + Date.now();
  }
}

async function upload(file) {
  if (!file) return;
  if (busy) return say("Something is already running. Stop it first.");
  say(`Uploading ${file.name} ...`);
  try {
    const r = await post("/api/upload", file, {"X-Filename": encodeURIComponent(file.name)});
    say(r.error || "Uploaded. Analysis started.");
  } catch (err) { say("Upload failed."); }
  loadStatus();
}
$("drop").onclick = () => $("file").click();
$("file").onchange = e => { upload(e.target.files[0]); e.target.value = ""; };
$("drop").ondragover = e => { e.preventDefault(); $("drop").classList.add("over"); };
$("drop").ondragleave = () => $("drop").classList.remove("over");
$("drop").ondrop = e => { e.preventDefault(); $("drop").classList.remove("over"); upload(e.dataTransfer.files[0]); };
$("startBtn").onclick = async () => {
  const source = $("src").value.trim();
  if (!source) return say("Enter an RTSP address or a camera number.");
  say("Connecting ...");
  const r = await post("/api/start", JSON.stringify({source, name: $("cam").value.trim()}));
  say(r.error || "Camera started.");
  loadStatus();
};
$("stopBtn").onclick = async () => { say("Stopping ..."); await post("/api/stop", ""); say(""); loadStatus(); };

loadEvents(); loadStatus();
setInterval(loadEvents, 3000); setInterval(loadStatus, 1000);
</script></body></html>
"""


class Jobs:
    """Runs at most one detect.py process at a time."""

    def __init__(self, out: Path):
        self.out = out
        self.proc: subprocess.Popen | None = None
        self.lock = threading.Lock()
        out.mkdir(parents=True, exist_ok=True)

    def busy(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, source: str, name: str) -> str | None:
        """Returns an error message, or None when the job started."""
        with self.lock:
            if self.busy():
                return "Something is already running. Stop it first."
            for f in ("live.jpg", "status.json", "stop"):
                (self.out / f).unlink(missing_ok=True)
            cmd = [sys.executable, str(ROOT / "detect.py"), "--source", source, "--out", str(self.out)]
            if name:
                cmd += ["--name", name]
            log = open(self.out / "detector.log", "w", encoding="utf-8", errors="replace")
            self.proc = subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
            return None

    def stop(self):
        with self.lock:
            proc = self.proc
            if proc is None or proc.poll() is not None:
                return
            (self.out / "stop").write_text("stop")   # detect.py sees this and finishes cleanly

        def kill_later():
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.terminate()
        threading.Thread(target=kill_later, daemon=True).start()

    def status(self) -> dict:
        st: dict = {"state": "idle"}
        try:
            st = json.loads((self.out / "status.json").read_text())
        except (OSError, ValueError):
            pass
        busy = self.busy()
        # the process died without saying goodbye (bad RTSP address, missing package ...)
        if not busy and self.proc is not None and st.get("state") in ("starting", "running"):
            st = {"state": "error", "source": st.get("source", ""),
                  "message": "Detector stopped unexpectedly. See output/detector.log"}
        st["busy"] = busy
        st["has_live"] = (self.out / "live.jpg").is_file()
        return st


def make_handler(out: Path, jobs: Jobs):
    events_dir = out / "events"
    uploads = out / "uploads"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # keep the console quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200):
            self._send(code, json.dumps(obj).encode(), "application/json")

        def _local(self) -> bool:
            # only this PC's browser may talk to the dashboard (blocks DNS-rebinding tricks)
            host = (self.headers.get("Host") or "").split(":")[0]
            return host in ("localhost", "127.0.0.1")

        def do_GET(self):
            if not self._local():
                return self._send(403, b"forbidden", "text/plain")
            path = self.path.split("?")[0]
            if path == "/":
                return self._send(200, PAGE.encode(), "text/html; charset=utf-8")
            if path == "/api/status":
                return self._json(jobs.status())
            if path == "/live.jpg":
                try:
                    return self._send(200, (out / "live.jpg").read_bytes(), "image/jpeg")
                except OSError:
                    return self._send(404, b"not found", "text/plain")
            if path == "/api/events":
                events = []
                if events_dir.is_dir():
                    for d in events_dir.iterdir():
                        j = d / "event.json"
                        if not j.is_file():
                            continue
                        try:
                            e = json.loads(j.read_text())
                            files = sorted(f.name for f in d.iterdir() if f.is_file())
                            mtime = int(max(f.stat().st_mtime for f in d.iterdir()))
                        except (OSError, ValueError):
                            continue  # the folder is being written right now
                        e.update(id=d.name, files=files, mtime=mtime)
                        events.append(e)
                events.sort(key=lambda e: e.get("captured_at", ""), reverse=True)
                return self._json(events)
            if path.startswith("/files/"):
                parts = path.split("/")[2:]
                # exactly <event folder>/<file>, nothing that could escape the events folder
                if len(parts) == 2 and all(p and p not in (".", "..") and "\\" not in p for p in parts):
                    f = events_dir / parts[0] / parts[1]
                    if f.is_file():
                        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
                        return self._send(200, f.read_bytes(), ctype)
            self._send(404, b"not found", "text/plain")

        def do_POST(self):
            # The custom header cannot be sent by a form or a cross-site script without a CORS
            # preflight, which this server never approves: other web pages cannot press our buttons.
            if not self._local() or self.headers.get("X-Requested-With") != "dashboard":
                return self._send(403, b"forbidden", "text/plain")
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            path = self.path.split("?")[0]

            if path == "/api/stop":
                jobs.stop()
                return self._json({"ok": True})

            if path == "/api/start":
                try:
                    data = json.loads(self.rfile.read(min(length, 4096)) or b"{}")
                except ValueError:
                    data = {}
                source = str(data.get("source", "")).strip()
                name = str(data.get("name", "")).strip()[:60]
                # only a camera number or a stream address: never a local file path or an option
                if not (re.fullmatch(r"\d{1,2}", source)
                        or re.fullmatch(r"(rtsp|rtsps|rtmp|http|https)://\S{3,400}", source)):
                    return self._json({"error": "Enter an RTSP address (rtsp://...) or a camera number like 0."})
                return self._json({"error": jobs.start(source, name)})

            if path == "/api/upload":
                name = Path(unquote(self.headers.get("X-Filename") or "")).name
                name = re.sub(r"[^\w.\- ]", "_", name).strip()
                if Path(name).suffix.lower() not in VIDEO_EXT:
                    return self._json({"error": "Please upload a video file (mp4, avi, mov, mkv, webm)."})
                if not 0 < length <= MAX_UPLOAD:
                    return self._json({"error": "File is empty or larger than 4 GB."})
                if jobs.busy():
                    return self._json({"error": "Something is already running. Stop it first."})
                uploads.mkdir(parents=True, exist_ok=True)
                dest = uploads / f"{time.strftime('%Y%m%d_%H%M%S')}_{name}"
                left = length
                with open(dest, "wb") as f:
                    while left > 0:
                        chunk = self.rfile.read(min(left, 1 << 20))
                        if not chunk:
                            break
                        f.write(chunk)
                        left -= len(chunk)
                if left:
                    dest.unlink(missing_ok=True)
                    return self._json({"error": "Upload was interrupted."})
                return self._json({"error": jobs.start(str(dest), name)})

            self._send(404, b"not found", "text/plain")

    return Handler


def main():
    ap = argparse.ArgumentParser(description="Phone snatch detector dashboard")
    ap.add_argument("--out", default="output", help="folder for events, uploads and status")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    out = Path(args.out).resolve()
    jobs = Jobs(out)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(out, jobs))
    print(f"Dashboard: http://localhost:{args.port}   (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        jobs.stop()


if __name__ == "__main__":
    main()
