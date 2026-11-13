"""Dashboard for the theft detector: shows every captured suspect with face and time.

  python dashboard.py            -> http://localhost:8000
  python dashboard.py --port 9000 --out output

It only reads the output folder, so it can run while detect.py is working;
the page refreshes itself every 3 seconds.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Station Theft Detector</title>
<style>
  :root { --bg:#0f1318; --card:#191f27; --line:#2a323d; --text:#e8ecf1; --dim:#93a0b0; --red:#ff4d4f; --amber:#ffb020; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font:15px/1.5 system-ui, Segoe UI, sans-serif; }
  header { display:flex; flex-wrap:wrap; gap:12px; align-items:center; justify-content:space-between;
           padding:16px 24px; border-bottom:1px solid var(--line); }
  h1 { margin:0; font-size:20px; }
  .stats { display:flex; gap:20px; color:var(--dim); font-size:14px; }
  .stats b { color:var(--text); font-size:18px; margin-right:4px; }
  .live { color:#3ddc84; } .live::before { content:"● "; }
  main { padding:20px 24px; display:grid; gap:16px; grid-template-columns:repeat(auto-fill, minmax(340px, 1fr)); }
  .card { background:var(--card); border:1px solid var(--line); border-radius:10px; overflow:hidden; }
  .top { display:flex; gap:14px; padding:14px; }
  .face { width:120px; height:120px; object-fit:cover; border-radius:8px; border:2px solid var(--red); background:#000; flex:none; }
  .noface { display:grid; place-items:center; color:var(--dim); font-size:12px; text-align:center; }
  .meta { min-width:0; }
  .tag { display:inline-block; background:var(--red); color:#fff; font-size:11px; font-weight:700;
         letter-spacing:.05em; padding:2px 8px; border-radius:4px; }
  .time { font-size:18px; font-weight:600; margin:6px 0 2px; font-variant-numeric:tabular-nums; }
  .dim { color:var(--dim); font-size:13px; }
  .bar { height:6px; background:var(--line); border-radius:3px; margin-top:8px; }
  .bar i { display:block; height:100%; background:var(--amber); border-radius:3px; }
  .thumbs { display:flex; gap:8px; padding:0 14px 12px; }
  .thumbs figure { margin:0; flex:1; min-width:0; }
  .thumbs img { width:100%; height:130px; object-fit:contain; background:#000; border-radius:6px; cursor:zoom-in; }
  figcaption { color:var(--dim); font-size:12px; text-align:center; }
  .ev { padding:0 14px 12px; display:flex; flex-wrap:wrap; gap:6px; }
  .chip { border:1px solid var(--line); border-radius:999px; padding:1px 9px; font-size:12px; color:var(--dim); }
  .chip.on { color:var(--text); border-color:var(--amber); }
  video { width:100%; display:block; background:#000; }
  .empty { grid-column:1/-1; text-align:center; color:var(--dim); padding:80px 0; }
  dialog { border:0; padding:0; background:transparent; max-width:95vw; } dialog img { max-width:95vw; max-height:90vh; }
  dialog::backdrop { background:rgba(0,0,0,.85); }
</style></head><body>
<header>
  <h1>Station Theft Detector</h1>
  <div class="stats"><span><b id="n">0</b>thefts captured</span><span><b id="f">0</b>faces</span>
  <span>last: <b id="last" style="font-size:14px">-</b></span><span class="live">auto refresh</span></div>
</header>
<main id="grid"></main>
<dialog id="zoom" onclick="this.close()"><img id="zoomimg" alt=""></dialog>
<script>
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
let sig = "";
function show(src) { zoomimg.src = src; zoom.showModal(); }
function card(e) {
  const p = "/files/" + e.id + "/", v = "?v=" + e.mtime, ev = e.evidence || {};
  const chip = (label, on) => `<span class="chip ${on ? "on" : ""}">${label}</span>`;
  const face = e.files.includes("suspect_face.jpg")
    ? `<img class="face" src="${p}suspect_face.jpg${v}" alt="suspect face" onclick="show(this.src)">`
    : `<div class="face noface">face not visible</div>`;
  const thumb = (f, cap) => e.files.includes(f)
    ? `<figure><img src="${p}${f}${v}" alt="${cap}" onclick="show(this.src)"><figcaption>${cap}</figcaption></figure>` : "";
  return `<article class="card">
    <div class="top">${face}<div class="meta">
      <span class="tag">PHONE SNATCHING</span>
      <div class="time">${esc(e.captured_at || "-")}</div>
      <div class="dim">video time ${esc(e.video_time ?? e.alert_time)}s · suspect #${esc(e.suspect_id)} · victim #${esc(e.victim_id)}</div>
      <div class="dim">confidence ${Math.round(e.score * 100)}%</div>
      <div class="bar"><i style="width:${Math.round(e.score * 100)}%"></i></div>
    </div></div>
    <div class="ev">${chip("ran away", ev.flee >= 0.3)}${chip("victim reacted", ev.reaction >= 0.3)}
      ${chip("victim had phone", ev.had_phone > 0)}${chip("phone changed hands", ev.transfer > 0)}</div>
    <div class="thumbs">${thumb("suspect_body.jpg", "suspect")}${thumb("victim.jpg", "victim")}${thumb("alert_frame.jpg", "alert frame")}</div>
    ${e.files.includes("clip.mp4") ? `<video src="${p}clip.mp4${v}" controls muted preload="metadata"></video>` : ""}
  </article>`;
}
async function load() {
  try {
    const events = await (await fetch("/api/events")).json();
    const s = JSON.stringify(events);
    if (s === sig) return;            // nothing new: do not interrupt a playing clip
    sig = s;
    n.textContent = events.length;
    f.textContent = events.filter(e => e.files.includes("suspect_face.jpg")).length;
    last.textContent = events.length ? events[0].captured_at || "-" : "-";
    grid.innerHTML = events.length ? events.map(card).join("")
      : '<div class="empty">No theft detected yet. Run detect.py and events will appear here.</div>';
  } catch (err) { /* server restarting: try again on the next tick */ }
}
load(); setInterval(load, 3000);
</script></body></html>
"""


def make_handler(events_dir: Path):
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

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/":
                return self._send(200, PAGE.encode(), "text/html; charset=utf-8")
            if path == "/api/events":
                events = []
                if events_dir.is_dir():
                    for d in sorted(events_dir.iterdir(), reverse=True):
                        j = d / "event.json"
                        if not j.is_file():
                            continue
                        try:
                            e = json.loads(j.read_text())
                        except ValueError:
                            continue  # file is being written right now
                        files = sorted(f.name for f in d.iterdir() if f.is_file())
                        e.update(id=d.name, files=files,
                                 mtime=int(max(f.stat().st_mtime for f in d.iterdir())))
                        events.append(e)
                events.sort(key=lambda e: e.get("captured_at", ""), reverse=True)
                return self._send(200, json.dumps(events).encode(), "application/json")
            if path.startswith("/files/"):
                parts = path.split("/")[2:]
                # exactly <event folder>/<file>, nothing that could escape the events folder
                if len(parts) == 2 and all(p and p not in (".", "..") and "\\" not in p for p in parts):
                    f = events_dir / parts[0] / parts[1]
                    if f.is_file():
                        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
                        return self._send(200, f.read_bytes(), ctype)
            self._send(404, b"not found", "text/plain")

    return Handler


def main():
    ap = argparse.ArgumentParser(description="Theft detector dashboard")
    ap.add_argument("--out", default="output", help="same folder as detect.py --out")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    events_dir = Path(args.out) / "events"
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(events_dir))
    print(f"Dashboard: http://localhost:{args.port}   (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
